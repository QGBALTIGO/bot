import os
import json
import random
import asyncio
import time
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from database import add_progress_xp, add_coin

DATA_PATH = Path("bot/data/perosnagsn_clean.json")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    DATA = json.load(f)

ALL_CHARACTERS = []
for anime in DATA["items"]:
    for c in anime["characters"]:
        ALL_CHARACTERS.append(c)

ENABLED_CHATS = set(
    int(x.strip())
    for x in os.getenv("CAPTURE_ENABLED_CHATS", "").split(",")
    if x.strip()
)

MESSAGE_COUNTER = {}
ACTIVE_SPAWNS = {}

SPAWN_EVERY = 100
ESCAPE_TIME = 300


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

    character = random.choice(ALL_CHARACTERS)

    ACTIVE_SPAWNS[chat_id] = {
        "character": character,
        "time": time.time(),
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
        parse_mode="HTML",
    )

    asyncio.create_task(escape_character(chat_id, context))


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

    await context.bot.send_message(chat_id, text, parse_mode="HTML")
