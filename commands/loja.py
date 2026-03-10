import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from database import create_or_get_user, touch_user_identity
from utils.gatekeeper import gatekeeper


BASE_URL = os.getenv("BASE_URL", "").strip()


async def loja(update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_user:
        return

    user = update.effective_user
    chat = update.effective_chat

    user_id = user.id
    username = user.username or ""
    full_name = user.full_name or ""

    # garante usuário no banco
    create_or_get_user(user_id)
    touch_user_identity(user_id, username, full_name)

    # gatekeeper (termos + canal)
    gk = await gatekeeper(update, context)
    if not gk:
        return

    if not BASE_URL:
        await update.message.reply_text("❌ Loja indisponível.")
        return

    webapp_url = f"{BASE_URL}/shop?uid={user_id}"

    keyboard = [
        [
            InlineKeyboardButton(
                "🏪 Abrir Loja",
                web_app=WebAppInfo(url=webapp_url)
            )
        ]
    ]

    text = (
        "🏪 <b>Loja do Jogo</b>\n\n"
        "💰 Venda personagens\n"
        "🎲 Compre dados\n"
        "🏷 Compre nickname\n"
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
