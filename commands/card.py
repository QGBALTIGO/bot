import html
import logging
import os
import re
import unicodedata
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cards_service import build_cards_final_data, search_characters
from database import (
    get_card_owner_count,
    get_card_total_copies,
    get_user_card_quantity,
)
from utils.gatekeeper import gatekeeper
from utils.runtime_guard import lock_manager, rate_limiter

logger = logging.getLogger(__name__)

CARD_CALLBACK_RATE_LIMIT = int(os.getenv("CARD_CALLBACK_RATE_LIMIT", "4"))
CARD_CALLBACK_RATE_WINDOW_SECONDS = float(
    os.getenv("CARD_CALLBACK_RATE_WINDOW_SECONDS", "3")
)


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


def _normalize(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").strip().casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.split())


def extract_id(text: str) -> Optional[int]:
    match = re.match(r"^\s*(\d+)", text or "")
    return int(match.group(1)) if match else None


def fmt_num(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def find_character(query: str) -> Optional[Dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return None

    data = build_cards_final_data()
    cid = extract_id(query)
    if cid is not None:
        return data["characters_by_id"].get(cid)

    candidates = search_characters(query, limit=100)
    if not candidates:
        return None

    normalized_query = _normalize(query)

    for char in candidates:
        if _normalize(char.get("name")) == normalized_query:
            return char

    for char in candidates:
        if _normalize(char.get("name")).startswith(normalized_query):
            return char

    return candidates[0]


async def _ensure_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    ok, message = await gatekeeper(update, context)
    if ok:
        return True

    if update.effective_message and message:
        await update.effective_message.reply_html(message)
    return False


async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    if not await _ensure_access(update, context):
        return

    if not context.args:
        await message.reply_html(
            "🎴 <b>Card</b>\n\n"
            "Use:\n"
            "<code>/card ID</code>\n"
            "<code>/card Nome</code>\n"
            "<code>/card ID. Nome</code>"
        )
        return

    try:
        query = " ".join(context.args).strip()
        char = find_character(query)

        if not char:
            await message.reply_text("❌ Personagem não encontrado.")
            return

        char_id = int(char["id"])
        name = html.escape(str(char.get("name") or "Sem nome"), quote=False)
        anime = html.escape(str(char.get("anime") or "Obra desconhecida"), quote=False)
        image = str(char.get("image") or "").strip()

        qty = get_user_card_quantity(user.id, char_id)
        emoji = get_dup_emoji(qty)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 Estatísticas", callback_data=f"cardstats:{char_id}")]
        ])

        caption = (
            f"╭─ 🧧 Card <code>#{char_id}</code>\n"
            "│\n"
            f"│ 👤 <b>{name}{emoji}</b>\n"
            f"│ 🎬 {anime}\n"
            "│\n"
            f"╰─ 📦 {qty}x na coleção"
        )

        if image:
            await message.reply_photo(
                photo=image,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            await message.reply_html(caption, reply_markup=keyboard)

    except Exception:
        logger.exception("Falha ao processar /card para user_id=%s", user.id)
        await message.reply_text("❌ Não foi possível carregar esse card agora.")


async def card_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    try:
        ok, _ = await gatekeeper(update, context)
        if not ok:
            await query.answer(
                "Acesso indisponível. Use /start no privado para regularizar.",
                show_alert=True,
            )
            return

        data = query.data or ""
        if not data.startswith("cardstats:"):
            await query.answer()
            return

        allowed = await rate_limiter.allow(
            key=f"cardstats:{user.id}",
            limit=CARD_CALLBACK_RATE_LIMIT,
            window_seconds=CARD_CALLBACK_RATE_WINDOW_SECONDS,
        )
        if not allowed:
            await query.answer(
                "⌛ Aguarde um instante antes de clicar novamente.",
                show_alert=False,
            )
            return

        char_id = int(data.split(":", 1)[1])
        if char_id not in build_cards_final_data()["characters_by_id"]:
            await query.answer("Card não encontrado.", show_alert=True)
            return

        lock = await lock_manager.acquire(f"cardstats:{user.id}:{char_id}")
        try:
            owners = get_card_owner_count(char_id)
            total_copies = get_card_total_copies(char_id)

            stats_message = (
                f"👥 Usuários que possuem: {fmt_num(owners)}\n"
                f"📦 Total de cópias: {fmt_num(total_copies)}"
            )
            await query.answer(stats_message, show_alert=True)
        finally:
            lock.release()

    except Exception:
        logger.exception("Falha no callback de estatísticas de card user_id=%s", user.id)
        try:
            await query.answer("Não foi possível carregar as estatísticas.", show_alert=True)
        except Exception:
            logger.debug("Falha ao responder callback após erro", exc_info=True)
