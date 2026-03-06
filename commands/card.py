import json
import os
import re
from typing import Dict, Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_PATHS = [
    os.path.join(BASE_DIR, "data", "personagens_anilist.txt"),
    os.path.join(BASE_DIR, "dados", "personagens_anilist.txt"),
]

_chars_cache: Optional[Dict[int, Dict[str, Any]]] = None


# ==================================================
# DUPLICATE EMOJI
# ==================================================

def get_dup_emoji(qty: int) -> str:
    if qty >= 20:
        return " 👑"
    elif qty >= 15:
        return " 🌟"
    elif qty >= 10:
        return " ⭐"
    elif qty >= 5:
        return " 💫"
    elif qty >= 2:
        return " ✨"
    return ""


# ==================================================
# DATA LOADER
# ==================================================

def _resolve_path():
    for p in DATA_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("personagens_anilist.txt não encontrado")


def load_characters():

    global _chars_cache

    if _chars_cache:
        return _chars_cache

    path = _resolve_path()

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        items = raw.get("items", [])
    else:
        items = raw

    chars = {}

    for anime in items:

        anime_name = anime.get("anime")

        for c in anime.get("characters", []):

            try:
                cid = int(c["id"])
            except:
                continue

            chars[cid] = {
                "id": cid,
                "name": c["name"],
                "image": c.get("image"),
                "anime": anime_name
            }

    _chars_cache = chars
    return chars


# ==================================================
# SEARCH
# ==================================================

def find_character_by_name(name: str):

    name = name.lower()

    for c in load_characters().values():

        if name in c["name"].lower():
            return c

    return None


def extract_id(text: str):

    m = re.match(r"^\s*(\d+)", text)

    if m:
        return int(m.group(1))

    return None


# ==================================================
# PREVIEW DATA (GACHA FUTURO)
# ==================================================

def get_preview_stats():

    return {
        "rolls": 12483,
        "owners": 1972,
        "copies": 3615
    }


def get_user_qty(user_id, char_id):

    return 1  # temporário


# ==================================================
# /CARD
# ==================================================

async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    if not context.args:

        await update.message.reply_html(
            "🎴 <b>Card</b>\n\n"
            "<code>/card ID</code>\n"
            "<code>/card Nome</code>"
        )
        return

    query = " ".join(context.args)

    chars = load_characters()

    char = None

    cid = extract_id(query)

    if cid:
        char = chars.get(cid)

    elif query.isdigit():
        char = chars.get(int(query))

    else:
        char = find_character_by_name(query)

    if not char:

        await update.message.reply_text("❌ Personagem não encontrado.")
        return

    user_id = update.effective_user.id

    char_id = char["id"]
    name = char["name"]
    anime = char["anime"]
    image = char["image"]

    qty = get_user_qty(user_id, char_id)

    emoji = get_dup_emoji(qty)

    stats = get_preview_stats()

    rolls = f"{stats['rolls']:,}".replace(",", ".")
    owners = f"{stats['owners']:,}".replace(",", ".")
    copies = f"{stats['copies']:,}".replace(",", ".")

    caption = (
        f"╭─ 🎴 Card <code>#{char_id}</code>\n"
        f"│\n"
        f"│ 👤 <b>{name}{emoji}</b>\n"
        f"│ 🎬 {anime}\n"
        f"│\n"
        f"╰─ 📦 {qty}x na coleção"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 Estatísticas do Card",
                callback_data=f"cardstats:{rolls}:{owners}:{copies}"
            )
        ]
    ])

    await update.message.reply_photo(
        photo=image,
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ==================================================
# CALLBACK POPUP
# ==================================================

async def card_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query

    if not q:
        return

    try:

        _, rolls, owners, copies = q.data.split(":")

        msg = (
            f"🎰 Giros totais: {rolls}\n"
            f"👥 Usuários que possuem: {owners}\n"
            f"📦 Total de cópias: {copies}"
        )

        await q.answer(msg, show_alert=True)

    except:

        await q.answer()
