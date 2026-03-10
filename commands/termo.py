import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import (
    add_progress_xp,
    add_user_coins,
    create_or_get_user,
    create_termo_game,
    ensure_termo_stats_row,
    finish_termo_game,
    get_termo_active_game,
    get_termo_daily_game,
    get_termo_global_ranking,
    get_termo_period_ranking,
    get_termo_stats,
    get_termo_user_rank,
    has_accepted_terms,
    has_user_used_termo_word,
    mark_termo_word_used,
    record_termo_result,
    touch_user_identity,
    update_termo_game_progress,
)

from utils.gatekeeper import TERMS_VERSION


WORDS_FILE = os.getenv("TERMO_WORDS_FILE", "data/anime_words_365.json")

SP_TZ = ZoneInfo("America/Sao_Paulo")

TIME_LIMIT_SECONDS = 300
MAX_ATTEMPTS = 6
WORD_LENGTH = 6
ANTI_FLOOD_SECONDS = 1.5
XP_REWARD = 10

ACTIVE_GAMES: Dict[int, Dict[str, Any]] = {}
LAST_GUESS_AT: Dict[int, float] = {}

WORDS_CACHE: List[Dict[str, str]] = []
VALID_WORDS: Set[str] = set()


# =========================================================
# TIME
# =========================================================

def _sp_now():
    return datetime.now(SP_TZ)


def _sp_today():
    return _sp_now().date()


def _next_reset_text():
    now = _sp_now()
    tomorrow = datetime.combine(
        (now + timedelta(days=1)).date(),
        datetime.min.time(),
        tzinfo=SP_TZ,
    )
    delta = tomorrow - now

    hours = int(delta.total_seconds()) // 3600
    minutes = (int(delta.total_seconds()) % 3600) // 60

    return f"{hours}h {minutes}m"


# =========================================================
# WORDS
# =========================================================

def _load_words():

    global WORDS_CACHE, VALID_WORDS

    if WORDS_CACHE:
        return WORDS_CACHE

    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    seen = set()

    for item in raw:

        word = str(item.get("word","")).strip().lower()

        if not re.fullmatch(r"[a-záàâãéèêíìîóòôõúùûç]{6}", word):
            continue

        if word in seen:
            continue

        seen.add(word)

        WORDS_CACHE.append({
            "word": word,
            "category": item.get("category","Anime"),
            "source": item.get("source","Anime")
        })

    VALID_WORDS = {x["word"] for x in WORDS_CACHE}

    return WORDS_CACHE


# =========================================================
# WORD PICK
# =========================================================

def _pick_daily_word():

    words = _load_words()

    seed = _sp_today().isoformat()

    rng = random.Random(seed)

    return rng.choice(words)


def _pick_train_word():
    return random.choice(_load_words())


# =========================================================
# WORDLE ENGINE
# =========================================================

def _evaluate(secret, guess):

    result = ["⬛"] * WORD_LENGTH
    remaining = {}

    for i in range(WORD_LENGTH):

        if guess[i] == secret[i]:
            result[i] = "🟩"
        else:
            remaining[secret[i]] = remaining.get(secret[i],0)+1

    for i in range(WORD_LENGTH):

        if result[i] == "🟩":
            continue

        letter = guess[i]

        if remaining.get(letter,0) > 0:
            result[i] = "🟨"
            remaining[letter] -= 1

    return "".join(result)


# =========================================================
# LETTER TRACKER
# =========================================================

def _used_letters(guesses):

    correct = set()
    present = set()
    absent = set()

    for g in guesses:

        word = g["guess"]
        result = g["result"]

        for i,c in enumerate(word):

            if result[i] == "🟩":
                correct.add(c)

            elif result[i] == "🟨":
                if c not in correct:
                    present.add(c)

            else:
                if c not in correct and c not in present:
                    absent.add(c)

    return (
        f"🟩 {' '.join(sorted(correct)) or '-'}\n"
        f"🟨 {' '.join(sorted(present)) or '-'}\n"
        f"⬛ {' '.join(sorted(absent)) or '-'}"
    )


# =========================================================
# HISTORY
# =========================================================

def _history_text(guesses):

    if not guesses:
        return "⬛⬛⬛⬛⬛⬛"

    lines = []

    for g in guesses:

        lines.append(g["guess"].upper())
        lines.append(g["result"])
        lines.append("")

    return "\n".join(lines).rstrip()


# =========================================================
# BOARD
# =========================================================

def _board_text(game):

    return (
        "🎌 <b>TERMO ANIME</b>\n\n"
        f"{_history_text(game['guesses'])}\n\n"
        f"🎯 Tentativas: <b>{len(game['guesses'])}/6</b>\n"
        f"⏱ Tempo restante: <b>{_fmt_time(_seconds_left(game['start_time']))}</b>\n\n"
        f"🔤 <b>Letras usadas</b>\n{_used_letters(game['guesses'])}"
    )


def _seconds_left(start):

    return max(TIME_LIMIT_SECONDS - (int(time.time()) - int(start)),0)


def _fmt_time(sec):

    m = sec//60
    s = sec%60

    return f"{m}:{s:02d}"


# =========================================================
# SHARE
# =========================================================

def _share_text(guesses, attempts, win, streak):

    grid = "\n".join([x["result"] for x in guesses])

    score = f"{attempts}/6" if win else "X/6"

    return (
        "🎌 TERMO ANIME — SourceBaltigo\n\n"
        f"{grid}\n\n"
        f"{score}\n"
        f"🔥 Streak: {streak}"
    )


def _share_button(text):

    url = f"https://t.me/share/url?text={quote_plus(text)}"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Compartilhar no Telegram", url=url)]
    ])


# =========================================================
# GAME
# =========================================================

def _start_game(user_id, mode):

    if mode == "daily":
        word = _pick_daily_word()
    else:
        word = _pick_train_word()

    game = {
        "user_id": user_id,
        "word": word["word"],
        "category": word["category"],
        "source": word["source"],
        "guesses": [],
        "mode": mode,
        "start_time": int(time.time())
    }

    ACTIVE_GAMES[user_id] = game

    return game


# =========================================================
# COMMAND
# =========================================================

async def termo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id in ACTIVE_GAMES:

        await update.message.reply_text(
            _board_text(ACTIVE_GAMES[user_id]),
            parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        "🎌 <b>TERMO ANIME — SourceBaltigo</b>\n\n"
        "Descubra a palavra secreta de <b>6 letras</b> relacionada ao mundo dos animes.\n\n"
        "🎯 6 tentativas\n"
        "⏱ 5 minutos para resolver\n\n"
        "🟩 posição correta\n"
        "🟨 existe na palavra\n"
        "⬛ não existe\n\n"
        "Use /termotreino para modo treino.",
        parse_mode="HTML"
    )

    _start_game(user_id,"daily")


# =========================================================
# GUESS
# =========================================================

async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    guess = update.message.text.lower().strip()

    if len(guess) != WORD_LENGTH:
        return

    user_id = update.effective_user.id

    if user_id not in ACTIVE_GAMES:
        return

    if guess not in VALID_WORDS:
        return

    game = ACTIVE_GAMES[user_id]

    game["guesses"].append({
        "guess": guess,
        "result": _evaluate(game["word"],guess)
    })

    if guess == game["word"]:

        share = _share_text(game["guesses"],len(game["guesses"]),True,0)

        ACTIVE_GAMES.pop(user_id)

        await update.message.reply_text(
            "🎉 <b>Você acertou!</b>\n\n"
            f"{_history_text(game['guesses'])}\n\n"
            f"Palavra: <b>{game['word'].upper()}</b>",
            parse_mode="HTML",
            reply_markup=_share_button(share)
        )

        return

    if len(game["guesses"]) >= MAX_ATTEMPTS:

        share = _share_text(game["guesses"],MAX_ATTEMPTS,False,0)

        ACTIVE_GAMES.pop(user_id)

        await update.message.reply_text(
            "❌ <b>Fim de jogo</b>\n\n"
            f"{_history_text(game['guesses'])}\n\n"
            f"Palavra: <b>{game['word'].upper()}</b>",
            parse_mode="HTML",
            reply_markup=_share_button(share)
        )

        return

    await update.message.reply_text(
        _board_text(game),
        parse_mode="HTML"
    )
