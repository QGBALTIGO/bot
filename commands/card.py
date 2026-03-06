import json
import os
from typing import Dict, Any, Optional

from telegram import Update
from telegram.ext import ContextTypes

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_PATHS = [
    os.path.join(BASE_DIR, "data", "personagens_anilist.txt"),
    os.path.join(BASE_DIR, "dados", "personagens_anilist.txt"),
]

_characters_cache: Optional[Dict[int, Dict[str, Any]]] = None


def _resolve_data_path() -> str:
    for path in DATA_PATHS:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"Arquivo personagens_anilist.txt não encontrado. Testados: {DATA_PATHS}"
    )


def load_characters() -> Dict[int, Dict[str, Any]]:
    global _characters_cache

    if _characters_cache is not None:
        return _characters_cache

    path = _resolve_data_path()

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        items = raw.get("items", [])
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    chars: Dict[int, Dict[str, Any]] = {}

    for anime in items:
        if not isinstance(anime, dict):
            continue

        anime_name = str(anime.get("anime") or "").strip()
        chars_raw = anime.get("characters", [])

        if not isinstance(chars_raw, list):
            continue

        for c in chars_raw:
            if not isinstance(c, dict):
                continue

            try:
                cid = int(c.get("id"))
            except Exception:
                continue

            name = str(c.get("name") or "").strip()
            image = str(c.get("image") or "").strip()

            if not name:
                continue

            chars[cid] = {
                "id": cid,
                "name": name,
                "image": image,
                "anime": anime_name,
            }

    _characters_cache = chars
    return chars


def find_character_by_name(query: str) -> Optional[Dict[str, Any]]:
    q = str(query or "").strip().lower()
    if not q:
        return None

    chars = load_characters()

    # exato primeiro
    for c in chars.values():
        if c["name"].lower() == q:
            return c

    # parcial depois
    for c in chars.values():
        if q in c["name"].lower():
            return c

    return None


async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not context.args:
        await update.message.reply_html(
            "👤 <b>Card</b>\n\n"
            "Use:\n"
            "<code>/card ID</code>\n"
            "<code>/card Nome do personagem</code>\n\n"
            "Exemplos:\n"
            "<code>/card 70683</code>\n"
            "<code>/card Vassago Casals</code>"
        )
        return

    try:
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
        anime = character["anime"] or "Obra desconhecida"
        image = character["image"]

        caption = (
            f"🪪 Card #{char_id}\n\n"
            f"👤 {name}\n"
            f"🎬 {anime}"
        )

        if image:
            await update.message.reply_photo(
                photo=image,
                caption=caption
            )
        else:
            await update.message.reply_text(caption)

    except Exception as e:
        await update.message.reply_text(f"❌ Erro no /card: {e}")
