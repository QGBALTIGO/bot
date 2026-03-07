import json
import os
import re
from typing import Dict, Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper

from database import (
    create_or_get_user,
    get_user_card_quantity,
    get_card_owner_count,
    get_card_total_copies,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_PATHS = [
    os.path.join(BASE_DIR, "data", "personagens_anilist.txt"),
    os.path.join(BASE_DIR, "dados", "personagens_anilist.txt"),
]

_chars_cache: Optional[Dict[int, Dict[str, Any]]] = None


def get_dup_emoji(qty: int) -> str:
    if qty >= 20:
        return " 👑"
    if qty >= 15:
        return " 🌟"
    if qty >= 10:
        return " ⭐"
    if qty >= 5:
        return " 💫"
    if qty >= 2:
        return " ✨"
    return ""


def _resolve_path() -> str:
    for p in DATA_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"personagens_anilist.txt não encontrado. Testados: {DATA_PATHS}")


def load_characters() -> Dict[int, Dict[str, Any]]:
    global _chars_cache

    if _chars_cache is not None:
        return _chars_cache

    path = _resolve_path()

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

        anime_name = str(anime.get("anime") or "Obra desconhecida").strip()

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

    _chars_cache = chars
    return chars


def find_character_by_name(name: str) -> Optional[Dict[str, Any]]:
    query = str(name or "").strip().lower()
    if not query:
        return None

    chars = load_characters()

    for c in chars.values():
        if c["name"].lower() == query:
            return c

    for c in chars.values():
        if c["name"].lower().startswith(query):
            return c

    for c in chars.values():
        if query in c["name"].lower():
            return c

    return None


def extract_id(text: str) -> Optional[int]:
    m = re.match(r"^\s*(\d+)", str(text or ""))
    if m:
        return int(m.group(1))
    return None


def fmt_num(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    try:
        ok, bloqueio = await gatekeeper(update, context)
        if not ok:
            if msg and bloqueio:
                await msg.reply_html(bloqueio)
            return

        if not msg or not update.effective_user:
            return

        user = update.effective_user
        create_or_get_user(user.id, user.first_name)

        if not context.args:
            await msg.reply_html(
                "🎴 <b>Card</b>\n\n"
                "Use:\n"
                "<code>/card ID</code>\n"
                "<code>/card Nome</code>\n"
                "<code>/card ID. Nome</code>"
            )
            return

        query = " ".join(context.args).strip()
        chars = load_characters()

        char = None
        cid = extract_id(query)

        if cid is not None:
            char = chars.get(cid)
        elif query.isdigit():
            char = chars.get(int(query))
        else:
            char = find_character_by_name(query)

        if not char:
            await msg.reply_text("❌ Personagem não encontrado.")
            return

        char_id = int(char["id"])
        name = str(char["name"])
        anime = str(char["anime"])
        image = str(char.get("image") or "").strip()

        qty = get_user_card_quantity(user.id, char_id)
        emoji = get_dup_emoji(qty)

        total_rolls = 12483
        owners = get_card_owner_count(char_id)
        total_copies = get_card_total_copies(char_id)

        caption = (
            f"╭─ 🧧 Card <code>#{char_id}</code>\n"
            f"│\n"
            f"│ 👤 <b>{name}{emoji}</b>\n"
            f"│ 🎬 {anime}\n"
            f"│\n"
            f"╰─ 📦 {qty}x na coleção"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎", callback_data=f"cardstats:{char_id}")]
        ])

        if image:
            await msg.reply_photo(
                photo=image,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            await msg.reply_html(
                caption,
                reply_markup=keyboard,
            )

    except Exception as e:
        if msg:
            await msg.reply_text(f"❌ Erro no /card: {e}")


async def card_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    try:
        data = q.data or ""
        if not data.startswith("cardstats:"):
            await q.answer()
            return

        char_id = int(data.split(":")[1])

        total_rolls = 12483
        owners = get_card_owner_count(char_id)
        total_copies = get_card_total_copies(char_id)

        popup = (
            f"🎰 Giros totais: {fmt_num(total_rolls)}\n"
            f"👥 Usuários que possuem: {fmt_num(owners)}\n"
            f"📦 Total de cópias: {fmt_num(total_copies)}"
        )

        await q.answer(popup, show_alert=True)

    except Exception as e:
        try:
            await q.answer(f"Erro: {e}", show_alert=True)
        except Exception:
            pass
