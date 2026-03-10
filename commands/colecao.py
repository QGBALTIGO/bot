import asyncio
import math
import time

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import ContextTypes

import database as db
from cards_service import build_cards_final_data, find_anime


# =========================================================
# CONFIG
# =========================================================

ITENS_POR_PAGINA = 10
ANTIFLOOD = 1.2

DEFAULT_COVER = "https://photo.chelpbot.me/AgACAgEAAxkBZxImgmmnL7d9nYjTFd0KNTThxz9KJ6uCAAK7C2sbxrE5RXkd0eZ9Eoc4AQADAgADeQADOgQ/photo.jpg"

CACHE_TTL = 20


# =========================================================
# CACHE / LOCKS
# =========================================================

_locks = {}
_last_click = {}
_cache = {}
_cards_cache = None


def get_lock(uid):
    if uid not in _locks:
        _locks[uid] = asyncio.Lock()
    return _locks[uid]


def antiflood(uid):
    now = time.time()
    last = _last_click.get(uid, 0)

    if now - last < ANTIFLOOD:
        return False

    _last_click[uid] = now
    return True


def cards_data():
    global _cards_cache

    if _cards_cache is None:
        _cards_cache = build_cards_final_data()

    return _cards_cache


def get_cache(uid):
    data = _cache.get(uid)

    if not data:
        return None

    ts, cards = data

    if time.time() - ts > CACHE_TTL:
        return None

    return cards


def set_cache(uid, cards):
    _cache[uid] = (time.time(), cards)


# =========================================================
# UTILS
# =========================================================

def duplicate_emoji(qty):

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


def get_user_cards(uid):

    cached = get_cache(uid)
    if cached:
        return cached

    raw = db.get_user_card_collection(uid) or []

    data = cards_data()
    chars = data["characters_by_id"]

    out = []

    for r in raw:

        cid = int(r["character_id"])
        qty = int(r["quantity"])

        ch = chars.get(cid)

        if not ch:
            continue

        out.append({
            "character_id": cid,
            "quantity": qty,
            "name": ch["name"],
            "anime": ch["anime"],
            "anime_id": ch["anime_id"],
            "image": ch["image"]
        })

    out.sort(
        key=lambda x: (
            x["anime"].lower(),
            x["name"].lower(),
            x["character_id"]
        )
    )

    set_cache(uid, out)

    return out


def get_favorite(uid):

    try:
        prof = db.get_collection_profile(uid)
        return prof.get("favorite_character_id")
    except:
        return None


# =========================================================
# PAGINATION
# =========================================================

def paginate(items, page):

    total = len(items)
    total_pages = max(1, math.ceil(total / ITENS_POR_PAGINA))

    page = max(1, min(page, total_pages))

    start = (page - 1) * ITENS_POR_PAGINA
    end = start + ITENS_POR_PAGINA

    return items[start:end], total, total_pages, page


# =========================================================
# KEYBOARDS
# =========================================================

def build_keyboard(prefix, page, total_pages, uid, extra=None):

    if total_pages <= 1:
        return None

    btn = []

    if page > 1:
        btn.append(
            InlineKeyboardButton(
                "◀️",
                callback_data=f"{prefix}:{uid}:{extra}:{page-1}" if extra else f"{prefix}:{uid}:{page-1}"
            )
        )

    btn.append(
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop")
    )

    if page < total_pages:
        btn.append(
            InlineKeyboardButton(
                "▶️",
                callback_data=f"{prefix}:{uid}:{extra}:{page+1}" if extra else f"{prefix}:{uid}:{page+1}"
            )
        )

    return InlineKeyboardMarkup([btn])


# =========================================================
# TEXT BUILDERS
# =========================================================

def build_collection_text(uid, cards, page):

    items, total, total_pages, page = paginate(cards, page)

    fav = get_favorite(uid)

    text = (
        "📚 <b>Minha Coleção</b>\n\n"
        f"📦 <i>Total:</i> <b>{total}</b>\n"
        f"📖 <i>Página:</i> <b>{page}/{total_pages}</b>\n\n"
    )

    if fav:

        for c in cards:
            if c["character_id"] == fav:

                emoji = duplicate_emoji(c["quantity"])

                text += (
                    f"❤️ <code>{fav}</code>. "
                    f"<b>{c['name']}</b>{emoji} — "
                    f"<i>{c['anime']}</i>\n\n"
                )
                break

    for c in items:

        cid = c["character_id"]

        if cid == fav:
            continue

        emoji = duplicate_emoji(c["quantity"])

        text += (
            f"🧧 <code>{cid}</code>. "
            f"<b>{c['name']}</b>{emoji} — "
            f"<i>{c['anime']}</i>\n"
        )

    return text, total_pages, page


# =========================================================
# COLECAO NORMAL
# =========================================================

async def send_collection(update, context, page, edit=False):

    uid = update.effective_user.id

    cards = get_user_cards(uid)

    text, total_pages, page = build_collection_text(uid, cards, page)

    cover = DEFAULT_COVER

    fav = get_favorite(uid)

    if fav:
        for c in cards:
            if c["character_id"] == fav and c["image"]:
                cover = c["image"]

    kb = build_keyboard("colecao", page, total_pages, uid)

    if edit:

        msg = update.callback_query.message

        try:
            if msg.photo:
                await msg.edit_caption(text, parse_mode="HTML", reply_markup=kb)
            else:
                await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except:
            pass

    else:

        await update.message.reply_photo(
            photo=cover,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )


async def colecao(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id
    lock = get_lock(uid)

    args = context.args

    async with lock:

        if not args:
            await send_collection(update, context, 1)
            return

        mode = args[0].lower()

        if mode not in ("s", "f", "x"):
            await send_collection(update, context, 1)
            return

        anime_name = " ".join(args[1:])

        anime = find_anime(anime_name)

        if not anime:
            await update.message.reply_text("Anime não encontrado.")
            return

        if mode == "s":
            await send_collection_anime_owned(update, context, anime, 1)

        elif mode == "f":
            await send_collection_anime_missing(update, context, anime, 1)

        else:
            await send_collection_gallery(update, context, anime, 0)


# =========================================================
# COLECAO S
# =========================================================

async def send_collection_anime_owned(update, context, anime, page, edit=False):

    uid = update.effective_user.id

    anime_id = anime["anime_id"]

    all_chars = cards_data()["characters_by_anime"][anime_id]

    owned = [c for c in get_user_cards(uid) if c["anime_id"] == anime_id]

    banner = anime.get("banner_image") or anime.get("cover_image") or DEFAULT_COVER

    if not owned:
        await update.message.reply_photo(
            banner,
            caption=f"Você ainda não tem personagens de <b>{anime['anime']}</b>.",
            parse_mode="HTML"
        )
        return

    items, total, total_pages, page = paginate(owned, page)

    text = (
        f"📚 <b>{anime['anime']}</b>\n\n"
        f"📦 <b>{len(owned)}/{len(all_chars)}</b>\n\n"
    )

    for c in items:

        emoji = duplicate_emoji(c["quantity"])

        text += (
            f"🧧 <code>{c['character_id']}</code>. "
            f"<b>{c['name']}</b>{emoji}\n"
        )

    kb = build_keyboard("colecao_s", page, total_pages, uid, anime_id)

    if edit:

        msg = update.callback_query.message

        try:
            await msg.edit_caption(text, parse_mode="HTML", reply_markup=kb)
        except:
            pass

    else:

        await update.message.reply_photo(
            banner,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )


# =========================================================
# COLECAO F
# =========================================================

async def send_collection_anime_missing(update, context, anime, page, edit=False):

    uid = update.effective_user.id

    anime_id = anime["anime_id"]

    all_chars = cards_data()["characters_by_anime"][anime_id]

    owned_ids = {c["character_id"] for c in get_user_cards(uid)}

    missing = []

    for ch in all_chars:

        if ch["id"] not in owned_ids:

            missing.append({
                "character_id": ch["id"],
                "name": ch["name"],
                "image": ch["image"]
            })

    banner = anime.get("banner_image") or anime.get("cover_image") or DEFAULT_COVER

    if not missing:

        await update.message.reply_photo(
            banner,
            caption=f"🎉 Você completou <b>{anime['anime']}</b>!",
            parse_mode="HTML"
        )
        return

    items, total, total_pages, page = paginate(missing, page)

    text = (
        f"❔ <b>Faltam em {anime['anime']}</b>\n\n"
        f"📦 <b>{len(all_chars)-len(missing)}/{len(all_chars)}</b>\n\n"
    )

    for c in items:

        text += (
            f"❔ <code>{c['character_id']}</code>. "
            f"<b>{c['name']}</b>\n"
        )

    kb = build_keyboard("colecao_f", page, total_pages, uid, anime_id)

    if edit:

        msg = update.callback_query.message

        try:
            await msg.edit_caption(text, parse_mode="HTML", reply_markup=kb)
        except:
            pass

    else:

        await update.message.reply_photo(
            banner,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )


# =========================================================
# COLECAO X (GALERIA COMPLETA)
# =========================================================

async def send_collection_gallery(update, context, anime, index, edit=False):

    uid = update.effective_user.id

    anime_id = anime["anime_id"]

    chars = cards_data()["characters_by_anime"][anime_id]

    owned = {c["character_id"]: c["quantity"] for c in get_user_cards(uid)}

    total = len(chars)

    index = max(0, min(index, total-1))

    ch = chars[index]

    cid = ch["id"]
    qty = owned.get(cid, 0)

    owned_total = len(owned)

    emoji = duplicate_emoji(qty)

    prefix = "🧧" if qty else "❔"

    caption = (
        f"🖼 <b>{anime['anime']}</b>\n\n"
        f"📦 <b>{owned_total}/{total}</b>\n"
        f"📖 <b>{index+1}/{total}</b>\n\n"
        f"{prefix} <code>{cid}</code>. "
        f"<b>{ch['name']}</b>{emoji}"
    )

    kb = build_keyboard("colecao_x", index, total, uid, anime_id)

    img = ch["image"] or anime.get("cover_image") or DEFAULT_COVER

    if edit:

        msg = update.callback_query.message

        try:

            await msg.edit_media(
                InputMediaPhoto(img, caption=caption, parse_mode="HTML"),
                reply_markup=kb
            )

        except:

            try:
                await msg.edit_caption(caption, parse_mode="HTML", reply_markup=kb)
            except:
                pass

    else:

        await update.message.reply_photo(
            img,
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb
        )


# =========================================================
# CALLBACKS
# =========================================================

async def colecao_callback(update, context):

    q = update.callback_query

    if q.data == "noop":
        await q.answer()
        return

    uid = q.from_user.id

    if not antiflood(uid):
        await q.answer("Calma 🙂")
        return

    _, owner, page = q.data.split(":")

    if uid != int(owner):
        await q.answer("Essa coleção não é sua.", show_alert=True)
        return

    await q.answer()

    await send_collection(update, context, int(page), edit=True)


async def colecao_s_callback(update, context):

    q = update.callback_query

    uid = q.from_user.id

    if not antiflood(uid):
        await q.answer("Calma 🙂")
        return

    _, owner, anime_id, page = q.data.split(":")

    if uid != int(owner):
        await q.answer("Essa coleção não é sua.", show_alert=True)
        return

    anime = find_anime(anime_id)

    await q.answer()

    await send_collection_anime_owned(update, context, anime, int(page), edit=True)


async def colecao_f_callback(update, context):

    q = update.callback_query

    uid = q.from_user.id

    if not antiflood(uid):
        await q.answer("Calma 🙂")
        return

    _, owner, anime_id, page = q.data.split(":")

    if uid != int(owner):
        await q.answer("Essa coleção não é sua.", show_alert=True)
        return

    anime = find_anime(anime_id)

    await q.answer()

    await send_collection_anime_missing(update, context, anime, int(page), edit=True)


async def colecao_x_callback(update, context):

    q = update.callback_query

    uid = q.from_user.id

    if not antiflood(uid):
        await q.answer("Calma 🙂")
        return

    _, owner, anime_id, index = q.data.split(":")

    if uid != int(owner):
        await q.answer("Essa coleção não é sua.", show_alert=True)
        return

    anime = find_anime(anime_id)

    await q.answer()

    await send_collection_gallery(update, context, anime, int(index), edit=True)

def get_completed_anime_message(user_id: int, character_id: int):
    data = cards_data()
    ch = data["characters_by_id"].get(int(character_id))

    if not ch:
        return None

    anime_id = int(ch.get("anime_id") or 0)
    if anime_id <= 0:
        return None

    anime = find_anime(str(anime_id))
    if not anime:
        return None

    anime_chars = data["characters_by_anime"].get(anime_id, []) or []
    owned_ids = {c["character_id"] for c in get_user_cards(int(user_id))}

    total_anime = len(anime_chars)
    total_owned = sum(1 for c in anime_chars if int(c.get("id") or 0) in owned_ids)

    if total_anime <= 0 or total_owned != total_anime:
        return None

    return (
        "🎉 <b>PARABÉNS!</b>\n\n"
        f"🏆 Você completou a coleção de <b>{anime['anime']}</b>!\n\n"
        f"📚 <i>Total coletado:</i> <b>{total_owned}/{total_anime}</b>\n\n"
        "Agora essa obra está 100% completa na sua coleção. 💖"
    )
