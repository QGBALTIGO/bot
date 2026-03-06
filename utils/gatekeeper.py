import os
from telegram import Update
from telegram.ext import ContextTypes

from database import create_or_get_user, get_user_status
from commands.nivel import register_progress

TERMS_VERSION = os.getenv("TERMS_VERSION", "v1").strip() or "v1"
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()

IGNORED_PROGRESS_COMMANDS = {
    "/start",

    # admin cards
    "/card_reload",
    "/card_delchar",
    "/card_addchar",
    "/card_setcharimg",
    "/card_setcharname",
    "/card_delanime",
    "/card_addanime",
    "/card_setanimebanner",
    "/card_setanimecover",
    "/card_addsubcat",
    "/card_delsubcat",
    "/card_subadd",
    "/card_subremove",
}


def _is_group(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))


def _extract_command(text: str) -> str:
    text = (text or "").strip()
    if not text.startswith("/"):
        return ""
    return text.split()[0].split("@")[0].lower()


async def _is_in_required_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True

    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ("creator", "administrator", "member")
    except Exception:
        return False


async def _maybe_register_progress(update: Update, command_name: str) -> None:
    if not command_name:
        return

    if command_name in IGNORED_PROGRESS_COMMANDS:
        return

    try:
        await register_progress(update)
    except Exception:
        # não quebra o comando principal se o sistema de nível falhar
        pass


async def gatekeeper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
    """
    (True, "") -> comando pode executar
    (False, "") -> bloqueia silenciosamente
    (False, "msg") -> bloqueia e responde
    """

    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return False, ""

    text = message.text or ""
    command_name = _extract_command(text)

    # =====================
    # GRUPOS
    # =====================

    if _is_group(update):

        # se não for comando → ignora
        if not text.startswith("/"):
            return False, ""

        # /start é tratado pelo próprio comando start
        if command_name == "/start":
            return True, ""

        # outros comandos em grupo → bloqueia silencioso
        return False, ""

    # =====================
    # PRIVADO
    # =====================

    # /start sempre pode executar
    if command_name == "/start":
        return True, ""

    user_id = user.id

    create_or_get_user(user_id)
    st = get_user_status(user_id) or {}

    # -------------------
    # TERMOS
    # -------------------

    if not st.get("terms_accepted"):
        return False, (
            "📜 <b>Termos obrigatórios</b>\n\n"
            "Antes de usar o <b>Source Baltigo</b>, você precisa aceitar "
            "os <b>Termos de Uso</b>.\n\n"
            "➡️ Envie <b>/start</b> para continuar."
        )

    if st.get("terms_version") != TERMS_VERSION:
        return False, (
            "📜 <b>Atualização dos Termos</b>\n\n"
            "Atualizamos nossos termos.\n"
            "Por favor envie <b>/start</b> novamente."
        )

    # -------------------
    # CANAL
    # -------------------

    ok = await _is_in_required_channel(update, context, user_id)

    if not ok:
        return False, (
            "📢 <b>Canal obrigatório</b>\n\n"
            "Para usar o <b>Source Baltigo</b>, você precisa entrar no canal oficial.\n\n"
            "Depois envie <b>/start</b> novamente."
        )

    # -------------------
    # PROGRESSO
    # -------------------

    if command_name:
        await _maybe_register_progress(update, command_name)

    return True, ""
