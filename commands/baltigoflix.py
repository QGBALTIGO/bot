import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"

BALTIGOFLIX_BANNER_URL = os.getenv(
    "BALTIGOFLIX_BANNER_URL",
    "https://i.imgur.com/8Km9tLL.png",
).strip()


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def baltigoflix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    if _is_group(update):
        texto = (
            "🎬 <b>BaltigoFlix</b>\n\n"
            "Esse comando funciona no <b>chat privado</b>.\n\n"
            "👇 Toque abaixo para abrir o bot:"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Abrir no privado", url=BOT_PRIVATE_URL)]
        ])
        await msg.reply_html(texto, reply_markup=kb)
        return

    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    webapp_url = f"{BASE_URL}/baltigoflix"

    texto = (
        "🎬 <b>BaltigoFlix</b>\n\n"
        "Acesse a área BaltigoFlix direto pelo Mini App.\n\n"
        "✨ Experiência integrada\n"
        "⚡ Acesso rápido\n"
        "📱 Tudo dentro do Telegram\n\n"
        "👇 Toque abaixo para continuar:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Abrir BaltigoFlix", web_app=WebAppInfo(url=webapp_url))]
    ])

    if BALTIGOFLIX_BANNER_URL:
        await msg.reply_photo(
            photo=BALTIGOFLIX_BANNER_URL,
            caption=texto,
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await msg.reply_html(texto, reply_markup=kb)
