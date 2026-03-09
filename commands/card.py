import json
import os
import re
from typing import Dict, Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.runtime_guard import lock_manager, rate_limiter

from database import (
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


CARD_CALLBACK_RATE_LIMIT = int(os.getenv("CARD_CALLBACK_RATE_LIMIT", "4"))
CARD_CALLBACK_RATE_WINDOW_SECONDS = float(os.getenv("CARD_CALLBACK_RATE_WINDOW_SECONDS", "3"))



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


def _resolve_path():
    for p in DATA_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("personagens_anilist.txt não encontrado")


def load_characters():
    global _chars_cache

    if _chars_cache is not None:
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
        if not isinstance(anime, dict):
            continue

        anime_name = anime.get("anime") or "Obra desconhecida"

        for c in anime.get("characters", []):
            if not isinstance(c, dict):
                continue

            try:
                cid = int(c["id"])
            except Exception:
                continue

            chars[cid] = {
                "id": cid,
                "name": c.get("name", "Sem nome"),
                "image": c.get("image"),
                "anime": anime_name,
            }

    _chars_cache = chars
    return chars


def find_character_by_name(name: str):
    name = name.lower().strip()

    chars = load_characters()

    for c in chars.values():
        if c["name"].lower() == name:
            return c

    for c in chars.values():
        if c["name"].lower().startswith(name):
            return c

    for c in chars.values():
        if name in c["name"].lower():
            return c

    return None


def extract_id(text: str):
    m = re.match(r"^\s*(\d+)", text)
    if m:
        return int(m.group(1))
    return None


def fmt_num(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    if not context.args:
        await update.message.reply_html(
            "🎴 <b>Card</b>\n\n"
            "Use:\n"
            "<code>/card ID</code>\n"
            "<code>/card Nome</code>\n"
            "<code>/card ID. Nome</code>"
        )
        return

    try:
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
            await update.message.reply_text("❌ Personagem não encontrado.")
            return

        user_id = update.effective_user.id
        char_id = int(char["id"])
        name = str(char["name"])
        anime = str(char["anime"])
        image = char.get("image")

        qty = get_user_card_quantity(user_id, char_id)
        emoji = get_dup_emoji(qty)

        total_rolls = 12483  # preview por enquanto
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

        popup_text = (
            f"🎰 Giros totais: {fmt_num(total_rolls)}\n"
            f"👥 Usuários que possuem: {fmt_num(owners)}\n"
            f"📦 Total de cópias: {fmt_num(total_copies)}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎", callback_data=f"cardstats:{char_id}")]
        ])

        # salva o texto do popup no contexto do callback_data simples? não.
        # então recalculamos no callback pelo char_id.
        if image:
            await update.message.reply_photo(
                photo=image,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_html(
                caption,
                reply_markup=keyboard
            )

    except Exception as e:
        await update.message.reply_text(f"❌ Erro no /card: {e}")


async def card_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    user = update.effective_user
    if not user:
        await q.answer()
        return

    try:
        data = q.data or ""
        if not data.startswith("cardstats:"):
            await q.answer()
            return

        allowed = await rate_limiter.allow(
            key=f"cardstats:{user.id}",
            limit=CARD_CALLBACK_RATE_LIMIT,
            window_seconds=CARD_CALLBACK_RATE_WINDOW_SECONDS,
        )
        if not allowed:
            await q.answer("⌛ Aguarde um instante antes de clicar novamente.", show_alert=False)
            return

        char_id = int(data.split(":")[1])

        lock = await lock_manager.acquire(f"cardstats:{user.id}:{char_id}")
        try:
            total_rolls = 12483  # preview por enquanto
            owners = get_card_owner_count(char_id)
            total_copies = get_card_total_copies(char_id)

            msg = (
                f"🎰 Giros totais: {fmt_num(total_rolls)}\n"
                f"👥 Usuários que possuem: {fmt_num(owners)}\n"
                f"📦 Total de cópias: {fmt_num(total_copies)}"
            )

            await q.answer(msg, show_alert=True)
        finally:
            lock.release()

    except Exception as e:
        try:
            await q.answer(f"Erro: {e}", show_alert=True)
        except Exception:
            pass
