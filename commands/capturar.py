import asyncio
import secrets
import time
import unicodedata
from html import escape
from typing import Any, Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from database import (
    add_card_copy,
    add_coin,
    add_progress_xp,
    create_or_get_user,
    get_user_card_quantity,
    get_user_coins,
    remove_coin,
    touch_user_identity,
)
from handlers.capture_spawn import (
    ACTIVE_SPAWNS,
    PURCHASE_COST,
    PURCHASE_WINDOW_SECONDS,
    XP_REWARD,
)
from utils.runtime_guard import lock_manager


_capture_locks: Dict[int, asyncio.Lock] = {}
PURCHASE_OFFERS: Dict[str, Dict[str, Any]] = {}


def _get_capture_lock(chat_id: int) -> asyncio.Lock:
    lock = _capture_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _capture_locks[chat_id] = lock
    return lock


def normalize(text: str) -> str:
    text = str(text or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in text)
    return " ".join(text.strip().split())


def _tokens(text: str) -> List[str]:
    return [item for item in normalize(text).split() if item]


def _matches_capture_name(character_name: str, guess_text: str) -> bool:
    full_name = normalize(character_name)
    guess = normalize(guess_text)

    if not full_name or not guess:
        return False

    if guess == full_name:
        return True

    name_tokens = _tokens(character_name)
    guess_tokens = _tokens(guess_text)

    if not name_tokens or not guess_tokens:
        return False

    if len(guess_tokens) == 1:
        probe = guess_tokens[0]

        if probe in name_tokens:
            return True

        if len(probe) >= 3 and any(token.startswith(probe) for token in name_tokens):
            return True

        if len(probe) >= 4 and probe in full_name.replace(" ", ""):
            return True

        return False

    if len(guess_tokens) > len(name_tokens):
        return False

    idx = 0
    for probe in guess_tokens:
        matched = False
        while idx < len(name_tokens):
            token = name_tokens[idx]
            idx += 1
            if probe == token or (len(probe) >= 3 and token.startswith(probe)):
                matched = True
                break
        if not matched:
            return False

    return True


def _display_name(user) -> str:
    full_name = " ".join(
        part
        for part in [
            (getattr(user, "first_name", "") or "").strip(),
            (getattr(user, "last_name", "") or "").strip(),
        ]
        if part
    ).strip()

    if full_name:
        return full_name

    username = (getattr(user, "username", "") or "").strip()
    if username:
        return username

    return "Cacador"


def _player_link(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={int(user_id)}">{escape(name)}</a>'


def _format_window(seconds: int) -> str:
    total = max(int(seconds), 0)
    minutes, sec = divmod(total, 60)

    if minutes <= 0:
        return f"{sec}s"
    if sec == 0:
        return f"{minutes} min"
    return f"{minutes} min {sec}s"


def _level_up_line(progress: Dict[str, Any]) -> str:
    if not progress:
        return ""

    old_level = int(progress.get("old_level") or 1)
    new_level = int(progress.get("new_level") or old_level)

    if new_level > old_level:
        return f"🔥 Subiu para o nivel <b>{new_level}</b>\n"

    return ""


def _build_offer_caption(
    offer: Dict[str, Any],
    mode: str,
    *,
    quantity_after: int = 0,
    coins_left: int = 0,
) -> str:
    buyer_link = _player_link(offer["buyer_user_id"], offer["buyer_name"])
    character_name = escape(str(offer.get("character_name") or "Sem nome"))
    anime_name = escape(str(offer.get("anime_name") or "Obra desconhecida"))
    level_up = str(offer.get("level_up_line") or "")

    xp_block = f"⭐ Claim garantido: <b>+{offer['xp_reward']} XP</b>\n{level_up}".rstrip()

    if mode == "available":
        return (
            "✦ <b>CLAIM FECHADO</b>\n\n"
            f"{buyer_link} levou o claim de <b>{character_name}</b>\n"
            f"🎬 <b>{anime_name}</b>\n\n"
            f"{xp_block}\n"
            f"🛒 Carta exclusiva: <b>{offer['price']} coins</b>\n"
            f"🔒 So o captor pode comprar\n"
            f"⏳ Janela de compra: <b>{offer['window_text']}</b>\n\n"
            "Se quiser transformar o claim em carta, garante agora no botao abaixo."
        )

    if mode == "purchased":
        if quantity_after <= 1:
            collection_line = "📚 Primeira copia enviada para a colecao"
        else:
            collection_line = f"📚 Agora voce tem <b>{quantity_after}</b> copias dessa carta"

        return (
            "✦ <b>CARTA GARANTIDA</b>\n\n"
            f"{buyer_link} adicionou <b>{character_name}</b> a colecao\n"
            f"🎬 <b>{anime_name}</b>\n\n"
            f"{xp_block}\n"
            f"🪙 -{offer['price']} coins\n"
            f"{collection_line}\n"
            f"💰 Saldo atual: <b>{coins_left}</b> coins"
        )

    return (
        "✦ <b>CLAIM ENCERRADO</b>\n\n"
        f"{buyer_link} levou <b>{character_name}</b>\n"
        f"🎬 <b>{anime_name}</b>\n\n"
        f"{xp_block}\n"
        "A janela de compra fechou, entao a carta nao entrou na colecao."
    )


def _offer_keyboard(offer_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"🛒 Garantir carta ({PURCHASE_COST} coins)",
                    callback_data=f"capturebuy:{offer_id}",
                )
            ]
        ]
    )


async def _send_offer_message(
    message: Message,
    image: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
):
    try:
        sent = await message.reply_photo(
            photo=image,
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return sent, True
    except Exception:
        sent = await message.reply_html(
            caption,
            reply_markup=reply_markup,
        )
        return sent, False


async def _edit_offer_message(
    context: ContextTypes.DEFAULT_TYPE,
    offer: Dict[str, Any],
    caption: str,
    reply_markup=None,
) -> bool:
    try:
        if offer.get("has_photo"):
            await context.bot.edit_message_caption(
                chat_id=offer["chat_id"],
                message_id=offer["message_id"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return True

        await context.bot.edit_message_text(
            chat_id=offer["chat_id"],
            message_id=offer["message_id"],
            text=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        return False


async def _expire_offer_later(offer_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    offer = PURCHASE_OFFERS.get(offer_id)
    if not offer:
        return

    delay = max(float(offer["expires_at"]) - time.time(), 0.0)
    await asyncio.sleep(delay)

    lock = await lock_manager.acquire(f"capturebuy:{offer_id}")
    try:
        offer = PURCHASE_OFFERS.get(offer_id)
        if not offer:
            return

        if time.time() < float(offer["expires_at"]):
            return

        PURCHASE_OFFERS.pop(offer_id, None)
        await _edit_offer_message(
            context,
            offer,
            _build_offer_caption(offer, "expired"),
            reply_markup=None,
        )
    finally:
        lock.release()


async def capturar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    if update.effective_chat.type not in ("group", "supergroup"):
        return

    if not context.args:
        return

    chat_id = update.effective_chat.id
    lock = _get_capture_lock(chat_id)

    async with lock:
        spawn = ACTIVE_SPAWNS.get(chat_id)
        if not spawn:
            return

        character = spawn.get("character") or {}
        if not _matches_capture_name(
            str(character.get("name") or ""),
            " ".join(context.args),
        ):
            return

        ACTIVE_SPAWNS.pop(chat_id, None)

        user = update.effective_user
        create_or_get_user(user.id)
        touch_user_identity(
            user.id,
            getattr(user, "username", "") or "",
            _display_name(user),
        )

        progress: Dict[str, Any] = {}
        try:
            progress = add_progress_xp(user.id, XP_REWARD) or {}
        except Exception:
            progress = {}

        created_at = time.time()
        offer_id = secrets.token_hex(6)
        offer = {
            "offer_id": offer_id,
            "chat_id": chat_id,
            "buyer_user_id": int(user.id),
            "buyer_name": _display_name(user),
            "character_id": int(character.get("id") or 0),
            "character_name": str(character.get("name") or "Sem nome"),
            "anime_name": str(character.get("anime") or "Obra desconhecida"),
            "image": str(character.get("image") or "").strip(),
            "price": PURCHASE_COST,
            "xp_reward": XP_REWARD,
            "level_up_line": _level_up_line(progress),
            "created_at": created_at,
            "expires_at": created_at + PURCHASE_WINDOW_SECONDS,
            "window_text": _format_window(PURCHASE_WINDOW_SECONDS),
            "message_id": int(spawn.get("message_id") or 0),
            "has_photo": True,
        }

        caption = _build_offer_caption(offer, "available")
        edited = False
        if offer["message_id"]:
            edited = await _edit_offer_message(
                context,
                offer,
                caption,
                reply_markup=_offer_keyboard(offer_id),
            )

        if not edited:
            sent, has_photo = await _send_offer_message(
                update.message,
                offer["image"],
                caption,
                _offer_keyboard(offer_id),
            )
            offer["message_id"] = getattr(sent, "message_id", 0)
            offer["has_photo"] = has_photo

        PURCHASE_OFFERS[offer_id] = offer

        asyncio.create_task(_expire_offer_later(offer_id, context))


async def capture_purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    if not query or not user or not query.data:
        return

    _, _, offer_id = query.data.partition(":")
    if not offer_id:
        await query.answer()
        return

    lock = await lock_manager.acquire(f"capturebuy:{offer_id}")
    try:
        offer = PURCHASE_OFFERS.get(offer_id)
        if not offer:
            await query.answer("Essa oferta ja acabou.", show_alert=True)
            return

        if time.time() >= float(offer["expires_at"]):
            PURCHASE_OFFERS.pop(offer_id, None)
            await _edit_offer_message(
                context,
                offer,
                _build_offer_caption(offer, "expired"),
                reply_markup=None,
            )
            await query.answer("A oferta exclusiva expirou.", show_alert=True)
            return

        if int(user.id) != int(offer["buyer_user_id"]):
            await query.answer("So quem capturou pode comprar essa carta.", show_alert=True)
            return

        create_or_get_user(user.id)
        touch_user_identity(
            user.id,
            getattr(user, "username", "") or "",
            _display_name(user),
        )

        price = int(offer["price"])
        coins_before = get_user_coins(user.id)
        if coins_before < price:
            missing = price - coins_before
            await query.answer(
                f"Faltam {missing} coins. Usa /daily e continua jogando.",
                show_alert=True,
            )
            return

        quantity_before = get_user_card_quantity(user.id, int(offer["character_id"]))

        if not remove_coin(user.id, price):
            await query.answer(
                "Nao consegui debitar suas coins agora. Tenta de novo em instantes.",
                show_alert=True,
            )
            return

        try:
            add_card_copy(user.id, int(offer["character_id"]), 1)
        except Exception:
            add_coin(user.id, price)
            await query.answer(
                "Nao consegui enviar a carta para a colecao. Suas coins foram devolvidas.",
                show_alert=True,
            )
            return

        coins_left = get_user_coins(user.id)
        quantity_after = quantity_before + 1
        PURCHASE_OFFERS.pop(offer_id, None)

        try:
            from commands.colecao import clear_user_collection_cache

            clear_user_collection_cache(user.id)
        except Exception:
            pass

        await _edit_offer_message(
            context,
            offer,
            _build_offer_caption(
                offer,
                "purchased",
                quantity_after=quantity_after,
                coins_left=coins_left,
            ),
            reply_markup=None,
        )
        await query.answer("Carta comprada e enviada para sua colecao!", show_alert=True)
    finally:
        lock.release()
