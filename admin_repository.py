from __future__ import annotations

import json
from typing import Any

from psycopg.rows import dict_row

from database import pool


def create_admin_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_audit_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    actor_user_id BIGINT NOT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT,
                    target_id TEXT,
                    status TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_admin_audit_v2_actor_created
                ON admin_audit_v2 (actor_user_id, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_admin_audit_v2_action_created
                ON admin_audit_v2 (action, created_at DESC)
                """
            )
            conn.commit()


def record_admin_event(
    actor_user_id: int,
    action: str,
    *,
    status: str = "success",
    target_type: str = "",
    target_id: Any = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO admin_audit_v2
                    (actor_user_id, action, target_type, target_id, status, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        int(actor_user_id),
                        str(action or "unknown")[:120],
                        str(target_type or "")[:80] or None,
                        str(target_id or "")[:180] or None,
                        str(status or "unknown")[:40],
                        json.dumps(metadata or {}, ensure_ascii=False),
                    ),
                )
                conn.commit()
    except Exception:
        # Logging must never turn an already-authorized bot action into a crash.
        return


def list_admin_events(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(500, int(limit)))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, actor_user_id, action, target_type, target_id, status, metadata, created_at
                FROM admin_audit_v2
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in (cur.fetchall() or [])]
