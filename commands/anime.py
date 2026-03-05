from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
import os

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado.")

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # abre o miniapp do catálogo (por enquanto)
    url = f"{BASE_URL}/catalogo"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Abrir Catálogo de Animes", web_app=WebAppInfo(url=url))]
    ])

    if update.message:
        await update.message.reply_text("📚 Abrindo o catálogo de animes…", reply_markup=kb)
