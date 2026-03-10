from telegram import Update
from telegram.ext import ContextTypes

from database import delete_user_account, delete_all_users

# coloque aqui os mesmos admins que já usa no bot
ADMINS = {123456789}


async def reset_user(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in ADMINS:
        return

    if not context.args:
        await update.message.reply_text(
            "Uso:\n"
            "/resetuser ID"
        )
        return

    try:
        target_id = int(context.args[0])
    except:
        await update.message.reply_text("ID inválido.")
        return

    delete_user_account(target_id)

    await update.message.reply_text(
        f"Conta do usuário {target_id} foi apagada."
    )


async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in ADMINS:
        return

    delete_all_users()

    await update.message.reply_text(
        "Todos os jogadores foram resetados."
    )
