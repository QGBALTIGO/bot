from __future__ import annotations

import time
from database_core import run

DEFAULT_THRESHOLD = 75
MIN_THRESHOLD = 20
MAX_THRESHOLD = 500
_ENSURED = False
_CACHE: dict[int, tuple[float, dict]] = {}
CACHE_TTL = 30.0


def ensure_capture_group_settings() -> None:
    global _ENSURED
    if _ENSURED:
        return
    run(
        """
        CREATE TABLE IF NOT EXISTS source_capture_group_settings (
            chat_id BIGINT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            message_threshold INTEGER NOT NULL DEFAULT 75
                CHECK(message_threshold BETWEEN 20 AND 500),
            updated_by BIGINT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    _ENSURED = True


def capture_group_settings(chat_id: int, default_threshold: int = DEFAULT_THRESHOLD) -> dict:
    ensure_capture_group_settings()
    cached = _CACHE.get(int(chat_id))
    if cached and time.monotonic() - cached[0] < CACHE_TTL:
        return dict(cached[1])
    row = run(
        "SELECT enabled,message_threshold FROM source_capture_group_settings WHERE chat_id=%s",
        (int(chat_id),),
        fetch="one",
    )
    if not row:
        state = {"enabled": True, "message_threshold": max(MIN_THRESHOLD, min(MAX_THRESHOLD, int(default_threshold)))}
    else:
        state = {
            "enabled": bool(row.get("enabled")),
            "message_threshold": int(row.get("message_threshold") or default_threshold),
        }
    _CACHE[int(chat_id)] = (time.monotonic(), dict(state))
    return state


def save_capture_group_settings(chat_id: int, user_id: int, *, enabled: bool | None = None, message_threshold: int | None = None) -> dict:
    ensure_capture_group_settings()
    current = capture_group_settings(chat_id)
    next_enabled = current["enabled"] if enabled is None else bool(enabled)
    next_threshold = current["message_threshold"] if message_threshold is None else int(message_threshold)
    if not MIN_THRESHOLD <= next_threshold <= MAX_THRESHOLD:
        raise ValueError(f"message_threshold must be between {MIN_THRESHOLD} and {MAX_THRESHOLD}")
    run(
        """
        INSERT INTO source_capture_group_settings(chat_id,enabled,message_threshold,updated_by,updated_at)
        VALUES(%s,%s,%s,%s,NOW())
        ON CONFLICT(chat_id) DO UPDATE SET
          enabled=EXCLUDED.enabled,
          message_threshold=EXCLUDED.message_threshold,
          updated_by=EXCLUDED.updated_by,
          updated_at=NOW()
        """,
        (int(chat_id), next_enabled, next_threshold, int(user_id)),
    )
    state = {"enabled": next_enabled, "message_threshold": next_threshold}
    _CACHE[int(chat_id)] = (time.monotonic(), dict(state))
    return state
