import os
import time
import hmac
import hashlib
import base64

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import create_or_get_user, has_anilist_login

ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
OAUTH_STATE_SECRET = os.getenv("OAUTH_STATE_SECRET", "").strip()


def make_state(user_id: int) -> str:
    ts = str(int(time.time()))
    payload = f"{user_id}.{ts}".encode()
    sig = hmac.new(OAUTH_STATE_SECRET.encode(), payload, hashlib.sha256).digest()
    raw = payload + b"." + sig
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return

    user_id = user.id
    create_or_get_user(user_id)

    if has_anilist_login(user_id):
        await update.message.reply_text(
            "✅ Sua conta AniList já está conectada.\n\nUse /perfil para ver seu perfil."
        )
        return

    if not ANILIST_CLIENT_ID or not PUBLIC_BASE_URL or not OAUTH_STATE_SECRET:
        await update.message.reply_text(
            "❌ O login AniList não está configurado corretamente no servidor."
        )
        return

    redirect_uri = f"{PUBLIC_BASE_URL}/callback"
    state = make_state(user_id)

    url = (
        "https://anilist.co/api/v2/oauth/authorize"
        f"?client_id={ANILIST_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        f"&state={state}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Conectar com AniList", url=url)]
    ])

    await update.message.reply_text(
        "🔑 Clique no botão abaixo para conectar sua conta AniList.",
        reply_markup=keyboard
    )
