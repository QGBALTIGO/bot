import os
import requests

from telegram import Update
from telegram.ext import ContextTypes

from database import save_anilist_account

ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID", "").strip()
ANILIST_CLIENT_SECRET = os.getenv("ANILIST_CLIENT_SECRET", "").strip()
ANILIST_REDIRECT_URL = os.getenv(
    "ANILIST_REDIRECT_URL",
    "https://anilist.co/api/v2/oauth/pin"
).strip()


async def code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id

    if not ANILIST_CLIENT_ID or not ANILIST_CLIENT_SECRET:
        await update.message.reply_text(
            "❌ O sistema AniList não está configurado corretamente no servidor."
        )
        return

    if not context.args:
        await update.message.reply_html(
            "❌ Envie o código assim:\n<code>/code SEU_CODIGO</code>"
        )
        return

    auth_code = context.args[0].strip()

    try:
        token_resp = requests.post(
            "https://anilist.co/api/v2/oauth/token",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "grant_type": "authorization_code",
                "client_id": ANILIST_CLIENT_ID,
                "client_secret": ANILIST_CLIENT_SECRET,
                "redirect_uri": ANILIST_REDIRECT_URL,
                "code": auth_code,
            },
            timeout=20,
        )

        token_json = token_resp.json()

        if "access_token" not in token_json:
            await update.message.reply_text(
                f"❌ Não foi possível autenticar no AniList.\n\nRetorno: {token_json}"
            )
            return

        access_token = token_json["access_token"]

        viewer_resp = requests.post(
            "https://graphql.anilist.co",
            json={"query": "query { Viewer { id name } }"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )

        viewer_json = viewer_resp.json()

        if "data" not in viewer_json or not viewer_json["data"] or not viewer_json["data"].get("Viewer"):
            await update.message.reply_text(
                f"❌ Token recebido, mas falhou ao buscar o perfil.\n\nRetorno: {viewer_json}"
            )
            return

        viewer = viewer_json["data"]["Viewer"]

        save_anilist_account(
            telegram_id=user_id,
            anilist_id=viewer["id"],
            username=viewer["name"],
            token=access_token
        )

        await update.message.reply_text(
            f"✅ Conta AniList conectada com sucesso!\n\nUsuário: {viewer['name']}\nUse /perfil para ver suas estatísticas."
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao conectar com AniList:\n{e}")
