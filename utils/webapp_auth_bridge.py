from __future__ import annotations

import asyncio
import secrets
import threading
import time
from typing import Any

from psycopg.rows import dict_row

from database import pool
from utils.telegram_webapp_auth import TelegramWebAppAuthError, validate_telegram_init_data


_TABLES_READY = False
_TABLES_LOCK = threading.Lock()
_CLEANUP_LOCK = threading.Lock()
_LAST_CLEANUP_MONOTONIC = 0.0
_CLEANUP_INTERVAL_SECONDS = 60.0

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS webapp_auth_requests (
    request_id TEXT PRIMARY KEY,
    init_data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    user_id BIGINT,
    username TEXT,
    full_name TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_webapp_auth_requests_pending
    ON webapp_auth_requests(status, created_at);
"""


def ensure_webapp_auth_tables() -> None:
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
                    "DELETE FROM webapp_auth_requests "
                    "WHERE created_at < NOW() - INTERVAL '10 minutes'"
                )
            conn.commit()
        _LAST_CLEANUP_MONOTONIC = now


def _delete_request(request_id: str) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM webapp_auth_requests WHERE request_id = %s", (str(request_id),))
        conn.commit()


def create_auth_request(init_data: str) -> str:
    ensure_webapp_auth_tables()
    _cleanup_old_requests()
    request_id = secrets.token_urlsafe(24)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO webapp_auth_requests(request_id, init_data, status)
                VALUES (%s, %s, 'pending')
                """,
                (request_id, str(init_data or "")),
            )
        conn.commit()
    return request_id


def _get_result(request_id: str) -> dict[str, Any] | None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT request_id, status, user_id, username, full_name, error_code
                FROM webapp_auth_requests
                WHERE request_id = %s
                """,
                (str(request_id),),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def wait_for_webapp_auth(init_data: str, timeout_seconds: float = 6.0) -> dict[str, Any]:
    request_id = create_auth_request(init_data)
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    try:
        while time.monotonic() < deadline:
            row = _get_result(request_id)
            status = str((row or {}).get("status") or "")
            if status == "ok":
                return {
                    "ok": True,
                    "user_id": int((row or {}).get("user_id") or 0),
                    "username": str((row or {}).get("username") or ""),
                    "full_name": str((row or {}).get("full_name") or ""),
                }
            if status == "invalid":
                return {
                    "ok": False,
                    "error_code": str((row or {}).get("error_code") or "init_data_invalid"),
                }
            time.sleep(0.15)
        return {"ok": False, "error_code": "auth_bridge_timeout"}
    finally:
        try:
            _delete_request(request_id)
        except Exception:
            pass


def _claim_pending(limit: int = 20) -> list[dict[str, Any]]:
    ensure_webapp_auth_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH picked AS (
                    SELECT request_id
                    FROM webapp_auth_requests
                    WHERE status = 'pending'
                       OR (status = 'processing' AND updated_at < NOW() - INTERVAL '15 seconds')
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE webapp_auth_requests AS r
                SET status = 'processing', updated_at = NOW(), error_code = NULL
                FROM picked
                WHERE r.request_id = picked.request_id
                RETURNING r.request_id, r.init_data
                """,
                (max(1, int(limit)),),
            )
            rows = cur.fetchall() or []
        conn.commit()
    return [dict(row) for row in rows]


def _complete_ok(request_id: str, user: dict[str, Any]) -> None:
    full_name = " ".join(
        part
        for part in (
            str(user.get("first_name") or "").strip(),
            str(user.get("last_name") or "").strip(),
        )
        if part
    ).strip()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE webapp_auth_requests
                SET status = 'ok',
                    user_id = %s,
                    username = %s,
                    full_name = %s,
                    init_data = '',
                    error_code = NULL,
                    updated_at = NOW()
                WHERE request_id = %s
                """,
                (
                    int(user.get("id") or 0),
                    str(user.get("username") or "").strip(),
                    full_name,
                    str(request_id),
                ),
            )
        conn.commit()


def _complete_invalid(request_id: str, error_code: str) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE webapp_auth_requests
                SET status = 'invalid',
                    init_data = '',
                    error_code = %s,
                    updated_at = NOW()
                WHERE request_id = %s
                """,
                (str(error_code or "init_data_invalid"), str(request_id)),
            )
        conn.commit()


async def webapp_auth_worker(application) -> None:
    ensure_webapp_auth_tables()
    print("[webapp-auth] worker iniciado", flush=True)
    token = str(application.bot.token or "").strip()

    while True:
        try:
            _cleanup_old_requests()
            rows = _claim_pending(limit=20)
            if not rows:
                await asyncio.sleep(0.25)
                continue

            for row in rows:
                request_id = str(row.get("request_id") or "")
                init_data = str(row.get("init_data") or "")
                try:
                    validated = validate_telegram_init_data(init_data, token)
                    _complete_ok(request_id, dict(validated.get("user") or {}))
                except TelegramWebAppAuthError as exc:
                    _complete_invalid(request_id, str(exc))
                except Exception as exc:
                    print(
                        f"[webapp-auth] erro request={request_id[:8]} type={type(exc).__name__}",
                        flush=True,
                    )
                    _complete_invalid(request_id, "auth_internal_error")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[webapp-auth] worker error={type(exc).__name__}", flush=True)
            await asyncio.sleep(1.0)
