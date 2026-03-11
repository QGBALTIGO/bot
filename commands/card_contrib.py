import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes


WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()


async def sugerircard(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type != "private":
        return

    if not WEBAPP_URL:
        await update.message.reply_text(
            "⚠️ O sistema de contribuições não está configurado."
        )
        return

    url = f"{WEBAPP_URL}/cards/contrib"

    await update.message.reply_text(
        "🖼 <b>Central de Contribuições dos Cards</b>\n\n"
        "Ajude a melhorar os cards enviando novas imagens ou sugerindo novas obras.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "Abrir Central",
                web_app=WebAppInfo(url)
            )]
        ]),
        parse_mode="HTML"
    )
