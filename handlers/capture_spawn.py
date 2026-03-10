import os
import random
import asyncio
import time
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

DATA_PATH = Path("data/personagens_anilist.txt")

CHARACTERS = []
ACTIVE_SPAWNS = {}
MESSAGE_COUNTER = {}

SPAWN_EVERY = 100
ESCAPE_TIME = 300

ENABLED_CHATS = set(
    int(x.strip())
    for x in os.getenv("CAPTURE_ENABLED_CHATS", "").split(",")
    if x.strip()
)


def _load_characters():
    items = []

    if not DATA_PATH.exists():
        print(f"[CAPTURE] arquivo não encontrado: {DATA_PATH}")
        return items

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or "|" not in line:
                continue

            parts = line.split("|")
            if len(parts) < 3:
                continue

            char_id = str(parts[0]).strip()
            name = str(parts[1]).strip()
            anime = str(parts[2]).strip()

            if not char_id.isdigit():
                continue

            items.append(
                {
                    "id": int(char_id),
                    "name": name,
                    "anime": anime,
                    "image": f"https://img.anili.st/character/{char_id}",
                }
            )

    return items


CHARACTERS = _load_characters()
print(f"[CAPTURE] personagens carregados: {len(CHARACTERS)}")


async def capture_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    chat_id = chat.id

    if chat_id not in ENABLED_CHATS:
        return

    if not CHARACTERS:
        return

    MESSAGE_COUNTER[chat_id] = MESSAGE_COUNTER.get(chat_id, 0) + 1

    if chat_id in ACTIVE_SPAWNS:
        return

    if MESSAGE_COUNTER[chat_id] < SPAWN_EVERY:
        return

    MESSAGE_COUNTER[chat_id] = 0

    character = random.choice(CHARACTERS)

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

    asyncio.create_task(_escape_character(chat_id, context))


async def _escape_character(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(ESCAPE_TIME)

    if chat_id not in ACTIVE_SPAWNS:
        return

    char = ACTIVE_SPAWNS.pop(chat_id)["character"]

    text = (
        "💨 <b>O personagem fugiu...</b>\n\n"
        f"👤 <b>{char['name']}</b>\n"
        f"📺 {char['anime']}"
    )

    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
