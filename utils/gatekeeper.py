from __future__ import annotations

import asyncio
import logging
import os
import time

from telegram import Update
from telegram.ext import ContextTypes

from commands.nivel import register_progress
from database import create_or_get_user, get_user_status
from utils.runtime_guard import rate_limiter

logger = logging.getLogger(__name__)

TERMS_VERSION = os.getenv("TERMS_VERSION", "v1").strip() or "v1"
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()

PROGRESS_RATE_LIMIT = int(os.getenv("PROGRESS_RATE_LIMIT", "1"))
PROGRESS_RATE_WINDOW_SECONDS = float(os.getenv("PROGRESS_RATE_WINDOW_SECONDS", "2.5"))
GATEKEEPER_RATE_LIMIT = int(os.getenv("GATEKEEPER_RATE_LIMIT", "8"))
GATEKEEPER_RATE_WINDOW_SECONDS = float(os.getenv("GATEKEEPER_RATE_WINDOW_SECONDS", "5"))

CHANNEL_MEMBERSHIP_CACHE_SECONDS = max(
    5.0,
    float(os.getenv("CHANNEL_MEMBERSHIP_CACHE_SECONDS", "60")),
)
CHANNEL_MEMBERSHIP_NEGATIVE_CACHE_SECONDS = max(
    1.0,
    float(os.getenv("CHANNEL_MEMBERSHIP_NEGATIVE_CACHE_SECONDS", "8")),
)
CHANNEL_MEMBERSHIP_CACHE_MAX = max(
    1000,
    int(os.getenv("CHANNEL_MEMBERSHIP_CACHE_MAX", "50000")),
)

_channel_membership_cache: dict[int, tuple[float, bool]] = {}
_channel_membership_cache_lock = asyncio.Lock()

ADMIN_COMMANDS = {
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

IGNORED_PROGRESS_COMMANDS = {
    "/start",
    *ADMIN_COMMANDS,
}


def _is_group(update: Update) -> bool:
    return bool(
        update.effective_chat
        and update.effective_chat.type in ("group", "supergroup")
    )


def _extract_command(text: str) -> str:
    value = (text or "").strip()
    if not value.startswith("/"):
        return ""
    return value.split()[0].split("@")[0].lower()


def _load_user_status(user_id: int) -> dict:
    """Run blocking database access outside Telegram's event loop."""

    create_or_get_user(int(user_id))
    return dict(get_user_status(int(user_id)) or {})


def _member_is_valid(member) -> bool:
    status = str(getattr(member, "status", "") or "").strip().lower()
    if status in {"creator", "administrator", "member"}:
        return True
    return status == "restricted" and bool(getattr(member, "is_member", False))


async def check_required_channel_membership(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    *,
    force: bool = False,
) -> bool:
    """Verify channel membership with a short bounded in-memory cache.

    Normal commands reuse positive checks for a short period instead of making a
    Telegram API roundtrip on every command. The start command can use force=True
    so a user who just joined the channel is recognized immediately.
    """

    if not REQUIRED_CHANNEL:
        return True

    uid = int(user_id)
    now = time.monotonic()

    if not force:
        async with _channel_membership_cache_lock:
            cached = _channel_membership_cache.get(uid)
            if cached is not None:
                expires_at, cached_ok = cached
                if now < expires_at:
                    return bool(cached_ok)
                _channel_membership_cache.pop(uid, None)

    try:
        member = await context.bot.get_chat_member(
            chat_id=REQUIRED_CHANNEL,
            user_id=uid,
        )
        ok = _member_is_valid(member)
    except Exception:
        logger.exception(
            "Falha ao verificar canal obrigatório user_id=%s channel=%s",
            uid,
            REQUIRED_CHANNEL,
        )
        return False

    ttl = (
        CHANNEL_MEMBERSHIP_CACHE_SECONDS
        if ok
        else CHANNEL_MEMBERSHIP_NEGATIVE_CACHE_SECONDS
    )
    expires_at = time.monotonic() + ttl

    async with _channel_membership_cache_lock:
        _channel_membership_cache[uid] = (expires_at, ok)

        if len(_channel_membership_cache) > CHANNEL_MEMBERSHIP_CACHE_MAX:
            current = time.monotonic()
            expired = [
                key
                for key, (expiry, _) in _channel_membership_cache.items()
                if expiry <= current
            ]
            for key in expired:
                _channel_membership_cache.pop(key, None)

            if len(_channel_membership_cache) > CHANNEL_MEMBERSHIP_CACHE_MAX:
                overflow = len(_channel_membership_cache) - CHANNEL_MEMBERSHIP_CACHE_MAX
                oldest = sorted(
                    _channel_membership_cache.items(),
                    key=lambda item: item[1][0],
                )
                for key, _ in oldest[:overflow]:
                    _channel_membership_cache.pop(key, None)

    return ok


async def _is_in_required_channel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> bool:
    return await check_required_channel_membership(context, user_id)


async def _maybe_register_progress(update: Update, command_name: str) -> None:
    if not command_name or command_name in IGNORED_PROGRESS_COMMANDS:
        return

    user = update.effective_user
    if not user:
        return

    allowed = await rate_limiter.allow(
        key=f"progress:{user.id}",
        limit=PROGRESS_RATE_LIMIT,
        window_seconds=PROGRESS_RATE_WINDOW_SECONDS,
    )
    if not allowed:
        return

    try:
        await register_progress(update)
    except Exception:
        # O sistema de nível nunca deve derrubar o comando principal.
        logger.exception(
            "Falha ao registrar progresso user_id=%s command=%s",
            user.id,
            command_name,
        )


async def gatekeeper(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[bool, str]:
    """
    Return whether the update may execute and an optional user-facing block message.

    ``(True, "")`` allows execution, ``(False, "")`` blocks silently and
    ``(False, message)`` blocks while asking the command to show ``message``.
    """

    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return False, ""

    text = message.text or ""
    command_name = _extract_command(text)

    # Administrative card handlers perform their own numeric-ID authorization
    # and rate limiting before touching data.
    if command_name in ADMIN_COMMANDS:
        return True, ""

    allowed = await rate_limiter.allow(
        key=f"gatekeeper:{user.id}",
        limit=GATEKEEPER_RATE_LIMIT,
        window_seconds=GATEKEEPER_RATE_WINDOW_SECONDS,
    )
    if not allowed:
        return False, ""

    # =====================
    # GRUPOS
    # =====================
    if _is_group(update):
        if not text.startswith("/"):
            return False, ""
        if command_name == "/start":
            return True, ""
        return False, ""

    # =====================
    # PRIVADO
    # =====================
    if command_name == "/start":
        return True, ""

    user_id = int(user.id)
    try:
        status = await asyncio.to_thread(_load_user_status, user_id)
    except Exception:
        logger.exception("Falha ao carregar estado do usuário user_id=%s", user_id)
        return False, (
            "⚠️ <b>Serviço temporariamente indisponível</b>\n\n"
            "Não foi possível validar sua conta agora. Tente novamente em instantes."
        )

    # -------------------
    # TERMOS
    # -------------------
    if not status.get("terms_accepted"):
        return False, (
            "📜 <b>Termos obrigatórios</b>\n\n"
            "Antes de usar o <b>Source Baltigo</b>, você precisa aceitar "
            "os <b>Termos de Uso</b>.\n\n"
            "➡️ Envie <b>/start</b> para continuar."
        )

    if status.get("terms_version") != TERMS_VERSION:
        return False, (
            "📜 <b>Atualização dos Termos</b>\n\n"
            "Atualizamos nossos termos.\n"
            "Por favor envie <b>/start</b> novamente."
        )

    # -------------------
    # CANAL
    # -------------------
    if not await _is_in_required_channel(update, context, user_id):
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
