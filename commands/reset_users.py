import os

from telegram import Update
from telegram.ext import ContextTypes

from database import delete_user_account, delete_all_users


BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0"))


def is_owner(user_id: int) -> bool:
    return user_id == BOT_OWNER_ID


async def reset_user(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not is_owner(user_id):
        await update.message.reply_text(
            "❌ Apenas o dono do bot pode usar este comando."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Uso correto:\n"
            "/resetuser ID_DO_USUARIO"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ ID inválido."
        )
        return

    try:
        delete_user_account(target_id)

        await update.message.reply_text(
            f"🧹 Conta do usuário `{target_id}` foi apagada com sucesso.",
            parse_mode="Markdown"
        )

    except Exception as e:

        await update.message.reply_text(
            f"❌ Erro ao apagar usuário:\n{e}"
        )


async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not is_owner(user_id):
        await update.message.reply_text(
            "❌ Apenas o dono do bot pode usar este comando."
        )
        return

    if not context.args or context.args[0].upper() != "CONFIRMAR":

        await update.message.reply_text(
            "⚠️ ESTE COMANDO VAI APAGAR TODOS OS JOGADORES.\n\n"
            "Para confirmar use:\n"
            "`/resetall CONFIRMAR`",
            parse_mode="Markdown"
        )
        return

    try:

        delete_all_users()

        await update.message.reply_text(
            "🔥 RESET GLOBAL EXECUTADO.\n\n"
            "Todos os jogadores foram apagados."
        )

    except Exception as e:

        await update.message.reply_text(
            f"❌ Erro ao resetar banco:\n{e}"
        )
