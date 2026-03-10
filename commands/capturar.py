import os
import random
from telegram import Update
from telegram.ext import ContextTypes

from handlers.capture_spawn import ALL_CHARACTERS, ACTIVE_SPAWNS

ADMIN_IDS = set(
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
)


async def spawnpersonagem(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id not in ADMIN_IDS:
        return

    chat_id = update.effective_chat.id

    character = random.choice(ALL_CHARACTERS)

    ACTIVE_SPAWNS[chat_id] = {
        "character": character
    }

    text = (
        "🧪 <b>SPAWN DE TESTE</b>\n\n"
        "Quem é esse personagem?\n\n"
        "<code>/capturar nome</code>"
    )

    await update.message.reply_photo(
        photo=character["image"],
        caption=text,
        parse_mode="HTML"
    )
