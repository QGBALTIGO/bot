from __future__ import annotations

import asyncio
from datetime import datetime
from html import escape
from typing import Any, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ContextTypes

from capture_repository import (
    attach_spawn_message,
    expire_spawn,
    get_spawn,
    list_active_spawns,
)
from capture_rules import ESCAPE_SECONDS, PURCHASE_PRICE, PURCHASE_WINDOW_SECONDS, XP_REWARD
from capture_service import CaptureServiceError, attempt_capture, buy_capture_offer, process_group_activity
from utils.runtime_guard import rate_limiter


_ESCAPE_TASKS: set[int] = set()


def _fmt_seconds(total: int) -> str:
    total = max(0, int(total))
    minutes, seconds = divmod(total, 60)
    if minutes and seconds:
        return f"{minutes}min {seconds}s"
    if minutes:
        return f"{minutes}min"
    return f"{seconds}s"


def _character_block(spawn: Dict[str, Any]) -> str:
    return (
        "<blockquote>"
        f"👤 <b>{escape(str(spawn.get('character_name') or 'Personagem'))}</b>\n"
        f"🎬 {escape(str(spawn.get('anime_name') or 'Obra desconhecida'))}"
        "</blockquote>"
    )


def spawn_caption(spawn: Dict[str, Any]) -> str:
    return (
        "✨ <b>UM VISITANTE ATRAVESSOU O PORTAL</b>\n\n"
        "A atividade real do grupo atraiu um personagem.\n\n"
        f"{_character_block(spawn)}\n\n"
        "<blockquote>"
        "🎯 Acerte com <code>/capturar nome</code>\n"
        f"⭐ Recompensa: <b>+{XP_REWARD} XP</b>\n"
        f"🪙 O vencedor pode garantir a carta por <b>{PURCHASE_PRICE} coins</b>\n"
        f"⏳ Fuga em <b>{_fmt_seconds(ESCAPE_SECONDS)}</b>"
        "</blockquote>\n\n"
        "<i>Nome completo, primeiro nome ou sobrenome são aceitos quando não houver ambiguidade.</i>"
    )


def escaped_caption(spawn: Dict[str, Any]) -> str:
    return (
        "💨 <b>O VISITANTE ESCAPOU</b>\n\n"
        f"{_character_block(spawn)}\n\n"
        "Ninguém concluiu a captura a tempo. A atividade do grupo começará a aquecer o próximo portal."
    )


def captured_caption(spawn: Dict[str, Any], progress: Dict[str, Any]) -> str:
    winner_id = int(spawn.get("winner_user_id") or 0)
    winner_name = escape(str(spawn.get("winner_name") or "Jogador"))
    winner = f'<a href="tg://user?id={winner_id}">{winner_name}</a>' if winner_id else winner_name
    level_line = ""
    if int(progress.get("new_level") or 1) > int(progress.get("old_level") or 1):
        level_line = f"\n🔥 Level up: <b>{int(progress.get('new_level') or 1)}</b>"
    return (
        "🎯 <b>CAPTURA CONCLUÍDA</b>\n\n"
        f"{_character_block(spawn)}\n\n"
        f"🏆 {winner} foi o primeiro a acertar.\n\n"
        "<blockquote>"
        f"⭐ +{int(progress.get('xp_reward') or XP_REWARD)} XP{level_line}\n"
        f"🪙 Carta exclusiva: <b>{int(spawn.get('purchase_price') or PURCHASE_PRICE)} coins</b>\n"
        f"⏳ Compra disponível por <b>{_fmt_seconds(PURCHASE_WINDOW_SECONDS)}</b>"
        "</blockquote>\n\n"
        "<i>Somente quem capturou pode usar o botão abaixo.</i>"
    )


def purchased_caption(spawn: Dict[str, Any], quantity: int, coins: int) -> str:
    winner_id = int(spawn.get("winner_user_id") or 0)
    winner_name = escape(str(spawn.get("winner_name") or "Jogador"))
    winner = f'<a href="tg://user?id={winner_id}">{winner_name}</a>' if winner_id else winner_name
    return (
        "🛒 <b>CARTA GARANTIDA</b>\n\n"
        f"{_character_block(spawn)}\n\n"
        f"{winner} concluiu a compra da captura.\n\n"
        "<blockquote>"
        f"📚 Quantidade na coleção: <b>x{int(quantity)}</b>\n"
        f"🪙 Saldo atual: <b>{int(coins)} coins</b>"
        "</blockquote>"
    )


def _purchase_keyboard(spawn: Dict[str, Any]) -> InlineKeyboardMarkup | None:
    token = str(spawn.get("purchase_token") or "").strip()
    if not token:
        return None
    price = int(spawn.get("purchase_price") or PURCHASE_PRICE)
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🛒 Garantir carta • {price} coins", callback_data=f"capbuy:{token}")]]
    )


async def _edit_spawn(bot, spawn: Dict[str, Any], text: str, reply_markup=None) -> None:
    chat_id = int(spawn.get("chat_id") or 0)
    message_id = int(spawn.get("spawn_message_id") or 0)
    if chat_id and message_id:
        try:
            if spawn.get("spawn_has_photo"):
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            return
        except Exception:
            pass
    if chat_id:
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception:
            pass


async def _publish_spawn(message, context: ContextTypes.DEFAULT_TYPE, spawn: Dict[str, Any]) -> None:
    text = spawn_caption(spawn)
    sent = None
    has_photo = False
    image = str(spawn.get("image_url") or "").strip()
    if image:
        try:
            sent = await message.reply_photo(photo=image, caption=text, parse_mode="HTML")
            has_photo = True
        except Exception:
            sent = None
    if sent is None:
        try:
            sent = await message.reply_html(text)
        except Exception:
            return
    attach_spawn_message(int(spawn["id"]), int(sent.message_id), has_photo)
    spawn["spawn_message_id"] = int(sent.message_id)
    spawn["spawn_has_photo"] = has_photo
    schedule_escape(int(spawn["id"]), context.application)


async def capture_activity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user:
        return
    if str(chat.type) not in {"group", "supergroup"} or bool(getattr(user, "is_bot", False)):
        return
    text = str(getattr(message, "text", "") or "")
    try:
        spawn = process_group_activity(int(chat.id), int(user.id), text)
    except Exception:
        return
    if spawn:
        await _publish_spawn(message, context, spawn)


async def capturar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user:
        return
    if str(chat.type) not in {"group", "supergroup"}:
        await message.reply_html("🎯 <b>Capturas acontecem nos grupos.</b> Use o comando quando um visitante aparecer.")
        return

    if not await rate_limiter.allow(
        f"capture:guess:{int(chat.id)}:{int(user.id)}", limit=5, window_seconds=10
    ):
        return

    guess = " ".join(context.args or []).strip()
    winner_name = str(user.full_name or user.first_name or user.username or "Jogador")
    try:
        result = attempt_capture(int(chat.id), int(user.id), winner_name, guess)
    except CaptureServiceError as exc:
        if exc.code in {"wrong_name", "missing_name", "no_spawn", "expired"}:
            await message.reply_html(f"⚠️ {escape(exc.message)}")
        return

    spawn = result["spawn"]
    await _edit_spawn(
        context.bot,
        spawn,
        captured_caption(spawn, result.get("progress") or {}),
        reply_markup=_purchase_keyboard(spawn),
    )


async def capture_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user or not query.data:
        return
    token = str(query.data).split(":", 1)[1] if ":" in str(query.data) else ""
    if not await rate_limiter.allow(f"capture:buy:{int(user.id)}", limit=4, window_seconds=10):
        await query.answer("Espere um instante antes de tentar novamente.", show_alert=True)
        return
    try:
        result = buy_capture_offer(int(user.id), token)
    except CaptureServiceError as exc:
        await query.answer(exc.message, show_alert=True)
        return

    spawn = result["spawn"]
    await query.answer("Carta adicionada à coleção!", show_alert=False)
    await _edit_spawn(
        context.bot,
        spawn,
        purchased_caption(
            spawn,
            int(result.get("quantity") or 1),
            int((result.get("wallet") or {}).get("coins") or 0),
        ),
        reply_markup=None,
    )


async def _escape_worker(spawn_id: int, application: Application) -> None:
    try:
        while True:
            spawn = get_spawn(int(spawn_id))
            if not spawn or str(spawn.get("status") or "") != "active":
                return
            expires_at = spawn.get("expires_at")
            if not expires_at:
                return
            delay = max((expires_at - datetime.now(expires_at.tzinfo)).total_seconds(), 0.0)
            if delay > 0:
                await asyncio.sleep(delay)
            escaped = expire_spawn(int(spawn_id))
            if not escaped:
                return
            await _edit_spawn(application.bot, escaped, escaped_caption(escaped), reply_markup=None)
            return
    finally:
        _ESCAPE_TASKS.discard(int(spawn_id))


def schedule_escape(spawn_id: int, application: Application) -> None:
    spawn_id = int(spawn_id)
    if spawn_id <= 0 or spawn_id in _ESCAPE_TASKS:
        return
    _ESCAPE_TASKS.add(spawn_id)
    asyncio.create_task(_escape_worker(spawn_id, application))


async def restore_capture_runtime(application: Application) -> None:
    for spawn in list_active_spawns():
        schedule_escape(int(spawn.get("id") or 0), application)
