from __future__ import annotations

import asyncio
import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from database import delete_all_users, delete_user_account

logger = logging.getLogger(__name__)


def _owner_id() -> int:
    raw = str(os.getenv("BOT_OWNER_ID", "0") or "").strip()
    if raw.isdigit():
        return int(raw)
    if raw:
        logger.error("BOT_OWNER_ID inválido; comandos de reset foram desativados")
    return 0


BOT_OWNER_ID = _owner_id()


def is_owner(user_id: int) -> bool:
    return BOT_OWNER_ID > 0 and int(user_id) == BOT_OWNER_ID


async def reset_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    if not is_owner(user.id):
        await message.reply_text("❌ Apenas o dono do bot pode usar este comando.")
        return

    if not context.args:
        await message.reply_html(
            "⚠️ <b>Uso correto:</b>\n<code>/resetuser ID_DO_USUARIO</code>"
        )
        return

    try:
        target_id = int(context.args[0])
    except (TypeError, ValueError):
        await message.reply_text("❌ ID inválido.")
        return

    if target_id <= 0:
        await message.reply_text("❌ ID inválido.")
        return

    try:
        await asyncio.to_thread(delete_user_account, target_id)
    except Exception:
        logger.exception(
            "Falha ao apagar conta target_user_id=%s requested_by=%s",
            target_id,
            user.id,
        )
        await message.reply_text(
            "❌ Não foi possível apagar essa conta agora. O erro foi registrado."
        )
        return

    logger.warning(
        "Conta apagada target_user_id=%s requested_by=%s",
        target_id,
        user.id,
    )
    await message.reply_html(
        f"🧹 Conta do usuário <code>{target_id}</code> apagada com sucesso."
    )


async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    if not is_owner(user.id):
        await message.reply_text("❌ Apenas o dono do bot pode usar este comando.")
        return

    confirmation = str(context.args[0] if context.args else "").strip().upper()
    if confirmation != "CONFIRMAR":
        await message.reply_html(
            "⚠️ <b>ESTE COMANDO APAGA TODOS OS JOGADORES.</b>\n\n"
            "Para confirmar use:\n<code>/resetall CONFIRMAR</code>"
        )
        return

    try:
        await asyncio.to_thread(delete_all_users)
    except Exception:
        logger.exception("Falha no reset global requested_by=%s", user.id)
        await message.reply_text(
            "❌ Não foi possível concluir o reset global. O erro foi registrado."
        )
        return

    logger.critical("Reset global executado requested_by=%s", user.id)
    await message.reply_text(
        "🔥 RESET GLOBAL EXECUTADO.\n\nTodos os jogadores foram apagados."
    )
