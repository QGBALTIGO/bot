import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper


BASE_URL = (os.getenv("BASE_URL", "").strip() or os.getenv("WEBAPP_URL", "").strip()).rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL nao configurado.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
if not BOT_USERNAME:
    raise RuntimeError("BOT_USERNAME nao configurado.")

COLECAO_BANNER_URL = os.getenv(
    "COLECAO_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZ0sajmmrHXRy1AZxkfEGC2Lx4yC6A80MAAJOC2sb1ZFYRQ5kxLI09cC2AQADAgADeQADOgQ/photo.jpg",
).strip()

BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def colec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    if _is_group(update):
        texto = (
            "<b>COLECAO MINI APP</b>\n\n"
            "Esse comando funciona apenas no privado do bot.\n\n"
            "Abra no privado para ver sua colecao sincronizada com a loja e com os cards em tempo real."
        )
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Abrir no privado", url=BOT_PRIVATE_URL)]]
        )
        await msg.reply_html(texto, reply_markup=kb)
        return

    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    url = f"{BASE_URL}/cccolecao?uid={user.id}"
    texto = (
        "<b>COLECAO BALTIGO</b>\n\n"
        "Abra sua colecao em um Mini App sincronizado com a loja, o favorito e as alteracoes mais recentes dos cards.\n\n"
        "Toque abaixo para abrir."
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Abrir Colecao", web_app=WebAppInfo(url=url))]]
    )

    await msg.reply_photo(
        photo=COLECAO_BANNER_URL,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
