import os
import random
import json
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from handlers.capture_spawn import ACTIVE_SPAWNS

ADMIN_IDS = set(
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
)

DATA_PATH = Path("bot/data/perosnagsn_clean.json")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    DATA = json.load(f)

ALL_CHARACTERS = []
for anime in DATA["items"]:
    for c in anime["characters"]:
        ALL_CHARACTERS.append(c)


async def spawn_personagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        return

    chat_id = update.effective_chat.id

    character = random.choice(ALL_CHARACTERS)

    ACTIVE_SPAWNS[chat_id] = {
        "character": character,
    }

    text = (
        "🧪 <b>SPAWN DE TESTE</b>\n\n"
        "Quem é esse personagem?\n\n"
        "<code>/capturar nome</code>"
    )

    await update.message.reply_photo(
        photo=character["image"],
        caption=text,
        parse_mode="HTML",
    )
