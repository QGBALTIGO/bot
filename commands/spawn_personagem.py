import os
import random
import asyncio
import time
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

DATA_PATH = Path("bot/data/personagens_anilist.txt")

CHARACTERS = []

# ---------------------------------------------------------
# LOAD TXT DATASET
# ---------------------------------------------------------

if DATA_PATH.exists():

    with open(DATA_PATH, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line or "|" not in line:
                continue

            parts = line.split("|")

            if len(parts) < 3:
                continue

            char_id = parts[0]
            name = parts[1]
            anime = parts[2]

            CHARACTERS.append({
                "id": int(char_id),
                "name": name,
                "anime": anime,
                "image": f"https://img.anili.st/character/{char_id}"
            })

print(f"[CAPTURE] personagens carregados: {len(CHARACTERS)}")

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

ENABLED_CHATS = set(
    int(x.strip())
    for x in os.getenv("CAPTURE_ENABLED_CHATS", "").split(",")
    if x.strip()
)

MESSAGE_COUNTER = {}

ACTIVE_SPAWNS = {}

SPAWN_EVERY = 100

ESCAPE_TIME = 300

# ---------------------------------------------------------
# SPAWN SYSTEM
# ---------------------------------------------------------

async def capture_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    chat_id = update.effective_chat.id

    if chat_id not in ENABLED_CHATS:
        return

    MESSAGE_COUNTER.setdefault(chat_id, 0)
    MESSAGE_COUNTER[chat_id] += 1

    if MESSAGE_COUNTER[chat_id] < SPAWN_EVERY:
        return

    MESSAGE_COUNTER[chat_id] = 0

    if chat_id in ACTIVE_SPAWNS:
        return

    character = random.choice(CHARACTERS)

    ACTIVE_SPAWNS[chat_id] = {
        "character": character,
        "time": time.time()
    }

    caption = (
        "✨ <b>UM PERSONAGEM APARECEU!</b>\n\n"
        "🕵️ <i>Quem é esse personagem?</i>\n\n"
        "⏳ Ele fugirá em <b>5 minutos</b>\n\n"
        "💬 Use:\n"
        "<code>/capturar nome</code>"
    )

    await update.message.reply_photo(
        photo=character["image"],
        caption=caption,
        parse_mode="HTML"
    )

    asyncio.create_task(escape_character(chat_id, context))


# ---------------------------------------------------------
# ESCAPE TIMER
# ---------------------------------------------------------

async def escape_character(chat_id, context):

    await asyncio.sleep(ESCAPE_TIME)

    if chat_id not in ACTIVE_SPAWNS:
        return

    char = ACTIVE_SPAWNS.pop(chat_id)["character"]

    text = (
        "💨 <b>O personagem fugiu...</b>\n\n"
        f"👤 <b>{char['name']}</b>\n"
        f"📺 {char['anime']}"
    )

    await context.bot.send_message(
        chat_id,
        text,
        parse_mode="HTML"
    )
