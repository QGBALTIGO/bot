from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from utils.telegram_webapp_auth import (
    TelegramWebAppAuthError,
    validate_telegram_init_data,
)

BOT_TOKEN = "123456789:abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"
NOW = 2_000_000_000


def _signed_init_data(
    *,
    user_id: int = 42,
    auth_date: int = NOW,
    bot_token: str = BOT_TOKEN,
) -> str:
    data = {
        "auth_date": str(auth_date),
        "query_id": "AAExampleQuery",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Akira",
                "username": "akira_test",
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    data["hash"] = hmac.new(
        secret_key,
        check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(data)


def test_valid_signed_identity_is_accepted() -> None:
    result = validate_telegram_init_data(
        _signed_init_data(user_id=987654321),
        BOT_TOKEN,
        max_age_seconds=600,
        now=NOW,
    )

    assert result["user_id"] == 987654321
    assert result["user"]["username"] == "akira_test"
    assert result["auth_date"] == NOW


def test_tampered_user_id_is_rejected() -> None:
    valid = _signed_init_data(user_id=100)
    tampered = valid.replace("%22id%22%3A100", "%22id%22%3A999")

    with pytest.raises(TelegramWebAppAuthError, match="init_data_hash_invalid"):
        validate_telegram_init_data(
            tampered,
            BOT_TOKEN,
            max_age_seconds=600,
            now=NOW,
        )


def test_wrong_bot_token_is_rejected() -> None:
    with pytest.raises(TelegramWebAppAuthError, match="init_data_hash_invalid"):
        validate_telegram_init_data(
            _signed_init_data(),
            BOT_TOKEN + "wrong",
            max_age_seconds=600,
            now=NOW,
        )


def test_expired_init_data_is_rejected() -> None:
    with pytest.raises(TelegramWebAppAuthError, match="auth_date_expired"):
        validate_telegram_init_data(
            _signed_init_data(auth_date=NOW - 601),
            BOT_TOKEN,
            max_age_seconds=600,
            now=NOW,
        )


def test_future_init_data_is_rejected() -> None:
    with pytest.raises(TelegramWebAppAuthError, match="auth_date_future"):
        validate_telegram_init_data(
            _signed_init_data(auth_date=NOW + 121),
            BOT_TOKEN,
            max_age_seconds=600,
            now=NOW,
        )


def test_duplicate_fields_are_rejected() -> None:
    duplicated = _signed_init_data() + "&auth_date=" + str(NOW)

    with pytest.raises(TelegramWebAppAuthError, match="init_data_duplicate_fields"):
        validate_telegram_init_data(
            duplicated,
            BOT_TOKEN,
            max_age_seconds=600,
            now=NOW,
        )
