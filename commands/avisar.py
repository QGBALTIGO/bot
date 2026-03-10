import asyncio
import os

from telegram import Update
from telegram.ext import ContextTypes

from database import get_all_user_ids


BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0"))


def is_owner(user_id: int) -> bool:
    return user_id == BOT_OWNER_ID


async def avisar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if not is_owner(user.id):
        await message.reply_text("❌ Apenas o dono do bot pode usar este comando.")
        return

    if not context.args or len(context.args) < 2:
        await message.reply_text(
            "⚠️ Uso correto:\n"
            "/avisar all sua mensagem\n"
            "/avisar ID_DO_USUARIO sua mensagem"
        )
        return

    target = context.args[0].strip()
    text = " ".join(context.args[1:]).strip()

    if not text:
        await message.reply_text("❌ Mensagem vazia.")
        return

    # enviar para todos
    if target.lower() == "all":
        user_ids = get_all_user_ids()

        total = len(user_ids)
        if total == 0:
            await message.reply_text("⚠️ Nenhum usuário encontrado.")
            return

        await message.reply_text(
            "📢 Iniciando envio global...\n\n"
            f"👥 Usuários encontrados: {total}"
        )

        sent = 0
        failed = 0

        final_text = f"📢 Aviso da Source Baltigo\n\n{text}"

        for uid in user_ids:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=final_text,
                )
                sent += 1
            except Exception:
                failed += 1

            await asyncio.sleep(0.04)

        await message.reply_text(
            "✅ Envio finalizado.\n\n"
            f"👥 Usuários encontrados: {total}\n"
            f"📨 Enviados: {sent}\n"
            f"❌ Falhas: {failed}"
        )
        return

    # enviar para um ID específico
    try:
        target_id = int(target)
    except ValueError:
        await message.reply_text("❌ ID inválido. Use `all` ou um ID numérico.", parse_mode="Markdown")
        return

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"📢 Aviso da Source Baltigo\n\n{text}",
        )
        await message.reply_text(f"✅ Aviso enviado para o usuário `{target_id}`.", parse_mode="Markdown")
    except Exception as e:
        await message.reply_text(f"❌ Falha ao enviar para `{target_id}`:\n`{e}`", parse_mode="Markdown")
