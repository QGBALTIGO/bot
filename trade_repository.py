from __future__ import annotations

from typing import Any, Dict, Optional

from psycopg.rows import dict_row

from database import pool


TRADE_TTL_SECONDS = 600


class TradeRepositoryError(RuntimeError):
    pass


def create_trade_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS card_trades_v2 (
                        id BIGSERIAL PRIMARY KEY,
                        from_user_id BIGINT NOT NULL,
                        to_user_id BIGINT NOT NULL,
                        from_character_id BIGINT NOT NULL,
                        to_character_id BIGINT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        resolved_at TIMESTAMPTZ,
                        CHECK (from_user_id <> to_user_id),
                        CHECK (from_character_id <> to_character_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_card_trades_v2_pending_users
                    ON card_trades_v2 (status, from_user_id, to_user_id, expires_at)
                    """
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "from_user_id": int(row.get("from_user_id") or 0),
        "to_user_id": int(row.get("to_user_id") or 0),
        "from_character_id": int(row.get("from_character_id") or 0),
        "to_character_id": int(row.get("to_character_id") or 0),
        "status": str(row.get("status") or ""),
        "created_at": row.get("created_at"),
        "expires_at": row.get("expires_at"),
        "resolved_at": row.get("resolved_at"),
    }


def _lock_users(cur, a: int, b: int) -> None:
    first, second = sorted((int(a), int(b)))
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (first,))
    if second != first:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (second,))


def _quantity(cur, user_id: int, character_id: int) -> int:
    cur.execute(
        """
        SELECT quantity
        FROM user_card_collection
        WHERE user_id = %s AND character_id = %s
        """,
        (int(user_id), int(character_id)),
    )
    return int((cur.fetchone() or {}).get("quantity") or 0)


def create_trade(
    from_user_id: int,
    to_user_id: int,
    from_character_id: int,
    to_character_id: int,
    *,
    ttl_seconds: int = TRADE_TTL_SECONDS,
) -> Dict[str, Any]:
    from_user_id = int(from_user_id)
    to_user_id = int(to_user_id)
    from_character_id = int(from_character_id)
    to_character_id = int(to_character_id)
    if from_user_id == to_user_id:
        return {"ok": False, "error": "same_user"}
    if from_character_id == to_character_id:
        return {"ok": False, "error": "same_character"}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                _lock_users(cur, from_user_id, to_user_id)
                cur.execute(
                    """
                    UPDATE card_trades_v2
                    SET status='expired', resolved_at=NOW()
                    WHERE status='pending' AND expires_at <= NOW()
                      AND (from_user_id IN (%s, %s) OR to_user_id IN (%s, %s))
                    """,
                    (from_user_id, to_user_id, from_user_id, to_user_id),
                )
                cur.execute(
                    """
                    SELECT id
                    FROM card_trades_v2
                    WHERE status='pending' AND expires_at > NOW()
                      AND (from_user_id IN (%s, %s) OR to_user_id IN (%s, %s))
                    LIMIT 1
                    """,
                    (from_user_id, to_user_id, from_user_id, to_user_id),
                )
                if cur.fetchone():
                    conn.rollback()
                    return {"ok": False, "error": "user_busy"}

                if _quantity(cur, from_user_id, from_character_id) <= 0:
                    conn.rollback()
                    return {"ok": False, "error": "from_missing_card"}
                if _quantity(cur, to_user_id, to_character_id) <= 0:
                    conn.rollback()
                    return {"ok": False, "error": "to_missing_card"}

                cur.execute(
                    """
                    INSERT INTO card_trades_v2
                    (from_user_id, to_user_id, from_character_id, to_character_id, expires_at)
                    VALUES (%s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'))
                    RETURNING *
                    """,
                    (from_user_id, to_user_id, from_character_id, to_character_id, max(30, int(ttl_seconds))),
                )
                row = cur.fetchone()
                conn.commit()
                return {"ok": True, "trade": _payload(dict(row or {}))}
            except Exception:
                conn.rollback()
                raise


def get_trade(trade_id: int) -> Optional[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM card_trades_v2 WHERE id=%s", (int(trade_id),))
            row = cur.fetchone()
            return _payload(dict(row)) if row else None


def resolve_trade(trade_id: int, actor_user_id: int, action: str) -> Dict[str, Any]:
    trade_id = int(trade_id)
    actor_user_id = int(actor_user_id)
    action = str(action or "").strip().lower()
    if action not in {"accept", "reject", "cancel"}:
        return {"ok": False, "error": "invalid_action"}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM card_trades_v2 WHERE id=%s FOR UPDATE", (trade_id,))
                row = cur.fetchone()
                if not row:
                    return {"ok": False, "error": "not_found"}
                trade = dict(row)
                if str(trade.get("status") or "") != "pending":
                    return {"ok": False, "error": "not_pending", "trade": _payload(trade)}

                if trade.get("expires_at") and trade["expires_at"] <= __import__("datetime").datetime.now(trade["expires_at"].tzinfo):
                    cur.execute(
                        "UPDATE card_trades_v2 SET status='expired', resolved_at=NOW() WHERE id=%s RETURNING *",
                        (trade_id,),
                    )
                    expired = cur.fetchone()
                    conn.commit()
                    return {"ok": False, "error": "expired", "trade": _payload(dict(expired or trade))}

                from_user = int(trade["from_user_id"])
                to_user = int(trade["to_user_id"])
                if action in {"accept", "reject"} and actor_user_id != to_user:
                    return {"ok": False, "error": "not_target"}
                if action == "cancel" and actor_user_id != from_user:
                    return {"ok": False, "error": "not_owner"}

                if action in {"reject", "cancel"}:
                    new_status = "rejected" if action == "reject" else "cancelled"
                    cur.execute(
                        "UPDATE card_trades_v2 SET status=%s, resolved_at=NOW() WHERE id=%s RETURNING *",
                        (new_status, trade_id),
                    )
                    resolved = cur.fetchone()
                    conn.commit()
                    return {"ok": True, "trade": _payload(dict(resolved or trade))}

                _lock_users(cur, from_user, to_user)
                from_char = int(trade["from_character_id"])
                to_char = int(trade["to_character_id"])
                pairs = sorted(((from_user, from_char), (to_user, to_char)))
                cur.execute(
                    """
                    SELECT user_id, character_id, quantity
                    FROM user_card_collection
                    WHERE (user_id = %s AND character_id = %s)
                       OR (user_id = %s AND character_id = %s)
                    ORDER BY user_id, character_id
                    FOR UPDATE
                    """,
                    (pairs[0][0], pairs[0][1], pairs[1][0], pairs[1][1]),
                )
                owned = {
                    (int(r["user_id"]), int(r["character_id"])): int(r.get("quantity") or 0)
                    for r in (cur.fetchall() or [])
                }
                if owned.get((from_user, from_char), 0) <= 0 or owned.get((to_user, to_char), 0) <= 0:
                    cur.execute(
                        "UPDATE card_trades_v2 SET status='invalidated', resolved_at=NOW() WHERE id=%s RETURNING *",
                        (trade_id,),
                    )
                    invalid = cur.fetchone()
                    conn.commit()
                    return {"ok": False, "error": "card_unavailable", "trade": _payload(dict(invalid or trade))}

                for user_id, character_id in ((from_user, from_char), (to_user, to_char)):
                    cur.execute(
                        """
                        UPDATE user_card_collection
                        SET quantity=quantity-1, updated_at=NOW()
                        WHERE user_id=%s AND character_id=%s AND quantity>0
                        """,
                        (user_id, character_id),
                    )
                    cur.execute(
                        "DELETE FROM user_card_collection WHERE user_id=%s AND character_id=%s AND quantity<=0",
                        (user_id, character_id),
                    )

                for user_id, character_id in ((from_user, to_char), (to_user, from_char)):
                    cur.execute(
                        """
                        INSERT INTO user_card_collection
                        (user_id, character_id, quantity, first_obtained_at, updated_at)
                        VALUES (%s, %s, 1, NOW(), NOW())
                        ON CONFLICT (user_id, character_id)
                        DO UPDATE SET quantity=user_card_collection.quantity+1, updated_at=NOW()
                        """,
                        (user_id, character_id),
                    )

                cur.execute(
                    "UPDATE card_trades_v2 SET status='accepted', resolved_at=NOW() WHERE id=%s RETURNING *",
                    (trade_id,),
                )
                resolved = cur.fetchone()
                conn.commit()
                return {"ok": True, "trade": _payload(dict(resolved or trade))}
            except Exception:
                conn.rollback()
                raise
