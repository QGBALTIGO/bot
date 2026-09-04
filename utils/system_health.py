from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

_PROCESS_STARTED_MONOTONIC = time.monotonic()
_PROCESS_STARTED_AT = datetime.now(timezone.utc)


def application_version() -> str:
    for name in (
        "RAILWAY_GIT_COMMIT_SHA",
        "GIT_COMMIT_SHA",
        "SOURCE_VERSION",
    ):
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value[:12]
    return "unknown"


def uptime_seconds() -> int:
    return max(0, int(time.monotonic() - _PROCESS_STARTED_MONOTONIC))


def started_at_iso() -> str:
    return _PROCESS_STARTED_AT.isoformat()


def database_snapshot() -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from database import pool

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
        ok = bool(row and int(row[0]) == 1)
        error = "" if ok else "unexpected_database_response"

        stats: dict[str, Any] = {}
        get_stats = getattr(pool, "get_stats", None)
        if callable(get_stats):
            try:
                raw_stats = get_stats() or {}
                if isinstance(raw_stats, dict):
                    allowed = {
                        "pool_min",
                        "pool_max",
                        "pool_size",
                        "pool_available",
                        "requests_waiting",
                        "requests_num",
                        "requests_queued",
                        "connections_num",
                    }
                    stats = {
                        str(key): value
                        for key, value in raw_stats.items()
                        if str(key) in allowed
                        and isinstance(value, (int, float, str, bool))
                    }
            except Exception:
                stats = {}
    except Exception as exc:
        ok = False
        error = type(exc).__name__
        stats = {}

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "ok": ok,
        "status": "healthy" if ok else "unhealthy",
        "duration_ms": duration_ms,
        "error": error,
        "stats": stats,
    }


def worker_snapshot(application: Any) -> dict[str, dict[str, Any]]:
    bot_data = getattr(application, "bot_data", {}) or {}
    configured = {
        "channel_verification": "terms_channel_worker",
        "telegram_outbox": "telegram_outbox_worker",
        "aninexus_news": "aninexus_news_worker",
    }
    result: dict[str, dict[str, Any]] = {}

    for label, key in configured.items():
        task = bot_data.get(key)
        if task is None:
            result[label] = {"ok": False, "status": "missing"}
            continue

        try:
            if task.cancelled():
                result[label] = {"ok": False, "status": "cancelled"}
            elif task.done():
                exception = task.exception()
                result[label] = {
                    "ok": exception is None,
                    "status": "stopped" if exception is None else "failed",
                    "error": "" if exception is None else type(exception).__name__,
                }
            else:
                result[label] = {"ok": True, "status": "running"}
        except Exception as exc:
            result[label] = {
                "ok": False,
                "status": "unknown",
                "error": type(exc).__name__,
            }

    return result


def public_health_snapshot() -> dict[str, Any]:
    database = database_snapshot()
    ok = bool(database.get("ok"))
    return {
        "ok": ok,
        "status": "healthy" if ok else "degraded",
        "service": "source-baltigo",
        "version": application_version(),
        "started_at": started_at_iso(),
        "uptime_seconds": uptime_seconds(),
        "components": {
            "database": {
                "ok": bool(database.get("ok")),
                "status": str(database.get("status") or "unknown"),
                "duration_ms": database.get("duration_ms"),
            }
        },
    }
