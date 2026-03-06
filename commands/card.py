from telegram import Update
from telegram.ext import ContextTypes
import json
import os

DATA_PATH = os.path.join("data", "personagens_anilist.txt")

_characters = None


def load_characters():
    global _characters

    if _characters:
        return _characters

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    chars = {}

    for anime in data:
        for c in anime["characters"]:
            chars[int(c["id"])] = {
                "id": int(c["id"]),
                "name": c["name"],
                "image": c["image"],
                "anime": anime["anime"],
            }

    _characters = chars
    return chars


def find_character_by_name(name):
    name = name.lower()
    chars = load_characters()

    for c in chars.values():
        if name in c["name"].lower():
            return c

    return None


async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "Use:\n"
            "/card ID\n"
            "/card Nome"
        )
        return

    query = " ".join(context.args).strip()

    chars = load_characters()

    character = None

    if query.isdigit():
        character = chars.get(int(query))
    else:
        character = find_character_by_name(query)

    if not character:
        await update.message.reply_text("❌ Personagem não encontrado.")
        return

    char_id = character["id"]
    name = character["name"]
    anime = character["anime"]
    image = character["image"]

    caption = (
        f"🪪 Card #{char_id}\n\n"
        f"👤 {name}\n"
        f"🎬 {anime}"
    )

    await update.message.reply_photo(
        photo=image,
        caption=caption
    )
