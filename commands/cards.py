import html
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from cards_service import find_anime
from utils.gatekeeper import gatekeeper
from utils.public_url import require_public_base_url

BASE_URL = require_public_base_url()
CARDS_BANNER = os.getenv(
    "CARDS_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZxImgmmnL7d9nYjTFd0KNTThxz9KJ6uCAAK7C2sbxrE5RXkd0eZ9Eoc4AQADAgADeQADOgQ/photo.jpg",
).strip()


async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    ok, blocked_message = await gatekeeper(update, context)
    if not ok:
        if message and blocked_message:
            await message.reply_html(blocked_message)
        return

    direct_query = " ".join(context.args).strip()
    if direct_query:
        anime = find_anime(direct_query)
        if anime:
            anime_id = int(anime["anime_id"])
            anime_name = html.escape(str(anime["anime"]), quote=False)
            url = f"{BASE_URL}/cards/anime?anime_id={anime_id}"
            text = f"🃏 <b>{anime_name}</b>\n\nAbrindo direto a obra encontrada nos cards."
            button_text = "🃏 Abrir Obra"
        else:
            safe_query = html.escape(direct_query, quote=False)
            url = f"{BASE_URL}/cards"
            text = (
                "🃏 <b>COLEÇÃO DE PERSONAGENS</b>\n\n"
                f"Não achei uma obra exata para: <b>{safe_query}</b>\n"
                "Vou abrir a página geral dos cards para você buscar lá."
            )
            button_text = "🃏 Abrir Cards"
    else:
        url = f"{BASE_URL}/cards"
        text = (
            "🃏 <b>COLEÇÃO DE PERSONAGENS</b>\n\n"
            "Explore todos os personagens disponíveis no sistema de cards.\n\n"
            "🎴 Veja personagens por obra\n⭐ Use subcategorias\n🎲 Prepare-se para o gacha\n\n"
            "Toque no botão abaixo."
        )
        button_text = "🃏 Abrir Cards"

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, web_app=WebAppInfo(url=url))]])
    if message:
        await message.reply_photo(photo=CARDS_BANNER, caption=text, parse_mode="HTML", reply_markup=keyboard)
