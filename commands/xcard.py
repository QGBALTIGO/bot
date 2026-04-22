import html
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

from database import (
    get_user_xcard_quantity,
    get_xcard_owner_count,
    get_xcard_total_copies,
)
from xcards_service import (
    get_xcards_for_character,
    resolve_xcard_query,
)


def _trim_text(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def _dup_emoji(qty: int) -> str:
    if qty >= 20:
        return " 🏆"
    if qty >= 15:
        return " 🌟"
    if qty >= 10:
        return " ⭐"
    if qty >= 5:
        return " 💫"
    if qty >= 2:
        return " ✨"
    return ""


def _build_variant_keyboard(
    owner_id: int,
    character_id: int,
    index: int,
    total: int,
    card_id: int,
) -> InlineKeyboardMarkup:
    buttons = []

    if total > 1:
        if index > 0:
            buttons.append(
                InlineKeyboardButton(
                    "◀️",
                    callback_data=f"xcardnav:{owner_id}:{character_id}:{index - 1}",
                )
            )

        buttons.append(
            InlineKeyboardButton(
                f"🎴 {index + 1}/{total}",
                callback_data="xcardnoop",
            )
        )

        if index < (total - 1):
            buttons.append(
                InlineKeyboardButton(
                    "▶️",
                    callback_data=f"xcardnav:{owner_id}:{character_id}:{index + 1}",
                )
            )

    stats_button = InlineKeyboardButton(
        "📊 Stats",
        callback_data=f"xcardstats:{card_id}",
    )

    if buttons:
        return InlineKeyboardMarkup([buttons, [stats_button]])
    return InlineKeyboardMarkup([[stats_button]])


def _find_card_index(cards: List[Dict[str, Any]], card_id: int) -> int:
    for index, card in enumerate(cards):
        if int(card.get("id") or 0) == int(card_id):
            return index
    return 0


def _safe_pt_br(card: Dict[str, Any], key: str, fallback_key: Optional[str] = None) -> str:
    pt_br = card.get("pt_br") if isinstance(card.get("pt_br"), dict) else {}
    value = str(pt_br.get(key) or "").strip()
    if value:
        return value
    if fallback_key:
        return str(card.get(fallback_key) or "").strip()
    return ""


def _build_caption(
    card: Dict[str, Any],
    quantity: int,
    current_index: int,
    total_variants: int,
) -> str:
    card_id = int(card.get("id") or 0)
    character_id = int(card.get("character_id") or 0)

    title = _safe_pt_br(card, "anime", "title") or "Obra desconhecida"
    rarity = _safe_pt_br(card, "raridade", "rarity") or "-"
    required_energy = _safe_pt_br(card, "energia_necessaria", "required_energy") or "-"
    ap_cost = _safe_pt_br(card, "custo_ap", "ap_cost") or "-"
    card_type = _safe_pt_br(card, "tipo_de_cartao", "card_type") or "-"
    power = _safe_pt_br(card, "pa", "bp") or "-"
    affinity = _safe_pt_br(card, "afinidade", "affinity") or "-"
    generated_energy_values = []
    pt_br = card.get("pt_br") if isinstance(card.get("pt_br"), dict) else {}
    for item in pt_br.get("energia_gerada") or card.get("generated_energy") or []:
        text = str(item or "").strip()
        if text:
            generated_energy_values.append(text)
    generated_energy = ", ".join(generated_energy_values) if generated_energy_values else "-"

    effect = _safe_pt_br(card, "efeito", "effect") or "-"
    trigger = _safe_pt_br(card, "acionar", "trigger") or "-"
    product_name = str(card.get("product_name") or "").strip() or "-"
    alt_art = bool(card.get("alt_art"))
    name = str(card.get("name") or "Sem nome")
    name_with_dup = name + _dup_emoji(quantity)

    presets = [
        {"product": 70, "affinity": 180, "effect": 230, "trigger": 150},
        {"product": 50, "affinity": 130, "effect": 170, "trigger": 100},
        {"product": 36, "affinity": 90, "effect": 110, "trigger": 70},
    ]

    for limits in presets:
        lines = [
            f"╭─ 🃏 <b>XCard</b> <code>#{card_id}</code>",
            "│",
            f"│ 👤 <b>{html.escape(name_with_dup)}</b>",
            f"│ 🎬 <i>{html.escape(title)}</i>",
            "│",
            f"│ ✨ <b>Raridade:</b> <i>{html.escape(rarity)}</i>",
            f"│ 🛡️ <b>BP:</b> <i>{html.escape(power)}</i>",
            "│",
            f"╰─ 📚 <b>{quantity}x na sua xcoleção</b>",
        ]
        caption = "\n".join(lines)
        if len(caption) <= 1024:
            return caption

    if len(caption) > 1024:
        caption = caption[:1021] + "..."

    return caption


async def _send_xcard_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    cards: List[Dict[str, Any]],
    index: int,
    *,
    edit: bool = False,
) -> None:
    if not cards:
        target = update.callback_query.message if update.callback_query else update.message
        if target:
            await target.reply_text("Nenhuma variante encontrada para esse personagem.")
        return

    index = max(0, min(index, len(cards) - 1))
    card = cards[index]
    user_id = update.effective_user.id
    card_id = int(card.get("id") or 0)
    character_id = int(card.get("character_id") or 0)
    image = str(card.get("image") or "").strip()

    quantity = int(get_user_xcard_quantity(user_id, card_id) or 0)
    caption = _build_caption(card, quantity, index, len(cards))
    keyboard = _build_variant_keyboard(
        owner_id=user_id,
        character_id=character_id,
        index=index,
        total=len(cards),
        card_id=card_id,
    )

    if edit and update.callback_query:
        message = update.callback_query.message
        try:
            if image and message.photo:
                await message.edit_media(
                    media=InputMediaPhoto(
                        media=image,
                        caption=caption,
                        parse_mode="HTML",
                    ),
                    reply_markup=keyboard,
                )
            elif image:
                await message.reply_photo(
                    photo=image,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            else:
                await message.edit_text(
                    text=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            return
        except Exception:
            try:
                await message.edit_text(
                    text=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return
            except Exception:
                pass

    if image:
        await update.message.reply_photo(
            photo=image,
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        await update.message.reply_html(caption, reply_markup=keyboard)


async def xcard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    if not context.args:
        await update.message.reply_html(
            "🃏 <b>XCard</b>\n\n"
            "Use:\n"
            "<code>/xcard Nome do personagem</code>\n"
            "<code>/xcard ID do personagem</code>\n"
            "<code>/xcard ID do card</code>\n"
            "<code>/xcard UE10BT/AOT-1-051</code>"
        )
        return

    query = " ".join(context.args).strip()

    try:
        resolved = resolve_xcard_query(query)
    except FileNotFoundError as exc:
        await update.message.reply_text(str(exc))
        return
    except Exception as exc:
        await update.message.reply_text(f"Erro ao carregar os xcards: {exc}")
        return

    if resolved.get("type") == "none":
        await update.message.reply_text("❌ Não encontrei esse personagem/card nos xcards.")
        return

    if resolved.get("type") == "card":
        card = resolved["card"]
        cards = get_xcards_for_character(int(card.get("character_id") or 0))
        index = _find_card_index(cards, int(card.get("id") or 0))
        await _send_xcard_message(update, context, cards, index, edit=False)
        return

    character = resolved["character"]
    cards = get_xcards_for_character(int(character.get("id") or 0))
    await _send_xcard_message(update, context, cards, 0, edit=False)


async def xcard_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    if q.data == "xcardnoop":
        await q.answer()
        return

    try:
        _, owner_id, character_id, index = (q.data or "").split(":")
    except Exception:
        await q.answer()
        return

    if int(owner_id) != int(q.from_user.id):
        await q.answer("Esse xcard não é seu.", show_alert=True)
        return

    cards = get_xcards_for_character(int(character_id))
    if not cards:
        await q.answer("Não encontrei as variantes.", show_alert=True)
        return

    await q.answer()
    await _send_xcard_message(update, context, cards, int(index), edit=True)


async def xcard_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    try:
        _, card_id = (q.data or "").split(":")
        parsed_card_id = int(card_id)
    except Exception:
        await q.answer()
        return

    owners = int(get_xcard_owner_count(parsed_card_id) or 0)
    total_copies = int(get_xcard_total_copies(parsed_card_id) or 0)

    await q.answer(
        f"📊 Usuários com esse xcard: {owners}\n"
        f"📦 Total de cópias: {total_copies}",
        show_alert=True,
    )
