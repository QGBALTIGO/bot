import os
from telegram import Update
from telegram.ext import ContextTypes

_chars_cache = {}


def _resolve_path():
    base = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(base, "data", "personagens_anilist.txt")


def load_characters():
    global _chars_cache

    if _chars_cache:
        return _chars_cache

    path = _resolve_path()
    chars = {}

    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        for line in f:

            line = line.strip()

            if not line:
                continue

            parts = line.split("|")

            if len(parts) < 3:
                continue

            try:
                char_id = int(parts[0])
            except:
                continue

            name = parts[1]
            anime = parts[2]

            image = ""

            chars[char_id] = {
                "id": char_id,
                "name": name,
                "anime": anime,
                "image": image,
            }

    _chars_cache = chars
    return chars


async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.effective_message

    try:

        if not context.args:
            await msg.reply_text("Use:\n/card ID_DO_PERSONAGEM")
            return

        try:
            char_id = int(context.args[0])
        except:
            await msg.reply_text("ID inválido.")
            return

        chars = load_characters()

        char = chars.get(char_id)

        if not char:
            await msg.reply_text("Personagem não encontrado.")
            return

        name = char["name"]
        anime = char["anime"]

        image_url = f"https://img.anili.st/character/{char_id}"

        text = (
            f"🎴 <b>{name}</b>\n"
            f"📺 {anime}\n"
            f"🆔 {char_id}"
        )

        await msg.reply_photo(
            photo=image_url,
            caption=text,
            parse_mode="HTML",
        )

    except Exception as e:
        await msg.reply_text(f"❌ Erro no /card: {e}")
