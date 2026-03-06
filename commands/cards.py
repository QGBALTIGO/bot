import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")

CARDS_BANNER = "https://photo.chelpbot.me/AgACAgEAAxkBZyvh2mmo3LWFjXlOT23EKmzTblnf5rGpAAIiDGsbzg9IRQ8V6kjWRBTgAQADAgADeQADOgQ/photo.jpg"


async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = f"{BASE_URL}/cards"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Abrir Cards", web_app=WebAppInfo(url=url))]
    ])

    texto = (
        "🃏 <b>COLEÇÃO DE PERSONAGENS</b>\n\n"
        "Explore todos os personagens disponíveis no sistema de cards.\n\n"
        "🎴 Veja personagens por anime\n"
        "⭐ Descubra raridades\n"
        "🎲 Prepare-se para o gacha\n\n"
        "Toque no botão abaixo."
    )

    await update.message.reply_photo(
        photo=CARDS_BANNER,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb
    )
