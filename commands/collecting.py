"""Small Telegram entrypoints for the same Source MiniApp, never another frontend."""

from __future__ import annotations
import asyncio
import html
import logging
import os
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent,
)
from telegram.error import BadRequest
from source_features import collection
from utils.miniapp_links import miniapp_url, miniapp_entrypoint
from utils.gatekeeper import gatekeeper
from utils.runtime_guard import rate_limiter

log = logging.getLogger(__name__)
ENTRIES = {
    "colecionar": ("collecting", "Coleção, desejos e proteção", {}),
    "cofre": ("collecting", "Cofre da coleção", {"view": "protected"}),
    "desejos": ("collecting", "Lista de desejos", {"view": "wishes"}),
    "mercado": ("marketplace", "Mercado de personagens", {}),
    "oficina": ("workshop", "Oficina de duplicatas", {}),
    "eventos": ("events", "Eventos e expedições", {}),
    "agora": ("activity", "Disponível agora", {}),
    "ajuda": ("help", "Central de ajuda", {}),
    "identificar": ("identify", "Identificar uma cena", {}),
}


def private_url(payload: str) -> str:
    username = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
    return f"https://t.me/{username}?start={payload}"


async def open_feature(update, context, key: str):
    message = update.effective_message
    if not message or not update.effective_user or key not in ENTRIES:
        return
    tab, title, params = ENTRIES[key]
    if update.effective_chat and update.effective_chat.type != "private":
        await message.reply_html(
            f"<b>{html.escape(title)}</b>\n\nAbra no privado para acessar sua conta com segurança. Tudo faz parte do mesmo aplicativo do Source.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Abrir no privado", url=private_url("source_" + key)
                        )
                    ]
                ]
            ),
        )
        return
    allowed, notice = await gatekeeper(update, context)
    if not allowed:
        if notice:
            await message.reply_html(notice)
        return
    await message.reply_html(
        f"<b>{html.escape(title)}</b>\n\nUse sua coleção e suas preferências no aplicativo único do Source. Nenhuma operação é feita sem sua confirmação.",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Abrir " + title,
                        web_app=WebAppInfo(url=miniapp_url(tab, **params)),
                    )
                ]
            ]
        ),
    )


async def collecting_command(update, context):
    text = (getattr(update.effective_message, "text", "") or "").strip()
    key = text.split()[0].split("@")[0].lstrip("/").lower() if text else "colecionar"
    await open_feature(update, context, key)


async def start_feature(update, context, payload: str) -> bool:
    if payload.startswith("source_") and payload[7:] in ENTRIES:
        await open_feature(update, context, payload[7:])
        return True
    if payload.startswith("sourcecard_") and payload[11:].isdigit():
        from cards_service import get_character_by_id

        card = get_character_by_id(int(payload[11:]))
        if card and update.effective_message:
            # /start has already completed its terms and membership checks.
            await update.effective_message.reply_html(
                f"<b>{html.escape(card['name'])}</b>\n{html.escape(card.get('anime', ''))}",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Ver no Source",
                                web_app=WebAppInfo(
                                    url=miniapp_url(
                                        "cards", view="characters", q=card["name"]
                                    )
                                ),
                            )
                        ]
                    ]
                ),
            )
            return True
    return False


def inline_cards(uid: int, search: str, offset: int) -> dict:
    """Explicit opt-in only. One bounded page; no per-card database counts."""
    if not collection.settings(uid)["share_inline"]:
        return {"items": [], "has_more": False}
    return collection.cards(uid, search, "owned", offset, 20)


async def inline_showcase(update, context):
    query = update.inline_query
    if not query or not query.from_user:
        return
    text = (query.query or "").strip()
    if not text.lower().startswith(("colecao", "coleção")):
        await query.answer([], cache_time=0, is_personal=True)
        return
    search = text.partition(" ")[2][:80]
    offset = int(query.offset) if str(query.offset or "").isdigit() else 0
    offset = min(offset, 10000)
    if not await rate_limiter.allow(f"collecting-inline:{query.from_user.id}", 12, 60):
        await query.answer([], cache_time=0, is_personal=True)
        return
    try:
        page = await asyncio.to_thread(inline_cards, query.from_user.id, search, offset)
        results = []
        for card in page["items"]:
            name = html.escape(card["name"])
            work = html.escape(card["anime"])
            image = card.get("image") or ""
            if image.startswith("/api/image-proxy?"):
                image = miniapp_entrypoint().removesuffix("/menu") + image
            if image.startswith(
                (
                    "https://s4.anilist.co/",
                    "https://img.anili.st/",
                    miniapp_entrypoint().removesuffix("/menu") + "/api/image-proxy?",
                )
            ):
                results.append(
                    InlineQueryResultPhoto(
                        id=f"collection-{card['id']}",
                        photo_url=image,
                        thumbnail_url=image,
                        title=card["name"],
                        caption=f"<b>{name}</b>\n{work}\n\nNa minha coleção do Source · {card['quantity']} cópia(s).",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        "Ver personagem",
                                        url=private_url(f"sourcecard_{card['id']}"),
                                    )
                                ]
                            ]
                        ),
                    )
                )
                continue
            # Article fallback avoids sending an unvalidated external image URL to Telegram.
            # Private identity is not embedded; the user explicitly chooses what to share.
            results.append(
                InlineQueryResultArticle(
                    id=f"collection-{card['id']}",
                    title=card["name"],
                    description=f"{card['anime']} · {card['quantity']} cópia(s)",
                    input_message_content=InputTextMessageContent(
                        f"<b>{name}</b>\n{work}\n\nNa minha coleção do Source · {card['quantity']} cópia(s).",
                        parse_mode="HTML",
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "Ver personagem",
                                    url=private_url(f"sourcecard_{card['id']}"),
                                )
                            ]
                        ]
                    ),
                )
            )
        await query.answer(
            results,
            cache_time=0,
            is_personal=True,
            next_offset=str(offset + 20) if page["has_more"] else "",
        )
    except BadRequest as exc:
        if (
            "query is too old" not in str(exc).lower()
            and "query_id_invalid" not in str(exc).lower()
        ):
            raise
    except Exception:
        log.exception("inline showcase failed")
        try:
            await query.answer([], cache_time=0, is_personal=True)
        except BadRequest:
            pass
