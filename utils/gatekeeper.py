
# utils/gatekeeper.py

import os
from telegram import Update
from telegram.ext import ContextTypes
from database import create_or_get_user, get_user_status

TERMS_VERSION = os.getenv("TERMS_VERSION", "v1").strip() or "v1"
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()  # @canal ou -100...

def _is_group(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))

async def _is_in_required_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True  # se não configurou canal, não bloqueia

    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        # status: creator/administrator/member/restricted/left/kicked
        return member.status in ("creator", "administrator", "member")
    except Exception:
        # se falhar, melhor bloquear (segurança)
        return False

async def gatekeeper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
    """
    Retorna:
      (True, "") -> pode continuar
      (False, "mensagem") -> bloqueia e devolve mensagem
    """
    user = update.effective_user
    if not user:
        return False, "❌ Não consegui identificar seu usuário."

    user_id = user.id

    # /start em grupo -> manda pro privado
    if _is_group(update):
        return False, "⚠️ Para usar o bot, me chame no privado: @SourceBaltigoBot"

    create_or_get_user(user_id)
    st = get_user_status(user_id) or {}

    # 1) termos
    if not st.get("terms_accepted"):
        return False, "📜 Você precisa ler e aceitar os Termos para continuar. Use /start e clique em “Ler e aceitar termos”."

    # 2) versão de termos mudou -> pedir aceite de novo
    if st.get("terms_version") != TERMS_VERSION:
        return False, "📜 Atualizamos os Termos. Para continuar, aceite novamente em /start."

    # 3) canal obrigatório
    ok = await _is_in_required_channel(update, context, user_id)
    if not ok:
        # você pode colocar o link do canal aqui
        return False, "📢 Para usar o bot, você precisa entrar no nosso canal oficial. Depois volte e envie /start."

    return True, ""
