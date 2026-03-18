import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado no Railway.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"

BALTIGOFLIX_BANNER_URL = os.getenv(
    "BALTIGOFLIX_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZ0w54WmrME4Fk9ObOXCy_CjgTb8IHF9cAAJRC2sb1ZFYRTRdgJDi4ysfAQADAgADeQADOgQ/photo.jpg"
).strip()


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def baltigoflix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if _is_group(update):
        texto = (
            "🎬 <b>BaltigoFlix disponível apenas no privado</b>\n\n"
            "Para ver os <b>planos</b> e abrir a área premium, use este comando no <b>chat privado</b>.\n\n"
            "👇 <b>Toque no botão abaixo para abrir o bot:</b>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Abrir no privado", url=BOT_PRIVATE_URL)]
        ])
        if msg:
            await msg.reply_html(texto, reply_markup=kb)
        return

    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if msg and bloqueio:
            await msg.reply_html(bloqueio)
        return

    url = f"{BASE_URL}/baltigoflix"

    texto = (
        "🎬 <b>BaltigoFlix</b>\n\n"
        "Veja os <b>planos</b>, benefícios e a área premium em um Mini App bonito e organizado.\n\n"
        "✨ Toque no botão abaixo para abrir."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Abrir BaltigoFlix", web_app=WebAppInfo(url=url))]
    ])

    if msg:
        await msg.reply_photo(
            photo=BALTIGOFLIX_BANNER_URL,
            caption=texto,
            parse_mode="HTML",
            reply_markup=kb,
        )
