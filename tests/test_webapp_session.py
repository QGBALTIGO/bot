from __future__ import annotations

import pytest

from utils.webapp_session import (
    WebAppSessionError,
    bearer_token,
    create_session_token,
    validate_session_token,
)


def test_session_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAPP_SESSION_SECRET", "test-secret-that-is-not-public")
    token = create_session_token(123456, now=2_000_000_000, ttl_seconds=3600)
    payload = validate_session_token(token, now=2_000_000_100)
    assert payload["user_id"] == 123456
    assert payload["expires_at"] == 2_000_003_600


def test_tampered_session_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAPP_SESSION_SECRET", "test-secret")
    token = create_session_token(123, now=2_000_000_000, ttl_seconds=3600)
    payload, signature = token.split(".", 1)
    tampered = ("A" if payload[0] != "A" else "B") + payload[1:] + "." + signature

    with pytest.raises(WebAppSessionError):
        validate_session_token(tampered, now=2_000_000_100)


def test_expired_session_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAPP_SESSION_SECRET", "test-secret")
    token = create_session_token(123, now=2_000_000_000, ttl_seconds=60)
    with pytest.raises(WebAppSessionError, match="session_expired"):
        validate_session_token(token, now=2_000_000_061)


def test_different_secret_invalidates_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAPP_SESSION_SECRET", "secret-a")
    token = create_session_token(123, now=2_000_000_000, ttl_seconds=3600)
    monkeypatch.setenv("WEBAPP_SESSION_SECRET", "secret-b")
    with pytest.raises(WebAppSessionError, match="session_signature_invalid"):
        validate_session_token(token, now=2_000_000_100)


def test_bearer_parser_only_accepts_bearer_scheme() -> None:
    assert bearer_token("Bearer abc.def") == "abc.def"
    assert bearer_token("bearer xyz") == "xyz"
    assert bearer_token("Basic nope") == ""
    assert bearer_token("") == ""
