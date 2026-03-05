# commands/anime.py

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot")

if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado.")

CATALOG_BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZzeISGmpyjb2CsPEQUv3zfVD-aj7780SAAKzC2sb6qtQRVbTTJ4IyPVIAQADAgADeQADOgQ/photo.jpg"


def _is_group(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))


async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # =========================
    # Se usar em grupo
    # =========================
    if _is_group(update):

        texto = (
            "⚠️ <b>Catálogo disponível apenas no privado</b>\n\n"
            "O <b>Source Baltigo</b> utiliza um <b>Mini App interativo</b> para "
            "explorar o catálogo completo de animes.\n\n"
            "📺 Para acessar a biblioteca, abra o bot no <b>chat privado</b>.\n\n"
            "🎴 <i>Lá você poderá navegar pelos títulos, descobrir novos animes "
            "e abrir diretamente os episódios disponíveis.</i>"
        )

        teclado = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📺 Abrir Catálogo no privado",
                    url=f"https://t.me/{BOT_USERNAME}"
                )
            ]
        ])

        if update.message:
            await update.message.reply_html(texto, reply_markup=teclado)

        return

    # =========================
    # Gatekeeper (termos + canal)
    # =========================
    ok, msg = await gatekeeper(update, context)

    if not ok:
        if update.message and msg:
            await update.message.reply_html(msg)
        return

    # =========================
    # Abrir MiniApp catálogo
    # =========================

    url = f"{BASE_URL}/catalogo"

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📺 Abrir Catálogo de Animes",
                web_app=WebAppInfo(url=url)
            )
        ]
    ])

    texto = (
        "📺 <b>Catálogo de Animes</b>\n\n"
        "A biblioteca do <b>Source Baltigo</b> está pronta para você explorar.\n\n"
        "🎴 Descubra títulos, encontre seus favoritos e navegue pelo catálogo completo.\n\n"
        "✨ Toque no botão abaixo para abrir o catálogo."
    )

    if update.message:
        await update.message.reply_photo(
            photo=CATALOG_BANNER_URL,
            caption=texto,
            parse_mode="HTML",
            reply_markup=teclado
        )
