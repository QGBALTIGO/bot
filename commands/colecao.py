import asyncio
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.ext import ContextTypes

import database as db
from cards_service import build_cards_final_data, find_anime, get_character_by_id


ITENS_POR_PAGINA = 10
ANTIFLOOD_SECONDS = 1.2

DEFAULT_COVER = (
    "https://photo.chelpbot.me/AgACAgEAAxkBZxImgmmnL7d9nYjTFd0KNTThxz9KJ6uCAAK7C2sbxrE5RXkd0eZ9Eoc4AQADAgADeQADOgQ/photo.jpg"
)

_locks: Dict[int, asyncio.Lock] = {}
_last_click: Dict[int, float] = {}
_cache: Dict[int, Tuple[float, List[Dict[str, Any]]]] = {}
CACHE_TTL = 20


# =========================================================
# CORE HELPERS
# =========================================================

def get_lock(uid: int) -> asyncio.Lock:
    lock = _locks.get(uid)
    if not lock:
        lock = asyncio.Lock()
        _locks[uid] = lock
    return lock


def antiflood(uid: int) -> bool:
    now = time.time()
    last = _last_click.get(uid, 0.0)

    if now - last < ANTIFLOOD_SECONDS:
        return False

    _last_click[uid] = now
    return True


def duplicate_emoji(qty: int) -> str:
    qty = int(qty or 0)

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


def get_cache(uid: int) -> Optional[List[Dict[str, Any]]]:
    data = _cache.get(uid)
    if not data:
        return None

    ts, cards = data
    if time.time() - ts > CACHE_TTL:
        _cache.pop(uid, None)
        return None

    return cards


def set_cache(uid: int, cards: List[Dict[str, Any]]) -> None:
    _cache[uid] = (time.time(), cards)


def clear_cache(uid: int) -> None:
    _cache.pop(uid, None)


def _cards_data() -> Dict[str, Any]:
    return build_cards_final_data()


def _character_meta(character_id: int) -> Optional[Dict[str, Any]]:
    data = _cards_data()
    ch = data["characters_by_id"].get(int(character_id))
    if not ch:
        return None

    return {
        "id": int(ch["id"]),
        "name": str(ch.get("name") or "").strip(),
        "image": str(ch.get("image") or "").strip(),
        "anime": str(ch.get("anime") or "").strip(),
        "anime_id": int(ch.get("anime_id") or 0),
    }


def get_favorite_id(uid: int) -> Optional[int]:
    try:
        prof = db.get_collection_profile(uid)
        if prof and prof.get("favorite_character_id"):
            return int(prof["favorite_character_id"])
    except Exception:
        pass
    return None


def sort_cards(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []

    for row in rows:
        cid = int(row.get("character_id") or 0)
        qty = int(row.get("quantity") or 0)

        if cid <= 0 or qty <= 0:
            continue

        meta = _character_meta(cid)
        if not meta:
            continue

        enriched.append({
            "character_id": cid,
            "quantity": qty,
            "name": meta["name"],
            "anime": meta["anime"],
            "anime_id": meta["anime_id"],
            "image": meta["image"],
        })

    enriched.sort(
        key=lambda x: (
            (x["anime"] or "").lower(),
            (x["name"] or "").lower(),
            int(x["character_id"]),
        )
    )
    return enriched


def get_user_cards(uid: int) -> List[Dict[str, Any]]:
    cached = get_cache(uid)
    if cached is not None:
        return cached

    raw = db.get_user_card_collection(uid) or []
    cards = sort_cards(raw)
    set_cache(uid, cards)
    return cards


def get_collection_cover(uid: int, cards: List[Dict[str, Any]]) -> str:
    fav = get_favorite_id(uid)
    if fav:
        for c in cards:
            if int(c["character_id"]) == fav and c.get("image"):
                return c["image"]

        try:
            ch = get_character_by_id(fav)
            if ch and ch.get("image"):
                return str(ch["image"]).strip()
        except Exception:
            pass

    return DEFAULT_COVER


def paginate(items: List[Dict[str, Any]], page: int, per_page: int = ITENS_POR_PAGINA):
    total = len(items)
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(int(page), total_pages))

    start = (page - 1) * per_page
    end = start + per_page

    return items[start:end], total, total_pages, page


def get_anime_data(query: str):
    anime = find_anime(query)
    if not anime:
        return None, []

    data = _cards_data()
    anime_id = int(anime["anime_id"])
    chars = data["characters_by_anime"].get(anime_id, []) or []

    chars = sorted(
        chars,
        key=lambda x: (
            str(x.get("name") or "").lower(),
            int(x.get("id") or 0),
        )
    )

    return anime, chars


# =========================================================
# KEYBOARDS
# =========================================================

def build_keyboard(page: int, total_pages: int, uid: int, prefix: str = "colecao"):
    if total_pages <= 1:
        return None

    btn = []

    if total_pages >= 4 and page > 3:
        btn.append(
            InlineKeyboardButton("⏪️", callback_data=f"{prefix}:{uid}:{max(1, page - 3)}")
        )

    if page > 1:
        btn.append(
            InlineKeyboardButton("◀️", callback_data=f"{prefix}:{uid}:{page - 1}")
        )

    btn.append(
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop")
    )

    if page < total_pages:
        btn.append(
            InlineKeyboardButton("▶️", callback_data=f"{prefix}:{uid}:{page + 1}")
        )

    if total_pages >= 4 and page <= total_pages - 3:
        btn.append(
            InlineKeyboardButton("⏩️", callback_data=f"{prefix}:{uid}:{min(total_pages, page + 3)}")
        )

    return InlineKeyboardMarkup([btn])


def build_anime_keyboard(page: int, total_pages: int, uid: int, anime_id: int, mode: str):
    if total_pages <= 1:
        return None

    btn = []

    if total_pages >= 4 and page > 3:
        btn.append(
            InlineKeyboardButton(
                "⏪️",
                callback_data=f"colecao_{mode}:{uid}:{anime_id}:{max(1, page - 3)}",
            )
        )

    if page > 1:
        btn.append(
            InlineKeyboardButton(
                "◀️",
                callback_data=f"colecao_{mode}:{uid}:{anime_id}:{page - 1}",
            )
        )

    btn.append(
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop")
    )

    if page < total_pages:
        btn.append(
            InlineKeyboardButton(
                "▶️",
                callback_data=f"colecao_{mode}:{uid}:{anime_id}:{page + 1}",
            )
        )

    if total_pages >= 4 and page <= total_pages - 3:
        btn.append(
            InlineKeyboardButton(
                "⏩️",
                callback_data=f"colecao_{mode}:{uid}:{anime_id}:{min(total_pages, page + 3)}",
            )
        )

    return InlineKeyboardMarkup([btn])


def build_gallery_keyboard(index: int, total: int, uid: int, anime_id: int):
    if total <= 1:
        return None

    page = index + 1
    btn = []

    if total >= 4 and index > 2:
        btn.append(
            InlineKeyboardButton(
                "⏪️",
                callback_data=f"colecao_x:{uid}:{anime_id}:{max(0, index - 3)}",
            )
        )

    if index > 0:
        btn.append(
            InlineKeyboardButton(
                "◀️",
                callback_data=f"colecao_x:{uid}:{anime_id}:{index - 1}",
            )
        )

    btn.append(
        InlineKeyboardButton(f"{page}/{total}", callback_data="noop")
    )

    if index < total - 1:
        btn.append(
            InlineKeyboardButton(
                "▶️",
                callback_data=f"colecao_x:{uid}:{anime_id}:{index + 1}",
            )
        )

    if total >= 4 and index < total - 3:
        btn.append(
            InlineKeyboardButton(
                "⏩️",
                callback_data=f"colecao_x:{uid}:{anime_id}:{min(total - 1, index + 3)}",
            )
        )

    return InlineKeyboardMarkup([btn])


# =========================================================
# TEXT BUILDERS
# =========================================================

def build_general_text(uid: int, cards: List[Dict[str, Any]], page: int):
    items, total, total_pages, page = paginate(cards, page)
    fav = get_favorite_id(uid)

    text = (
        "📚 <b>Minha Coleção</b>\n\n"
        f"📦 <i>Total:</i> <b>{total}</b>\n"
        f"📖 <i>Página:</i> <b>{page}/{total_pages}</b>\n\n"
    )

    if fav:
        for c in cards:
            if int(c["character_id"]) == fav:
                emoji = duplicate_emoji(c["quantity"])
                text += (
                    f"❤️ <code>{fav}</code>. "
                    f"<b>{c['name']}</b>{emoji} — "
                    f"<i>{c['anime']}</i>\n\n"
                )
                break

    for c in items:
        cid = int(c["character_id"])

        if cid == fav:
            continue

        emoji = duplicate_emoji(c["quantity"])
        text += (
            f"🧧 <code>{cid}</code>. "
            f"<b>{c['name']}</b>{emoji} — "
            f"<i>{c['anime']}</i>\n"
        )

    return text, total_pages, page


def build_owned_anime_cards(uid: int, anime_id: int) -> List[Dict[str, Any]]:
    user_cards = get_user_cards(uid)
    return [c for c in user_cards if int(c.get("anime_id") or 0) == int(anime_id)]


def build_owned_anime_text(uid: int, anime: Dict[str, Any], owned_cards: List[Dict[str, Any]], total_anime_chars: int, page: int):
    items, owned_total, total_pages, page = paginate(owned_cards, page)
    fav = get_favorite_id(uid)
    anime_name = str(anime["anime"])

    text = (
        f"📚 <b>Minha Coleção</b> — <b>{anime_name}</b>\n\n"
        f"📦 <i>Obtidos:</i> <b>{owned_total}/{total_anime_chars}</b>\n"
        f"📖 <i>Página:</i> <b>{page}/{total_pages}</b>\n\n"
    )

    if fav:
        for c in owned_cards:
            if int(c["character_id"]) == fav:
                emoji = duplicate_emoji(c["quantity"])
                text += (
                    f"❤️ <code>{fav}</code>. "
                    f"<b>{c['name']}</b>{emoji} — "
                    f"<i>{c['anime']}</i>\n\n"
                )
                break

    for c in items:
        cid = int(c["character_id"])
        if cid == fav:
            continue

        emoji = duplicate_emoji(c["quantity"])
        text += (
            f"🧧 <code>{cid}</code>. "
            f"<b>{c['name']}</b>{emoji} — "
            f"<i>{c['anime']}</i>\n"
        )

    return text, total_pages, page


def build_missing_anime_items(uid: int, anime_chars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    owned_ids = {int(c["character_id"]) for c in get_user_cards(uid)}
    missing: List[Dict[str, Any]] = []

    for ch in anime_chars:
        cid = int(ch.get("id") or 0)
        if cid <= 0 or cid in owned_ids:
            continue

        missing.append({
            "character_id": cid,
            "name": str(ch.get("name") or "").strip(),
            "anime": str(ch.get("anime") or "").strip(),
            "image": str(ch.get("image") or "").strip(),
        })

    return missing


def build_missing_anime_text(anime: Dict[str, Any], missing_cards: List[Dict[str, Any]], owned_total: int, total_anime_chars: int, page: int):
    items, missing_total, total_pages, page = paginate(missing_cards, page)
    anime_name = str(anime["anime"])

    text = (
        f"📚 <b>Faltam na sua coleção</b> — <b>{anime_name}</b>\n\n"
        f"📦 <i>Progresso:</i> <b>{owned_total}/{total_anime_chars}</b>\n"
        f"❔ <i>Faltando:</i> <b>{missing_total}</b>\n"
        f"📖 <i>Página:</i> <b>{page}/{total_pages}</b>\n\n"
    )

    for c in items:
        text += (
            f"❔ <code>{c['character_id']}</code>. "
            f"<b>{c['name']}</b> — "
            f"<i>{c['anime']}</i>\n"
        )

    return text, total_pages, page


def build_gallery_caption(anime: Dict[str, Any], owned_cards: List[Dict[str, Any]], index: int, total_anime_chars: int):
    total_owned = len(owned_cards)
    if total_owned <= 0:
        return None, None, None

    index = max(0, min(index, total_owned - 1))
    c = owned_cards[index]
    emoji = duplicate_emoji(c["quantity"])

    caption = (
        f"🖼 <b>{anime['anime']}</b>\n\n"
        f"📦 <i>Obtidos:</i> <b>{total_owned}/{total_anime_chars}</b>\n"
        f"📖 <i>Card:</i> <b>{index + 1}/{total_owned}</b>\n\n"
        f"🧧 <code>{c['character_id']}</code>. "
        f"<b>{c['name']}</b>{emoji}"
    )

    return c, caption, index


# =========================================================
# SENDERS
# =========================================================

async def send_general_collection(update, context, page: int, edit: bool = False):
    uid = update.effective_user.id
    cards = get_user_cards(uid)

    text, total_pages, page = build_general_text(uid, cards, page)
    cover = get_collection_cover(uid, cards)
    kb = build_keyboard(page, total_pages, uid, prefix="colecao")

    if edit:
        msg = update.callback_query.message
        try:
            if msg.photo:
                await msg.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
            else:
                await msg.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        return

    await update.message.reply_photo(
        photo=cover,
        caption=text,
        parse_mode="HTML",
        reply_markup=kb,
    )


async def send_owned_anime_collection(update, context, anime: Dict[str, Any], page: int, edit: bool = False):
    uid = update.effective_user.id
    anime_id = int(anime["anime_id"])
    anime_chars = _cards_data()["characters_by_anime"].get(anime_id, []) or []
    owned_cards = build_owned_anime_cards(uid, anime_id)

    banner = (
        str(anime.get("banner_image") or "").strip()
        or str(anime.get("cover_image") or "").strip()
        or DEFAULT_COVER
    )

    if not owned_cards:
        text = f"📦 <b>Você ainda não tem nenhum personagem de <i>{anime['anime']}</i>.</b>"
        if edit:
            msg = update.callback_query.message
            try:
                if msg.photo:
                    await msg.edit_caption(caption=text, parse_mode="HTML", reply_markup=None)
                else:
                    await msg.edit_text(text=text, parse_mode="HTML", reply_markup=None)
            except Exception:
                pass
        else:
            await update.message.reply_photo(photo=banner, caption=text, parse_mode="HTML")
        return

    text, total_pages, page = build_owned_anime_text(uid, anime, owned_cards, len(anime_chars), page)
    kb = build_anime_keyboard(page, total_pages, uid, anime_id, "s")

    if edit:
        msg = update.callback_query.message
        try:
            if msg.photo:
                await msg.edit_media(
                    media=InputMediaPhoto(media=banner, caption=text, parse_mode="HTML"),
                    reply_markup=kb,
                )
            else:
                await msg.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            try:
                if msg.photo:
                    await msg.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
        return

    await update.message.reply_photo(
        photo=banner,
        caption=text,
        parse_mode="HTML",
        reply_markup=kb,
    )


async def send_missing_anime_collection(update, context, anime: Dict[str, Any], page: int, edit: bool = False):
    uid = update.effective_user.id
    anime_id = int(anime["anime_id"])
    anime_chars = _cards_data()["characters_by_anime"].get(anime_id, []) or []
    owned_cards = build_owned_anime_cards(uid, anime_id)
    missing_cards = build_missing_anime_items(uid, anime_chars)

    banner = (
        str(anime.get("banner_image") or "").strip()
        or str(anime.get("cover_image") or "").strip()
        or DEFAULT_COVER
    )

    if not missing_cards:
        text = (
            f"🎉 <b>Você já completou a coleção de <i>{anime['anime']}</i>!</b>\n\n"
            f"🏆 <i>Progresso final:</i> <b>{len(owned_cards)}/{len(anime_chars)}</b>"
        )
        if edit:
            msg = update.callback_query.message
            try:
                if msg.photo:
                    await msg.edit_media(
                        media=InputMediaPhoto(media=banner, caption=text, parse_mode="HTML"),
                        reply_markup=None,
                    )
                else:
                    await msg.edit_text(text=text, parse_mode="HTML", reply_markup=None)
            except Exception:
                try:
                    if msg.photo:
                        await msg.edit_caption(caption=text, parse_mode="HTML", reply_markup=None)
                except Exception:
                    pass
        else:
            await update.message.reply_photo(photo=banner, caption=text, parse_mode="HTML")
        return

    text, total_pages, page = build_missing_anime_text(
        anime,
        missing_cards,
        len(owned_cards),
        len(anime_chars),
        page,
    )
    kb = build_anime_keyboard(page, total_pages, uid, anime_id, "f")

    if edit:
        msg = update.callback_query.message
        try:
            if msg.photo:
                await msg.edit_media(
                    media=InputMediaPhoto(media=banner, caption=text, parse_mode="HTML"),
                    reply_markup=kb,
                )
            else:
                await msg.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            try:
                if msg.photo:
                    await msg.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
        return

    await update.message.reply_photo(
        photo=banner,
        caption=text,
        parse_mode="HTML",
        reply_markup=kb,
    )


async def send_gallery_anime_collection(update, context, anime: Dict[str, Any], index: int, edit: bool = False):
    uid = update.effective_user.id
    anime_id = int(anime["anime_id"])
    anime_chars = _cards_data()["characters_by_anime"].get(anime_id, []) or []
    owned_cards = build_owned_anime_cards(uid, anime_id)

    if not owned_cards:
        text = f"📦 <b>Você ainda não tem personagens de <i>{anime['anime']}</i>.</b>"
        banner = (
            str(anime.get("banner_image") or "").strip()
            or str(anime.get("cover_image") or "").strip()
            or DEFAULT_COVER
        )

        if edit:
            msg = update.callback_query.message
            try:
                if msg.photo:
                    await msg.edit_media(
                        media=InputMediaPhoto(media=banner, caption=text, parse_mode="HTML"),
                        reply_markup=None,
                    )
                else:
                    await msg.edit_text(text=text, parse_mode="HTML", reply_markup=None)
            except Exception:
                try:
                    if msg.photo:
                        await msg.edit_caption(caption=text, parse_mode="HTML", reply_markup=None)
                except Exception:
                    pass
        else:
            await update.message.reply_photo(photo=banner, caption=text, parse_mode="HTML")
        return

    card, caption, index = build_gallery_caption(anime, owned_cards, index, len(anime_chars))
    kb = build_gallery_keyboard(index, len(owned_cards), uid, anime_id)
    image = (
        str(card.get("image") or "").strip()
        or str(anime.get("cover_image") or "").strip()
        or str(anime.get("banner_image") or "").strip()
        or DEFAULT_COVER
    )

    if edit:
        msg = update.callback_query.message
        try:
            if msg.photo:
                await msg.edit_media(
                    media=InputMediaPhoto(media=image, caption=caption, parse_mode="HTML"),
                    reply_markup=kb,
                )
            else:
                await msg.edit_text(text=caption, parse_mode="HTML", reply_markup=kb)
        except Exception:
            try:
                if msg.photo:
                    await msg.edit_caption(caption=caption, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
        return

    await update.message.reply_photo(
        photo=image,
        caption=caption,
        parse_mode="HTML",
        reply_markup=kb,
    )


# =========================================================
# COMMAND
# =========================================================

async def colecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lock = get_lock(uid)
    args = context.args or []

    async with lock:
        if not args:
            await send_general_collection(update, context, 1, edit=False)
            return

        mode = str(args[0] or "").strip().lower()

        if mode not in ("s", "f", "x"):
            await send_general_collection(update, context, 1, edit=False)
            return

        query = " ".join(args[1:]).strip()
        if not query:
            await update.message.reply_html("❌ <b>Informe o nome do anime.</b>")
            return

        anime, _chars = get_anime_data(query)
        if not anime:
            await update.message.reply_html("❌ <b>Anime não encontrado.</b>")
            return

        if mode == "s":
            await send_owned_anime_collection(update, context, anime, 1, edit=False)
            return

        if mode == "f":
            await send_missing_anime_collection(update, context, anime, 1, edit=False)
            return

        if mode == "x":
            await send_gallery_anime_collection(update, context, anime, 0, edit=False)
            return


# =========================================================
# CALLBACKS
# =========================================================

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
        _, owner, page = q.data.split(":")
        owner = int(owner)
        page = int(page)
    except Exception:
        await q.answer("Erro")
        return

    if uid != owner:
        await q.answer("Essa coleção não é sua.", show_alert=True)
        return

    await q.answer()

    lock = get_lock(uid)
    async with lock:
        await send_general_collection(update, context, page, edit=True)


async def colecao_s_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        _, owner, anime_id, page = q.data.split(":")
        owner = int(owner)
        anime_id = int(anime_id)
        page = int(page)
    except Exception:
        await q.answer("Erro")
        return

    if uid != owner:
        await q.answer("Essa coleção não é sua.", show_alert=True)
        return

    anime = find_anime(str(anime_id))
    if not anime:
        await q.answer("Anime não encontrado.")
        return

    await q.answer()

    lock = get_lock(uid)
    async with lock:
        await send_owned_anime_collection(update, context, anime, page, edit=True)


async def colecao_f_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        _, owner, anime_id, page = q.data.split(":")
        owner = int(owner)
        anime_id = int(anime_id)
        page = int(page)
    except Exception:
        await q.answer("Erro")
        return

    if uid != owner:
        await q.answer("Essa coleção não é sua.", show_alert=True)
        return

    anime = find_anime(str(anime_id))
    if not anime:
        await q.answer("Anime não encontrado.")
        return

    await q.answer()

    lock = get_lock(uid)
    async with lock:
        await send_missing_anime_collection(update, context, anime, page, edit=True)


async def colecao_x_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        _, owner, anime_id, index = q.data.split(":")
        owner = int(owner)
        anime_id = int(anime_id)
        index = int(index)
    except Exception:
        await q.answer("Erro")
        return

    if uid != owner:
        await q.answer("Essa coleção não é sua.", show_alert=True)
        return

    anime = find_anime(str(anime_id))
    if not anime:
        await q.answer("Anime não encontrado.")
        return

    await q.answer()

    lock = get_lock(uid)
    async with lock:
        await send_gallery_anime_collection(update, context, anime, index, edit=True)


# =========================================================
# COMPLETION MESSAGE HELPER
# Use isso no fluxo do gacha depois de adicionar a carta.
# =========================================================

def get_completed_anime_message(user_id: int, character_id: int) -> Optional[str]:
    meta = _character_meta(character_id)
    if not meta:
        return None

    anime_id = int(meta["anime_id"])
    anime = find_anime(str(anime_id))
    if not anime:
        return None

    anime_chars = _cards_data()["characters_by_anime"].get(anime_id, []) or []
    owned_cards = build_owned_anime_cards(int(user_id), anime_id)

    total_anime = len(anime_chars)
    total_owned = len(owned_cards)

    if total_anime <= 0 or total_owned != total_anime:
        return None

    return (
        "🎉 <b>PARABÉNS!</b>\n\n"
        f"🏆 Você completou a coleção de <b>{anime['anime']}</b>!\n\n"
        f"📚 <i>Total coletado:</i> <b>{total_owned}/{total_anime}</b>\n\n"
        "Agora essa obra está 100% completa na sua coleção. 💖"
    )
