from __future__ import annotations

import asyncio
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from database import pool


REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourceBaltigo").strip()
_SELFTEST_USER_ID = -1
_TABLES_READY = False
_TABLES_LOCK = threading.Lock()
_CLEANUP_LOCK = threading.Lock()
_LAST_CLEANUP_MONOTONIC = 0.0
_CLEANUP_INTERVAL_SECONDS = 60.0

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS channel_verification_requests (
    request_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_channel_verification_requests_pending
    ON channel_verification_requests(status, created_at);

CREATE TABLE IF NOT EXISTS channel_verification_worker (
    worker_key TEXT PRIMARY KEY,
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    channel TEXT NOT NULL DEFAULT ''
);
"""


def ensure_channel_verification_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return

    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_TABLE_SQL)
            conn.commit()
        _TABLES_READY = True


def _cleanup_old_requests() -> None:
    global _LAST_CLEANUP_MONOTONIC
    now = time.monotonic()
    if now - _LAST_CLEANUP_MONOTONIC < _CLEANUP_INTERVAL_SECONDS:
        return

    with _CLEANUP_LOCK:
        now = time.monotonic()
        if now - _LAST_CLEANUP_MONOTONIC < _CLEANUP_INTERVAL_SECONDS:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM channel_verification_requests "
                    "WHERE created_at < NOW() - INTERVAL '10 minutes'"
                )
            conn.commit()
        _LAST_CLEANUP_MONOTONIC = now


def create_verification_request(user_id: int) -> str:
    ensure_channel_verification_tables()
    _cleanup_old_requests()
    request_id = secrets.token_urlsafe(24)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO channel_verification_requests(request_id, user_id, status)
                VALUES (%s, %s, 'pending')
                """,
                (request_id, int(user_id)),
            )
        conn.commit()
    return request_id


def get_verification_result(request_id: str, user_id: int) -> dict[str, Any] | None:
    ensure_channel_verification_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT request_id, user_id, status, message, created_at, updated_at
                FROM channel_verification_requests
                WHERE request_id = %s AND user_id = %s
                """,
                (str(request_id), int(user_id)),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def wait_for_verification(user_id: int, timeout_seconds: float = 8.0) -> dict[str, Any]:
    request_id = create_verification_request(user_id)
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))

    while time.monotonic() < deadline:
        row = get_verification_result(request_id, user_id)
        status = str((row or {}).get("status") or "")
        if status == "ok":
            return {"ok": True, "status": "ok"}
        if status == "not_member":
            return {"ok": False, "status": "not_member"}
        if status == "error":
            return {
                "ok": False,
                "status": "error",
                "message": str((row or {}).get("message") or "Não foi possível verificar sua inscrição agora."),
            }
        time.sleep(0.20)

    return {
        "ok": False,
        "status": "timeout",
        "message": "A verificação demorou mais que o esperado. Toque em verificar novamente.",
    }


def _claim_pending(limit: int = 10) -> list[dict[str, Any]]:
    ensure_channel_verification_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH picked AS (
                    SELECT request_id
                    FROM channel_verification_requests
                    WHERE (
                        status = 'pending'
                        OR (status = 'processing' AND updated_at < NOW() - INTERVAL '15 seconds')
                    )
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE channel_verification_requests AS r
                SET status = 'processing', updated_at = NOW(), message = NULL
                FROM picked
                WHERE r.request_id = picked.request_id
                RETURNING r.request_id, r.user_id
                """,
                (max(1, int(limit)),),
            )
            rows = cur.fetchall() or []
        conn.commit()
    return [dict(row) for row in rows]


def _complete(request_id: str, status: str, message: str | None = None) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE channel_verification_requests
                SET status = %s, message = %s, updated_at = NOW()
                WHERE request_id = %s
                """,
                (status, message, str(request_id)),
            )
        conn.commit()


def _heartbeat() -> None:
    ensure_channel_verification_tables()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO channel_verification_worker(worker_key, last_seen, channel)
                VALUES ('telegram-bot', NOW(), %s)
                ON CONFLICT (worker_key) DO UPDATE
                SET last_seen = EXCLUDED.last_seen, channel = EXCLUDED.channel
                """,
                (REQUIRED_CHANNEL,),
            )
        conn.commit()


def _heartbeat_state() -> dict[str, Any]:
    ensure_channel_verification_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT last_seen, channel
                FROM channel_verification_worker
                WHERE worker_key = 'telegram-bot'
                """
            )
            row = cur.fetchone()

    if not row:
        return {"ok": False, "status": "missing"}

    last_seen = row["last_seen"]
    now = datetime.now(timezone.utc)
    age = max(0.0, (now - last_seen).total_seconds())
    return {
        "ok": age <= 15.0,
        "status": "online" if age <= 15.0 else "stale",
        "age_seconds": round(age, 2),
        "channel": str(row.get("channel") or ""),
    }


def worker_health() -> dict[str, Any]:
    """Live health check including a real Telegram roundtrip through the bot worker."""
    heartbeat = _heartbeat_state()
    if not heartbeat.get("ok"):
        return heartbeat

    probe = wait_for_verification(_SELFTEST_USER_ID, timeout_seconds=5.0)
    probe_status = str(probe.get("status") or "")
    return {
        **heartbeat,
        "ok": probe_status == "ok",
        "roundtrip": probe_status,
        "roundtrip_message": str(probe.get("message") or ""),
    }


def _member_is_valid(member: Any) -> bool:
    status = str(getattr(member, "status", "") or "").strip().lower()
    if status in {"creator", "administrator", "member"}:
        return True
    return status == "restricted" and bool(getattr(member, "is_member", False))


def _member_is_admin(member: Any) -> bool:
    status = str(getattr(member, "status", "") or "").strip().lower()
    return status in {"creator", "administrator"}


async def channel_verification_worker(application) -> None:
    ensure_channel_verification_tables()
    print("[terms-membership] worker do bot iniciado", flush=True)

    while True:
        try:
            _heartbeat()
            rows = _claim_pending(limit=10)
            if not rows:
                await asyncio.sleep(0.35)
                continue

            for row in rows:
                request_id = str(row["request_id"])
                user_id = int(row["user_id"])
                try:
                    if not REQUIRED_CHANNEL:
                        _complete(request_id, "ok")
                        continue

                    if user_id == _SELFTEST_USER_ID:
                        me = await application.bot.get_me()
                        member = await application.bot.get_chat_member(
                            chat_id=REQUIRED_CHANNEL,
                            user_id=me.id,
                        )
                        if _member_is_admin(member):
                            _complete(request_id, "ok")
                        else:
                            _complete(
                                request_id,
                                "error",
                                "O bot está no canal, mas não é administrador.",
                            )
                        continue

                    member = await application.bot.get_chat_member(
                        chat_id=REQUIRED_CHANNEL,
                        user_id=user_id,
                    )
                    _complete(
                        request_id,
                        "ok" if _member_is_valid(member) else "not_member",
                    )
                except Exception as exc:
                    print(
                        f"[terms-membership] worker falhou user_id={user_id}: "
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    _complete(
                        request_id,
                        "error",
                        "O Telegram não conseguiu verificar sua inscrição agora.",
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                f"[terms-membership] erro no worker: {type(exc).__name__}: {exc}",
                flush=True,
            )
            await asyncio.sleep(1.0)
