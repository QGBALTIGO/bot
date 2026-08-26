import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from commands.nivel import register_progress
from database import create_or_get_user, get_user_status
from identity_repository import sync_telegram_identity
from utils.runtime_guard import rate_limiter

logger = logging.getLogger(__name__)

TERMS_VERSION = os.getenv("TERMS_VERSION", "v1").strip() or "v1"
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourceBaltigo").strip()

PROGRESS_RATE_LIMIT = int(os.getenv("PROGRESS_RATE_LIMIT", "1"))
PROGRESS_RATE_WINDOW_SECONDS = float(os.getenv("PROGRESS_RATE_WINDOW_SECONDS", "2.5"))
GATEKEEPER_RATE_LIMIT = int(os.getenv("GATEKEEPER_RATE_LIMIT", "8"))
GATEKEEPER_RATE_WINDOW_SECONDS = float(os.getenv("GATEKEEPER_RATE_WINDOW_SECONDS", "5"))

ADMIN_COMMANDS = {
    "/card_reload", "/card_delchar", "/card_addchar", "/card_setcharimg", "/card_setcharname",
    "/card_delanime", "/card_addanime", "/card_setanimebanner", "/card_setanimecover",
    "/card_addsubcat", "/card_delsubcat", "/card_subadd", "/card_subremove",
    "/admin", "/avisar", "/walletgive", "/spawn_test", "/resetuser",
}

GROUP_ALLOWED_COMMANDS = {"/capturar", "/trocar", "/duelo"}

# Navegação, consulta, social e ações que já concedem recompensa no próprio domínio
# não ganham XP simplesmente por abrir/acionar o comando.
IGNORED_PROGRESS_COMMANDS = {
    "/start", "/hub", "/menu", "/ajuda", "/configuracoes", "/notificacoes", "/atividade",
    "/favoritos", "/watchlist", "/agenda", "/noticias", "/recomendar", "/amigos", "/missoes",
    "/conquistas", "/nivel", "/ranking", "/loja", "/colecao", "/perfil", "/memoria", "/termo",
    "/xcard", "/xcolecao", "/capturar", "/trocar", "/duelo", "/mensagens", "/msgtutorial", "/msg",
    "/msganon", "/msgconfig", "/bloquearmsg", "/desbloquearmsg", "/denunciarmsg", "/contribuir",
    "/sugerircard", *ADMIN_COMMANDS,
}


def _is_group(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))


def _extract_command(text: str) -> str:
    text = (text or "").strip()
    if not text.startswith("/"):
        return ""
    return text.split()[0].split("@")[0].lower()


def _member_has_access(member) -> bool:
    status = getattr(member, "status", "")
    if status in ("creator", "administrator", "member"):
        return True
    return status == "restricted" and bool(getattr(member, "is_member", False))


async def _is_in_required_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return _member_has_access(member)
    except Exception:
        logger.warning("Falha ao verificar canal obrigatório user_id=%s channel=%s", user_id, REQUIRED_CHANNEL, exc_info=True)
        return False


async def _maybe_register_progress(update: Update, command_name: str) -> None:
    if not command_name or command_name in IGNORED_PROGRESS_COMMANDS:
        return
    user = update.effective_user
    if not user:
        return
    allowed = await rate_limiter.allow(key=f"progress:{user.id}", limit=PROGRESS_RATE_LIMIT, window_seconds=PROGRESS_RATE_WINDOW_SECONDS)
    if not allowed:
        return
    try:
        await register_progress(update)
    except Exception:
        logger.exception("Falha ao registrar progresso user_id=%s", user.id)


async def gatekeeper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return False, ""

    text = message.text or ""
    command_name = _extract_command(text)

    if command_name in ADMIN_COMMANDS:
        return True, ""

    allowed = await rate_limiter.allow(key=f"gatekeeper:{user.id}", limit=GATEKEEPER_RATE_LIMIT, window_seconds=GATEKEEPER_RATE_WINDOW_SECONDS)
    if not allowed:
        return False, ""

    if _is_group(update):
        if not text.startswith("/"):
            return False, ""
        if command_name == "/start":
            return True, ""
        if command_name not in GROUP_ALLOWED_COMMANDS:
            return False, ""

    if command_name == "/start":
        return True, ""

    user_id = int(user.id)
    create_or_get_user(user_id)
    try:
        sync_telegram_identity(user_id, username=str(user.username or ""), full_name=str(user.full_name or ""))
    except Exception:
        logger.exception("Falha ao sincronizar identidade V2 user_id=%s", user_id)

    status = get_user_status(user_id) or {}
    if not status.get("terms_accepted"):
        return False, "📜 <b>Termos obrigatórios</b>\n\nAntes de usar o <b>Source Baltigo</b>, aceite os <b>Termos de Uso</b>.\n\n➡️ Envie <b>/start</b>."
    if status.get("terms_version") != TERMS_VERSION:
        return False, "📜 <b>Atualização dos Termos</b>\n\nOs termos mudaram. Envie <b>/start</b> novamente para revisar."
    if not await _is_in_required_channel(update, context, user_id):
        return False, "📢 <b>Canal obrigatório</b>\n\nEntre no canal oficial da Source Baltigo e depois envie <b>/start</b>."

    if command_name:
        await _maybe_register_progress(update, command_name)
    return True, ""
