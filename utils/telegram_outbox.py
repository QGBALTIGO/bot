from __future__ import annotations

import asyncio
import math
import threading
from datetime import timedelta
from typing import Any

from psycopg.rows import dict_row
from telegram.error import RetryAfter

from database import pool


_TABLES_READY = False
_TABLES_LOCK = threading.Lock()

_OUTBOX_SQL = """
CREATE TABLE IF NOT EXISTS telegram_outbox (
    id BIGSERIAL PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    chat_id BIGINT NOT NULL,
    kind TEXT NOT NULL,
    photo TEXT,
    caption TEXT NOT NULL DEFAULT '',
    parse_mode TEXT NOT NULL DEFAULT 'HTML',
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_telegram_outbox_pending
    ON telegram_outbox(status, available_at, id);
"""


def ensure_telegram_outbox_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return

    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_OUTBOX_SQL)
            conn.commit()
        _TABLES_READY = True


def enqueue_photo(
    *,
    dedupe_key: str,
    chat_id: int,
    photo: str,
    caption: str,
    parse_mode: str = "HTML",
) -> bool:
    ensure_telegram_outbox_tables()
    key = str(dedupe_key or "").strip()
    image = str(photo or "").strip()
    if not key or int(chat_id) <= 0 or not image:
        return False

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO telegram_outbox
                    (dedupe_key, chat_id, kind, photo, caption, parse_mode)
                VALUES (%s, %s, 'photo', %s, %s, %s)
                ON CONFLICT (dedupe_key) DO NOTHING
                RETURNING id
                """,
                (
                    key,
                    int(chat_id),
                    image,
                    str(caption or ""),
                    str(parse_mode or "HTML"),
                ),
            )
            inserted = cur.fetchone()
        conn.commit()
    return bool(inserted)


def _claim_pending(limit: int = 12) -> list[dict[str, Any]]:
    ensure_telegram_outbox_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("BEGIN")
            cur.execute(
                """
                SELECT id, dedupe_key, chat_id, kind, photo, caption, parse_mode, attempts
                FROM telegram_outbox
                WHERE (
                    (status = 'pending' AND available_at <= NOW())
                    OR (status = 'sending' AND updated_at < NOW() - INTERVAL '2 minutes')
                )
                ORDER BY id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (max(1, min(int(limit), 50)),),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
            if rows:
                ids = [int(row["id"]) for row in rows]
                cur.execute(
                    """
                    UPDATE telegram_outbox
                    SET status = 'sending',
                        attempts = attempts + 1,
                        updated_at = NOW()
                    WHERE id = ANY(%s)
                    """,
                    (ids,),
                )
            conn.commit()
    return rows


def _mark_sent(outbox_id: int) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE telegram_outbox
                SET status = 'sent',
                    sent_at = NOW(),
                    updated_at = NOW(),
                    last_error = NULL
                WHERE id = %s
                """,
                (int(outbox_id),),
            )
        conn.commit()


def _reschedule(outbox_id: int, error: str, delay_seconds: float, *, permanent: bool = False) -> None:
    safe_delay = max(1, min(int(math.ceil(float(delay_seconds))), 3600))
    with pool.connection() as conn:
        with conn.cursor() as cur:
            if permanent:
                cur.execute(
                    """
                    UPDATE telegram_outbox
                    SET status = 'failed',
                        last_error = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (str(error or "telegram_delivery_failed")[:1000], int(outbox_id)),
                )
            else:
                cur.execute(
                    """
                    UPDATE telegram_outbox
                    SET status = 'pending',
                        available_at = NOW() + (%s * INTERVAL '1 second'),
                        last_error = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        safe_delay,
                        str(error or "telegram_delivery_failed")[:1000],
                        int(outbox_id),
                    ),
                )
        conn.commit()


def _retry_after_seconds(exc: RetryAfter) -> float:
    value = getattr(exc, "retry_after", 1)
    if isinstance(value, timedelta):
        return max(1.0, value.total_seconds())
    try:
        return max(1.0, float(value))
    except Exception:
        return 1.0


async def telegram_outbox_worker(app) -> None:
    await asyncio.to_thread(ensure_telegram_outbox_tables)

    while True:
        try:
            rows = await asyncio.to_thread(_claim_pending, 12)
            if not rows:
                await asyncio.sleep(0.8)
                continue

            for row in rows:
                outbox_id = int(row["id"])
                attempts = int(row.get("attempts") or 0) + 1
                try:
                    if str(row.get("kind") or "") != "photo":
                        raise RuntimeError("unsupported_outbox_kind")

                    await app.bot.send_photo(
                        chat_id=int(row["chat_id"]),
                        photo=str(row.get("photo") or ""),
                        caption=str(row.get("caption") or ""),
                        parse_mode=str(row.get("parse_mode") or "HTML"),
                    )
                    await asyncio.to_thread(_mark_sent, outbox_id)
                except RetryAfter as exc:
                    await asyncio.to_thread(
                        _reschedule,
                        outbox_id,
                        str(exc),
                        _retry_after_seconds(exc) + 1,
                    )
                except Exception as exc:
                    permanent = attempts >= 6
                    delay = min(300, max(2, 2 ** min(attempts, 8)))
                    await asyncio.to_thread(
                        _reschedule,
                        outbox_id,
                        repr(exc),
                        delay,
                        permanent=permanent,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[telegram-outbox] worker-error {type(exc).__name__}", flush=True)
            await asyncio.sleep(2.0)
