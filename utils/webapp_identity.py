from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import HTTPException

from database import create_or_get_user
from utils.telegram_webapp_auth import (
    TelegramWebAppAuthError,
    validate_telegram_init_data,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


def verify_telegram_init_data(init_data: str) -> dict:
    """Valida o initData assinado pelo Telegram e normaliza o payload usado pela WebApp."""

    try:
        validated = validate_telegram_init_data(init_data, BOT_TOKEN)
    except TelegramWebAppAuthError as exc:
        code = str(exc) or "init_data_invalid"
        status_code = 503 if code == "bot_token_missing" else 401
        raise HTTPException(status_code=status_code, detail=code) from exc

    return {
        "user": dict(validated.get("user") or {}),
        "raw": dict(validated.get("raw") or {}),
    }


def get_tg_user(x_telegram_init_data: str) -> Dict[str, Any]:
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]

    user_id = int(user["id"])
    username = (user.get("username") or "").strip()
    full_name = " ".join(
        p
        for p in [
            (user.get("first_name") or "").strip(),
            (user.get("last_name") or "").strip(),
        ]
        if p
    ).strip()

    create_or_get_user(user_id)
    return {
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
    }


def coerce_positive_uid(*values: Any) -> int:
    for value in values:
        try:
            uid = int(str(value or "").strip())
        except Exception:
            continue
        if uid > 0:
            return uid
    return 0


def build_fallback_webapp_user(user_id: int) -> Dict[str, Any]:
    from database import get_user_status

    user_id = int(user_id or 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="uid ausente")

    create_or_get_user(user_id)
    row = get_user_status(user_id) or {}

    return {
        "user_id": int(user_id),
        "username": str(row.get("username") or "").strip(),
        "full_name": str(row.get("full_name") or "").strip(),
        "auth_mode": "uid_fallback",
    }


def resolve_webapp_user(
    *,
    x_telegram_init_data: str = "",
    uid: Any = None,
    x_webapp_uid: Any = None,
    body_uid: Any = None,
) -> Dict[str, Any]:
    """Resolve a identidade da MiniApp priorizando sempre o Telegram initData assinado."""

    fallback_uid = coerce_positive_uid(body_uid, uid, x_webapp_uid)

    if x_telegram_init_data:
        data = get_tg_user(x_telegram_init_data)
        signed_user_id = int(data["user_id"])
        if fallback_uid > 0 and fallback_uid != signed_user_id:
            raise HTTPException(status_code=403, detail="uid_divergente")
        data["auth_mode"] = "telegram_init_data"
        return data

    allow_insecure_fallback = os.getenv(
        "ALLOW_INSECURE_WEBAPP_UID_FALLBACK",
        "",
    ).strip().lower() in {"1", "true", "yes", "on"}
    if allow_insecure_fallback and fallback_uid > 0:
        return build_fallback_webapp_user(fallback_uid)

    raise HTTPException(status_code=401, detail="telegram_init_data_required")
