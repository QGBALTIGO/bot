from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg.rows import dict_row

from capture_rules import (
    ACTIVITY_THRESHOLD,
    ACTIVITY_WINDOW_SECONDS,
    ESCAPE_SECONDS,
    GROUP_SPAWN_COOLDOWN_SECONDS,
    MIN_UNIQUE_PARTICIPANTS,
    PURCHASE_PRICE,
    PURCHASE_WINDOW_SECONDS,
    USER_ACTIVITY_COOLDOWN_SECONDS,
    XP_REWARD,
)
from database import pool, xp_to_level
from wallet_tx import insert_ledger, lock_wallet, wallet_payload


class CaptureRepositoryError(RuntimeError):
    pass


class CapturePurchaseError(CaptureRepositoryError):
    pass


def create_capture_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS capture_group_state_v2 (
                        chat_id BIGINT PRIMARY KEY,
                        heat INTEGER NOT NULL DEFAULT 0 CHECK (heat >= 0),
                        total_valid_messages BIGINT NOT NULL DEFAULT 0,
                        last_spawn_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS capture_user_activity_v2 (
                        chat_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        last_valid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        valid_count BIGINT NOT NULL DEFAULT 1,
                        PRIMARY KEY (chat_id, user_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_capture_user_activity_v2_recent
                    ON capture_user_activity_v2 (chat_id, last_valid_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS capture_spawns_v2 (
                        id BIGSERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        character_id BIGINT NOT NULL,
                        character_name TEXT NOT NULL,
                        anime_name TEXT NOT NULL,
                        image_url TEXT,
                        status TEXT NOT NULL DEFAULT 'active',
                        winner_user_id BIGINT,
                        winner_name TEXT,
                        spawn_message_id BIGINT,
                        spawn_has_photo BOOLEAN NOT NULL DEFAULT FALSE,
                        spawned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        captured_at TIMESTAMPTZ,
                        purchase_token TEXT UNIQUE,
                        purchase_price INTEGER,
                        purchase_expires_at TIMESTAMPTZ,
                        purchased_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_capture_spawns_v2_active_chat
                    ON capture_spawns_v2 (chat_id)
                    WHERE status = 'active'
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_capture_spawns_v2_chat_created
                    ON capture_spawns_v2 (chat_id, spawned_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_capture_spawns_v2_status_expiry
                    ON capture_spawns_v2 (status, expires_at)
                    """
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _spawn_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "chat_id": int(row.get("chat_id") or 0),
        "character_id": int(row.get("character_id") or 0),
        "character_name": str(row.get("character_name") or ""),
        "anime_name": str(row.get("anime_name") or ""),
        "image_url": str(row.get("image_url") or ""),
        "status": str(row.get("status") or ""),
        "winner_user_id": int(row.get("winner_user_id") or 0) or None,
        "winner_name": str(row.get("winner_name") or ""),
        "spawn_message_id": int(row.get("spawn_message_id") or 0),
        "spawn_has_photo": bool(row.get("spawn_has_photo")),
        "spawned_at": row.get("spawned_at"),
        "expires_at": row.get("expires_at"),
        "captured_at": row.get("captured_at"),
        "purchase_token": str(row.get("purchase_token") or ""),
        "purchase_price": int(row.get("purchase_price") or 0),
        "purchase_expires_at": row.get("purchase_expires_at"),
        "purchased_at": row.get("purchased_at"),
    }


def register_valid_activity(chat_id: int, user_id: int) -> Dict[str, Any]:
    chat_id = int(chat_id)
    user_id = int(user_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO capture_group_state_v2 (chat_id)
                    VALUES (%s)
                    ON CONFLICT (chat_id) DO NOTHING
                    """,
                    (chat_id,),
                )
                cur.execute(
                    """
                    SELECT chat_id, heat, total_valid_messages, last_spawn_at
                    FROM capture_group_state_v2
                    WHERE chat_id = %s
                    FOR UPDATE
                    """,
                    (chat_id,),
                )
                state = dict(cur.fetchone() or {})

                cur.execute(
                    """
                    SELECT last_valid_at
                    FROM capture_user_activity_v2
                    WHERE chat_id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (chat_id, user_id),
                )
                activity = cur.fetchone()
                if activity:
                    cur.execute(
                        """
                        SELECT (%s::timestamptz <= NOW() - (%s * INTERVAL '1 second')) AS allowed
                        """,
                        (activity.get("last_valid_at"), USER_ACTIVITY_COOLDOWN_SECONDS),
                    )
                    if not bool((cur.fetchone() or {}).get("allowed")):
                        conn.commit()
                        return {
                            "counted": False,
                            "eligible": False,
                            "heat": int(state.get("heat") or 0),
                            "participants": 0,
                            "reason": "user_cooldown",
                        }

                cur.execute(
                    """
                    INSERT INTO capture_user_activity_v2
                    (chat_id, user_id, last_valid_at, valid_count)
                    VALUES (%s, %s, NOW(), 1)
                    ON CONFLICT (chat_id, user_id)
                    DO UPDATE SET
                        last_valid_at = NOW(),
                        valid_count = capture_user_activity_v2.valid_count + 1
                    """,
                    (chat_id, user_id),
                )

                heat = min(ACTIVITY_THRESHOLD * 2, int(state.get("heat") or 0) + 1)
                total = int(state.get("total_valid_messages") or 0) + 1
                cur.execute(
                    """
                    SELECT COUNT(*) AS participants
                    FROM capture_user_activity_v2
                    WHERE chat_id = %s
                      AND last_valid_at >= NOW() - (%s * INTERVAL '1 second')
                    """,
                    (chat_id, ACTIVITY_WINDOW_SECONDS),
                )
                participants = int((cur.fetchone() or {}).get("participants") or 0)

                last_spawn_at = state.get("last_spawn_at")
                cooldown_ok = True
                if last_spawn_at:
                    cur.execute(
                        """
                        SELECT (%s::timestamptz <= NOW() - (%s * INTERVAL '1 second')) AS allowed
                        """,
                        (last_spawn_at, GROUP_SPAWN_COOLDOWN_SECONDS),
                    )
                    cooldown_ok = bool((cur.fetchone() or {}).get("allowed"))

                eligible = bool(
                    heat >= ACTIVITY_THRESHOLD
                    and participants >= MIN_UNIQUE_PARTICIPANTS
                    and cooldown_ok
                )
                cur.execute(
                    """
                    UPDATE capture_group_state_v2
                    SET heat = %s,
                        total_valid_messages = %s,
                        updated_at = NOW()
                    WHERE chat_id = %s
                    """,
                    (heat, total, chat_id),
                )
                conn.commit()
                return {
                    "counted": True,
                    "eligible": eligible,
                    "heat": heat,
                    "participants": participants,
                    "threshold": ACTIVITY_THRESHOLD,
                }
            except Exception:
                conn.rollback()
                raise


def get_recent_character_ids(chat_id: int, limit: int) -> List[int]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT character_id
                FROM capture_spawns_v2
                WHERE chat_id = %s
                ORDER BY spawned_at DESC
                LIMIT %s
                """,
                (int(chat_id), max(1, int(limit))),
            )
            return [int(row.get("character_id") or 0) for row in (cur.fetchall() or []) if row.get("character_id")]


def create_spawn_if_eligible(chat_id: int, character: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    chat_id = int(chat_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO capture_group_state_v2 (chat_id)
                    VALUES (%s)
                    ON CONFLICT (chat_id) DO NOTHING
                    """,
                    (chat_id,),
                )
                cur.execute(
                    """
                    SELECT heat, last_spawn_at
                    FROM capture_group_state_v2
                    WHERE chat_id = %s
                    FOR UPDATE
                    """,
                    (chat_id,),
                )
                state = dict(cur.fetchone() or {})

                cur.execute(
                    """
                    SELECT id
                    FROM capture_spawns_v2
                    WHERE chat_id = %s AND status = 'active'
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (chat_id,),
                )
                if cur.fetchone():
                    conn.commit()
                    return None

                cur.execute(
                    """
                    SELECT COUNT(*) AS participants
                    FROM capture_user_activity_v2
                    WHERE chat_id = %s
                      AND last_valid_at >= NOW() - (%s * INTERVAL '1 second')
                    """,
                    (chat_id, ACTIVITY_WINDOW_SECONDS),
                )
                participants = int((cur.fetchone() or {}).get("participants") or 0)
                if int(state.get("heat") or 0) < ACTIVITY_THRESHOLD or participants < MIN_UNIQUE_PARTICIPANTS:
                    conn.commit()
                    return None

                if state.get("last_spawn_at"):
                    cur.execute(
                        """
                        SELECT (%s::timestamptz <= NOW() - (%s * INTERVAL '1 second')) AS allowed
                        """,
                        (state.get("last_spawn_at"), GROUP_SPAWN_COOLDOWN_SECONDS),
                    )
                    if not bool((cur.fetchone() or {}).get("allowed")):
                        conn.commit()
                        return None

                cur.execute(
                    """
                    INSERT INTO capture_spawns_v2
                    (chat_id, character_id, character_name, anime_name, image_url, expires_at)
                    VALUES (%s, %s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'))
                    RETURNING *
                    """,
                    (
                        chat_id,
                        int(character.get("id") or 0),
                        str(character.get("name") or "Personagem")[:180],
                        str(character.get("anime") or "Obra desconhecida")[:220],
                        str(character.get("image") or "")[:2000],
                        ESCAPE_SECONDS,
                    ),
                )
                row = cur.fetchone()
                cur.execute(
                    """
                    UPDATE capture_group_state_v2
                    SET heat = 0,
                        last_spawn_at = NOW(),
                        updated_at = NOW()
                    WHERE chat_id = %s
                    """,
                    (chat_id,),
                )
                conn.commit()
                return _spawn_payload(dict(row or {}))
            except Exception as exc:
                conn.rollback()
                # Partial unique index is the final cross-process guard against
                # two workers creating an active spawn at the same time.
                if getattr(exc, "sqlstate", "") == "23505":
                    return None
                raise


def attach_spawn_message(spawn_id: int, message_id: int, has_photo: bool) -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE capture_spawns_v2
                SET spawn_message_id = %s,
                    spawn_has_photo = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (int(message_id), bool(has_photo), int(spawn_id)),
            )
            conn.commit()


def get_active_spawn(chat_id: int) -> Optional[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM capture_spawns_v2
                WHERE chat_id = %s AND status = 'active'
                ORDER BY spawned_at DESC
                LIMIT 1
                """,
                (int(chat_id),),
            )
            row = cur.fetchone()
            return _spawn_payload(dict(row)) if row else None


def get_spawn(spawn_id: int) -> Optional[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM capture_spawns_v2 WHERE id = %s", (int(spawn_id),))
            row = cur.fetchone()
            return _spawn_payload(dict(row)) if row else None


def list_active_spawns() -> List[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM capture_spawns_v2 WHERE status = 'active' ORDER BY expires_at ASC")
            return [_spawn_payload(dict(row)) for row in (cur.fetchall() or [])]


def expire_spawn(spawn_id: int) -> Optional[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    UPDATE capture_spawns_v2
                    SET status = 'escaped', updated_at = NOW()
                    WHERE id = %s
                      AND status = 'active'
                      AND expires_at <= NOW()
                    RETURNING *
                    """,
                    (int(spawn_id),),
                )
                row = cur.fetchone()
                conn.commit()
                return _spawn_payload(dict(row)) if row else None
            except Exception:
                conn.rollback()
                raise


def claim_spawn(spawn_id: int, user_id: int, winner_name: str) -> Dict[str, Any]:
    spawn_id = int(spawn_id)
    user_id = int(user_id)
    purchase_token = secrets.token_urlsafe(18)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM capture_spawns_v2 WHERE id = %s FOR UPDATE", (spawn_id,))
                row = cur.fetchone()
                if not row:
                    return {"ok": False, "reason": "not_found"}
                if str(row.get("status") or "") != "active":
                    return {"ok": False, "reason": "not_active", "spawn": _spawn_payload(dict(row))}
                if row.get("expires_at") and row.get("expires_at") <= datetime.now(row.get("expires_at").tzinfo):
                    cur.execute(
                        "UPDATE capture_spawns_v2 SET status='escaped', updated_at=NOW() WHERE id=%s RETURNING *",
                        (spawn_id,),
                    )
                    expired = cur.fetchone()
                    conn.commit()
                    return {"ok": False, "reason": "expired", "spawn": _spawn_payload(dict(expired or row))}

                cur.execute(
                    """
                    UPDATE capture_spawns_v2
                    SET status = 'captured',
                        winner_user_id = %s,
                        winner_name = %s,
                        captured_at = NOW(),
                        purchase_token = %s,
                        purchase_price = %s,
                        purchase_expires_at = NOW() + (%s * INTERVAL '1 second'),
                        updated_at = NOW()
                    WHERE id = %s AND status = 'active'
                    RETURNING *
                    """,
                    (
                        user_id,
                        str(winner_name or "Jogador")[:128],
                        purchase_token,
                        PURCHASE_PRICE,
                        PURCHASE_WINDOW_SECONDS,
                        spawn_id,
                    ),
                )
                claimed = cur.fetchone()
                if not claimed:
                    conn.rollback()
                    return {"ok": False, "reason": "race_lost"}

                cur.execute(
                    """
                    INSERT INTO user_progress (user_id, xp, level, total_actions, updated_at)
                    VALUES (%s, 0, 1, 0, NOW())
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (user_id,),
                )
                cur.execute(
                    "SELECT xp, level, total_actions FROM user_progress WHERE user_id = %s FOR UPDATE",
                    (user_id,),
                )
                progress = dict(cur.fetchone() or {})
                old_level = int(progress.get("level") or 1)
                new_xp = int(progress.get("xp") or 0) + XP_REWARD
                new_level = xp_to_level(new_xp)
                new_actions = int(progress.get("total_actions") or 0) + 1
                cur.execute(
                    """
                    UPDATE user_progress
                    SET xp=%s, level=%s, total_actions=%s, updated_at=NOW()
                    WHERE user_id=%s
                    """,
                    (new_xp, new_level, new_actions, user_id),
                )
                conn.commit()
                return {
                    "ok": True,
                    "spawn": _spawn_payload(dict(claimed)),
                    "progress": {
                        "xp_reward": XP_REWARD,
                        "xp": new_xp,
                        "old_level": old_level,
                        "new_level": new_level,
                    },
                }
            except Exception:
                conn.rollback()
                raise


def purchase_captured_card(purchase_token: str, user_id: int) -> Dict[str, Any]:
    token = str(purchase_token or "").strip()
    user_id = int(user_id)
    if not token:
        raise CapturePurchaseError("invalid_token")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT * FROM capture_spawns_v2 WHERE purchase_token = %s FOR UPDATE",
                    (token,),
                )
                row = cur.fetchone()
                if not row:
                    raise CapturePurchaseError("offer_not_found")
                if int(row.get("winner_user_id") or 0) != user_id:
                    raise CapturePurchaseError("not_owner")
                if str(row.get("status") or "") == "purchased":
                    raise CapturePurchaseError("already_purchased")
                if str(row.get("status") or "") != "captured":
                    raise CapturePurchaseError("offer_unavailable")
                expires_at = row.get("purchase_expires_at")
                if not expires_at or expires_at <= datetime.now(expires_at.tzinfo):
                    raise CapturePurchaseError("offer_expired")

                wallet = lock_wallet(cur, user_id)
                price = int(row.get("purchase_price") or PURCHASE_PRICE)
                if int(wallet.get("coins") or 0) < price:
                    raise CapturePurchaseError("insufficient_coins")

                cur.execute(
                    """
                    UPDATE game_wallets
                    SET coins = coins - %s, updated_at = NOW()
                    WHERE user_id = %s AND coins >= %s
                    RETURNING user_id, coins, dice, spins, dice_slot
                    """,
                    (price, user_id, price),
                )
                wallet = dict(cur.fetchone() or {})
                if not wallet:
                    raise CapturePurchaseError("insufficient_coins")

                cur.execute(
                    """
                    INSERT INTO user_card_collection
                    (user_id, character_id, quantity, first_obtained_at, updated_at)
                    VALUES (%s, %s, 1, NOW(), NOW())
                    ON CONFLICT (user_id, character_id)
                    DO UPDATE SET quantity = user_card_collection.quantity + 1, updated_at = NOW()
                    RETURNING quantity
                    """,
                    (user_id, int(row.get("character_id") or 0)),
                )
                collection = cur.fetchone() or {}
                cur.execute(
                    """
                    UPDATE capture_spawns_v2
                    SET status='purchased', purchased_at=NOW(), updated_at=NOW()
                    WHERE id=%s AND status='captured'
                    RETURNING *
                    """,
                    (int(row.get("id") or 0),),
                )
                purchased = cur.fetchone()
                if not purchased:
                    raise CapturePurchaseError("purchase_race")

                insert_ledger(
                    cur,
                    user_id=user_id,
                    resource="coins",
                    delta=-price,
                    reason="capture_card_purchase",
                    reference=f"capture:{int(row.get('id') or 0)}",
                    metadata={"character_id": int(row.get("character_id") or 0)},
                )
                conn.commit()
                return {
                    "spawn": _spawn_payload(dict(purchased)),
                    "quantity": int(collection.get("quantity") or 1),
                    "wallet": wallet_payload(wallet),
                }
            except CapturePurchaseError:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise
