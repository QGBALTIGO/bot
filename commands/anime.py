import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado.")

CATALOGO_URL = f"{BASE_URL}/catalogo"

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Abrir Catálogo", web_app=WebAppInfo(url=CATALOGO_URL))]
    ])

    await update.message.reply_text(
        "📚 <b>Catálogo de Animes</b>\n\nToque no botão abaixo para abrir o MiniApp.",
        parse_mode="HTML",
        reply_markup=kb,
    )
