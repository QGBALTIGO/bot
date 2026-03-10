import os
import random
from telegram import Update
from telegram.ext import ContextTypes

from handlers.capture_spawn import CHARACTERS, ACTIVE_SPAWNS


ADMIN_IDS = set(
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
)


async def spawn_personagem(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        return

    chat_id = update.effective_chat.id

    if not CHARACTERS:
        await update.message.reply_text("Dataset de personagens não carregado.")
        return

    character = random.choice(CHARACTERS)

    ACTIVE_SPAWNS[chat_id] = {
        "character": character
    }

    caption = (
        "🧪 <b>SPAWN DE TESTE</b>\n\n"
        "🕵️ Quem é esse personagem?\n\n"
        "Use:\n"
        "<code>/capturar nome</code>"
    )

    await update.message.reply_photo(
        photo=character["image"],
        caption=caption,
        parse_mode="HTML"
    )
