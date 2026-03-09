# commands/termo.py

import json
import random
import time
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from database import _run

WORDS_PATH = "data/anime_words_365.json"

MAX_ATTEMPTS = 6
TIME_LIMIT = 300  # 5 minutos


# =====================================================
# CARREGAR PALAVRAS
# =====================================================

with open(WORDS_PATH, encoding="utf-8") as f:
    WORDS = json.load(f)


def pick_word(user_id: int):
    random.seed(f"{user_id}-{time.strftime('%Y-%m-%d')}")
    return random.choice(WORDS)


# =====================================================
# COMPARAÇÃO WORDLE
# =====================================================

def evaluate_guess(word: str, guess: str):

    result = []

    for i in range(6):

        if guess[i] == word[i]:
            result.append("🟩")

        elif guess[i] in word:
            result.append("🟨")

        else:
            result.append("⬛")

    return "".join(result)


# =====================================================
# COMANDO TEXTO "termo"
# =====================================================

async def termo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.text.lower() != "termo":
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Iniciar Desafio", callback_data="termo_start")]
    ])

    text = (
        "🎌 <b>TERMO ANIME — SourceBaltigo</b>\n\n"
        "Descubra a palavra secreta de <b>6 letras</b> relacionada ao mundo dos animes.\n\n"
        "🎯 6 tentativas\n"
        "⏱ 5 minutos\n"
        "🎁 Recompensa ao acertar\n\n"
        "🪙 +2 Coins\n"
        "⭐ +10 XP\n\n"
        "🟩 Letra correta posição correta\n"
        "🟨 Letra existe posição errada\n"
        "⬛ Letra não existe\n\n"
        "A palavra muda todos os dias às 00:00."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=kb
    )


# =====================================================
# BOTÃO INICIAR
# =====================================================

async def termo_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user = query.from_user.id

    today = time.strftime("%Y-%m-%d")

    played = _run(
        "SELECT * FROM termo_games WHERE user_id=%s AND date=%s",
        (user, today),
        "one"
    )

    if played:
        await query.edit_message_text(
            "❌ Você já jogou o desafio de hoje."
        )
        return

    word = pick_word(user)

    _run(
        """
        INSERT INTO termo_games
        (user_id,date,word,attempts,status,start_time)
        VALUES (%s,%s,%s,0,'playing',%s)
        """,
        (user, today, word["word"], int(time.time()))
    )

    await query.edit_message_text(
        "🎌 <b>TERMO ANIME</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: 0/6\n"
        "Tempo restante: 5:00\n\n"
        "Digite uma palavra de 6 letras.",
        parse_mode="HTML"
    )


# =====================================================
# PROCESSAR TENTATIVA
# =====================================================

async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    guess = update.message.text.lower()

    if len(guess) != 6:
        return

    user = update.effective_user.id

    game = _run(
        "SELECT * FROM termo_games WHERE user_id=%s AND status='playing'",
        (user,),
        "one"
    )

    if not game:
        return

    if time.time() - game["start_time"] > TIME_LIMIT:

        _run(
            "UPDATE termo_games SET status='timeout' WHERE user_id=%s",
            (user,)
        )

        await update.message.reply_text(
            f"⏱ Tempo esgotado!\n\nPalavra: {game['word'].upper()}"
        )
        return

    attempts = game["attempts"] + 1
    word = game["word"]

    result = evaluate_guess(word, guess)

    if guess == word:

        _run(
            "UPDATE termo_games SET status='win', attempts=%s WHERE user_id=%s",
            (attempts, user)
        )

        _run(
            "UPDATE users SET coins = coins + 2, xp = xp + 10 WHERE user_id=%s",
            (user,)
        )

        await update.message.reply_text(
            f"{guess.upper()}\n{result}\n\n🎉 Você acertou!"
        )

        return

    if attempts >= MAX_ATTEMPTS:

        _run(
            "UPDATE termo_games SET status='lose', attempts=%s WHERE user_id=%s",
            (attempts, user)
        )

        await update.message.reply_text(
            f"{guess.upper()}\n{result}\n\n❌ Fim de jogo.\nPalavra: {word.upper()}"
        )

        return

    _run(
        "UPDATE termo_games SET attempts=%s WHERE user_id=%s",
        (attempts, user)
    )

    await update.message.reply_text(
        f"{guess.upper()}\n{result}\n\nTentativas: {attempts}/6"
    )
