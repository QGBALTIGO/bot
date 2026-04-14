import os

from telegram import Update
from telegram.ext import ContextTypes

from handlers.capture_spawn import expire_active_spawn_if_needed, get_active_spawn, start_spawn


ADMIN_IDS = {
    int(item.strip())
    for item in os.getenv("ADMIN_IDS", "").split(",")
    if item.strip()
}


async def spawn_personagem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.effective_chat:
        return

    if int(update.effective_user.id) not in ADMIN_IDS:
        await update.message.reply_html(
            "⛔ <b>ACESSO RESTRITO</b>\n\n"
            "<i>Esse comando de teste esta disponivel apenas para administradores.</i>"
        )
        return

    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_html(
            "🧪 <b>SPAWN DE TESTE</b>\n\n"
            "<i>Use esse comando dentro de um grupo para testar o evento completo.</i>"
        )
        return

    chat_id = int(update.effective_chat.id)
    await expire_active_spawn_if_needed(chat_id, context.bot)

    if get_active_spawn(chat_id):
        await update.message.reply_html(
            "⚠️ <b>SPAWN JA ATIVO</b>\n\n"
            "<i>Ja existe um visitante em campo nesse grupo. Finalize o atual antes de abrir outro teste.</i>"
        )
        return

    spawned = await start_spawn(update.message, context, manual=True)
    if not spawned:
        await update.message.reply_html(
            "❌ <b>FALHA AO ABRIR O TESTE</b>\n\n"
            "<i>Nao consegui iniciar o spawn agora. Tente novamente em instantes.</i>"
        )
