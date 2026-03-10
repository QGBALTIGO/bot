import math
import asyncio
import time

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db
from services.cards_service import get_character_by_id


ITENS_POR_PAGINA = 10
ANTIFLOOD_SECONDS = 1.2


# =========================
# LOCKS
# =========================

_user_locks = {}
_last_click = {}


def get_lock(uid: int):
    lock = _user_locks.get(uid)
    if not lock:
        lock = asyncio.Lock()
        _user_locks[uid] = lock
    return lock


def antiflood(uid: int) -> bool:
    now = time.time()
    last = _last_click.get(uid, 0)

    if now - last < ANTIFLOOD_SECONDS:
        return False

    _last_click[uid] = now
    return True


# =========================
# DUPLICATE EMOJI
# =========================

def duplicate_emoji(qty: int) -> str:
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


# =========================
# PAGINATION
# =========================

def build_keyboard(page: int, total_pages: int, owner_id: int):

    if total_pages <= 1:
        return None

    buttons = []

    if total_pages >= 4 and page > 3:
        buttons.append(
            InlineKeyboardButton("⏪️", callback_data=f"colecao:{owner_id}:{max(1,page-3)}")
        )

    if page > 1:
        buttons.append(
            InlineKeyboardButton("◀️", callback_data=f"colecao:{owner_id}:{page-1}")
        )

    buttons.append(
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop")
    )

    if page < total_pages:
        buttons.append(
            InlineKeyboardButton("▶️", callback_data=f"colecao:{owner_id}:{page+1}")
        )

    if total_pages >= 4 and page <= total_pages - 3:
        buttons.append(
            InlineKeyboardButton("⏩️", callback_data=f"colecao:{owner_id}:{min(total_pages,page+3)}")
        )

    return InlineKeyboardMarkup([buttons])


# =========================
# FORMAT TEXT
# =========================

def build_text(user_id: int, page: int):

    cards = db.get_user_card_collection(user_id) or []

    total = len(cards)
    total_pages = max(1, math.ceil(total / ITENS_POR_PAGINA))

    page = max(1, min(page, total_pages))

    start = (page - 1) * ITENS_POR_PAGINA
    end = start + ITENS_POR_PAGINA

    page_cards = cards[start:end]

    profile = db.get_collection_profile(user_id)
    fav_id = profile.get("favorite_character_id") if profile else None

    text = (
        "📚 <b>Minha Coleção</b>\n\n"
        f"📦 <i>Total:</i> <b>{total}</b>\n"
        f"📖 <i>Página:</i> <b>{page}/{total_pages}</b>\n\n"
    )

    # =========================
    # FAVORITO
    # =========================

    if fav_id:

        fav = next((c for c in cards if c["character_id"] == fav_id), None)

        if fav:
            data = get_character_by_id(fav_id)

            name = data["name"]
            anime = data["anime"]
            emoji = duplicate_emoji(fav["quantity"])

            text += f"❤️ <code>{fav_id}</code>. <b>{name}</b>{emoji} — <i>{anime}</i>\n\n"

    # =========================
    # LISTA
    # =========================

    for row in page_cards:

        cid = row["character_id"]
        qty = row["quantity"]

        if cid == fav_id:
            continue

        data = get_character_by_id(cid)

        name = data["name"]
        anime = data["anime"]

        emoji = duplicate_emoji(qty)

        text += f"🧧 <code>{cid}</code>. <b>{name}</b>{emoji} — <i>{anime}</i>\n"

    return text, total_pages, page


# =========================
# SEND
# =========================

async def send_collection(update, context, page: int, edit=False):

    user = update.effective_user
    uid = user.id

    text, total_pages, page = build_text(uid, page)

    kb = build_keyboard(page, total_pages, uid)

    if edit and update.callback_query:

        msg = update.callback_query.message

        try:
            await msg.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=kb
            )
        except:
            pass

    else:

        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=kb
        )


# =========================
# COMMAND
# =========================

async def colecao(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    uid = user.id

    lock = get_lock(uid)

    async with lock:

        await send_collection(update, context, 1)


# =========================
# CALLBACK
# =========================

async def colecao_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query

    if not q:
        return

    if q.data == "noop":
        await q.answer()
        return

    uid = q.from_user.id

    if not antiflood(uid):
        await q.answer("Calma 🙂")
        return

    try:

        _, owner_id, page = q.data.split(":")
        owner_id = int(owner_id)
        page = int(page)

    except:
        await q.answer("Erro.")
        return

    if uid != owner_id:
        await q.answer("Essa coleção não é sua.", show_alert=True)
        return

    await q.answer()

    lock = get_lock(uid)

    async with lock:

        await send_collection(update, context, page, edit=True)
