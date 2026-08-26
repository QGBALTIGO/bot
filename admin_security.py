from __future__ import annotations

import os
from typing import Any

from admin_repository import record_admin_event
from utils.runtime_guard import rate_limiter


def _ids_from_env(name: str) -> set[int]:
    result: set[int] = set()
    for raw in os.getenv(name, "").split(","):
        value = raw.strip()
        if value.lstrip("-").isdigit():
            parsed = int(value)
            if parsed > 0:
                result.add(parsed)
    return result


def owner_ids() -> set[int]:
    values = _ids_from_env("BOT_OWNER_IDS")
    single = os.getenv("BOT_OWNER_ID", "").strip()
    if single.isdigit() and int(single) > 0:
        values.add(int(single))
    return values


def admin_ids() -> set[int]:
    # Legacy names remain accepted only to make migration non-breaking.
    return owner_ids() | _ids_from_env("ADMIN_IDS") | _ids_from_env("ADMINS") | _ids_from_env("CARD_ADMIN_IDS")


def is_owner(user_id: int) -> bool:
    return int(user_id) in owner_ids()


def is_admin(user_id: int) -> bool:
    return int(user_id) in admin_ids()


async def authorize_admin(
    update: Any,
    *,
    action: str,
    owner_only: bool = False,
    private_only: bool = False,
    limit: int = 12,
    window_seconds: float = 10.0,
) -> tuple[bool, str]:
    user = getattr(update, "effective_user", None)
    chat = getattr(update, "effective_chat", None)
    if not user:
        return False, "Usuário não identificado."

    user_id = int(user.id)
    allowed_role = is_owner(user_id) if owner_only else is_admin(user_id)
    if not allowed_role:
        record_admin_event(user_id, action, status="denied", metadata={"owner_only": owner_only})
        return False, "❌ Você não tem permissão para usar esse comando."

    if private_only and chat and str(getattr(chat, "type", "")) != "private":
        record_admin_event(user_id, action, status="blocked_context", metadata={"chat_type": str(getattr(chat, "type", ""))})
        return False, "⛔ Esse comando administrativo só pode ser usado no privado."

    allowed = await rate_limiter.allow(
        f"admin-v2:{user_id}:{action}",
        limit=max(1, int(limit)),
        window_seconds=max(1.0, float(window_seconds)),
    )
    if not allowed:
        record_admin_event(user_id, action, status="rate_limited")
        return False, "⌛ Aguarde um instante antes de repetir essa ação administrativa."

    record_admin_event(user_id, action, status="authorized")
    return True, ""
