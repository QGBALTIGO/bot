import os

from telegram import Update
from telegram.ext import ContextTypes

from database import admin_give_dado_to_user, admin_give_dado_to_all
from utils.gatekeeper import gatekeeper

ADMINS = {
    int(x.strip())
    for x in os.getenv("ADMINS", "").split(",")
    if x.strip().isdigit()
}


def _is_admin(user_id: int) -> bool:
    return int(user_id) in ADMINS


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def dadogive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    if _is_group(update):
        await msg.reply_html(
            "⛔ <b>Comando administrativo disponível apenas no privado.</b>"
        )
        return

    if not _is_admin(user.id):
        await msg.reply_html("⛔ <b>Acesso negado.</b>")
        return

    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    if len(context.args) < 2:
        await msg.reply_html(
            "⚙️ <b>Uso correto:</b>\n\n"
            "<code>/dadogive USER_ID QUANTIDADE</code>\n\n"
            "Exemplo:\n"
            "<code>/dadogive 123456789 5</code>"
        )
        return

    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
    except Exception:
        await msg.reply_html("❌ <b>USER_ID ou quantidade inválidos.</b>")
        return

    if amount <= 0:
        await msg.reply_html("❌ <b>A quantidade precisa ser maior que 0.</b>")
        return

    if amount > 100:
        await msg.reply_html("❌ <b>Quantidade máxima por comando: 100.</b>")
        return

    result = admin_give_dado_to_user(target_user_id, amount)
    if not result.get("ok"):
        await msg.reply_html("❌ <b>Não foi possível adicionar os dados.</b>")
        return

    await msg.reply_html(
        "✅ <b>Dados adicionados com sucesso</b>\n\n"
        f"👤 <b>Usuário:</b> <code>{result['user_id']}</code>\n"
        f"➕ <b>Pedido:</b> <code>{result['added']}</code>\n"
        f"🎯 <b>Aplicado:</b> <code>{result['applied']}</code>\n"
        f"📦 <b>Antes:</b> <code>{result['old_balance']}</code>\n"
        f"🎲 <b>Agora:</b> <code>{result['new_balance']}</code>"
    )


async def dadogiveall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    if _is_group(update):
        await msg.reply_html(
            "⛔ <b>Comando administrativo disponível apenas no privado.</b>"
        )
        return

    if not _is_admin(user.id):
        await msg.reply_html("⛔ <b>Acesso negado.</b>")
        return

    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    if len(context.args) < 1:
        await msg.reply_html(
            "⚙️ <b>Uso correto:</b>\n\n"
            "<code>/dadogiveall QUANTIDADE</code>\n\n"
            "Exemplo:\n"
            "<code>/dadogiveall 3</code>"
        )
        return

    try:
        amount = int(context.args[0])
    except Exception:
        await msg.reply_html("❌ <b>Quantidade inválida.</b>")
        return

    if amount <= 0:
        await msg.reply_html("❌ <b>A quantidade precisa ser maior que 0.</b>")
        return

    if amount > 24:
        await msg.reply_html("❌ <b>Quantidade máxima no geral: 24.</b>")
        return

    notice = await msg.reply_html(
        "⏳ <b>Distribuindo dados para todos os usuários...</b>"
    )

    result = admin_give_dado_to_all(amount)
    if not result.get("ok"):
        await notice.edit_text(
            "❌ <b>Não foi possível distribuir os dados.</b>",
            parse_mode="HTML",
        )
        return

    await notice.edit_text(
        "✅ <b>Distribuição concluída</b>\n\n"
        f"👥 <b>Usuários processados:</b> <code>{result['total_users']}</code>\n"
        f"➕ <b>Valor por usuário:</b> <code>{result['added']}</code>\n"
        f"🎯 <b>Total aplicado real:</b> <code>{result['total_applied']}</code>",
        parse_mode="HTML",
    )
