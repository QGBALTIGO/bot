import os
import time
import hmac
import hashlib
import base64

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import create_or_get_user, has_anilist_login

ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID", "").strip()
PUBLIC_BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
OAUTH_STATE_SECRET = os.getenv("OAUTH_STATE_SECRET", "").strip()


def make_state(user_id: int) -> str:
    ts = str(int(time.time()))
    payload = f"{user_id}.{ts}".encode()

    sig = hmac.new(
        OAUTH_STATE_SECRET.encode(),
        payload,
        hashlib.sha256
    ).digest()

    return base64.urlsafe_b64encode(payload + b"." + sig).decode().rstrip("=")


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id

    create_or_get_user(user_id)

    if has_anilist_login(user_id):
        await update.message.reply_text(
            "✅ Você já conectou sua conta AniList.\n\nUse /perfil para ver suas estatísticas."
        )
        return

    state = make_state(user_id)

    redirect_uri = f"{PUBLIC_BASE_URL}/callback"

    url = (
        "https://anilist.co/api/v2/oauth/authorize"
        f"?client_id={ANILIST_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        f"&state={state}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Conectar AniList", url=url)]
    ])

    await update.message.reply_text(
        "🔑 Conecte sua conta AniList para sincronizar seus animes e mangás.",
        reply_markup=keyboard
    )
