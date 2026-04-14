import asyncio
import secrets
import time
import unicodedata
from html import escape
from typing import Any, Dict

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
    return " ".join(text.strip().split())


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

    xp_block = f"⭐ +{offer['xp_reward']} XP garantidos\n{level_up}".rstrip()

    if mode == "available":
        return (
            f"🏆 {buyer_link} foi mais rapido e capturou <b>{character_name}</b>!\n"
            f"🎬 {anime_name}\n\n"
            f"{xp_block}\n"
            f"🪙 Compra exclusiva liberada por <b>{offer['price']} coins</b>\n"
            f"⏳ So o captor pode comprar durante <b>{offer['window_text']}</b>\n\n"
            "Se quiser transformar essa captura em carta, toca no botao abaixo."
        )

    if mode == "purchased":
        if quantity_after <= 1:
            collection_line = "📚 Nova carta enviada para a sua colecao"
        else:
            collection_line = f"📚 Agora voce tem <b>{quantity_after}</b> copias dessa carta"

        return (
            f"🛒 <b>Compra concluida!</b>\n\n"
            f"{buyer_link} garantiu <b>{character_name}</b> para a colecao.\n"
            f"🎬 {anime_name}\n\n"
            f"{xp_block}\n"
            f"🪙 -{offer['price']} coins\n"
            f"{collection_line}\n"
            f"💰 Saldo atual: <b>{coins_left}</b> coins"
        )

    return (
        f"⌛ <b>Oferta encerrada.</b>\n\n"
        f"{buyer_link} capturou <b>{character_name}</b>.\n"
        f"🎬 {anime_name}\n\n"
        f"{xp_block}\n"
        "Os XP foram garantidos, mas a carta nao entrou na colecao a tempo."
    )


def _offer_keyboard(offer_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"🪙 Comprar por {PURCHASE_COST} coins",
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
) -> None:
    try:
        if offer.get("has_photo"):
            await context.bot.edit_message_caption(
                chat_id=offer["chat_id"],
                message_id=offer["message_id"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return

        await context.bot.edit_message_text(
            chat_id=offer["chat_id"],
            message_id=offer["message_id"],
            text=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception:
        pass


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
        correct_name = normalize(character.get("name", ""))
        guess = normalize(" ".join(context.args))

        if not correct_name or guess != correct_name:
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
        }

        caption = _build_offer_caption(offer, "available")
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
