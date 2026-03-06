from telegram import Update
from telegram.ext import ContextTypes

from database import get_anilist_profile


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    profile = get_anilist_profile(user_id)

    if not profile:
        await update.message.reply_text(
            "❌ Você ainda não conectou sua conta AniList.\n\nUse /login para conectar."
        )
        return

    text = (
        f"👤 Nome: {profile['name']}\n"
        f"🆔 ID: {profile['anilist_id']}\n\n"
        f"📺 Animes assistidos: {profile['anime_count']}\n"
        f"⏱ Dias assistidos: {profile['days']}\n"
        f"📖 Mangás lidos: {profile['manga_count']}"
    )

    await update.message.reply_text(text)
