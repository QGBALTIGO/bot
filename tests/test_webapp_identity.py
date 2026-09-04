from __future__ import annotations

import pytest
from fastapi import HTTPException

from utils import webapp_identity


def test_signed_identity_wins_and_keeps_auth_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        webapp_identity,
        "get_tg_user",
        lambda _value: {"user_id": 42, "username": "akira", "full_name": "Akira"},
    )

    result = webapp_identity.resolve_webapp_user(
        x_telegram_init_data="signed",
        uid=42,
        x_webapp_uid="42",
    )

    assert result["user_id"] == 42
    assert result["auth_mode"] == "telegram_init_data"


def test_signed_identity_rejects_divergent_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        webapp_identity,
        "get_tg_user",
        lambda _value: {"user_id": 42, "username": "", "full_name": ""},
    )

    with pytest.raises(HTTPException) as exc_info:
        webapp_identity.resolve_webapp_user(
            x_telegram_init_data="signed",
            body_uid=99,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "uid_divergente"


def test_uid_fallback_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOW_INSECURE_WEBAPP_UID_FALLBACK", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        webapp_identity.resolve_webapp_user(uid=42)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "telegram_init_data_required"


def test_uid_fallback_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_INSECURE_WEBAPP_UID_FALLBACK", "true")
    monkeypatch.setattr(
        webapp_identity,
        "build_fallback_webapp_user",
        lambda user_id: {
            "user_id": int(user_id),
            "username": "",
            "full_name": "",
            "auth_mode": "uid_fallback",
        },
    )

    result = webapp_identity.resolve_webapp_user(body_uid="77")

    assert result["user_id"] == 77
    assert result["auth_mode"] == "uid_fallback"


def test_uid_coercion_ignores_invalid_and_non_positive_values() -> None:
    assert webapp_identity.coerce_positive_uid("", "abc", 0, -3, "15") == 15
    assert webapp_identity.coerce_positive_uid(None, "abc", 0, -3) == 0
