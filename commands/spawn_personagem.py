import os

from telegram import Update
from telegram.ext import ContextTypes

from handlers.capture_spawn import ACTIVE_SPAWNS, start_spawn


ADMIN_IDS = set(
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
)


async def spawn_personagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat:
        return

    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_html(
            "⛔ <b>Acesso restrito</b>\n\n"
            "<i>Esse comando de teste está disponível apenas para administradores.</i>"
        )
        return

    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_html(
            "🧪 <b>SPAWN DE TESTE</b>\n\n"
            "<i>Use esse comando dentro de um grupo para testar o evento completo.</i>"
        )
        return

    chat_id = update.effective_chat.id
    if chat_id in ACTIVE_SPAWNS:
        await update.message.reply_html(
            "⚠️ <b>Spawn já ativo</b>\n\n"
            "<i>Já existe um visitante em campo nesse grupo. Finalize o atual antes de abrir outro teste.</i>"
        )
        return

    spawned = await start_spawn(update.message, context, manual=True)
    if not spawned:
        await update.message.reply_html(
            "❌ <b>Falha ao abrir o teste</b>\n\n"
            "<i>Não consegui iniciar o spawn agora. Tente novamente em instantes.</i>"
        )
