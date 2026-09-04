from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.parse import parse_qsl

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # pragma: no cover - dependency is declared in requirements.txt
    InvalidSignature = Exception
    Ed25519PublicKey = None  # type: ignore[assignment]


DEFAULT_MAX_AGE_SECONDS = max(60, int(os.getenv("WEBAPP_INITDATA_MAX_AGE_SECONDS", "21600")))
MAX_FUTURE_SKEW_SECONDS = max(0, int(os.getenv("WEBAPP_INITDATA_FUTURE_SKEW_SECONDS", "120")))
TELEGRAM_PRODUCTION_PUBLIC_KEY = bytes.fromhex(
    "e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d"
)
TELEGRAM_TEST_PUBLIC_KEY = bytes.fromhex(
    "40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec"
)


class TelegramWebAppAuthError(ValueError):
    pass


def _telegram_bot_id(bot_token: str) -> int:
    override = str(os.getenv("TELEGRAM_WEBAPP_BOT_ID", "") or "").strip()
    candidate = override or str(bot_token or "").strip().split(":", 1)[0]
    try:
        bot_id = int(candidate)
    except (TypeError, ValueError) as exc:
        raise TelegramWebAppAuthError("bot_id_invalid") from exc
    if bot_id <= 0:
        raise TelegramWebAppAuthError("bot_id_invalid")
    return bot_id


def _decode_signature(value: str) -> bytes:
    raw = str(value or "").strip()
    if not raw:
        raise TelegramWebAppAuthError("init_data_signature_missing")
    padded = raw + ("=" * (-len(raw) % 4))
    try:
        return base64.b64decode(padded, altchars=b"-_", validate=True)
    except (ValueError, TypeError, base64.binascii.Error) as exc:
        raise TelegramWebAppAuthError("init_data_signature_invalid") from exc


def _verify_hmac(data: dict[str, str], received_hash: str, bot_token: str) -> bool:
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret_key,
        check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(calculated_hash, received_hash)


def _verify_telegram_signature(data: dict[str, str], bot_token: str) -> bool:
    signature = _decode_signature(data.get("signature", ""))
    signed_data = {
        key: value
        for key, value in data.items()
        if key not in {"hash", "signature"}
    }
    check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(signed_data.items())
    )
    message = f"{_telegram_bot_id(bot_token)}:WebAppData\n{check_string}".encode("utf-8")

    if Ed25519PublicKey is None:
        raise TelegramWebAppAuthError("init_data_signature_unavailable")

    env_name = str(os.getenv("TELEGRAM_WEBAPP_ENV", "production") or "production")
    public_key = (
        TELEGRAM_TEST_PUBLIC_KEY
        if env_name.strip().lower() in {"test", "testing"}
        else TELEGRAM_PRODUCTION_PUBLIC_KEY
    )
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except InvalidSignature:
        return False
    except (TypeError, ValueError) as exc:
        raise TelegramWebAppAuthError("init_data_signature_invalid") from exc
    return True


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

    parsed = dict(pairs)
    received_hash = str(parsed.get("hash", "") or "").strip().lower()
    if len(received_hash) != 64:
        raise TelegramWebAppAuthError("init_data_hash_missing")

    hmac_data = {key: value for key, value in parsed.items() if key != "hash"}
    auth_method = "hmac"
    if not _verify_hmac(hmac_data, received_hash, token):
        if "signature" not in parsed:
            raise TelegramWebAppAuthError("init_data_hash_invalid")
        if not _verify_telegram_signature(parsed, token):
            raise TelegramWebAppAuthError("init_data_signature_invalid")
        auth_method = "ed25519"

    try:
        auth_date = int(str(parsed.get("auth_date") or "0"))
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

    user_raw = parsed.get("user")
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

    raw_data = {
        key: value
        for key, value in parsed.items()
        if key != "hash"
    }
    return {
        "user": user,
        "user_id": user_id,
        "auth_date": auth_date,
        "auth_method": auth_method,
        "raw": raw_data,
    }
