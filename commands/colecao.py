import asyncio
import math
import time
from typing import Any, Dict, List, Optional

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
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

_locks: Dict[int, asyncio.Lock] = {}
_last_click: Dict[int, float] = {}

# cache apenas da coleção bruta do usuário (id/quantidade)
# para não congelar nome/imagem/anime após override admin
_raw_collection_cache: Dict[int, Any] = {}


def get_lock(uid: int) -> asyncio.Lock:
    if uid not in _locks:
        _locks[uid] = asyncio.Lock()
    return _locks[uid]


def antiflood(uid: int) -> bool:
    now = time.time()
    last = _last_click.get(uid, 0.0)

    if now - last < ANTIFLOOD:
        return False

    _last_click[uid] = now
    return True


def cards_data():
    # Sem cache local persistente aqui.
    # Sempre pega do cards_service para refletir imediatamente:
    # - /card_setcharimg
    # - /card_setcharname
    # - /card_addchar
    # - /card_delchar
    # - alterações de anime/banner/cover
    return build_cards_final_data()


def get_cached_raw_collection(uid: int):
    item = _raw_collection_cache.get(uid)
    if not item:
        return None

    ts, rows = item
    if time.time() - ts > CACHE_TTL:
        return None

    return rows


def set_cached_raw_collection(uid: int, rows):
    _raw_collection_cache[uid] = (time.time(), rows)


def clear_user_collection_cache(uid: int):
    _raw_collection_cache.pop(uid, None)


# =========================================================
# UTILS
# =========================================================

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


def _extract_characters_by_id(data) -> Dict[int, Dict[str, Any]]:
    if isinstance(data, dict):
        return data.get("characters_by_id", {}) or {}
    return {}


def _extract_characters_by_anime(data) -> Dict[int, List[Dict[str, Any]]]:
    if isinstance(data, dict):
        return data.get("characters_by_anime", {}) or {}
    return {}


def get_user_cards(uid: int):
    raw = get_cached_raw_collection(uid)
    if raw is None:
        raw = db.get_user_card_collection(uid) or []
        set_cached_raw_collection(uid, raw)

    data = cards_data()
    chars = _extract_characters_by_id(data)

    out = []

    for r in raw:
        try:
            cid = int(r["character_id"])
            qty = int(r["quantity"])
        except Exception:
            continue

        ch = chars.get(cid)
        if not ch:
            continue

        out.append(
            {
                "character_id": cid,
                "quantity": qty,
                "name": ch.get("name", "Sem nome"),
                "anime": ch.get("anime", "Obra desconhecida"),
                "anime_id": ch.get("anime_id"),
                "image": ch.get("image"),
            }
        )

    out.sort(
        key=lambda x: (
            str(x["anime"]).lower(),
            str(x["name"]).lower(),
            x["character_id"],
        )
    )

    return out


def get_favorite(uid: int) -> Optional[int]:
    try:
        prof = db.get_profile_settings(uid)
        if not prof:
            return None
        fav_id = prof.get("favorite_character_id")
        return int(fav_id) if fav_id else None
    except Exception:
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
                callback_data=(
                    f"{prefix}:{uid}:{extra}:{page-1}"
                    if extra is not None
                    else f"{prefix}:{uid}:{page-1}"
                ),
            )
        )

    btn.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))

    if page < total_pages:
        btn.append(
            InlineKeyboardButton(
                "▶️",
                callback_data=(
                    f"{prefix}:{uid}:{extra}:{page+1}"
                    if extra is not None
                    else f"{prefix}:{uid}:{page+1}"
                ),
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

async def send_collection(update, context, page, edit=False, target_uid=None):
    uid = int(target_uid) if target_uid is not None else update.effective_user.id
    cards = get_user_cards(uid)

    text, total_pages, page = build_collection_text(uid, cards, page)

    cover = DEFAULT_COVER
    fav = get_favorite(uid)

    if fav:
        for c in cards:
            if c["character_id"] == fav and c.get("image"):
                cover = c["image"]
                break

    kb = build_keyboard("colecao", page, total_pages, uid)

    if edit:
        msg = update.callback_query.message

        try:
            if msg.photo:
                await msg.edit_caption(text, parse_mode="HTML", reply_markup=kb)
            else:
                await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
    else:
        await update.message.reply_photo(
            photo=cover,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb,
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

        anime_name = " ".join(args[1:]).strip()
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

async def send_collection_anime_owned(update, context, anime, page, edit=False, target_uid=None):
    uid = int(target_uid) if target_uid is not None else update.effective_user.id
    anime_id = int(anime["anime_id"])

    all_chars = _extract_characters_by_anime(cards_data()).get(anime_id, []) or []
    owned = [c for c in get_user_cards(uid) if int(c["anime_id"] or 0) == anime_id]

    banner = anime.get("banner_image") or anime.get("cover_image") or DEFAULT_COVER

    if not owned:
        if edit and update.callback_query:
            try:
                await update.callback_query.message.edit_media(
                    InputMediaPhoto(
                        media=banner,
                        caption=f"Você ainda não tem personagens de <b>{anime['anime']}</b>.",
                        parse_mode="HTML",
                    )
                )
            except Exception:
                try:
                    await update.callback_query.message.edit_caption(
                        caption=f"Você ainda não tem personagens de <b>{anime['anime']}</b>.",
                        parse_mode="HTML",
                        reply_markup=None,
                    )
                except Exception:
                    pass
        else:
            await update.message.reply_photo(
                banner,
                caption=f"Você ainda não tem personagens de <b>{anime['anime']}</b>.",
                parse_mode="HTML",
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
            if msg.photo:
                await msg.edit_caption(text, parse_mode="HTML", reply_markup=kb)
            else:
                await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
    else:
        await update.message.reply_photo(
            banner,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb,
        )


# =========================================================
# COLECAO F
# =========================================================

async def send_collection_anime_missing(update, context, anime, page, edit=False, target_uid=None):
    uid = int(target_uid) if target_uid is not None else update.effective_user.id
    anime_id = int(anime["anime_id"])

    all_chars = _extract_characters_by_anime(cards_data()).get(anime_id, []) or []
    owned_ids = {c["character_id"] for c in get_user_cards(uid)}

    missing = []

    for ch in all_chars:
        try:
            cid = int(ch["id"])
        except Exception:
            continue

        if cid not in owned_ids:
            missing.append(
                {
                    "character_id": cid,
                    "name": ch.get("name", "Sem nome"),
                    "image": ch.get("image"),
                }
            )

    banner = anime.get("banner_image") or anime.get("cover_image") or DEFAULT_COVER

    if not missing:
        if edit and update.callback_query:
            try:
                await update.callback_query.message.edit_media(
                    InputMediaPhoto(
                        media=banner,
                        caption=f"🎉 Você completou <b>{anime['anime']}</b>!",
                        parse_mode="HTML",
                    )
                )
            except Exception:
                try:
                    await update.callback_query.message.edit_caption(
                        caption=f"🎉 Você completou <b>{anime['anime']}</b>!",
                        parse_mode="HTML",
                        reply_markup=None,
                    )
                except Exception:
                    pass
        else:
            await update.message.reply_photo(
                banner,
                caption=f"🎉 Você completou <b>{anime['anime']}</b>!",
                parse_mode="HTML",
            )
        return

    items, total, total_pages, page = paginate(missing, page)

    text = (
        f"❔ <b>Faltam em {anime['anime']}</b>\n\n"
        f"📦 <b>{len(all_chars) - len(missing)}/{len(all_chars)}</b>\n\n"
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
            if msg.photo:
                await msg.edit_caption(text, parse_mode="HTML", reply_markup=kb)
            else:
                await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
    else:
        await update.message.reply_photo(
            banner,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb,
        )


# =========================================================
# COLECAO X (GALERIA COMPLETA)
# =========================================================

async def send_collection_gallery(update, context, anime, index, edit=False, target_uid=None):
    uid = int(target_uid) if target_uid is not None else update.effective_user.id
    anime_id = int(anime["anime_id"])

    chars = _extract_characters_by_anime(cards_data()).get(anime_id, []) or []
    owned = {c["character_id"]: c["quantity"] for c in get_user_cards(uid)}

    total = len(chars)
    if total <= 0:
        text = f"Não encontrei personagens para <b>{anime['anime']}</b>."
        if edit and update.callback_query:
            try:
                await update.callback_query.message.edit_caption(
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                pass
        else:
            await update.message.reply_photo(
                anime.get("cover_image") or DEFAULT_COVER,
                caption=text,
                parse_mode="HTML",
            )
        return

    index = max(0, min(index, total - 1))
    ch = chars[index]

    cid = int(ch["id"])
    qty = int(owned.get(cid, 0))

    owned_total = sum(1 for c in chars if int(c.get("id") or 0) in owned)

    emoji = duplicate_emoji(qty)
    prefix = "🧧" if qty else "❔"

    caption = (
        f"🖼 <b>{anime['anime']}</b>\n\n"
        f"📦 <b>{owned_total}/{total}</b>\n"
        f"📖 <b>{index + 1}/{total}</b>\n\n"
        f"{prefix} <code>{cid}</code>. "
        f"<b>{ch.get('name', 'Sem nome')}</b>{emoji}"
    )

    kb = build_keyboard("colecao_x", index, total, uid, anime_id)
    img = ch.get("image") or anime.get("cover_image") or DEFAULT_COVER

    if edit:
        msg = update.callback_query.message

        try:
            await msg.edit_media(
                InputMediaPhoto(img, caption=caption, parse_mode="HTML"),
                reply_markup=kb,
            )
        except Exception:
            try:
                await msg.edit_caption(caption, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
    else:
        await update.message.reply_photo(
            img,
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb,
        )


# =========================================================
# CALLBACKS
# =========================================================

async def colecao_callback(update, context):
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
    except Exception:
        await q.answer()
        return

    await q.answer()
    await send_collection(update, context, int(page), edit=True, target_uid=int(owner))


async def colecao_s_callback(update, context):
    q = update.callback_query
    if not q:
        return

    uid = q.from_user.id

    if not antiflood(uid):
        await q.answer("Calma 🙂")
        return

    try:
        _, owner, anime_id, page = q.data.split(":")
    except Exception:
        await q.answer()
        return

    anime = find_anime(anime_id)
    if not anime:
        await q.answer("Anime não encontrado.", show_alert=True)
        return

    await q.answer()
    await send_collection_anime_owned(
        update,
        context,
        anime,
        int(page),
        edit=True,
        target_uid=int(owner),
    )


async def colecao_f_callback(update, context):
    q = update.callback_query
    if not q:
        return

    uid = q.from_user.id

    if not antiflood(uid):
        await q.answer("Calma 🙂")
        return

    try:
        _, owner, anime_id, page = q.data.split(":")
    except Exception:
        await q.answer()
        return

    anime = find_anime(anime_id)
    if not anime:
        await q.answer("Anime não encontrado.", show_alert=True)
        return

    await q.answer()
    await send_collection_anime_missing(
        update,
        context,
        anime,
        int(page),
        edit=True,
        target_uid=int(owner),
    )


async def colecao_x_callback(update, context):
    q = update.callback_query
    if not q:
        return

    uid = q.from_user.id

    if not antiflood(uid):
        await q.answer("Calma 🙂")
        return

    try:
        _, owner, anime_id, index = q.data.split(":")
    except Exception:
        await q.answer()
        return

    anime = find_anime(anime_id)
    if not anime:
        await q.answer("Anime não encontrado.", show_alert=True)
        return

    await q.answer()
    await send_collection_gallery(
        update,
        context,
        anime,
        int(index),
        edit=True,
        target_uid=int(owner),
    )


def get_completed_anime_message(user_id: int, character_id: int):
    data = cards_data()
    ch = _extract_characters_by_id(data).get(int(character_id))

    if not ch:
        return None

    anime_id = int(ch.get("anime_id") or 0)
    if anime_id <= 0:
        return None

    anime = find_anime(str(anime_id))
    if not anime:
        return None

    anime_chars = _extract_characters_by_anime(data).get(anime_id, []) or []
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
