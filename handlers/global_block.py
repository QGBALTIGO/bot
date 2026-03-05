# handlers/global_block.py

from telegram import Update
from telegram.ext import ContextTypes
from utils.gatekeeper import gatekeeper

async def global_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, msg = await gatekeeper(update, context)
    if ok:
        return  # deixa outros handlers rodarem
    # responde com a mensagem de bloqueio
    try:
        if update.message:
            await update.message.reply_text(msg)
        elif update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
    except Exception:
        pass
