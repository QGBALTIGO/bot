import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from cards_service import find_anime

ok, msg = await gatekeeper(update, context)
if not ok:
    if msg:
        await update.message.reply_html(msg)
    return
    
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
CARDS_BANNER = "https://photo.chelpbot.me/AgACAgEAAxkBZxImgmmnL7d9nYjTFd0KNTThxz9KJ6uCAAK7C2sbxrE5RXkd0eZ9Eoc4AQADAgADeQADOgQ/photo.jpg"


async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    direct_query = " ".join(context.args).strip()

    if direct_query:
        anime = find_anime(direct_query)

        if anime:
            url = f"{BASE_URL}/cards/anime?anime_id={anime['anime_id']}"
            texto = (
                f"🃏 <b>{anime['anime']}</b>\n\n"
                "Abrindo direto a obra encontrada nos cards."
            )
            botao = "🃏 Abrir Obra"
        else:
            url = f"{BASE_URL}/cards"
            texto = (
                "🃏 <b>COLEÇÃO DE PERSONAGENS</b>\n\n"
                f"Não achei uma obra exata para: <b>{direct_query}</b>\n"
                "Vou abrir a página geral dos cards para você buscar lá."
            )
            botao = "🃏 Abrir Cards"
    else:
        url = f"{BASE_URL}/cards"
        texto = (
            "🃏 <b>COLEÇÃO DE PERSONAGENS</b>\n\n"
            "Explore todos os personagens disponíveis no sistema de cards.\n\n"
            "🎴 Veja personagens por obra\n"
            "⭐ Use subcategorias\n"
            "🎲 Prepare-se para o gacha\n\n"
            "Toque no botão abaixo."
        )
        botao = "🃏 Abrir Cards"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(botao, web_app=WebAppInfo(url=url))]
    ])

    await update.message.reply_photo(
        photo=CARDS_BANNER,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb
    )
