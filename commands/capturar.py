import unicodedata
from telegram import Update
from telegram.ext import ContextTypes

from handlers.capture_spawn import ACTIVE_SPAWNS
from database import add_coin, add_progress_xp


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.strip()


async def capturar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    chat_id = update.effective_chat.id

    if chat_id not in ACTIVE_SPAWNS:
        return

    if not context.args:
        return

    guess = _normalize(" ".join(context.args))

    character = ACTIVE_SPAWNS[chat_id]["character"]

    correct = _normalize(character["name"])

    if guess != correct:
        return

    user = update.effective_user

    # recompensa
    add_coin(user.id, 1)
    add_progress_xp(user.id, 10)

    text = (
        "🎉 <b>CAPTURADO!</b>\n\n"
        f"👤 <b>{character['name']}</b>\n"
        f"📺 {character['anime']}\n\n"
        "💰 +1 coin\n"
        "⭐ +10 XP"
    )

    await update.message.reply_photo(
        photo=character["image"],
        caption=text,
        parse_mode="HTML"
    )

    del ACTIVE_SPAWNS[chat_id]
