import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()


async def sugerircard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type != "private":
        await message.reply_text(
            "🖼 <b>Central de Contribuições dos Cards</b>\n\n"
            "Esse recurso só pode ser usado no privado do bot.",
            parse_mode="HTML",
        )
        return

    if not WEBAPP_URL:
        await message.reply_text(
            "⚠️ <b>Sistema indisponível</b>\n\n"
            "O WEBAPP_URL não está configurado.",
            parse_mode="HTML",
        )
        return

    url = f"{WEBAPP_URL}/cards/contrib"

    await message.reply_text(
        "🖼 <b>Central de Contribuições dos Cards</b>\n\n"
        "Ajude a melhorar os cards enviando novas imagens ou sugerindo novas obras.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Abrir Central", web_app=WebAppInfo(url))]
        ]),
        parse_mode="HTML",
    )
