import os
import re
import unicodedata
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils.runtime_guard import lock_manager, rate_limiter

from database import (
    get_card_owner_count,
    get_card_total_copies,
    get_user_card_quantity,
)

from cards_service import (
    get_character_by_id,
    search_characters,
)

CARD_CALLBACK_RATE_LIMIT = int(os.getenv("CARD_CALLBACK_RATE_LIMIT", "4"))
CARD_CALLBACK_RATE_WINDOW_SECONDS = float(
    os.getenv("CARD_CALLBACK_RATE_WINDOW_SECONDS", "3")
)


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


def _normalize_text(text: Any) -> str:
    text = str(text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def extract_id(text: str) -> Optional[int]:
    m = re.match(r"^\s*(\d+)", str(text or ""))
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


def fmt_num(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def _pick_best_character(query: str) -> Optional[Dict[str, Any]]:
    query = str(query or "").strip()
    if not query:
        return None

    cid = extract_id(query)
    if cid is not None:
        ch = get_character_by_id(cid)
        if ch:
            return ch

    if query.isdigit():
        ch = get_character_by_id(int(query))
        if ch:
            return ch

    results = search_characters(query, limit=25)
    if not results:
        return None

    nq = _normalize_text(query)

    def score(item: Dict[str, Any]):
        name = _normalize_text(item.get("name"))
        anime = _normalize_text(item.get("anime"))
        hay = f"{name} {anime}"

        if name == nq:
            return (0, len(name), len(anime))
        if hay == nq:
            return (1, len(name), len(anime))
        if name.startswith(nq):
            return (2, len(name), len(anime))
        if hay.startswith(nq):
            return (3, len(name), len(anime))
        if nq in name:
            return (4, len(name), len(anime))
        if nq in hay:
            return (5, len(name), len(anime))
        return (6, len(name), len(anime))

    results.sort(key=score)
    return results[0]


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
        char = _pick_best_character(query)

        if not char:
            await update.message.reply_text("❌ Personagem não encontrado.")
            return

        user_id = update.effective_user.id
        char_id = int(char["id"])
        name = str(char.get("name") or "Sem nome")
        anime = str(char.get("anime") or "Obra desconhecida")
        image = str(char.get("image") or "").strip()

        qty = int(get_user_card_quantity(user_id, char_id) or 0)
        emoji = get_dup_emoji(qty)

        total_rolls = 12483  # preview por enquanto
        owners = int(get_card_owner_count(char_id) or 0)
        total_copies = int(get_card_total_copies(char_id) or 0)

        caption = (
            f"╭─ 🧧 Card <code>#{char_id}</code>\n"
            f"│\n"
            f"│ 👤 <b>{name}{emoji}</b>\n"
            f"│ 🎬 {anime}\n"
            f"│\n"
            f"╰─ 📦 {qty}x na coleção"
        )

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔎", callback_data=f"cardstats:{char_id}")]]
        )

        if image:
            await update.message.reply_photo(
                photo=image,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            await update.message.reply_html(
                caption,
                reply_markup=keyboard,
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
            await q.answer(
                "⌛ Aguarde um instante antes de clicar novamente.",
                show_alert=False,
            )
            return

        char_id = int(data.split(":", 1)[1])

        lock = await lock_manager.acquire(f"cardstats:{user.id}:{char_id}")
        try:
            total_rolls = 12483  # preview por enquanto
            owners = int(get_card_owner_count(char_id) or 0)
            total_copies = int(get_card_total_copies(char_id) or 0)

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
