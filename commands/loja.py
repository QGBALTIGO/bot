import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes


BASE_URL = os.getenv("BASE_URL")


async def loja(update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    keyboard = [
        [
            InlineKeyboardButton(
                "🛒 Abrir Loja",
                web_app=WebAppInfo(
                    url=f"{BASE_URL}/shop"
                )
            )
        ]
    ]

    await update.message.reply_text(
        "🛒 Loja Baltigo",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
