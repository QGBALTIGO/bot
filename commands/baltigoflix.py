import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes


BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"
WEBAPP_BASE = (
    os.getenv("BASE_URL", "").strip()
    or os.getenv("WEBAPP_URL", "").strip()
    or "https://bot-production-1980.up.railway.app"
).rstrip("/")
MINI_APP_URL = f"{WEBAPP_BASE}/baltigoflix"
BALTIGOFLIX_BANNER_URL = os.getenv(
    "BALTIGOFLIX_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBaDfI-2m66g4WQ-Jj6FZRPjNKhpCO_4kNAAIXrzEbj2ehRbC9NWdU_qoOAQADAgADeQADOgQ/photo.jpg",
).strip()


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def baltigoflix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    if _is_group(update):
        texto = (
            "<b>BaltigoFlix disponivel apenas no privado</b>\n\n"
            "Para conhecer os planos e acessar a area premium, use este comando no chat privado.\n\n"
            "Toque abaixo para abrir."
        )
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Abrir no privado", url=BOT_PRIVATE_URL)]]
        )
        await msg.reply_html(texto, reply_markup=kb)
        return

    texto = (
        "<b>BaltigoFlix</b>\n\n"
        "Chegou o BaltigoFlix, a forma definitiva de assistir tudo em um so lugar.\n\n"
        "Mais de 2.000 canais, streaming, suporte dedicado e checkout rapido.\n\n"
        "Toque abaixo e comece agora."
    )
    url = f"{MINI_APP_URL}?uid={user.id}"
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Abrir BaltigoFlix", web_app=WebAppInfo(url=url))]]
    )

    await msg.reply_photo(
        photo=BALTIGOFLIX_BANNER_URL,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
