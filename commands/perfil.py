import asyncio
import time
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from cards_service import get_character_by_id


DEFAULT_PROFILE_COVER = "https://photo.chelpbot.me/AgACAgEAAxkBZxImgmmnL7d9nYjTFd0KNTThxz9KJ6uCAAK7C2sbxrE5RXkd0eZ9Eoc4AQADAgADeQADOgQ/photo.jpg"

ANTIFLOOD_SECONDS = 2.0
_profile_locks = {}
_last_profile_click = {}


def get_profile_lock(user_id: int) -> asyncio.Lock:
    lock = _profile_locks.get(user_id)
    if not lock:
        lock = asyncio.Lock()
        _profile_locks[user_id] = lock
    return lock


def profile_antiflood(user_id: int) -> bool:
    now = time.time()
    last = _last_profile_click.get(user_id, 0.0)

    if now - last < ANTIFLOOD_SECONDS:
        return False

    _last_profile_click[user_id] = now
    return True


def _safe_name(user_row: dict) -> str:
    full_name = str(user_row.get("full_name") or "").strip()
    username = str(user_row.get("username") or "").strip()

    if full_name:
        return full_name
    if username:
        return f"@{username}"
    return "User"


def _get_level(user_id: int) -> int:
    try:
        row = db.get_progress_row(user_id) or {}
        return int(row.get("level") or 1)
    except Exception:
        return 1


def _get_collection_total(user_id: int) -> int:
    try:
        cards = db.get_user_card_collection(user_id) or []
        return len(cards)
    except Exception:
        return 0


def _get_favorite_data(user_id: int):
    try:
        profile = db.get_collection_profile(user_id)
        if not profile:
            return None

        fav_id = profile.get("favorite_character_id")
        if not fav_id:
            return None

        ch = get_character_by_id(int(fav_id))
        if not ch:
            return None

        return {
            "character_id": int(fav_id),
            "name": str(ch.get("name") or "").strip(),
            "anime": str(ch.get("anime") or "").strip(),
            "image": str(ch.get("image") or "").strip(),
        }
    except Exception:
        return None


def _build_profile_text(user_row: dict, level: int, total_collection: int, favorite: Optional[dict]) -> str:
    user_id = int(user_row["user_id"])
    display_name = _safe_name(user_row)
    coins = int(user_row.get("coins") or 0)

    text = (
        "🎴 <b>PERFIL DO USUÁRIO</b>\n\n"
        f"👤 <b>{display_name}</b>\n"
        f"🆔 <code>{user_id}</code>\n\n"
        f"📚 <i>Coleção:</i> <b>{total_collection}</b>\n"
        f"🪙 <i>Coins:</i> <b>{coins}</b>\n"
        f"⭐ <i>Nível:</i> <b>{level}</b>\n\n"
        "❤️ <i>Favorito:</i>\n"
    )

    if favorite:
        text += (
            f"🧧 <code>{favorite['character_id']}</code>. "
            f"<b>{favorite['name']}</b>"
        )
        if favorite.get("anime"):
            text += f" — <i>{favorite['anime']}</i>"
    else:
        text += "— Nenhum favorito"

    return text


def _resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    viewer = update.effective_user
    if not viewer:
        return None

    if not context.args:
        return db.get_user_status(viewer.id) | {"user_id": viewer.id} if db.get_user_status(viewer.id) else {"user_id": viewer.id, "full_name": viewer.full_name or "", "username": viewer.username or "", "coins": 0}

    raw = str(context.args[0]).strip()

    if not raw.isdigit():
        return None

    target_id = int(raw)
    row = db.get_user_status(target_id)

    if row:
        row = dict(row)
        row["user_id"] = target_id
        return row

    return None


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    viewer_id = update.effective_user.id

    if not profile_antiflood(viewer_id):
        return

    db.create_or_get_user(viewer_id)
    db.touch_user_identity(
        viewer_id,
        update.effective_user.username or "",
        update.effective_user.full_name or "",
    )

    lock = get_profile_lock(viewer_id)

    async with lock:
        target = _resolve_target_user(update, context)

        if not target:
            await update.message.reply_html(
                "❌ <b>Usuário não encontrado.</b>\n\n"
                "Use:\n"
                "<code>/perfil</code>\n"
                "ou\n"
                "<code>/perfil 123456789</code>"
            )
            return

        target_id = int(target["user_id"])

        level = _get_level(target_id)
        total_collection = _get_collection_total(target_id)
        favorite = _get_favorite_data(target_id)

        text = _build_profile_text(target, level, total_collection, favorite)

        photo = DEFAULT_PROFILE_COVER
        if favorite and favorite.get("image"):
            photo = favorite["image"]

        try:
            await update.message.reply_photo(
                photo=photo,
                caption=text,
                parse_mode="HTML",
            )
        except Exception:
            await update.message.reply_html(text)
