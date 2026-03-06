import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import create_or_get_user, has_anilist_login

ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID", "").strip()
ANILIST_REDIRECT_URL = os.getenv(
    "ANILIST_REDIRECT_URL",
    "https://anilist.co/api/v2/oauth/pin"
).strip()


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    create_or_get_user(user_id)

    if has_anilist_login(user_id):
        await update.message.reply_text(
            "✅ Sua conta AniList já está conectada.\n\nUse /perfil para ver seu perfil."
        )
        return

    if not ANILIST_CLIENT_ID:
        await update.message.reply_text(
            "❌ O login AniList não está configurado corretamente no servidor."
        )
        return

    url = (
        "https://anilist.co/api/v2/oauth/authorize"
        f"?client_id={ANILIST_CLIENT_ID}"
        f"&redirect_uri={ANILIST_REDIRECT_URL}"
        "&response_type=code"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Autorizar com AniList", url=url)]
    ])

    text = (
        "🔑 Para conectar sua conta AniList:\n\n"
        "1. Clique no botão abaixo\n"
        "2. Autorize o aplicativo no AniList\n"
        "3. Copie o código mostrado na tela\n"
        "4. Envie aqui no bot usando:\n"
        "<code>/code SEU_CODIGO</code>"
    )

    await update.message.reply_html(text, reply_markup=keyboard)
