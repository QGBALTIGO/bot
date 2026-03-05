# commands/manga.py

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper


BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado no Railway.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigoBot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"

MANGA_BANNER_URL = os.getenv(
    "MANGA_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzguBWmp1rAsEzc6la-5rpAwuyD7vdm0AAL8C2sb1ZFIRYepX3uNQGYyAQADAgADeQADOgQ/photo.jpg"
).strip()


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message  # funciona mesmo se update.message for None

    # =========================
    # /manga em grupo -> mandar pro privado
    # =========================
    if _is_group(update):
        texto = (
            "⚠️ <b>Catálogo disponível apenas no privado</b>\n\n"
            "Para abrir o <b>Catálogo de Mangás &amp; Manhwas</b>, use este comando no <b>chat privado</b>.\n"
            "Assim seu acesso fica seguro e organizado. 📚✨\n\n"
            "👇 <b>Toque no botão para abrir o bot no privado:</b>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Abrir no privado", url=BOT_PRIVATE_URL)]
        ])
        if msg:
            await msg.reply_html(texto, reply_markup=kb)
        return

    # =========================
    # Gatekeeper (termos + canal)
    # =========================
    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        # (gatekeeper NÃO deve responder em /start; aqui é /manga, então pode)
        if msg and bloqueio:
            await msg.reply_html(bloqueio)
        return

    # =========================
    # Abre o MiniApp do catálogo de mangás
    # =========================
    url = f"{BASE_URL}/mangas"

    texto = (
        "📚 <b>Catálogo de Mangás &amp; Manhwas</b>\n\n"
        "A biblioteca do <b>Source Baltigo</b> está pronta para você explorar.\n\n"
        "🎴 Descubra títulos, encontre seus favoritos e navegue pelo catálogo completo.\n\n"
        "✨ Toque no botão abaixo para abrir o catálogo."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Abrir Catálogo de Mangás", web_app=WebAppInfo(url=url))]
    ])

    if msg:
        await msg.reply_photo(
            photo=MANGA_BANNER_URL,
            caption=texto,
            parse_mode="HTML",
            reply_markup=kb,
        )
