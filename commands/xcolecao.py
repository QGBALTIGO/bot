import asyncio
import math
import time
from typing import Any, Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

import database as db
from xcards_service import (
    build_xcards_data,
    find_xtitle,
    get_xcard_by_id,
    get_xcards_for_title,
)


ITEMS_PER_PAGE = 10
ANTIFLOOD_SECONDS = 1.2
CACHE_TTL = 20

_locks: Dict[int, asyncio.Lock] = {}
_last_click: Dict[int, float] = {}
_raw_xcollection_cache: Dict[int, Any] = {}


def _get_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _locks:
        _locks[user_id] = asyncio.Lock()
    return _locks[user_id]


def _antiflood(user_id: int) -> bool:
    now = time.time()
    last = _last_click.get(user_id, 0.0)
    if (now - last) < ANTIFLOOD_SECONDS:
        return False
    _last_click[user_id] = now
    return True


def _duplicate_marker(quantity: int) -> str:
    if quantity >= 20:
        return " 🏆"
    if quantity >= 10:
        return " ⭐"
    if quantity >= 5:
        return " 💫"
    if quantity >= 2:
        return " ✨"
    return ""


def _get_cached_raw_xcollection(user_id: int):
    item = _raw_xcollection_cache.get(user_id)
    if not item:
        return None

    ts, rows = item
    if time.time() - ts > CACHE_TTL:
        return None
    return rows


def set_cached_raw_xcollection(user_id: int, rows):
    _raw_xcollection_cache[user_id] = (time.time(), rows)


def clear_user_xcollection_cache(user_id: int):
    _raw_xcollection_cache.pop(user_id, None)


def _paginate(items: List[Dict[str, Any]], page: int):
    total = len(items)
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    return items[start:end], total, total_pages, page


def _build_keyboard(prefix: str, user_id: int, page: int, total_pages: int, extra: int = 0):
    if total_pages <= 1:
        return None

    row = []
    if page > 1:
        row.append(
            InlineKeyboardButton(
                "◀️",
                callback_data=f"{prefix}:{user_id}:{extra}:{page - 1}",
            )
        )

    row.append(InlineKeyboardButton(f"📖 {page}/{total_pages}", callback_data="xcolecao_noop"))

    if page < total_pages:
        row.append(
            InlineKeyboardButton(
                "▶️",
                callback_data=f"{prefix}:{user_id}:{extra}:{page + 1}",
            )
        )

    return InlineKeyboardMarkup([row])


def _build_gallery_keyboard(prefix: str, user_id: int, title_id: int, index: int, total: int):
    row = []
    if index > 0:
        row.append(
            InlineKeyboardButton(
                "◀️",
                callback_data=f"{prefix}:{user_id}:{title_id}:{index - 1}",
            )
        )

    row.append(InlineKeyboardButton(f"🎴 {index + 1}/{total}", callback_data="xcolecao_noop"))

    if index < (total - 1):
        row.append(
            InlineKeyboardButton(
                "▶️",
                callback_data=f"{prefix}:{user_id}:{title_id}:{index + 1}",
            )
        )

    return InlineKeyboardMarkup([row])


def _default_cover() -> str:
    data = build_xcards_data()
    titles = data.get("titles_list") or []
    if not titles:
        return ""
    return str(titles[0].get("cover_image") or titles[0].get("logo_image") or "").strip()


def get_user_xcards(user_id: int) -> List[Dict[str, Any]]:
    raw = _get_cached_raw_xcollection(user_id)
    if raw is None:
        raw = db.get_user_xcard_collection(user_id) or []
        set_cached_raw_xcollection(user_id, raw)

    merged = []
    for row in raw:
        try:
            card_id = int(row.get("card_id") or 0)
            quantity = int(row.get("quantity") or 0)
        except Exception:
            continue

        if card_id <= 0 or quantity <= 0:
            continue

        card = get_xcard_by_id(card_id)
        if not card:
            continue

        merged.append(
            {
                "card_id": card_id,
                "quantity": quantity,
                "card_no": str(card.get("card_no") or ""),
                "name": str(card.get("name") or "Sem nome"),
                "title": str(card.get("title") or "Obra desconhecida"),
                "title_id": int(card.get("title_id") or 0),
                "image": str(card.get("image") or "").strip(),
                "character_id": int(card.get("character_id") or 0),
            }
        )

    merged.sort(
        key=lambda item: (
            str(item["title"]).lower(),
            str(item["name"]).lower(),
            str(item["card_no"]).lower(),
            item["card_id"],
        )
    )
    return merged


def _build_owned_text(cards: List[Dict[str, Any]], page: int) -> str:
    items, total, total_pages, page = _paginate(cards, page)

    if total <= 0:
        return (
            "📚 <b>Minha XColeção</b>\n\n"
            "Você ainda não possui xcards.\n"
            "Quando começarmos a liberar drops/pack/loja para esse sistema,\n"
            "eles vão aparecer aqui separados da coleção normal."
        )

    lines = [
        "📚 <b>Minha XColeção</b>",
        "",
        f"📦 <i>Total de xcards:</i> <b>{total}</b>",
        f"📖 <i>Página:</i> <b>{page}/{total_pages}</b>",
        "",
    ]

    for item in items:
        marker = _duplicate_marker(int(item["quantity"]))
        qty_text = f" x{int(item['quantity'])}" if int(item["quantity"]) > 1 else ""
        lines.append(
            f"🃏 <code>{item['card_id']}</code>. "
            f"<b>{item['name']}</b>{marker}{qty_text} — "
            f"<i>{item['title']}</i>"
        )

    return "\n".join(lines)


async def _send_owned_collection(update, context, page: int, *, edit: bool = False):
    user_id = update.effective_user.id
    cards = get_user_xcards(user_id)
    text = _build_owned_text(cards, page)
    _, _, total_pages, current_page = _paginate(cards, page)
    keyboard = _build_keyboard("xcolecao", user_id, current_page, total_pages)
    cover = cards[0]["image"] if cards and cards[0].get("image") else _default_cover()

    if edit and update.callback_query:
        message = update.callback_query.message
        try:
            if message.photo:
                await message.edit_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await message.edit_text(text=text, parse_mode="HTML", reply_markup=keyboard)
            return
        except Exception:
            pass

    if cover:
        await update.message.reply_photo(
            photo=cover,
            caption=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        await update.message.reply_html(text, reply_markup=keyboard)


async def _send_title_owned(update, context, title: Dict[str, Any], page: int, *, edit: bool = False):
    user_id = update.effective_user.id
    title_id = int(title["id"])
    all_cards = get_xcards_for_title(title_id)
    owned_cards = [item for item in get_user_xcards(user_id) if int(item["title_id"]) == title_id]

    cover = str(title.get("cover_image") or title.get("logo_image") or "").strip() or _default_cover()
    if not owned_cards:
        text = f"📚 Você ainda não tem xcards de <b>{title['name']}</b>."
        if edit and update.callback_query:
            message = update.callback_query.message
            try:
                await message.edit_media(
                    InputMediaPhoto(media=cover, caption=text, parse_mode="HTML")
                )
                return
            except Exception:
                try:
                    await message.edit_caption(caption=text, parse_mode="HTML", reply_markup=None)
                    return
                except Exception:
                    pass
        else:
            await update.message.reply_photo(photo=cover, caption=text, parse_mode="HTML")
        return

    items, _, total_pages, current_page = _paginate(owned_cards, page)
    lines = [
        f"📚 <b>{title['name']}</b>",
        "",
        f"📦 <i>Obtidos:</i> <b>{len(owned_cards)}/{len(all_cards)}</b>",
        f"📖 <i>Página:</i> <b>{current_page}/{total_pages}</b>",
        "",
    ]
    for item in items:
        marker = _duplicate_marker(int(item["quantity"]))
        qty_text = f" x{int(item['quantity'])}" if int(item["quantity"]) > 1 else ""
        lines.append(
            f"🃏 <code>{item['card_id']}</code>. "
            f"<b>{item['name']}</b>{marker}{qty_text} — "
            f"<code>{item['card_no']}</code>"
        )

    text = "\n".join(lines)
    keyboard = _build_keyboard("xcolecao_s", user_id, current_page, total_pages, title_id)

    if edit and update.callback_query:
        message = update.callback_query.message
        try:
            if message.photo:
                await message.edit_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await message.edit_text(text=text, parse_mode="HTML", reply_markup=keyboard)
            return
        except Exception:
            pass

    await update.message.reply_photo(
        photo=cover,
        caption=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def _send_title_missing(update, context, title: Dict[str, Any], page: int, *, edit: bool = False):
    user_id = update.effective_user.id
    title_id = int(title["id"])
    all_cards = get_xcards_for_title(title_id)
    owned_ids = {int(item["card_id"]) for item in get_user_xcards(user_id)}

    missing = [card for card in all_cards if int(card.get("id") or 0) not in owned_ids]
    cover = str(title.get("cover_image") or title.get("logo_image") or "").strip() or _default_cover()

    if not missing:
        text = f"🎉 Você completou os xcards de <b>{title['name']}</b>."
        if edit and update.callback_query:
            message = update.callback_query.message
            try:
                await message.edit_media(
                    InputMediaPhoto(media=cover, caption=text, parse_mode="HTML")
                )
                return
            except Exception:
                try:
                    await message.edit_caption(caption=text, parse_mode="HTML", reply_markup=None)
                    return
                except Exception:
                    pass
        else:
            await update.message.reply_photo(photo=cover, caption=text, parse_mode="HTML")
        return

    items, _, total_pages, current_page = _paginate(missing, page)
    lines = [
        f"🃏 <b>Faltam em {title['name']}</b>",
        "",
        f"📦 <i>Progresso:</i> <b>{len(all_cards) - len(missing)}/{len(all_cards)}</b>",
        f"📖 <i>Página:</i> <b>{current_page}/{total_pages}</b>",
        "",
    ]
    for card in items:
        lines.append(
            f"🃏 <code>{card['id']}</code>. "
            f"<b>{card['name']}</b>"
        )

    text = "\n".join(lines)
    keyboard = _build_keyboard("xcolecao_f", user_id, current_page, total_pages, title_id)

    if edit and update.callback_query:
        message = update.callback_query.message
        try:
            if message.photo:
                await message.edit_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await message.edit_text(text=text, parse_mode="HTML", reply_markup=keyboard)
            return
        except Exception:
            pass

    await update.message.reply_photo(
        photo=cover,
        caption=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def _send_title_gallery(update, context, title: Dict[str, Any], index: int, *, edit: bool = False):
    user_id = update.effective_user.id
    title_id = int(title["id"])
    cards = get_xcards_for_title(title_id)
    if not cards:
        text = f"❌ Não encontrei xcards para <b>{title['name']}</b>."
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
            await update.message.reply_html(text)
        return

    index = max(0, min(index, len(cards) - 1))
    card = cards[index]
    owned_map = {int(item["card_id"]): int(item["quantity"]) for item in get_user_xcards(user_id)}
    quantity = int(owned_map.get(int(card.get("id") or 0), 0))
    owned_total = sum(1 for item in cards if int(item.get("id") or 0) in owned_map)
    marker = _duplicate_marker(quantity)
    status = "✅ Tem na coleção" if quantity > 0 else "❔ Ainda falta"
    qty_text = f"x{quantity}" if quantity > 0 else "0x"
    rarity = str(card.get("rarity") or "-").strip() or "-"

    text = (
        f"🖼️ <b>{title['name']}</b>\n\n"
        f"📦 <b>{owned_total}/{len(cards)}</b>\n"
        f"📖 <b>{index + 1}/{len(cards)}</b>\n\n"
        f"🃏 <b>{card['name']}</b>{marker}\n"
        f"📦 <b>{qty_text}</b>"
    )

    keyboard = _build_gallery_keyboard("xcolecao_x", user_id, title_id, index, len(cards))
    image = str(card.get("image") or title.get("cover_image") or title.get("logo_image") or "").strip()

    if edit and update.callback_query:
        message = update.callback_query.message
        try:
            await message.edit_media(
                InputMediaPhoto(media=image, caption=text, parse_mode="HTML"),
                reply_markup=keyboard,
            )
            return
        except Exception:
            try:
                await message.edit_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
                return
            except Exception:
                pass

    await update.message.reply_photo(
        photo=image,
        caption=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def xcolecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    args = context.args
    lock = _get_lock(user_id)

    async with lock:
        if not args:
            await _send_owned_collection(update, context, 1, edit=False)
            return

        mode = str(args[0] or "").strip().lower()
        if mode not in ("s", "f", "x"):
            await _send_owned_collection(update, context, 1, edit=False)
            return

        title_query = " ".join(args[1:]).strip()
        title = find_xtitle(title_query)
        if not title:
            await update.effective_message.reply_text("❌ Obra de xcards não encontrada.")
            return

        if mode == "s":
            await _send_title_owned(update, context, title, 1, edit=False)
        elif mode == "f":
            await _send_title_missing(update, context, title, 1, edit=False)
        else:
            await _send_title_gallery(update, context, title, 0, edit=False)


async def xcolecao_callback(update, context):
    q = update.callback_query
    if not q:
        return

    if q.data == "xcolecao_noop":
        await q.answer()
        return

    if not _antiflood(q.from_user.id):
        await q.answer("Calma 🙂", show_alert=False)
        return

    try:
        _, owner_id, _extra, page = (q.data or "").split(":")
    except Exception:
        await q.answer()
        return

    if int(owner_id) != int(q.from_user.id):
        await q.answer("Essa xcoleção não é sua.", show_alert=True)
        return

    await q.answer()
    await _send_owned_collection(update, context, int(page), edit=True)


async def xcolecao_s_callback(update, context):
    q = update.callback_query
    if not q:
        return

    if not _antiflood(q.from_user.id):
        await q.answer("Calma 🙂", show_alert=False)
        return

    try:
        _, owner_id, title_id, page = (q.data or "").split(":")
    except Exception:
        await q.answer()
        return

    if int(owner_id) != int(q.from_user.id):
        await q.answer("Essa xcoleção não é sua.", show_alert=True)
        return

    title = find_xtitle(title_id)
    if not title:
        await q.answer("Obra não encontrada.", show_alert=True)
        return

    await q.answer()
    await _send_title_owned(update, context, title, int(page), edit=True)


async def xcolecao_f_callback(update, context):
    q = update.callback_query
    if not q:
        return

    if not _antiflood(q.from_user.id):
        await q.answer("Calma 🙂", show_alert=False)
        return

    try:
        _, owner_id, title_id, page = (q.data or "").split(":")
    except Exception:
        await q.answer()
        return

    if int(owner_id) != int(q.from_user.id):
        await q.answer("Essa xcoleção não é sua.", show_alert=True)
        return

    title = find_xtitle(title_id)
    if not title:
        await q.answer("Obra não encontrada.", show_alert=True)
        return

    await q.answer()
    await _send_title_missing(update, context, title, int(page), edit=True)


async def xcolecao_x_callback(update, context):
    q = update.callback_query
    if not q:
        return

    if not _antiflood(q.from_user.id):
        await q.answer("Calma 🙂", show_alert=False)
        return

    try:
        _, owner_id, title_id, index = (q.data or "").split(":")
    except Exception:
        await q.answer()
        return

    if int(owner_id) != int(q.from_user.id):
        await q.answer("Essa xcoleção não é sua.", show_alert=True)
        return

    title = find_xtitle(title_id)
    if not title:
        await q.answer("Obra não encontrada.", show_alert=True)
        return

    await q.answer()
    await _send_title_gallery(update, context, title, int(index), edit=True)
