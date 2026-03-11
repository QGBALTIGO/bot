import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import has_accepted_terms
from utils.gatekeeper import TERMS_VERSION


MSG_ANON_COST = int(os.getenv("MSG_ANON_COST", "3"))
MSG_COOLDOWN_NORMAL_SECONDS = int(os.getenv("MSG_COOLDOWN_NORMAL_SECONDS", "30"))
MSG_COOLDOWN_ANON_SECONDS = int(os.getenv("MSG_COOLDOWN_ANON_SECONDS", "90"))


async def msgtutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if not has_accepted_terms(user.id, TERMS_VERSION):
        await message.reply_text(
            "📜 <b>Antes de usar este recurso</b>\n\n"
            "Você precisa aceitar os termos do bot primeiro.\n"
            "Use <code>/start</code> para continuar.",
            parse_mode=ParseMode.HTML,
        )
        return

    text = (
        "💬 <b>Guia do Sistema de Mensagens</b>\n\n"
        "Converse com outros jogadores usando o <b>nickname</b>.\n\n"

        "📨 <b>Mensagem normal</b>\n"
        "Use <code>/msg nickname mensagem</code>\n"
        "É <b>grátis</b>.\n"
        f"Cooldown: <b>{MSG_COOLDOWN_NORMAL_SECONDS}s</b>\n\n"

        "👤 <b>Mensagem anônima</b>\n"
        "Use <code>/msganon nickname mensagem</code>\n"
        f"Custa <b>{MSG_ANON_COST} coins</b> por envio.\n"
        f"Cooldown: <b>{MSG_COOLDOWN_ANON_SECONDS}s</b>\n\n"

        "🏷️ <b>Nickname obrigatório</b>\n"
        "Você precisa definir um nickname para usar esse sistema.\n\n"

        "🚫 <b>Bloquear jogador</b>\n"
        "Use <code>/bloquearmsg nickname</code>\n\n"

        "✅ <b>Desbloquear jogador</b>\n"
        "Use <code>/desbloquearmsg nickname</code>\n\n"

        "⚙️ <b>Configurações</b>\n"
        "Use <code>/msgconfig</code> para ativar ou desativar mensagens.\n\n"

        "🚨 <b>Denunciar mensagem</b>\n"
        "Use <code>/denunciarmsg ID motivo</code>\n\n"

        "🎮 <b>Dica</b>\n"
        "Use mensagens com respeito. Abusos podem gerar punições."
    )

    await message.reply_text(text, parse_mode=ParseMode.HTML)
