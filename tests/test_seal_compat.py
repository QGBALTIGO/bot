from __future__ import annotations

import time

import pytest

from webapp_routes import seal_compat


def test_seal_session_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456789:test-secret")
    monkeypatch.delenv("SEAL_SESSION_SECRET", raising=False)

    token = seal_compat._issue_session(
        {
            "id": 42,
            "first_name": "Luffy",
            "last_name": "Monkey",
            "username": "strawhat",
            "photo_url": "https://example.test/luffy.jpg",
        }
    )
    payload = seal_compat._read_session(token)

    assert payload["user"]["id"] == 42
    assert payload["user"]["username"] == "strawhat"
    assert payload["exp"] > int(time.time())


def test_seal_session_rejects_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456789:test-secret")
    token = seal_compat._issue_session({"id": 42, "first_name": "Luffy"})
    body, signature = token.rsplit(".", 1)
    tampered = ("A" if body[0] != "A" else "B") + body[1:] + "." + signature

    with pytest.raises(ValueError):
        seal_compat._read_session(tampered)


def test_character_payload_preserves_source_identity() -> None:
    payload = seal_compat._character_payload(
        {
            "id": 184,
            "name": "Monkey D. Luffy",
            "anime": "One Piece",
            "image": "https://example.test/luffy.jpg",
            "rarity": "Legendary",
        },
        3,
    )

    assert payload["id"] == "184"
    assert payload["name"] == "Monkey D. Luffy"
    assert payload["count"] == 3
    assert payload["owned"] is True
    assert payload["rarity"] == "Legendary"


def test_missing_rarity_has_safe_default() -> None:
    payload = seal_compat._character_payload(
        {"id": 1, "name": "Test", "anime": "Test Anime", "image": ""},
        1,
    )
    assert payload["rarity"] == "COMMON"
