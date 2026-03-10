import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "").strip().rstrip("/")

    if not WEBAPP_BASE_URL:
        await update.message.reply_html(
            "❌ <b>WEBAPP_BASE_URL não configurado.</b>"
        )
        return

    uid = int(update.effective_user.id)
    url = f"{WEBAPP_BASE_URL}/menu?uid={uid}"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⚙️ ABRIR MENU",
                web_app=WebAppInfo(url=url)
            )
        ]
    ])

    await update.message.reply_html(
        "⚙️ <b>MENU DO USUÁRIO</b>\n\n"
        "Abra o painel para configurar sua conta.",
        reply_markup=kb
    )
