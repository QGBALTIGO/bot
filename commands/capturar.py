import asyncio
import secrets
import time
import unicodedata
from html import escape
from typing import Any, Dict, List, Optional

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
    finish_spawn_as_escaped,
    get_chat_spawn_result,
    record_chat_spawn_result,
)
from utils.runtime_guard import lock_manager


_capture_locks: Dict[int, asyncio.Lock] = {}
PURCHASE_OFFERS: Dict[str, Dict[str, Any]] = {}
_feedback_timestamps: Dict[str, float] = {}


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

    used_indexes = set()
    for probe in guess_tokens:
        matched = False
        for idx, token in enumerate(name_tokens):
            if idx in used_indexes:
                continue
            if probe == token or (len(probe) >= 3 and token.startswith(probe)):
                used_indexes.add(idx)
                matched = True
                break
        if not matched:
            return False

    return True


def _time_left_text(expires_at: float) -> str:
    return _format_window(max(int(expires_at - time.time()), 0))


def _feedback_key(chat_id: int, user_id: int, kind: str) -> str:
    return f"{int(chat_id)}:{int(user_id)}:{kind}"


def _feedback_allowed(chat_id: int, user_id: int, kind: str, window: float = 1.5) -> bool:
    now = time.monotonic()
    key = _feedback_key(chat_id, user_id, kind)
    last = _feedback_timestamps.get(key, 0.0)
    if now - last < window:
        return False
    _feedback_timestamps[key] = now
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
            "✨ <b>O VISITANTE FOI CAPTURADO</b>\n\n"
            f"<blockquote>👤 <b>{character_name}</b>\n🎬 <b>{anime_name}</b></blockquote>\n\n"
            f"{buyer_link} acertou o visitante e fechou a captura com sucesso.\n\n"
            "<blockquote>"
            f"{xp_block}\n"
            f"🪙 Compra exclusiva da carta liberada por <b>{offer['price']} coins</b>\n"
            "🔒 Só o captor pode usar o botão abaixo"
            "</blockquote>\n\n"
            "<i>Continuem conversando para atrair o próximo visitante.</i>"
        )

    if mode == "purchased":
        if quantity_after <= 1:
            collection_line = "📚 Primeira copia enviada para a colecao"
        else:
            collection_line = f"📚 Agora voce tem <b>{quantity_after}</b> copias dessa carta"

        return (
            "🛒 <b>CARTA GARANTIDA</b>\n\n"
            f"<blockquote>👤 <b>{character_name}</b>\n🎬 <b>{anime_name}</b></blockquote>\n\n"
            f"{buyer_link} comprou a carta com sucesso.\n\n"
            "<blockquote>"
            f"{xp_block}\n"
            f"🪙 -{offer['price']} coins\n"
            f"{collection_line}\n"
            f"💰 Saldo atual: <b>{coins_left}</b> coins"
            "</blockquote>\n\n"
            "<i>Continuem conversando para atrair o próximo visitante.</i>"
        )

    return (
        "⌛ <b>JANELA DE COMPRA ENCERRADA</b>\n\n"
        f"<blockquote>👤 <b>{character_name}</b>\n🎬 <b>{anime_name}</b></blockquote>\n\n"
        f"{buyer_link} garantiu o claim e recebeu os XP, mas a janela exclusiva de compra acabou.\n\n"
        f"<blockquote>{xp_block}</blockquote>\n\n"
        "<i>Continuem conversando para chamar o próximo visitante.</i>"
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


async def _reply_context(message: Message, text: str) -> None:
    await message.reply_html(text)


def _build_usage_text(active: bool) -> str:
    status_line = (
        "<i>O visitante ainda está em campo. Se liga no formato e tenta de novo.</i>"
        if active
        else "<i>No momento não há visitante ativo neste chat, mas o comando funciona assim.</i>"
    )

    return (
        "🎯 <b>COMO CAPTURAR</b>\n\n"
        f"{status_line}\n\n"
        "<blockquote>"
        "Use assim:\n"
        "<code>/capturar Nome do Personagem</code>\n\n"
        "Exemplo:\n"
        "<code>/capturar Victor Nikiforov</code>"
        "</blockquote>\n\n"
        "<i>Vale nome completo, primeiro nome ou sobrenome. Capricha no chute.</i>"
    )


def _build_wrong_name_text(character: Dict[str, Any], expires_at: float) -> str:
    return (
        "❌ <b>TENTATIVA FALHOU</b>\n\n"
        "<i>Esse nome não corresponde ao visitante atual.</i>\n\n"
        "<blockquote>"
        "Use <code>/capturar nome</code> com o nome do personagem exibido.\n"
        "Vale nome completo, primeiro nome ou sobrenome.\n"
        f"⏳ Tempo restante: <b>{_time_left_text(expires_at)}</b>"
        "</blockquote>\n\n"
        "<i>O spawn continua ativo. Respira e tenta de novo.</i>"
    )


def _build_no_spawn_text() -> str:
    return (
        "🕊 <b>NENHUM VISITANTE EM CAMPO</b>\n\n"
        "<i>No momento não há nenhum spawn ativo neste chat.</i>\n\n"
        "<blockquote>"
        "Quando um visitante aparecer, use:\n"
        "<code>/capturar Nome do Personagem</code>\n\n"
        "Exemplo:\n"
        "<code>/capturar Victor Nikiforov</code>"
        "</blockquote>\n\n"
        "<i>Continuem conversando para atrair o próximo evento.</i>"
    )


def _build_captured_text(result: Dict[str, Any]) -> str:
    winner_name = str(result.get("winner_name") or "Outro jogador")
    winner_id = int(result.get("winner_user_id") or 0)
    winner = _player_link(winner_id, winner_name) if winner_id else escape(winner_name)
    character_name = escape(str(result.get("character_name") or "Sem nome"))
    anime_name = escape(str(result.get("anime_name") or "Obra desconhecida"))

    return (
        "🏁 <b>CAPTURA ENCERRADA</b>\n\n"
        f"<blockquote>👤 <b>{character_name}</b>\n🎬 <b>{anime_name}</b></blockquote>\n\n"
        f"<i>Esse visitante já foi capturado por {winner}. Agora é esperar o próximo.</i>"
    )


def _build_escaped_text(result: Dict[str, Any]) -> str:
    character_name = escape(str(result.get("character_name") or "Sem nome"))
    anime_name = escape(str(result.get("anime_name") or "Obra desconhecida"))

    return (
        "💨 <b>VISITANTE INDISPONÍVEL</b>\n\n"
        f"<blockquote>👤 <b>{character_name}</b>\n🎬 <b>{anime_name}</b></blockquote>\n\n"
        "<i>Esse visitante já foi embora. Continuem conversando para chamar o próximo.</i>"
    )


async def _reply_for_inactive_state(
    message: Message,
    chat_id: int,
    user_id: int,
    *,
    no_name: bool,
) -> None:
    if no_name:
        if _feedback_allowed(chat_id, user_id, "no_name_idle", window=2.0):
            await _reply_context(message, _build_usage_text(active=False))
        return

    result = get_chat_spawn_result(chat_id)
    if result and result.get("status") == "captured":
        if _feedback_allowed(chat_id, user_id, "captured", window=2.0):
            await _reply_context(message, _build_captured_text(result))
        return

    if result and result.get("status") == "escaped":
        if _feedback_allowed(chat_id, user_id, "escaped", window=2.0):
            await _reply_context(message, _build_escaped_text(result))
        return

    if _feedback_allowed(chat_id, user_id, "no_spawn", window=2.0):
        text = _build_no_spawn_text()
        await _reply_context(message, text)


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

    chat = update.effective_chat
    message = update.message
    user = update.effective_user
    chat_id = chat.id

    if chat.type not in ("group", "supergroup"):
        if _feedback_allowed(chat_id, user.id, "outside_group", window=3.0):
            await _reply_context(
                message,
                (
                    "🧭 <b>CAPTURA EM GRUPO</b>\n\n"
                    "<i>As capturas acontecem nos grupos quando um visitante aparece no chat.</i>\n\n"
                    "<blockquote>"
                    "Quando o spawn surgir, use:\n"
                    "<code>/capturar Nome do Personagem</code>"
                    "</blockquote>"
                ),
            )
        return

    lock = _get_capture_lock(chat_id)

    async with lock:
        spawn = ACTIVE_SPAWNS.get(chat_id)
        if not spawn:
            await _reply_for_inactive_state(
                message,
                chat_id,
                user.id,
                no_name=not bool(context.args),
            )
            return

        expires_at = float(spawn.get("expires_at") or 0.0)
        if expires_at and time.time() >= expires_at:
            await finish_spawn_as_escaped(chat_id, context)
            await _reply_for_inactive_state(
                message,
                chat_id,
                user.id,
                no_name=not bool(context.args),
            )
            return

        if not context.args:
            if _feedback_allowed(chat_id, user.id, "usage_active", window=2.0):
                await _reply_context(message, _build_usage_text(active=True))
            return

        character = spawn.get("character") or {}
        if not _matches_capture_name(
            str(character.get("name") or ""),
            " ".join(context.args),
        ):
            if _feedback_allowed(chat_id, user.id, "wrong_name", window=1.3):
                await _reply_context(message, _build_wrong_name_text(character, expires_at))
            return

        ACTIVE_SPAWNS.pop(chat_id, None)

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

        record_chat_spawn_result(
            chat_id,
            "captured",
            character,
            winner_user_id=int(user.id),
            winner_name=offer["buyer_name"],
        )

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
            await query.answer("Só quem capturou pode usar essa compra exclusiva.", show_alert=True)
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
                "Não consegui debitar suas coins agora. Tenta de novo em instantes.",
                show_alert=True,
            )
            return

        try:
            add_card_copy(user.id, int(offer["character_id"]), 1)
        except Exception:
            add_coin(user.id, price)
            await query.answer(
                "Não consegui enviar a carta para a coleção. Suas coins foram devolvidas.",
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
        await query.answer("Carta comprada e enviada para sua coleção!", show_alert=True)
    finally:
        lock.release()
