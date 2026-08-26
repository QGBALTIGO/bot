from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from database import pool


class ContributionError(ValueError):
    pass


class ContributionNotFound(ContributionError):
    pass


def create_contribution_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS card_image_suggestions_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    character_id BIGINT NOT NULL,
                    character_name TEXT NOT NULL,
                    current_image_url TEXT,
                    suggested_image_url TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_by BIGINT,
                    review_note TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reviewed_at TIMESTAMPTZ
                )
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_card_image_suggestions_v2_pending
                ON card_image_suggestions_v2 (user_id, character_id, suggested_image_url)
                WHERE status = 'pending'
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS card_work_suggestions_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    media_type TEXT NOT NULL DEFAULT 'anime',
                    anilist_id BIGINT,
                    title TEXT NOT NULL,
                    cover_url TEXT,
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_by BIGINT,
                    review_note TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reviewed_at TIMESTAMPTZ
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_card_image_suggestions_v2_status
                ON card_image_suggestions_v2 (status, created_at ASC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_card_work_suggestions_v2_status
                ON card_work_suggestions_v2 (status, created_at ASC)
                """
            )
            conn.commit()


def create_image_suggestion(
    user_id: int,
    character_id: int,
    character_name: str,
    current_image_url: str,
    suggested_image_url: str,
    note: str = "",
) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO card_image_suggestions_v2
                    (user_id, character_id, character_name, current_image_url, suggested_image_url, note)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        int(user_id), int(character_id), str(character_name)[:180],
                        str(current_image_url or "")[:2000] or None,
                        str(suggested_image_url)[:2000], str(note or "")[:700],
                    ),
                )
                row = dict(cur.fetchone() or {})
                conn.commit()
                return row
            except Exception as exc:
                conn.rollback()
                if getattr(exc, "sqlstate", "") == "23505":
                    raise ContributionError("Essa mesma sugestão já está pendente.") from exc
                raise


def create_work_suggestion(
    user_id: int,
    media_type: str,
    title: str,
    *,
    anilist_id: int | None = None,
    cover_url: str = "",
    note: str = "",
) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO card_work_suggestions_v2
                (user_id, media_type, anilist_id, title, cover_url, note)
                VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    int(user_id), str(media_type)[:30], int(anilist_id) if anilist_id else None,
                    str(title)[:220], str(cover_url or "")[:2000] or None, str(note or "")[:700],
                ),
            )
            row = dict(cur.fetchone() or {})
            conn.commit()
            return row


def list_user_contributions(user_id: int, limit: int = 50) -> dict[str, list[dict[str, Any]]]:
    limit = max(1, min(100, int(limit)))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM card_image_suggestions_v2 WHERE user_id=%s ORDER BY id DESC LIMIT %s",
                (int(user_id), limit),
            )
            images = [dict(row) for row in (cur.fetchall() or [])]
            cur.execute(
                "SELECT * FROM card_work_suggestions_v2 WHERE user_id=%s ORDER BY id DESC LIMIT %s",
                (int(user_id), limit),
            )
            works = [dict(row) for row in (cur.fetchall() or [])]
            return {"images": images, "works": works}


def list_pending_contributions(limit: int = 100) -> dict[str, list[dict[str, Any]]]:
    limit = max(1, min(300, int(limit)))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM card_image_suggestions_v2 WHERE status='pending' ORDER BY id ASC LIMIT %s",
                (limit,),
            )
            images = [dict(row) for row in (cur.fetchall() or [])]
            cur.execute(
                "SELECT * FROM card_work_suggestions_v2 WHERE status='pending' ORDER BY id ASC LIMIT %s",
                (limit,),
            )
            works = [dict(row) for row in (cur.fetchall() or [])]
            return {"images": images, "works": works}


def get_pending_contribution(kind: str, suggestion_id: int, *, for_update: bool = False, cur=None):
    table = "card_image_suggestions_v2" if kind == "image" else "card_work_suggestions_v2"
    suffix = " FOR UPDATE" if for_update else ""
    sql = f"SELECT * FROM {table} WHERE id=%s AND status='pending'{suffix}"
    if cur is not None:
        cur.execute(sql, (int(suggestion_id),))
        row = cur.fetchone()
        return dict(row) if row else None
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as local_cur:
            local_cur.execute(sql, (int(suggestion_id),))
            row = local_cur.fetchone()
            return dict(row) if row else None


def mark_contribution_reviewed(
    kind: str,
    suggestion_id: int,
    reviewer_id: int,
    decision: str,
    review_note: str = "",
) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise ContributionError("Decisão inválida.")
    table = "card_image_suggestions_v2" if kind == "image" else "card_work_suggestions_v2"
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                UPDATE {table}
                SET status=%s, reviewed_by=%s, review_note=%s, reviewed_at=NOW()
                WHERE id=%s AND status='pending'
                RETURNING *
                """,
                (decision, int(reviewer_id), str(review_note or "")[:700] or None, int(suggestion_id)),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                raise ContributionNotFound("Sugestão não encontrada ou já revisada.")
            conn.commit()
            return dict(row)
