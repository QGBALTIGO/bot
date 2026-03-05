# commands/anime.py

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper  # usa termos + canal obrigatório (se configurado)

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado.")

CATALOG_BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZzeISGmpyjb2CsPEQUv3zfVD-aj7780SAAKzC2sb6qtQRVbTTJ4IyPVIAQADAgADeQADOgQ/photo.jpg"


async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1) Gatekeeper (termos + canal). Se bloquear, manda a mensagem e para.
    ok, msg = await gatekeeper(update, context)
    if not ok:
        # gatekeeper já devolve msg pronta (e NÃO responde pra /start)
        if update.message and msg:
            await update.message.reply_html(msg)
        return

    # 2) Abre o MiniApp
    url = f"{BASE_URL}/catalogo"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Abrir Catálogo", web_app=WebAppInfo(url=url))],
    ])

    caption = (
        "📚 <b>Catálogo de Animes</b>\n\n"
        "A biblioteca do <b>Source Baltigo</b> está pronta para você explorar.\n\n"
        "🎴 Descubra títulos, encontre seus favoritos e navegue pelo catálogo completo.\n\n"
        "✨ Toque no botão abaixo para abrir o catálogo."
    )

    if update.message:
        await update.message.reply_photo(
            photo=CATALOG_BANNER_URL,
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb,
        )
