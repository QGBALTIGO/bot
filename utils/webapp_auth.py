import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import parse_qsl


class WebAppAuthError(ValueError):
    """Raised when Telegram WebApp init data cannot be trusted."""


@dataclass(frozen=True)
class TelegramWebAppIdentity:
    user_id: int
    username: str
    first_name: str
    last_name: str
    auth_date: int
    raw_user: Dict[str, Any]

    @property
    def full_name(self) -> str:
        return " ".join(
            part for part in (self.first_name.strip(), self.last_name.strip()) if part
        ).strip()


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 3600,
    now: int | None = None,
) -> TelegramWebAppIdentity:
    """Validate Telegram Mini App initData using Telegram's HMAC scheme."""

    init_data = (init_data or "").strip()
    bot_token = (bot_token or "").strip()

    if not init_data:
        raise WebAppAuthError("initData ausente")
    if not bot_token:
        raise WebAppAuthError("BOT_TOKEN ausente")

    try:
        values = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise WebAppAuthError("initData inválido") from exc

    received_hash = values.pop("hash", "")
    if not received_hash:
        raise WebAppAuthError("hash ausente")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(values.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise WebAppAuthError("assinatura inválida")

    try:
        auth_date = int(values.get("auth_date") or 0)
    except (TypeError, ValueError) as exc:
        raise WebAppAuthError("auth_date inválido") from exc

    if auth_date <= 0:
        raise WebAppAuthError("auth_date ausente")

    current_time = int(time.time() if now is None else now)
    age = current_time - auth_date
    if age < -30:
        raise WebAppAuthError("auth_date no futuro")
    if max_age_seconds > 0 and age > max_age_seconds:
        raise WebAppAuthError("initData expirado")

    raw_user_json = values.get("user")
    if not raw_user_json:
        raise WebAppAuthError("usuário ausente")

    try:
        raw_user = json.loads(raw_user_json)
        user_id = int(raw_user.get("id") or 0)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WebAppAuthError("usuário inválido") from exc

    if user_id <= 0:
        raise WebAppAuthError("user_id inválido")

    return TelegramWebAppIdentity(
        user_id=user_id,
        username=str(raw_user.get("username") or "").strip(),
        first_name=str(raw_user.get("first_name") or "").strip(),
        last_name=str(raw_user.get("last_name") or "").strip(),
        auth_date=auth_date,
        raw_user=raw_user,
    )
