from utils.miniapp_links import miniapp_url, miniapp_entrypoint
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes


WEBAPP_URL = miniapp_entrypoint().removesuffix('/menu')


async def sugerircard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type != "private":
        await message.reply_text(
            "<b>Central de Contribuicoes dos Cards</b>\n\n"
            "Esse recurso so pode ser usado no privado do bot.",
            parse_mode="HTML",
        )
        return

    if not WEBAPP_URL:
        await message.reply_text(
            "<b>Sistema indisponivel</b>\n\n"
            "O WEBAPP_URL/BASE_URL nao esta configurado.",
            parse_mode="HTML",
        )
        return

    url = miniapp_url('contribute')

    await message.reply_text(
        "<b>Central de Contribuicoes dos Cards</b>\n\n"
        "Ajude a melhorar os cards enviando novas imagens ou sugerindo novas obras.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Abrir Central", web_app=WebAppInfo(url=url))]]
        ),
        parse_mode="HTML",
    )
