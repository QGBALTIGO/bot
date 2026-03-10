import asyncio
import time

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from cards_service import get_character_by_id


ANTIFLOOD = 2.0
_locks = {}
_last = {}


# =========================================================
# LOCK
# =========================================================

def get_lock(uid):

    if uid not in _locks:
        _locks[uid] = asyncio.Lock()

    return _locks[uid]


def antiflood(uid):

    now = time.time()
    last = _last.get(uid, 0)

    if now - last < ANTIFLOOD:
        return False

    _last[uid] = now
    return True


# =========================================================
# HELPERS
# =========================================================

def is_admin(user_id: int):

    try:
        admins = db.get_admins()
        return user_id in admins
    except:
        return False


def get_level(user_id: int):

    try:
        row = db.get_progress_row(user_id) or {}
        return int(row.get("level") or 1)
    except:
        return 1


def get_collection_total(user_id: int):

    try:
        cards = db.get_user_card_collection(user_id) or []
        return len(cards)
    except:
        return 0


def get_favorite(user_id: int):

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
            "id": fav_id,
            "name": ch["name"],
            "anime": ch["anime"],
            "image": ch["image"]
        }

    except:
        return None


# =========================================================
# PERFIL
# =========================================================

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_user or not update.message:
        return

    viewer = update.effective_user
    viewer_id = viewer.id

    if not antiflood(viewer_id):
        return

    db.create_or_get_user(viewer_id)

    lock = get_lock(viewer_id)

    async with lock:

        target_id = viewer_id

        if context.args:

            arg = context.args[0].strip()

            if arg.isdigit():
                target_id = int(arg)
            else:
                await update.message.reply_html(
                    "❌ <b>Usuário não encontrado</b>"
                )
                return

        row = db.get_user_status(target_id)

        if not row:
            await update.message.reply_html(
                "❌ <b>Usuário não encontrado</b>"
            )
            return

        name = viewer.full_name if target_id == viewer_id else f"User {target_id}"

        role = "Admin" if is_admin(target_id) else "User"

        coins = int(row.get("coins") or 0)
        level = get_level(target_id)
        total = get_collection_total(target_id)

        fav = get_favorite(target_id)

        texto = (
            "🇧🇷 <b>PERFIL DO USUÁRIO</b>\n\n"
            f"👤 | <i>{role}</i> <b>{name}</b>\n\n"
            f"📚 | <i>Coleção:</i> <b>{total}</b>\n"
            f"🪙 | <i>Coins:</i> <b>{coins}</b>\n"
            f"⭐️ | <i>Nível:</i> <b>{level}</b>\n\n"
            "❤️ <b>Favorito:</b>\n"
        )

        if fav:

            texto += (
                f"🧧 <b>{fav['name']}</b>"
            )

            await update.message.reply_photo(
                fav["image"],
                caption=texto,
                parse_mode="HTML"
            )

        else:

            texto += "— Nenhum favorito"

            await update.message.reply_html(texto)
