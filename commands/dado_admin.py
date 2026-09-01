from __future__ import annotations

import asyncio
import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from database import admin_give_dado_to_all, admin_give_dado_to_user
from utils.gatekeeper import gatekeeper

logger = logging.getLogger(__name__)


def _parse_admins() -> frozenset[int]:
    values = {
        int(value.strip())
        for value in str(os.getenv("ADMINS", "") or "").split(",")
        if value.strip().isdigit() and int(value.strip()) > 0
    }
    owner = str(os.getenv("BOT_OWNER_ID", "") or "").strip()
    if owner.isdigit() and int(owner) > 0:
        values.add(int(owner))
    return frozenset(values)


ADMINS = _parse_admins()


def _is_admin(user_id: int) -> bool:
    return int(user_id) in ADMINS


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def dadogive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    if _is_group(update):
        await message.reply_html(
            "⛔ <b>Comando administrativo disponível apenas no privado.</b>"
        )
        return

    if not _is_admin(user.id):
        await message.reply_html("⛔ <b>Acesso negado.</b>")
        return

    allowed, blocked_message = await gatekeeper(update, context)
    if not allowed:
        if blocked_message:
            await message.reply_html(blocked_message)
        return

    if len(context.args) < 2:
        await message.reply_html(
            "⚙️ <b>Uso correto:</b>\n\n"
            "<code>/dadogive USER_ID QUANTIDADE</code>\n\n"
            "Exemplo:\n<code>/dadogive 123456789 5</code>"
        )
        return

    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
    except (TypeError, ValueError):
        await message.reply_html("❌ <b>USER_ID ou quantidade inválidos.</b>")
        return

    if target_user_id <= 0:
        await message.reply_html("❌ <b>USER_ID inválido.</b>")
        return
    if not 1 <= amount <= 100:
        await message.reply_html(
            "❌ <b>A quantidade precisa estar entre 1 e 100.</b>"
        )
        return

    try:
        result = await asyncio.to_thread(
            admin_give_dado_to_user,
            target_user_id,
            amount,
        )
    except Exception:
        logger.exception(
            "Falha no /dadogive target=%s amount=%s requested_by=%s",
            target_user_id,
            amount,
            user.id,
        )
        await message.reply_html(
            "❌ <b>Não foi possível adicionar os dados agora.</b>"
        )
        return

    if not result.get("ok"):
        await message.reply_html("❌ <b>Não foi possível adicionar os dados.</b>")
        return

    logger.info(
        "Dados adicionados target=%s requested=%s applied=%s requested_by=%s",
        target_user_id,
        amount,
        result.get("applied"),
        user.id,
    )
    await message.reply_html(
        "✅ <b>Dados adicionados com sucesso</b>\n\n"
        f"👤 <b>Usuário:</b> <code>{int(result['user_id'])}</code>\n"
        f"➕ <b>Pedido:</b> <code>{int(result['added'])}</code>\n"
        f"🎯 <b>Aplicado:</b> <code>{int(result['applied'])}</code>\n"
        f"📦 <b>Antes:</b> <code>{int(result['old_balance'])}</code>\n"
        f"🎲 <b>Agora:</b> <code>{int(result['new_balance'])}</code>"
    )


async def dadogiveall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    if _is_group(update):
        await message.reply_html(
            "⛔ <b>Comando administrativo disponível apenas no privado.</b>"
        )
        return

    if not _is_admin(user.id):
        await message.reply_html("⛔ <b>Acesso negado.</b>")
        return

    allowed, blocked_message = await gatekeeper(update, context)
    if not allowed:
        if blocked_message:
            await message.reply_html(blocked_message)
        return

    if not context.args:
        await message.reply_html(
            "⚙️ <b>Uso correto:</b>\n\n"
            "<code>/dadogiveall QUANTIDADE</code>\n\n"
            "Exemplo:\n<code>/dadogiveall 3</code>"
        )
        return

    try:
        amount = int(context.args[0])
    except (TypeError, ValueError):
        await message.reply_html("❌ <b>Quantidade inválida.</b>")
        return

    if not 1 <= amount <= 24:
        await message.reply_html(
            "❌ <b>A quantidade precisa estar entre 1 e 24.</b>"
        )
        return

    notice = await message.reply_html(
        "⏳ <b>Distribuindo dados para todos os usuários...</b>"
    )

    try:
        result = await asyncio.to_thread(admin_give_dado_to_all, amount)
    except Exception:
        logger.exception(
            "Falha no /dadogiveall amount=%s requested_by=%s",
            amount,
            user.id,
        )
        await notice.edit_text(
            "❌ <b>Não foi possível distribuir os dados agora.</b>",
            parse_mode="HTML",
        )
        return

    if not result.get("ok"):
        await notice.edit_text(
            "❌ <b>Não foi possível distribuir os dados.</b>",
            parse_mode="HTML",
        )
        return

    logger.warning(
        "Distribuição global de dados amount=%s total_users=%s requested_by=%s",
        amount,
        result.get("total_users"),
        user.id,
    )
    await notice.edit_text(
        "✅ <b>Distribuição concluída</b>\n\n"
        f"👥 <b>Usuários processados:</b> <code>{int(result['total_users'])}</code>\n"
        f"➕ <b>Valor por usuário:</b> <code>{int(result['added'])}</code>\n"
        f"🎯 <b>Total aplicado real:</b> <code>{int(result['total_applied'])}</code>",
        parse_mode="HTML",
    )
