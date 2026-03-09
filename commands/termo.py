import json
import random
import time
from datetime import date

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram import Update
from telegram.ext import ContextTypes

from database import (
    create_termo_game,
    get_termo_active_game,
    finish_termo_game,
    record_termo_result,
    get_termo_global_ranking,
    add_progress_xp,
    _run
)

WORDS_FILE = "data/anime_words_365.json"

MAX_ATTEMPTS = 6
TIME_LIMIT = 300

ACTIVE_GAMES = {}
LAST_GUESS = {}

COOLDOWN = 2

ADMINS = {123456789}


# =========================================================
# LOAD WORDS
# =========================================================

with open(WORDS_FILE, encoding="utf8") as f:
    WORDS = json.load(f)

VALID_WORDS = {w["word"] for w in WORDS}


# =========================================================
# UTIL
# =========================================================

def anti_flood(user_id):

    now = time.time()
    last = LAST_GUESS.get(user_id, 0)

    if now - last < COOLDOWN:
        return False

    LAST_GUESS[user_id] = now
    return True


def pick_word(user_id):

    today = date.today()

    seed = f"{user_id}-{today}"

    random.seed(seed)

    return random.choice(WORDS)


def evaluate(word, guess):

    result = ["⬛"] * 6
    remaining = {}

    for i in range(6):

        if guess[i] == word[i]:
            result[i] = "🟩"
        else:
            remaining[word[i]] = remaining.get(word[i], 0) + 1

    for i in range(6):

        if result[i] == "🟩":
            continue

        g = guess[i]

        if remaining.get(g, 0) > 0:
            result[i] = "🟨"
            remaining[g] -= 1

    return "".join(result)


def build_share(rows, attempts, streak):

    grid = "\n".join(rows)

    return (
        "🎌 TERMO ANIME\n\n"
        f"{grid}\n\n"
        f"{attempts}/6\n"
        f"🔥 Streak: {streak}"
    )


# =========================================================
# START MESSAGE
# =========================================================

async def termo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    txt = update.message.text.lower()

    if txt == "termo":

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 Iniciar Desafio", callback_data="termo_start")]
        ])

        text = (
            "🎌 <b>TERMO ANIME — SourceBaltigo</b>\n\n"
            "Descubra a palavra secreta de 6 letras relacionada a anime.\n\n"
            "🎯 6 tentativas\n"
            "⏱ 5 minutos\n"
            "🎁 Recompensa\n\n"
            "🪙 +2 Coins\n"
            "⭐ +10 XP\n\n"
            "🟩 posição correta\n"
            "🟨 letra existe\n"
            "⬛ letra não existe"
        )

        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=kb
        )

    if txt == "termo ranking":

        ranking = get_termo_global_ranking()

        msg = "🏆 Ranking Termo\n\n"

        for i, r in enumerate(ranking, 1):

            msg += f"{i}. {r['user_id']} — {r['wins']} vitórias\n"

        await update.message.reply_text(msg)

    if txt == "termo treino":

        user = update.effective_user.id

        if user not in ADMINS:
            return

        word = random.choice(WORDS)

        ACTIVE_GAMES[user] = {
            "word": word["word"],
            "rows": [],
            "attempts": 0,
            "mode": "train",
            "start": time.time()
        }

        await update.message.reply_text(
            "🧪 MODO TREINO\n\nDigite palavras."
        )


# =========================================================
# START GAME
# =========================================================

async def termo_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user = query.from_user.id

    word = pick_word(user)

    ACTIVE_GAMES[user] = {
        "word": word["word"],
        "rows": [],
        "attempts": 0,
        "mode": "daily",
        "start": time.time()
    }

    create_termo_game(
        user,
        date.today(),
        word["word"],
        int(time.time())
    )

    await query.edit_message_text(
        "🎌 <b>TERMO ANIME</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: 0/6\n"
        "Tempo restante: 5:00\n\n"
        "Digite uma palavra.",
        parse_mode="HTML"
    )


# =========================================================
# GUESS
# =========================================================

async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    guess = update.message.text.lower()

    if len(guess) != 6:
        return

    if guess not in VALID_WORDS:
        await update.message.reply_text("❌ Palavra inválida.")
        return

    user = update.effective_user.id

    if user not in ACTIVE_GAMES:

        game = get_termo_active_game(user)

        if not game:
            return

        ACTIVE_GAMES[user] = {
            "word": game["word"],
            "rows": [],
            "attempts": game["attempts"],
            "mode": game["mode"],
            "start": game["start_time"]
        }

    if not anti_flood(user):
        return

    game = ACTIVE_GAMES[user]

    if time.time() - game["start"] > TIME_LIMIT:

        await update.message.reply_text(
            f"⏱ Tempo esgotado!\n\nPalavra: {game['word'].upper()}"
        )

        finish_termo_game(user, "timeout", game["attempts"])

        del ACTIVE_GAMES[user]

        return

    if guess in [r["guess"] for r in game["rows"]]:

        await update.message.reply_text("❌ Palavra já usada.")
        return

    result = evaluate(game["word"], guess)

    game["rows"].append({
        "guess": guess,
        "result": result
    })

    game["attempts"] += 1

    rows = [r["result"] for r in game["rows"]]

    if guess == game["word"]:

        if game["mode"] == "daily":

            _run(
                "UPDATE users SET coins=coins+2 WHERE user_id=%s",
                (user,)
            )

            add_progress_xp(user, 10)

            record_termo_result(user, True, game["attempts"])

        share = build_share(rows, game["attempts"], 0)

        await update.message.reply_text(
            f"{guess.upper()}\n{result}\n\n🎉 Você acertou!\n\n{share}"
        )

        finish_termo_game(user, "win", game["attempts"])

        del ACTIVE_GAMES[user]

        return

    if game["attempts"] >= MAX_ATTEMPTS:

        await update.message.reply_text(
            f"{guess.upper()}\n{result}\n\n❌ Fim de jogo\nPalavra: {game['word'].upper()}"
        )

        if game["mode"] == "daily":
            record_termo_result(user, False, game["attempts"])

        finish_termo_game(user, "lose", game["attempts"])

        del ACTIVE_GAMES[user]

        return

    board = "\n".join(rows)

    await update.message.reply_text(
        f"{guess.upper()}\n{result}\n\n{board}\n\nTentativas: {game['attempts']}/6"
    )
