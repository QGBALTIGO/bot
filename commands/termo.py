import json
import random
import time
from datetime import datetime, timedelta

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram import Update
from telegram.ext import ContextTypes

from database import _run

WORDS_FILE = "data/anime_words_365.json"

MAX_ATTEMPTS = 6
TIME_LIMIT = 300

ACTIVE_GAMES = {}
LAST_GUESS = {}

COOLDOWN = 2


with open(WORDS_FILE,encoding="utf8") as f:
    WORDS = json.load(f)


def anti_flood(user_id):

    now = time.time()

    last = LAST_GUESS.get(user_id,0)

    if now-last < COOLDOWN:
        return False

    LAST_GUESS[user_id] = now

    return True


def pick_word(user_id):

    today = datetime.utcnow().strftime("%Y-%m-%d")

    random.seed(f"{user_id}-{today}")

    return random.choice(WORDS)


def evaluate(word,guess):

    result = []

    for i in range(6):

        if guess[i] == word[i]:
            result.append("🟩")

        elif guess[i] in word:
            result.append("🟨")

        else:
            result.append("⬛")

    return "".join(result)


async def termo(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.message.text.lower() != "termo":
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Iniciar Desafio",callback_data="termo_start")]
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
        "⬛ letra não existe\n\n"
        "A palavra muda todos os dias."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=kb
    )


async def termo_start(update:Update,context:ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    user = q.from_user.id

    today = datetime.utcnow().strftime("%Y-%m-%d")

    played = _run(
        "SELECT * FROM termo_games WHERE user_id=%s AND date=%s",
        (user,today),
        "one"
    )

    if played:
        await q.edit_message_text("❌ Você já jogou hoje.")
        return

    w = pick_word(user)

    ACTIVE_GAMES[user] = {
        "word":w["word"],
        "category":w["category"],
        "source":w["source"],
        "attempts":0,
        "rows":[],
        "start":time.time()
    }

    _run(
        "INSERT INTO termo_games (user_id,date,word,attempts,status,start_time) VALUES (%s,%s,%s,0,'playing',%s)",
        (user,today,w["word"],int(time.time()))
    )

    await q.edit_message_text(
        "🎌 <b>TERMO ANIME</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: 0/6\n"
        "Tempo restante: 5:00\n\n"
        "Digite uma palavra.",
        parse_mode="HTML"
    )


async def termo_guess(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    guess = update.message.text.lower()

    if len(guess) != 6:
        return

    user = update.effective_user.id

    if user not in ACTIVE_GAMES:
        return

    if not anti_flood(user):
        return

    game = ACTIVE_GAMES[user]

    if time.time() - game["start"] > TIME_LIMIT:

        await update.message.reply_text(
            f"⏱ Tempo esgotado!\n\nPalavra: {game['word'].upper()}"
        )

        del ACTIVE_GAMES[user]

        return

    result = evaluate(game["word"],guess)

    game["rows"].append(result)

    game["attempts"] += 1

    if guess == game["word"]:

        _run(
            "UPDATE users SET coins=coins+2,xp=xp+10 WHERE user_id=%s",
            (user,)
        )

        await update.message.reply_text(
            f"{guess.upper()}\n{result}\n\n🎉 Acertou!\n\n🪙 +2 Coins\n⭐ +10 XP"
        )

        del ACTIVE_GAMES[user]

        return

    if game["attempts"] >= MAX_ATTEMPTS:

        await update.message.reply_text(
            f"{guess.upper()}\n{result}\n\n❌ Fim de jogo\nPalavra: {game['word'].upper()}"
        )

        del ACTIVE_GAMES[user]

        return

    rows = "\n".join(game["rows"])

    await update.message.reply_text(
        f"{guess.upper()}\n{result}\n\n"
        f"{rows}\n\n"
        f"Tentativas: {game['attempts']}/6"
    )
