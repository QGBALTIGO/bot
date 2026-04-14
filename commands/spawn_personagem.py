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
        return

    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Use esse comando em um grupo para testar o spawn.")
        return

    chat_id = update.effective_chat.id
    if chat_id in ACTIVE_SPAWNS:
        await update.message.reply_text("Ja tem um personagem em campo nesse grupo.")
        return

    spawned = await start_spawn(update.message, context, manual=True)
    if not spawned:
        await update.message.reply_text("Nao consegui iniciar o spawn agora.")
