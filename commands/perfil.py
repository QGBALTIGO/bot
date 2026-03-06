from telegram import Update
from telegram.ext import ContextTypes

from database import get_anilist_profile


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    profile = get_anilist_profile(user_id)

    if not profile:
        await update.message.reply_text(
            "❌ Você ainda não conectou sua conta AniList.\n\nUse /login para conectar."
        )
        return

    name = profile["name"]
    anilist_id = profile["anilist_id"]

    anime_count = profile["anime_count"]
    days = profile["days"]
    manga_count = profile["manga_count"]

    text = (
        f"👤 Nome: {name}\n"
        f"ID: {anilist_id}\n\n"
        f"📺 Anime Watched: {anime_count}\n"
        f"⏱ Days Watched: {days}\n"
        f"📖 Manga Read: {manga_count}"
    )

    await update.message.reply_text(text)
