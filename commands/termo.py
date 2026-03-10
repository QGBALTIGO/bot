import json
import os
import random
import re
import time
from datetime import datetime
from typing import Dict, List, Any
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import (
    get_termo_stats,
    get_termo_global_ranking,
)

SP_TZ = ZoneInfo("America/Sao_Paulo")

WORD_LENGTH = 6
MAX_ATTEMPTS = 6

WORDS_FILE = os.getenv("TERMO_WORDS_FILE", "data/anime_words_365.json")

ACTIVE_GAMES: Dict[int, Dict[str, Any]] = {}
WORDS: List[Dict[str, str]] = []
VALID_WORDS = set()


# =========================================================
# WORDS
# =========================================================

def load_words():

    global WORDS, VALID_WORDS

    if WORDS:
        return WORDS

    with open(WORDS_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    seen = set()

    for w in raw:

        word = str(w.get("word","")).lower().strip()

        if not re.fullmatch(r"[a-z]{6}", word):
            continue

        if word in seen:
            continue

        seen.add(word)

        WORDS.append({
            "word": word,
            "category": w.get("category","Anime"),
            "source": w.get("source","Anime")
        })

    VALID_WORDS = {x["word"] for x in WORDS}

    return WORDS


# =========================================================
# WORD PICK
# =========================================================

def pick_daily():

    words = load_words()

    seed = datetime.now(SP_TZ).date().isoformat()

    rng = random.Random(seed)

    return rng.choice(words)


def pick_random():
    return random.choice(load_words())


# =========================================================
# WORDLE ENGINE
# =========================================================

def evaluate(secret, guess):

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
# UI
# =========================================================

def history(guesses):

    if not guesses:
        return "⬛⬛⬛⬛⬛⬛"

    out = []

    for g in guesses:
        out.append(g["guess"].upper())
        out.append(g["result"])
        out.append("")

    return "\n".join(out).rstrip()


def used_letters(guesses):

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
                present.add(c)

            else:
                absent.add(c)

    return (
        f"🟩 {' '.join(sorted(correct)) or '-'}\n"
        f"🟨 {' '.join(sorted(present)) or '-'}\n"
        f"⬛ {' '.join(sorted(absent)) or '-'}"
    )


def board(game):

    return (
        "🎌 <b>TERMO ANIME</b>\n\n"
        f"{history(game['guesses'])}\n\n"
        f"Tentativas: <b>{len(game['guesses'])}/6</b>\n\n"
        f"🔤 Letras usadas\n{used_letters(game['guesses'])}"
    )


def share_text(guesses, attempts, win):

    grid = "\n".join([x["result"] for x in guesses])

    score = f"{attempts}/6" if win else "X/6"

    return (
        "🎌 TERMO ANIME — SourceBaltigo\n\n"
        f"{grid}\n\n{score}"
    )


def share_button(text):

    url = f"https://t.me/share/url?text={quote_plus(text)}"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Compartilhar no Telegram", url=url)]
    ])


# =========================================================
# GAME
# =========================================================

def start_game(user, mode):

    if mode == "daily":
        word = pick_daily()
    else:
        word = pick_random()

    ACTIVE_GAMES[user] = {
        "word": word["word"],
        "guesses": [],
        "mode": mode,
    }

    return ACTIVE_GAMES[user]


# =========================================================
# COMMANDS
# =========================================================

async def termo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user.id

    if user in ACTIVE_GAMES:

        await update.message.reply_text(
            board(ACTIVE_GAMES[user]),
            parse_mode="HTML"
        )
        return

    start_game(user,"daily")

    await update.message.reply_text(
        "🎌 <b>TERMO ANIME — SourceBaltigo</b>\n\n"
        "Descubra a palavra secreta de <b>6 letras</b> relacionada a anime.\n\n"
        "🟩 posição correta\n"
        "🟨 existe na palavra\n"
        "⬛ não existe\n\n"
        "Envie sua tentativa.",
        parse_mode="HTML"
    )


async def termo_treino_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user.id

    start_game(user,"train")

    await update.message.reply_text(
        "🧪 <b>Modo treino iniciado</b>\n\n"
        "Envie palavras de 6 letras.",
        parse_mode="HTML"
    )


async def termo_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user.id

    stats = get_termo_stats(user)

    if not stats:
        await update.message.reply_text("Sem estatísticas.")
        return

    await update.message.reply_text(
        f"📊 <b>Estatísticas</b>\n\n"
        f"Jogos: {stats['games_played']}\n"
        f"Vitórias: {stats['wins']}\n"
        f"Derrotas: {stats['losses']}",
        parse_mode="HTML"
    )


async def termo_ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    rows = get_termo_global_ranking(10)

    lines = ["🏆 <b>Ranking Termo</b>\n"]

    medals = ["🥇","🥈","🥉"]

    for i,row in enumerate(rows):

        medal = medals[i] if i < 3 else f"{i+1}."

        lines.append(
            f"{medal} {row['username']} — {row['wins']} vitórias"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML"
    )


# =========================================================
# GUESS
# =========================================================

async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    guess = update.message.text.lower().strip()

    if len(guess) != WORD_LENGTH:
        return

    user = update.effective_user.id

    if user not in ACTIVE_GAMES:
        return

    load_words()

    if guess not in VALID_WORDS:
        return

    game = ACTIVE_GAMES[user]

    game["guesses"].append({
        "guess": guess,
        "result": evaluate(game["word"], guess)
    })

    if guess == game["word"]:

        share = share_text(game["guesses"], len(game["guesses"]), True)

        ACTIVE_GAMES.pop(user)

        await update.message.reply_text(
            "🎉 <b>Você acertou!</b>\n\n"
            f"{history(game['guesses'])}\n\n"
            f"Palavra: <b>{game['word'].upper()}</b>",
            parse_mode="HTML",
            reply_markup=share_button(share)
        )

        return

    if len(game["guesses"]) >= MAX_ATTEMPTS:

        share = share_text(game["guesses"], MAX_ATTEMPTS, False)

        ACTIVE_GAMES.pop(user)

        await update.message.reply_text(
            "❌ <b>Fim de jogo</b>\n\n"
            f"{history(game['guesses'])}\n\n"
            f"Palavra: <b>{game['word'].upper()}</b>",
            parse_mode="HTML",
            reply_markup=share_button(share)
        )

        return

    await update.message.reply_text(
        board(game),
        parse_mode="HTML"
    )
