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
OFFICIAL_BOT_ID = 7_342_037_359
OFFICIAL_AUTH_DATE = 1_733_509_682
OFFICIAL_INIT_DATA = (
    "user=%7B%22id%22%3A279058397%2C%22first_name%22%3A%22Vladislav%20%2B%20-%20%3F%20%5C%2F%22%2C%22last_name%22%3A%22Kibenko%22%2C%22username%22%3A%22vdkfrost%22%2C%22language_code%22%3A%22ru%22%2C%22is_premium%22%3Atrue%2C%22allows_write_to_pm%22%3Atrue%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2F4FPEE4tmP3ATHa57u6MqTDih13LTOiMoKoLDRG4PnSA.svg%22%7D"
    "&chat_instance=8134722200314281151"
    "&chat_type=private"
    "&auth_date=1733509682"
    "&signature=TYJxVcisqbWjtodPepiJ6ghziUL94-KNpG8Pau-X7oNNLNBM72APCpi_RKiUlBvcqo5L-LAxIc3dnTzcZX_PDg"
    "&hash=a433d8f9847bd6addcc563bff7cc82c89e97ea0d90c11fe5729cae6796a36d73"
)


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
    assert result["auth_method"] == "hmac"


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


def test_telegram_signature_accepts_rotated_secret_for_same_bot_id() -> None:
    result = validate_telegram_init_data(
        OFFICIAL_INIT_DATA,
        f"{OFFICIAL_BOT_ID}:rotated-or-stale-secret",
        max_age_seconds=86_400,
        now=OFFICIAL_AUTH_DATE,
    )

    assert result["user_id"] == 279058397
    assert result["auth_method"] == "ed25519"


def test_telegram_signature_rejects_wrong_bot_id() -> None:
    with pytest.raises(TelegramWebAppAuthError, match="init_data_signature_invalid"):
        validate_telegram_init_data(
            OFFICIAL_INIT_DATA,
            f"{OFFICIAL_BOT_ID + 1}:wrong-bot",
            max_age_seconds=86_400,
            now=OFFICIAL_AUTH_DATE,
        )


def test_telegram_bot_id_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBAPP_BOT_ID", str(OFFICIAL_BOT_ID))
    result = validate_telegram_init_data(
        OFFICIAL_INIT_DATA,
        "1:wrong-token-from-another-service",
        max_age_seconds=86_400,
        now=OFFICIAL_AUTH_DATE,
    )

    assert result["auth_method"] == "ed25519"
