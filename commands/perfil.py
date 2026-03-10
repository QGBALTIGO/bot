import asyncio
import os
import time

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from cards_service import get_character_by_id
from utils.gatekeeper import gatekeeper


ANTIFLOOD = 2.0
_profile_locks = {}
_last_profile = {}


# =========================================================
# ADMINS
# =========================================================

def _load_admins() -> set[int]:
    raw = os.getenv("ADMINS", "").strip()
    if not raw:
        return set()

    out = set()

    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except Exception:
            pass

    return out


ADMINS_SET = _load_admins()


def is_admin(user_id: int) -> bool:
    return int(user_id) in ADMINS_SET


# =========================================================
# LOCK / ANTIFLOOD
# =========================================================

def _get_profile_lock(user_id: int) -> asyncio.Lock:
    lock = _profile_locks.get(int(user_id))
    if lock is None:
        lock = asyncio.Lock()
        _profile_locks[int(user_id)] = lock
    return lock


def _anti_spam(user_id: int) -> bool:
    now = time.time()
    last = _last_profile.get(int(user_id), 0.0)

    if now - last < ANTIFLOOD:
        return False

    _last_profile[int(user_id)] = now
    return True


# =========================================================
# HELPERS
# =========================================================

def _get_level(user_id: int) -> int:
    try:
        row = db.get_progress_row(int(user_id)) or {}
        return int(row.get("level") or 1)
    except Exception:
        return 1


def _get_collection_total(user_id: int) -> int:
    try:
        cards = db.get_user_card_collection(int(user_id)) or []
        return len(cards)
    except Exception:
        return 0


def _get_favorite(user_id: int):
    try:
        profile = db.get_collection_profile(int(user_id))
        if not profile:
            return None

        fav_id = profile.get("favorite_character_id")
        if not fav_id:
            return None

        ch = get_character_by_id(int(fav_id))
        if not ch:
            return None

        return {
            "id": int(fav_id),
            "name": str(ch.get("name") or "").strip(),
            "anime": str(ch.get("anime") or "").strip(),
            "image": str(ch.get("image") or "").strip(),
        }
    except Exception:
        return None


def _resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    viewer = update.effective_user
    if not viewer:
        return None

    # perfil próprio
    if not context.args:
        db.create_or_get_user(int(viewer.id))
        db.touch_user_identity(
            int(viewer.id),
            viewer.username or "",
            viewer.full_name or "",
        )

        row = db.get_user_status(int(viewer.id)) or {}
        row = dict(row)
        row["user_id"] = int(viewer.id)
        row["display_name"] = (viewer.full_name or viewer.first_name or "User").strip()
        return row

    # por ID
    raw = str(context.args[0] or "").strip()
    if not raw.isdigit():
        return None

    target_id = int(raw)
    row = db.get_user_status(target_id)
    if not row:
        return None

    row = dict(row)
    row["user_id"] = target_id

    full_name = str(row.get("full_name") or "").strip()
    username = str(row.get("username") or "").strip()

    if full_name:
        row["display_name"] = full_name
    elif username:
        row["display_name"] = f"@{username}"
    else:
        row["display_name"] = f"User {target_id}"

    return row


def _build_profile_text(target: dict, level: int, total_collection: int, favorite) -> str:
    user_id = int(target["user_id"])
    display_name = str(target.get("display_name") or "User").strip()
    coins = int(target.get("coins") or 0)
    role = "Admin" if is_admin(user_id) else "User"

    text = (
        "🇧🇷 <b>PERFIL DO USUÁRIO</b>\n\n"
        f"👤 | <i>{role}:</i> <b>{display_name}</b>\n\n"
        f"📚 | <i>Coleção:</i> <b>{total_collection}</b>\n"
        f"🪙 | <i>Coins:</i> <b>{coins}</b>\n"
        f"⭐️ | <i>Nível:</i> <b>{level}</b>\n\n"
        "❤️ <b>Favorito:</b>\n"
    )

    if favorite:
        text += f"🧧 <b>{favorite['name']}</b>"
    else:
        text += "— Nenhum favorito"

    return text


# =========================================================
# /perfil
# =========================================================

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    viewer_id = int(update.effective_user.id)

    if not _anti_spam(viewer_id):
        return

    lock = _get_profile_lock(viewer_id)

    async with lock:
        target = _resolve_target(update, context)

        if not target:
            await update.message.reply_html(
                "❌ <b>Usuário não encontrado</b>\n\n"
                "Use:\n"
                "<code>/perfil</code>\n"
                "ou\n"
                "<code>/perfil 123456789</code>"
            )
            return

        target_id = int(target["user_id"])

        level = _get_level(target_id)
        total_collection = _get_collection_total(target_id)
        favorite = _get_favorite(target_id)

        text = _build_profile_text(
            target=target,
            level=level,
            total_collection=total_collection,
            favorite=favorite,
        )

        # sem favorito = sem foto
        if favorite and favorite.get("image"):
            try:
                await update.message.reply_photo(
                    photo=favorite["image"],
                    caption=text,
                    parse_mode="HTML",
                )
                return
            except Exception:
                pass

        await update.message.reply_html(text)
