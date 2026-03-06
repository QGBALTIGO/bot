# commands/pedido.py

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado no Railway.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"

PEDIDO_BANNER_URL = os.getenv(
    "PEDIDO_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzeISGmpyjb2CsPEQUv3zfVD-aj7780SAAKzC2sb6qtQRVbTTJ4IyPVIAQADAgADeQADOgQ/photo.jpg"
).strip()


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if _is_group(update):
        texto = (
            "⚠️ <b>Central de pedidos disponível apenas no privado</b>\n\n"
            "Para pedir <b>animes</b>, <b>mangás</b> ou <b>reportar um erro</b>, use este comando no <b>chat privado</b>.\n\n"
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

    url = f"{BASE_URL}/pedido"

    texto = (
        "📩 <b>Central de Pedidos</b>\n\n"
        "Peça <b>animes</b>, <b>mangás</b> ou envie um <b>report de erro</b> em um só lugar.\n\n"
        "✨ Toque no botão abaixo para abrir o Mini App."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Abrir Central de Pedidos", web_app=WebAppInfo(url=url))]
    ])

    if msg:
        await msg.reply_photo(
            photo=PEDIDO_BANNER_URL,
            caption=texto,
            parse_mode="HTML",
            reply_markup=kb,
        )
