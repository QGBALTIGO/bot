import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper


BASE_URL = (os.getenv("BASE_URL", "").strip() or os.getenv("WEBAPP_URL", "").strip()).rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL nao configurado.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"

PEDIDO_BANNER_URL = os.getenv(
    "PEDIDO_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZ0w54WmrME4Fk9ObOXCy_CjgTb8IHF9cAAJRC2sb1ZFYRTRdgJDi4ysfAQADAgADeQADOgQ/photo.jpg",
).strip()


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    if _is_group(update):
        texto = (
            "<b>Central de pedidos disponivel apenas no privado</b>\n\n"
            "Para pedir animes, mangas ou reportar um erro, use este comando no chat privado.\n\n"
            "Toque no botao abaixo para abrir o bot."
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

    url = f"{BASE_URL}/pedido?uid={user.id}"
    texto = (
        "<b>Central de Pedidos</b>\n\n"
        "Peca animes, mangas ou envie um report de erro em um so lugar.\n\n"
        "Toque no botao abaixo para abrir o Mini App."
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Abrir Central de Pedidos", web_app=WebAppInfo(url=url))]]
    )

    await msg.reply_photo(
        photo=PEDIDO_BANNER_URL,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
