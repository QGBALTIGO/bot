from __future__ import annotations

import html

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry
from xcards_service import get_xcards_for_character, resolve_xcard_query


def _caption(card: dict) -> str:
    name = html.escape(str(card.get("name") or "XCARD"), quote=False)
    title = html.escape(str(card.get("title") or "Obra desconhecida"), quote=False)
    number = html.escape(str(card.get("card_no") or "—"), quote=False)
    rarity = html.escape(str(card.get("rarity") or "—"), quote=False)
    bp = int(card.get("bp_value") or 0)
    card_id = int(card.get("id") or 0)
    return (
        "🃏 <b>XCARD • UNION ARENA</b>\n\n"
        f"👤 <b>{name}</b>\n"
        f"🎬 {title}\n\n"
        f"🔖 <b>Nº:</b> <code>{number}</code>\n"
        f"✨ <b>Raridade:</b> {rarity}\n"
        f"⚔️ <b>BP:</b> {bp:,}\n"
        f"🆔 <b>ID:</b> <code>{card_id}</code>\n\n"
        "<i>XCards são o baralho competitivo usado no sistema de duelo.</i>"
    ).replace(",", ".")


async def xcard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    if not context.args:
        await message.reply_html(
            "🃏 <b>XCard</b>\n\n"
            "Consulte por personagem, número ou ID:\n"
            "<code>/xcard Levi</code>\n"
            "<code>/xcard UE10BT/AOT-1-051</code>\n\n"
            "Use <code>/xcolecao</code> para ver as cartas que você possui e o mercado diário."
        )
        return

    query = " ".join(context.args).strip()
    try:
        resolved = resolve_xcard_query(query)
    except (FileNotFoundError, ValueError):
        await message.reply_text("❌ O catálogo XCards está indisponível no momento.")
        return

    card = None
    if resolved.get("type") == "card":
        card = resolved.get("card")
    elif resolved.get("type") == "character":
        character = resolved.get("character") or {}
        variants = get_xcards_for_character(int(character.get("id") or 0))
        card = variants[0] if variants else None

    if not card:
        await message.reply_text("❌ Não encontrei esse personagem ou XCard.")
        return

    image = str(card.get("image") or "").strip()
    caption = _caption(card)
    if image:
        try:
            await message.reply_photo(photo=image, caption=caption, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.reply_html(caption)


async def xcolecao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="XColeção",
            description=(
                "Veja seus XCards Union Arena, compare BP e aproveite as ofertas diárias "
                "que alimentam o sistema competitivo de duelos."
            ),
            button="🃏 Abrir XColeção",
            path="/xcollection",
            icon="🃏",
        ),
    )
