from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from utils.webapp_identity import build_fallback_webapp_user, resolve_webapp_user
from utils.webapp_session import WebAppSessionError, bearer_token, validate_session_token


def resolve_source_v2_identity(
    *,
    x_telegram_init_data: str = "",
    x_webapp_uid: str = "",
    authorization: str = "",
) -> dict[str, Any]:
    """Resolve the Source v2 identity from Telegram initData or a Source-signed session."""

    if str(x_telegram_init_data or "").strip():
        return resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            x_webapp_uid=x_webapp_uid,
        )

    token = bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="telegram_init_data_or_session_required")
    try:
        session = validate_session_token(token)
    except WebAppSessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc) or "session_invalid") from exc

    identity = build_fallback_webapp_user(int(session["user_id"]))
    identity["auth_mode"] = "source_session"
    return identity
