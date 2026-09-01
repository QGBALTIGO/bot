from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from handlers.capture_spawn import expire_active_spawn_if_needed, get_active_spawn, start_spawn

logger = logging.getLogger(__name__)


def _parse_admin_ids() -> frozenset[int]:
    values: set[int] = set()

    for raw_item in str(os.getenv("ADMIN_IDS", "") or "").split(","):
        item = raw_item.strip()
        if not item:
            continue
        if not item.isdigit() or int(item) <= 0:
            logger.error("ADMIN_IDS contém valor inválido; item ignorado")
            continue
        values.add(int(item))

    owner_raw = str(os.getenv("BOT_OWNER_ID", "") or "").strip()
    if owner_raw:
        if owner_raw.isdigit() and int(owner_raw) > 0:
            values.add(int(owner_raw))
        else:
            logger.error("BOT_OWNER_ID inválido; dono não adicionado ao spawn manual")

    return frozenset(values)


ADMIN_IDS = _parse_admin_ids()


async def spawn_personagem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return

    if int(user.id) not in ADMIN_IDS:
        await message.reply_html(
            "⛔ <b>ACESSO RESTRITO</b>\n\n"
            "<i>Esse comando de teste está disponível apenas para administradores.</i>"
        )
        return

    if chat.type not in ("group", "supergroup"):
        await message.reply_html(
            "🧪 <b>SPAWN DE TESTE</b>\n\n"
            "<i>Use esse comando dentro de um grupo para testar o evento completo.</i>"
        )
        return

    chat_id = int(chat.id)
    try:
        await expire_active_spawn_if_needed(chat_id, context.bot)

        if get_active_spawn(chat_id):
            await message.reply_html(
                "⚠️ <b>SPAWN JÁ ATIVO</b>\n\n"
                "<i>Já existe um visitante em campo neste grupo. "
                "Finalize o atual antes de abrir outro teste.</i>"
            )
            return

        spawned = await start_spawn(message, context, manual=True)
    except Exception:
        logger.exception(
            "Falha no spawn manual chat_id=%s requested_by=%s",
            chat_id,
            user.id,
        )
        await message.reply_html(
            "❌ <b>FALHA AO ABRIR O TESTE</b>\n\n"
            "<i>O erro foi registrado. Tente novamente em instantes.</i>"
        )
        return

    if not spawned:
        await message.reply_html(
            "❌ <b>FALHA AO ABRIR O TESTE</b>\n\n"
            "<i>Não consegui iniciar o spawn agora. Tente novamente em instantes.</i>"
        )
