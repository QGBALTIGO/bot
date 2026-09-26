from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from source_features.capture_groups import (
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    capture_group_settings,
    save_capture_group_settings,
)


async def _is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user or chat.type not in ("group", "supergroup"):
        return False
    member = await context.bot.get_chat_member(chat.id, user.id)
    return str(getattr(member, "status", "")) in {"administrator", "creator"}


async def spawnconfig(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not user:
        return
    if chat.type not in ("group", "supergroup"):
        await message.reply_text("Use /spawnconfig dentro do grupo que você quer configurar.")
        return
    if not await _is_group_admin(update, context):
        await message.reply_text("Apenas administradores do grupo podem alterar o spawn.")
        return

    args = [str(x).strip().lower() for x in (context.args or []) if str(x).strip()]
    try:
        if not args:
            state = capture_group_settings(chat.id)
        elif args[0] in {"on", "ativar", "ligar"}:
            state = save_capture_group_settings(chat.id, user.id, enabled=True)
        elif args[0] in {"off", "desativar", "desligar"}:
            state = save_capture_group_settings(chat.id, user.id, enabled=False)
        elif args[0].isdigit():
            state = save_capture_group_settings(chat.id, user.id, message_threshold=int(args[0]))
        else:
            await message.reply_text(f"Use /spawnconfig on, /spawnconfig off ou /spawnconfig {MIN_THRESHOLD}-{MAX_THRESHOLD}.")
            return
    except ValueError:
        await message.reply_text(f"Escolha um intervalo entre {MIN_THRESHOLD} e {MAX_THRESHOLD} mensagens.")
        return

    status = "ativado" if state["enabled"] else "desativado"
    await message.reply_html(
        "🎴 <b>SPAWN DO GRUPO</b>\n\n"
        f"Status: <b>{status}</b>\n"
        f"Intervalo: <b>{state['message_threshold']} mensagens</b>\n\n"
        "<i>A alteração vale somente para este grupo.</i>"
    )
