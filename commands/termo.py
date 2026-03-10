import json
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import (
    create_termo_game,
    get_termo_active_game,
    update_termo_game_progress,
    finish_termo_game,
    record_termo_result,
    get_termo_stats,
    get_termo_user_rank,
    get_termo_global_ranking,
    add_user_coins,
    add_progress_xp,
)

SP_TZ = ZoneInfo("America/Sao_Paulo")

WORD_LENGTH = 6
MAX_ATTEMPTS = 6
TIME_LIMIT = 300

WORDS_FILE = "data/anime_words_365.json"

WORDS = []
VALID_WORDS = set()

ACTIVE_GAMES = {}


def sp_today():
    return datetime.now(SP_TZ).date()


def load_words():

    global WORDS, VALID_WORDS

    if WORDS:
        return WORDS

    with open(WORDS_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    cleaned = []
    seen = set()

    for w in raw:

        word = w["word"].lower().strip()

        if len(word) != WORD_LENGTH:
            continue

        if word in seen:
            continue

        seen.add(word)

        cleaned.append({
            "word": word,
            "category": w.get("category","Anime"),
            "source": w.get("source","Anime")
        })

    WORDS = cleaned
    VALID_WORDS = {x["word"] for x in cleaned}

    return WORDS


def daily_word():

    words = load_words()

    seed = sp_today().isoformat()

    rng = random.Random(seed)

    return rng.choice(words)


def random_word():

    words = load_words()

    return random.choice(words)


def evaluate(secret, guess):

    result = ["⬛"] * WORD_LENGTH
    remaining = {}

    for i in range(WORD_LENGTH):

        if guess[i] == secret[i]:
            result[i] = "🟩"
        else:
            remaining[secret[i]] = remaining.get(secret[i],0)+1

    for i in range(WORD_LENGTH):

        if result[i] != "⬛":
            continue

        if guess[i] in remaining and remaining[guess[i]] > 0:
            result[i] = "🟨"
            remaining[guess[i]] -= 1

    return "".join(result)


def grid(game):

    lines = []

    for g in game["guesses"]:
        lines.append(evaluate(game["word"], g) + f" {g.upper()}")

    return "\n".join(lines)


def start_game(user_id, mode):

    if mode == "daily":
        word_data = daily_word()
    else:
        word_data = random_word()

    game = {
        "user_id": user_id,
        "word": word_data["word"],
        "category": word_data["category"],
        "source": word_data["source"],
        "mode": mode,
        "guesses": [],
        "start": int(time.time())
    }

    ACTIVE_GAMES[user_id] = game

    if mode == "daily":

        create_termo_game(
            user_id=user_id,
            game_date=sp_today(),
            word=word_data["word"],
            category=word_data["category"],
            source=word_data["source"],
            start_time=game["start"],
            mode="daily",
        )

    return game


async def termo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id

    if user_id in ACTIVE_GAMES:

        await update.message.reply_text(
            "🎮 Você já tem um jogo ativo.\n"
            "Envie sua tentativa."
        )
        return

    db_game = get_termo_active_game(user_id)

    if db_game:

        ACTIVE_GAMES[user_id] = {
            "user_id": user_id,
            "word": db_game["word"],
            "category": db_game["category"],
            "source": db_game["source"],
            "mode": db_game["mode"],
            "guesses": db_game["guesses"] or [],
            "start": db_game["start_time"]
        }

        await update.message.reply_text(
            "🎮 Você já iniciou o jogo hoje.\n"
            "Continue tentando!"
        )
        return

    game = start_game(user_id, "daily")

    await update.message.reply_text(
        "🎮 <b>TERMO</b>\n\n"
        "Adivinhe a palavra de 6 letras.\n"
        "Você tem 6 tentativas.",
        parse_mode="HTML"
    )


async def termo_treino_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    game = start_game(user_id, "train")

    await update.message.reply_text(
        "🎯 <b>Modo Treino</b>\n\n"
        "Adivinhe a palavra.",
        parse_mode="HTML"
    )


async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    text = update.message.text.lower().strip()

    if len(text) != WORD_LENGTH:
        return

    user_id = update.effective_user.id

    if user_id not in ACTIVE_GAMES:
        return

    if text not in VALID_WORDS:
        return

    game = ACTIVE_GAMES[user_id]

    if len(game["guesses"]) >= MAX_ATTEMPTS:
        return

    game["guesses"].append(text)

    result = evaluate(game["word"], text)

    msg = result

    if text == game["word"]:

        if game["mode"] == "daily":

            add_user_coins(user_id, 10)
            add_progress_xp(user_id, 15)

            record_termo_result(user_id, True, len(game["guesses"]))

        ACTIVE_GAMES.pop(user_id)

        await update.message.reply_text(
            f"{grid(game)}\n\n"
            f"🎉 Você acertou!\n"
            f"Palavra: <b>{game['word']}</b>",
            parse_mode="HTML"
        )

        return

    if len(game["guesses"]) >= MAX_ATTEMPTS:

        if game["mode"] == "daily":
            record_termo_result(user_id, False, MAX_ATTEMPTS)

        ACTIVE_GAMES.pop(user_id)

        await update.message.reply_text(
            f"{grid(game)}\n\n"
            f"❌ Você perdeu.\n"
            f"Palavra: <b>{game['word']}</b>",
            parse_mode="HTML"
        )

        return

    await update.message.reply_text(msg)


async def termo_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    stats = get_termo_stats(user_id)

    if not stats:
        await update.message.reply_text("Nenhuma estatística ainda.")
        return

    msg = (
        "📊 <b>Estatísticas</b>\n\n"
        f"Jogos: {stats['games']}\n"
        f"Vitórias: {stats['wins']}\n"
        f"Derrotas: {stats['losses']}\n"
        f"Streak: {stats['streak']}"
    )

    await update.message.reply_text(msg, parse_mode="HTML")


async def termo_ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    ranking = get_termo_global_ranking()

    lines = []

    for i,row in enumerate(ranking[:10],1):

        medal = ""

        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"

        lines.append(
            f"{medal}{i}. {row['username']} — {row['wins']} vitórias"
        )

    await update.message.reply_text(
        "🏆 <b>Ranking Termo</b>\n\n" + "\n".join(lines),
        parse_mode="HTML"
    )
