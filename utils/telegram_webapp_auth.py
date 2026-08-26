from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.parse import parse_qsl


DEFAULT_MAX_AGE_SECONDS = max(60, int(os.getenv("WEBAPP_INITDATA_MAX_AGE_SECONDS", "21600")))
MAX_FUTURE_SKEW_SECONDS = max(0, int(os.getenv("WEBAPP_INITDATA_FUTURE_SKEW_SECONDS", "120")))


class TelegramWebAppAuthError(ValueError):
    pass


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    raw = str(init_data or "").strip()
    token = str(bot_token or "").strip()
    if not raw:
        raise TelegramWebAppAuthError("init_data_missing")
    if not token:
        raise TelegramWebAppAuthError("bot_token_missing")

    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=False)
    if not pairs:
        raise TelegramWebAppAuthError("init_data_invalid")

    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise TelegramWebAppAuthError("init_data_duplicate_fields")

    data = dict(pairs)
    received_hash = str(data.pop("hash", "") or "").strip().lower()
    if len(received_hash) != 64:
        raise TelegramWebAppAuthError("init_data_hash_missing")

    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramWebAppAuthError("init_data_hash_invalid")

    try:
        auth_date = int(str(data.get("auth_date") or "0"))
    except (TypeError, ValueError) as exc:
        raise TelegramWebAppAuthError("auth_date_invalid") from exc
    if auth_date <= 0:
        raise TelegramWebAppAuthError("auth_date_invalid")

    current_time = int(time.time() if now is None else now)
    max_age = DEFAULT_MAX_AGE_SECONDS if max_age_seconds is None else max(60, int(max_age_seconds))
    if auth_date > current_time + MAX_FUTURE_SKEW_SECONDS:
        raise TelegramWebAppAuthError("auth_date_future")
    if current_time - auth_date > max_age:
        raise TelegramWebAppAuthError("auth_date_expired")

    user_raw = data.get("user")
    if not user_raw:
        raise TelegramWebAppAuthError("user_missing")
    try:
        user = json.loads(user_raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramWebAppAuthError("user_invalid") from exc
    if not isinstance(user, dict):
        raise TelegramWebAppAuthError("user_invalid")

    try:
        user_id = int(user.get("id") or 0)
    except (TypeError, ValueError) as exc:
        raise TelegramWebAppAuthError("user_invalid") from exc
    if user_id <= 0:
        raise TelegramWebAppAuthError("user_invalid")

    return {
        "user": user,
        "user_id": user_id,
        "auth_date": auth_date,
        "raw": data,
    }
