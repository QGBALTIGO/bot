import asyncio
import secrets
import time
import unicodedata
from html import escape
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ContextTypes

from database import (
    add_progress_xp,
    complete_capture_purchase,
    create_or_get_user,
    get_capture_spawn,
    get_capture_spawn_by_purchase_token,
    get_latest_capture_spawn,
    list_open_capture_purchase_spawns,
    mark_capture_purchase_expired,
    mark_capture_spawn_escaped,
    mark_capture_spawn_captured,
    touch_user_identity,
)
from handlers.capture_spawn import (
    PURCHASE_COST,
    PURCHASE_WINDOW_SECONDS,
    XP_REWARD,
    build_escape_caption,
    build_character_block,
    edit_spawn_post,
    expire_active_spawn_if_needed,
    format_capture_window,
    get_active_spawn,
)
from utils.runtime_guard import lock_manager


_SCHEDULED_PURCHASE_TASKS: set[int] = set()
_feedback_timestamps: Dict[str, float] = {}


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


def normalize(text: str) -> str:
    text = str(text or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in text)
    return " ".join(text.strip().split())


def _tokens(text: str) -> List[str]:
    return [item for item in normalize(text).split() if item]


def _matches_capture_name(character_name: str, guess_text: str) -> bool:
    full_name = normalize(character_name)
    guess = normalize(guess_text)

    if not full_name or not guess:
        return False

    if guess == full_name or guess.replace(" ", "") == full_name.replace(" ", ""):
        return True

    name_tokens = _tokens(character_name)
    guess_tokens = _tokens(guess_text)
    if not name_tokens or not guess_tokens:
        return False

    if len(guess_tokens) == 1:
        probe = guess_tokens[0]
        if len(probe) < 2:
            return False
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


def _is_captured_status(status: str) -> bool:
    return status in {"captured_offer_open", "captured_offer_expired", "purchased"}


def _build_usage_text(active: bool) -> str:
    status_line = (
        "<i>O visitante ainda esta em campo. Se liga no formato e tenta de novo.</i>"
        if active
        else "<i>Voce precisa informar o nome do personagem para tentar a captura.</i>"
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
        "<i>Vale nome completo, primeiro nome ou sobrenome. Ajusta o chute e tenta de novo.</i>"
    )


def _build_no_spawn_text() -> str:
    return (
        "🕊 <b>NENHUM VISITANTE EM CAMPO</b>\n\n"
        "<i>No momento nao ha nenhum spawn ativo neste chat.</i>\n\n"
        "<blockquote>"
        "Quando um visitante aparecer, use:\n"
        "<code>/capturar Nome do Personagem</code>\n\n"
        "Exemplo:\n"
        "<code>/capturar Victor Nikiforov</code>"
        "</blockquote>\n\n"
        "<i>Continuem conversando para atrair o proximo evento.</i>"
    )


def _build_wrong_name_text(expires_at_ts: float) -> str:
    time_left = max(int(expires_at_ts - time.time()), 0)
    return (
        "❌ <b>TENTATIVA FALHOU</b>\n\n"
        "<i>Esse nome nao corresponde ao visitante atual.</i>\n\n"
        "<blockquote>"
        "Use <code>/capturar nome</code> com o nome do personagem exibido.\n"
        "Vale nome completo, primeiro nome ou sobrenome.\n"
        f"⏳ Tempo restante: <b>{format_capture_window(time_left)}</b>"
        "</blockquote>\n\n"
        "<i>O spawn continua ativo. Respira, ajusta o chute e tenta de novo.</i>"
    )


def _build_outside_group_text() -> str:
    return (
        "🧭 <b>CAPTURA EM GRUPO</b>\n\n"
        "<i>As capturas acontecem nos grupos quando um visitante aparece no chat.</i>\n\n"
        "<blockquote>"
        "Quando o spawn surgir, use:\n"
        "<code>/capturar Nome do Personagem</code>"
        "</blockquote>"
    )


def _build_captured_text(spawn: Dict[str, Any]) -> str:
    winner_name = str(spawn.get("winner_name") or "Outro jogador")
    winner_id = int(spawn.get("winner_user_id") or 0)
    winner = _player_link(winner_id, winner_name) if winner_id else escape(winner_name)

    return (
        "🏁 <b>CAPTURA ENCERRADA</b>\n\n"
        f"{build_character_block(spawn)}\n\n"
        f"<i>Esse visitante ja foi capturado por {winner}. Agora e esperar o proximo.</i>"
    )


def _build_escaped_text(spawn: Dict[str, Any]) -> str:
    return (
        "💨 <b>VISITANTE INDISPONIVEL</b>\n\n"
        f"{build_character_block(spawn)}\n\n"
        "<i>Esse visitante ja foi embora. Continuem conversando para chamar o proximo.</i>"
    )


def _level_up_line(progress: Dict[str, Any]) -> str:
    old_level = int((progress or {}).get("old_level") or 1)
    new_level = int((progress or {}).get("new_level") or old_level)
    if new_level > old_level:
        return f"🔥 Subiu para o nivel <b>{new_level}</b>\n"
    return ""


def _build_offer_caption(
    spawn: Dict[str, Any],
    mode: str,
    *,
    level_up_line: str = "",
    quantity_after: int = 0,
    coins_left: int = 0,
) -> str:
    buyer_name = str(spawn.get("winner_name") or "Cacador")
    buyer_id = int(spawn.get("winner_user_id") or 0)
    buyer = _player_link(buyer_id, buyer_name) if buyer_id else escape(buyer_name)
    xp_block = f"⭐ Recompensa imediata: <b>+{XP_REWARD} XP</b>\n{level_up_line}".rstrip()

    if mode == "available":
        return (
            "✨ <b>CAPTURA CONCLUIDA</b>\n\n"
            f"{build_character_block(spawn)}\n\n"
            f"{buyer} acertou o visitante e fechou a captura.\n\n"
            "<blockquote>"
            f"{xp_block}\n"
            f"🪙 Compra exclusiva liberada por <b>{int(spawn.get('purchase_price') or PURCHASE_COST)} coins</b>\n"
            f"🔒 So o captor pode usar o botao abaixo\n"
            f"⏳ Oferta disponivel por <b>{format_capture_window(PURCHASE_WINDOW_SECONDS)}</b>"
            "</blockquote>\n\n"
            "<i>Continuem conversando para atrair o proximo visitante.</i>"
        )

    if mode == "purchased":
        if quantity_after <= 1:
            collection_line = "📚 Primeira copia enviada para a colecao"
        else:
            collection_line = f"📚 Agora voce tem <b>{quantity_after}</b> copias dessa carta"

        return (
            "🛒 <b>CARTA GARANTIDA</b>\n\n"
            f"{build_character_block(spawn)}\n\n"
            f"{buyer} garantiu a compra exclusiva com sucesso.\n\n"
            "<blockquote>"
            f"⭐ Claim ja garantido: <b>+{XP_REWARD} XP</b>\n"
            f"🪙 -{int(spawn.get('purchase_price') or PURCHASE_COST)} coins\n"
            f"{collection_line}\n"
            f"💰 Saldo atual: <b>{coins_left}</b> coins"
            "</blockquote>\n\n"
            "<i>Continuem conversando para atrair o proximo visitante.</i>"
        )

    return (
        "⌛ <b>JANELA DE COMPRA ENCERRADA</b>\n\n"
        f"{build_character_block(spawn)}\n\n"
        f"{buyer} garantiu o claim e recebeu os XP, mas a janela exclusiva de compra acabou.\n\n"
        "<blockquote>"
        f"⭐ Claim ja garantido: <b>+{XP_REWARD} XP</b>\n"
        "🪙 A carta nao foi comprada a tempo"
        "</blockquote>\n\n"
        "<i>Continuem conversando para chamar o proximo visitante.</i>"
    )


def _offer_keyboard(spawn: Dict[str, Any]) -> InlineKeyboardMarkup:
    price = int(spawn.get("purchase_price") or PURCHASE_COST)
    token = str(spawn.get("purchase_token") or "").strip()
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🛒 Garantir carta ({price} coins)", callback_data=f"capturebuy:{token}")]]
    )


async def _reply_html(update_message, text: str) -> None:
    await update_message.reply_html(text)


async def _reply_for_inactive_state(message, chat_id: int, user_id: int, *, no_name: bool) -> None:
    if no_name:
        if _feedback_allowed(chat_id, user_id, "usage_idle", window=2.0):
            await _reply_html(message, _build_usage_text(active=False))
        return

    latest = get_latest_capture_spawn(chat_id)
    if latest and _is_captured_status(str(latest.get("status") or "").strip().lower()):
        if _feedback_allowed(chat_id, user_id, "captured", window=2.0):
            await _reply_html(message, _build_captured_text(latest))
        return

    if latest and str(latest.get("status") or "").strip().lower() == "escaped":
        if _feedback_allowed(chat_id, user_id, "escaped", window=2.0):
            await _reply_html(message, _build_escaped_text(latest))
        return

    if _feedback_allowed(chat_id, user_id, "no_spawn", window=2.0):
        await _reply_html(message, _build_no_spawn_text())


async def capturar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat = update.effective_chat
    message = update.message
    user = update.effective_user
    chat_id = int(chat.id)
    user_id = int(user.id)

    if chat.type not in ("group", "supergroup"):
        if _feedback_allowed(chat_id, user_id, "outside_group", window=3.0):
            await _reply_html(message, _build_outside_group_text())
        return

    await expire_active_spawn_if_needed(chat_id, context.bot)

    guess_text = " ".join(context.args or []).strip()
    escaped_now: Optional[Dict[str, Any]] = None
    captured: Optional[Dict[str, Any]] = None
    inactive_reply_needed = False

    lock = await lock_manager.acquire(f"capture:chat:{chat_id}")
    try:
        active = get_active_spawn(chat_id)
        if not active:
            inactive_reply_needed = True
        else:
            expires_at_ts = float(active.get("expires_at_ts") or 0.0)
            if expires_at_ts and expires_at_ts <= time.time():
                escaped_now = mark_capture_spawn_escaped(int(active["id"]))
                if escaped_now:
                    active = None

        if not active:
            inactive_reply_needed = True
        else:
            expires_at_ts = float(active.get("expires_at_ts") or 0.0)

            if not guess_text:
                if _feedback_allowed(chat_id, user_id, "usage_active", window=2.0):
                    await _reply_html(message, _build_usage_text(active=True))
                return

            if not _matches_capture_name(str(active.get("character_name") or ""), guess_text):
                if _feedback_allowed(chat_id, user_id, "wrong_name", window=1.3):
                    await _reply_html(message, _build_wrong_name_text(expires_at_ts))
                return

            winner_name = _display_name(user)
            purchase_token = secrets.token_hex(12)
            purchase_expires_at_ts = time.time() + PURCHASE_WINDOW_SECONDS

            captured = mark_capture_spawn_captured(
                int(active["id"]),
                winner_user_id=user_id,
                winner_name=winner_name,
                purchase_token=purchase_token,
                purchase_price=PURCHASE_COST,
                purchase_expires_at_ts=purchase_expires_at_ts,
            )
            if not captured:
                latest = get_latest_capture_spawn(chat_id)
                if latest and _is_captured_status(str(latest.get("status") or "").strip().lower()):
                    if _feedback_allowed(chat_id, user_id, "captured_race", window=1.2):
                        await _reply_html(message, _build_captured_text(latest))
                    return
                if latest and str(latest.get("status") or "").strip().lower() == "escaped":
                    if _feedback_allowed(chat_id, user_id, "escaped_race", window=1.2):
                        await _reply_html(message, _build_escaped_text(latest))
                    return
                inactive_reply_needed = True
    finally:
        lock.release()

    if escaped_now:
        await edit_spawn_post(
            context.bot,
            escaped_now,
            build_escape_caption(escaped_now),
            reply_markup=None,
        )

    if inactive_reply_needed:
        await _reply_for_inactive_state(
            message,
            chat_id,
            user_id,
            no_name=not bool(guess_text),
        )
        return

    create_or_get_user(user_id)
    touch_user_identity(
        user_id,
        getattr(user, "username", "") or "",
        _display_name(user),
    )

    progress: Dict[str, Any] = {}
    try:
        progress = add_progress_xp(user_id, XP_REWARD) or {}
    except Exception:
        progress = {}

    caption = _build_offer_caption(
        captured,
        "available",
        level_up_line=_level_up_line(progress),
    )
    await edit_spawn_post(
        context.bot,
        captured,
        caption,
        reply_markup=_offer_keyboard(captured),
    )
    _schedule_purchase_task(int(captured["id"]), context.application)


async def _purchase_expiry_worker(spawn_id: int, application: Application) -> None:
    try:
        while True:
            spawn = get_capture_spawn(int(spawn_id))
            if not spawn:
                return

            if str(spawn.get("status") or "").strip().lower() != "captured_offer_open":
                return

            delay = max(float(spawn.get("purchase_expires_at_ts") or 0.0) - time.time(), 0.0)
            if delay > 0:
                await asyncio.sleep(delay)

            lock = await lock_manager.acquire(f"capture:chat:{int(spawn['chat_id'])}")
            try:
                fresh = get_capture_spawn(int(spawn_id))
                if not fresh:
                    return
                if str(fresh.get("status") or "").strip().lower() != "captured_offer_open":
                    return
                if float(fresh.get("purchase_expires_at_ts") or 0.0) > time.time():
                    continue

                expired = mark_capture_purchase_expired(int(spawn_id))
                if not expired:
                    return
            finally:
                lock.release()

            await edit_spawn_post(
                application.bot,
                expired,
                _build_offer_caption(expired, "expired"),
                reply_markup=None,
            )
            return
    finally:
        _SCHEDULED_PURCHASE_TASKS.discard(int(spawn_id))


def _schedule_purchase_task(spawn_id: int, application: Application) -> None:
    spawn_id = int(spawn_id)
    if spawn_id <= 0 or spawn_id in _SCHEDULED_PURCHASE_TASKS:
        return

    _SCHEDULED_PURCHASE_TASKS.add(spawn_id)
    asyncio.create_task(_purchase_expiry_worker(spawn_id, application))


async def restore_capture_purchase_runtime(application: Application) -> None:
    for spawn in list_open_capture_purchase_spawns():
        _schedule_purchase_task(int(spawn["id"]), application)


async def capture_purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if not query or not user or not query.data:
        return

    _, _, purchase_token = query.data.partition(":")
    purchase_token = (purchase_token or "").strip()
    if not purchase_token:
        await query.answer()
        return

    spawn = get_capture_spawn_by_purchase_token(purchase_token)
    if not spawn:
        await query.answer("Essa oferta ja acabou.", show_alert=True)
        return

    chat_lock = await lock_manager.acquire(f"capture:chat:{int(spawn['chat_id'])}")
    try:
        result = complete_capture_purchase(purchase_token, int(user.id))
    finally:
        chat_lock.release()

    if not result.get("ok"):
        reason = str(result.get("reason") or "")
        latest_spawn = result.get("spawn") or spawn

        if reason == "forbidden":
            await query.answer("So quem capturou pode usar essa compra exclusiva.", show_alert=True)
            return

        if reason == "insufficient_coins":
            coins_left = int(result.get("coins_left") or 0)
            missing = max(int(latest_spawn.get("purchase_price") or PURCHASE_COST) - coins_left, 0)
            await query.answer(
                f"Faltam {missing} coins. Usa /daily e continua jogando.",
                show_alert=True,
            )
            return

        if reason in {"expired", "not_open"}:
            await edit_spawn_post(
                context.bot,
                latest_spawn,
                _build_offer_caption(latest_spawn, "expired"),
                reply_markup=None,
            )
            await query.answer("A oferta exclusiva expirou.", show_alert=True)
            return

        if reason == "already_purchased":
            await query.answer("Essa carta ja foi garantida.", show_alert=True)
            return

        await query.answer("Nao consegui concluir a compra agora. Tenta de novo em instantes.", show_alert=True)
        return

    purchased_spawn = result.get("spawn") or spawn
    coins_left = int(result.get("coins_left") or 0)
    quantity_after = int(result.get("quantity_after") or 0)

    try:
        from commands.colecao import clear_user_collection_cache

        clear_user_collection_cache(int(user.id))
    except Exception:
        pass

    await edit_spawn_post(
        context.bot,
        purchased_spawn,
        _build_offer_caption(
            purchased_spawn,
            "purchased",
            quantity_after=quantity_after,
            coins_left=coins_left,
        ),
        reply_markup=None,
    )
    await query.answer("Carta comprada e enviada para sua colecao!", show_alert=True)
