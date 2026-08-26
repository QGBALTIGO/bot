from __future__ import annotations

from typing import Any, Dict

from psycopg.rows import dict_row

from database import pool, xp_to_level


def add_progress_xp_atomic(user_id: int, amount: int = 3) -> Dict[str, Any]:
    """Add XP with a database row lock so multiple bot processes cannot lose updates."""
    user_id = int(user_id)
    amount = max(0, int(amount))

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO user_progress (user_id, xp, level, total_actions, updated_at)
                    VALUES (%s, 0, 1, 0, NOW())
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (user_id,),
                )
                cur.execute(
                    """
                    SELECT user_id, xp, level, total_actions
                    FROM user_progress
                    WHERE user_id = %s
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                row = cur.fetchone() or {}
                old_xp = int(row.get("xp") or 0)
                old_level = int(row.get("level") or 1)
                old_actions = int(row.get("total_actions") or 0)

                new_xp = old_xp + amount
                new_level = xp_to_level(new_xp)
                new_actions = old_actions + 1

                cur.execute(
                    """
                    UPDATE user_progress
                    SET xp = %s,
                        level = %s,
                        total_actions = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    RETURNING user_id, xp, level, total_actions, updated_at
                    """,
                    (new_xp, new_level, new_actions, user_id),
                )
                updated = dict(cur.fetchone() or {})
                conn.commit()
                return {
                    "old_xp": old_xp,
                    "old_level": old_level,
                    "new_level": int(updated.get("level") or new_level),
                    "xp": int(updated.get("xp") or new_xp),
                    "total_actions": int(updated.get("total_actions") or new_actions),
                }
            except Exception:
                conn.rollback()
                raise


def decrement_card_copy_atomic(user_id: int, character_id: int, amount: int = 1) -> Dict[str, Any]:
    """Safely remove copies without a read-then-write race.

    Returns removed=False when the user does not own enough copies.
    """
    user_id = int(user_id)
    character_id = int(character_id)
    amount = max(1, int(amount))

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    UPDATE user_card_collection
                    SET quantity = quantity - %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                      AND character_id = %s
                      AND quantity >= %s
                    RETURNING quantity
                    """,
                    (amount, user_id, character_id, amount),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return {"removed": False, "quantity": 0}

                quantity = int(row.get("quantity") or 0)
                if quantity <= 0:
                    cur.execute(
                        """
                        DELETE FROM user_card_collection
                        WHERE user_id = %s
                          AND character_id = %s
                          AND quantity <= 0
                        """,
                        (user_id, character_id),
                    )
                    quantity = 0

                conn.commit()
                return {"removed": True, "quantity": quantity}
            except Exception:
                conn.rollback()
                raise
