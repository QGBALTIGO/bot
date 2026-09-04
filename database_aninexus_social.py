from __future__ import annotations

from threading import Lock
from typing import Any, Dict, List

from psycopg.rows import dict_row

from database_core import pool


_TABLE_LOCK = Lock()
_TABLE_READY = False
REFERRAL_REQUIRED_LEVEL = 2
REFERRER_REWARD_COINS = 1
REFERRED_REWARD_DADOS = 1
TRADE_TTL_HOURS = 24


def _ensure_tables() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    with _TABLE_LOCK:
        if _TABLE_READY:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_referral_rewards (
                        referred_user_id BIGINT PRIMARY KEY,
                        referrer_user_id BIGINT NOT NULL,
                        reward_coins INTEGER NOT NULL DEFAULT 1,
                        reward_dados INTEGER NOT NULL DEFAULT 1,
                        rewarded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_aninexus_referral_rewards_referrer
                    ON aninexus_referral_rewards (referrer_user_id, rewarded_at DESC)
                    """
                )
                conn.commit()
        _TABLE_READY = True


def _expire_stale_trades_locked(cur) -> None:
    cur.execute(
        """
        UPDATE card_trades
        SET status = 'expired'
        WHERE status = 'pending'
          AND created_at < NOW() - (%s || ' hours')::interval
        """,
        (str(TRADE_TTL_HOURS),),
    )


def _display_name(row: Dict[str, Any], user_id: int) -> str:
    nickname = str(row.get("nickname") or "").strip()
    if nickname:
        return nickname
    full_name = str(row.get("full_name") or "").strip()
    if full_name:
        return full_name
    username = str(row.get("username") or "").strip().lstrip("@")
    if username:
        return f"@{username}"
    return f"Usuário {int(user_id)}"


def list_referrals(referrer_user_id: int) -> List[Dict[str, Any]]:
    _ensure_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    r.referred_user_id,
                    u.username,
                    u.full_name,
                    ups.nickname,
                    COALESCE(up.level, 1) AS level,
                    (arr.referred_user_id IS NOT NULL) AS rewarded,
                    r.created_at
                FROM user_referrals r
                LEFT JOIN users u ON u.user_id = r.referred_user_id
                LEFT JOIN user_profile_settings ups ON ups.user_id = r.referred_user_id
                LEFT JOIN user_progress up ON up.user_id = r.referred_user_id
                LEFT JOIN aninexus_referral_rewards arr
                       ON arr.referred_user_id = r.referred_user_id
                WHERE r.referrer_user_id = %s
                ORDER BY r.created_at DESC, r.referred_user_id ASC
                """,
                (int(referrer_user_id),),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
            conn.commit()

    return [
        {
            "referred_id": int(row.get("referred_user_id") or 0),
            "referred_name": _display_name(row, int(row.get("referred_user_id") or 0)),
            "level": max(1, int(row.get("level") or 1)),
            "rewarded": bool(row.get("rewarded")),
        }
        for row in rows
        if int(row.get("referred_user_id") or 0) > 0
    ]


def get_referral_stats(referrer_user_id: int) -> Dict[str, Any]:
    _ensure_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS invited_count,
                    COUNT(*) FILTER (WHERE COALESCE(up.level, 1) >= %s) AS qualified_count,
                    COUNT(*) FILTER (
                        WHERE COALESCE(up.level, 1) >= %s
                          AND arr.referred_user_id IS NULL
                    ) AS claimable_count
                FROM user_referrals r
                LEFT JOIN user_progress up ON up.user_id = r.referred_user_id
                LEFT JOIN aninexus_referral_rewards arr
                       ON arr.referred_user_id = r.referred_user_id
                WHERE r.referrer_user_id = %s
                """,
                (REFERRAL_REQUIRED_LEVEL, REFERRAL_REQUIRED_LEVEL, int(referrer_user_id)),
            )
            counts = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM aninexus_referral_rewards
                WHERE referrer_user_id = %s
                """,
                (int(referrer_user_id),),
            )
            rewarded = int((cur.fetchone() or {}).get("total") or 0)
            conn.commit()

    return {
        "invited_count": int(counts.get("invited_count") or 0),
        "qualified_count": int(counts.get("qualified_count") or 0),
        "claimable_count": int(counts.get("claimable_count") or 0),
        "rewarded_count": rewarded,
        "earned_coins": rewarded * REFERRER_REWARD_COINS,
        "required_level": REFERRAL_REQUIRED_LEVEL,
        "referrer_reward_coins": REFERRER_REWARD_COINS,
        "referred_reward_dados": REFERRED_REWARD_DADOS,
    }


def claim_referral_rewards(referrer_user_id: int) -> Dict[str, Any]:
    _ensure_tables()
    referrer_user_id = int(referrer_user_id)
    awarded = 0

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT r.referred_user_id
                    FROM user_referrals r
                    LEFT JOIN user_progress up ON up.user_id = r.referred_user_id
                    LEFT JOIN aninexus_referral_rewards arr
                           ON arr.referred_user_id = r.referred_user_id
                    WHERE r.referrer_user_id = %s
                      AND COALESCE(up.level, 1) >= %s
                      AND arr.referred_user_id IS NULL
                    ORDER BY r.created_at ASC, r.referred_user_id ASC
                    """,
                    (referrer_user_id, REFERRAL_REQUIRED_LEVEL),
                )
                candidates = [int(row.get("referred_user_id") or 0) for row in (cur.fetchall() or [])]

                for referred_user_id in candidates:
                    if referred_user_id <= 0:
                        continue
                    cur.execute(
                        """
                        INSERT INTO aninexus_referral_rewards
                            (referred_user_id, referrer_user_id, reward_coins, reward_dados)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (referred_user_id) DO NOTHING
                        RETURNING referred_user_id
                        """,
                        (
                            referred_user_id,
                            referrer_user_id,
                            REFERRER_REWARD_COINS,
                            REFERRED_REWARD_DADOS,
                        ),
                    )
                    if not cur.fetchone():
                        continue

                    cur.execute(
                        """
                        UPDATE users
                        SET coins = COALESCE(coins, 0) + %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        RETURNING coins
                        """,
                        (REFERRER_REWARD_COINS, referrer_user_id),
                    )
                    balance_row = cur.fetchone() or {}
                    balance_after = int(balance_row.get("coins") or 0)

                    cur.execute(
                        """
                        UPDATE users
                        SET dado_balance = LEAST(24, COALESCE(dado_balance, 0) + %s),
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (REFERRED_REWARD_DADOS, referred_user_id),
                    )

                    cur.execute(
                        """
                        INSERT INTO shop_transactions
                            (user_id, type, amount, balance_after, reference_id, metadata)
                        VALUES (
                            %s,
                            'aninexus_referral_reward',
                            %s,
                            %s,
                            %s,
                            jsonb_build_object('referred_user_id', %s)
                        )
                        """,
                        (
                            referrer_user_id,
                            REFERRER_REWARD_COINS,
                            balance_after,
                            referred_user_id,
                            referred_user_id,
                        ),
                    )
                    awarded += 1

                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return {
        "ok": True,
        "claimed": awarded,
        "coins": awarded * REFERRER_REWARD_COINS,
        "dados_distributed": awarded * REFERRED_REWARD_DADOS,
    }


def is_profile_private(user_id: int) -> bool:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT private_profile
                FROM user_profile_settings
                WHERE user_id = %s
                """,
                (int(user_id),),
            )
            row = cur.fetchone() or {}
            conn.commit()
            return bool(row.get("private_profile"))


def get_trade_collection(user_id: int) -> List[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT character_id, quantity
                FROM user_card_collection
                WHERE user_id = %s AND quantity > 0
                ORDER BY updated_at DESC, character_id ASC
                """,
                (int(user_id),),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
            conn.commit()
            return rows


def _lock_collection_row(cur, user_id: int, character_id: int) -> int:
    cur.execute(
        """
        SELECT quantity
        FROM user_card_collection
        WHERE user_id = %s AND character_id = %s
        FOR UPDATE
        """,
        (int(user_id), int(character_id)),
    )
    return int((cur.fetchone() or {}).get("quantity") or 0)


def _card_is_reserved_locked(cur, user_id: int, character_id: int) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM card_trades
        WHERE status = 'pending'
          AND (
              (from_user = %s AND from_character_id = %s)
              OR (to_user = %s AND to_character_id = %s)
          )
        LIMIT 1
        """,
        (int(user_id), int(character_id), int(user_id), int(character_id)),
    )
    return bool(cur.fetchone())


def create_trade_offer(
    sender_id: int,
    receiver_id: int,
    sender_character_id: int,
    receiver_character_id: int,
) -> Dict[str, Any]:
    sender_id = int(sender_id)
    receiver_id = int(receiver_id)
    sender_character_id = int(sender_character_id)
    receiver_character_id = int(receiver_character_id)

    if sender_id <= 0 or receiver_id <= 0 or sender_id == receiver_id:
        return {"ok": False, "error": "invalid_user"}
    if sender_character_id <= 0 or receiver_character_id <= 0:
        return {"ok": False, "error": "invalid_character"}
    if sender_character_id == receiver_character_id:
        return {"ok": False, "error": "same_character"}
    if is_profile_private(receiver_id):
        return {"ok": False, "error": "private_profile"}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                _expire_stale_trades_locked(cur)
                cur.execute("SELECT user_id FROM users WHERE user_id = %s", (receiver_id,))
                if not cur.fetchone():
                    conn.rollback()
                    return {"ok": False, "error": "receiver_not_found"}

                pairs = sorted(
                    [(sender_id, sender_character_id), (receiver_id, receiver_character_id)],
                    key=lambda item: (item[0], item[1]),
                )
                quantities: Dict[tuple[int, int], int] = {}
                for uid, cid in pairs:
                    quantities[(uid, cid)] = _lock_collection_row(cur, uid, cid)

                if quantities[(sender_id, sender_character_id)] <= 0:
                    conn.rollback()
                    return {"ok": False, "error": "sender_card_missing"}
                if quantities[(receiver_id, receiver_character_id)] <= 0:
                    conn.rollback()
                    return {"ok": False, "error": "receiver_card_missing"}
                if _card_is_reserved_locked(cur, sender_id, sender_character_id):
                    conn.rollback()
                    return {"ok": False, "error": "sender_card_reserved"}
                if _card_is_reserved_locked(cur, receiver_id, receiver_character_id):
                    conn.rollback()
                    return {"ok": False, "error": "receiver_card_reserved"}

                cur.execute(
                    """
                    INSERT INTO card_trades
                        (from_user, to_user, from_character_id, to_character_id, status, created_at)
                    VALUES (%s, %s, %s, %s, 'pending', NOW())
                    RETURNING trade_id
                    """,
                    (sender_id, receiver_id, sender_character_id, receiver_character_id),
                )
                trade_id = int((cur.fetchone() or {}).get("trade_id") or 0)
                conn.commit()
                return {"ok": True, "trade_id": trade_id}
            except Exception:
                conn.rollback()
                raise


def list_trade_offers(user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _expire_stale_trades_locked(cur)
            cur.execute(
                """
                SELECT *
                FROM card_trades
                WHERE from_user = %s OR to_user = %s
                ORDER BY trade_id DESC
                LIMIT %s
                """,
                (int(user_id), int(user_id), max(1, min(int(limit), 100))),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
            conn.commit()
            return rows


def _remove_one_locked(cur, user_id: int, character_id: int, quantity: int) -> None:
    if quantity <= 1:
        cur.execute(
            "DELETE FROM user_card_collection WHERE user_id = %s AND character_id = %s",
            (int(user_id), int(character_id)),
        )
    else:
        cur.execute(
            """
            UPDATE user_card_collection
            SET quantity = quantity - 1, updated_at = NOW()
            WHERE user_id = %s AND character_id = %s
            """,
            (int(user_id), int(character_id)),
        )


def _add_one_locked(cur, user_id: int, character_id: int) -> None:
    cur.execute(
        """
        INSERT INTO user_card_collection
            (user_id, character_id, quantity, first_obtained_at, updated_at)
        VALUES (%s, %s, 1, NOW(), NOW())
        ON CONFLICT (user_id, character_id)
        DO UPDATE SET
            quantity = user_card_collection.quantity + 1,
            updated_at = NOW()
        """,
        (int(user_id), int(character_id)),
    )


def respond_trade_offer(user_id: int, trade_id: int, action: str) -> Dict[str, Any]:
    user_id = int(user_id)
    trade_id = int(trade_id)
    action = str(action or "").strip().lower()
    if action not in {"accept", "reject"}:
        return {"ok": False, "error": "invalid_action"}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM card_trades WHERE trade_id = %s FOR UPDATE", (trade_id,))
                trade = dict(cur.fetchone() or {})
                if not trade:
                    conn.rollback()
                    return {"ok": False, "error": "trade_not_found"}
                if int(trade.get("to_user") or 0) != user_id:
                    conn.rollback()
                    return {"ok": False, "error": "forbidden"}
                if str(trade.get("status") or "") != "pending":
                    conn.rollback()
                    return {"ok": False, "error": "trade_not_pending"}

                created_at = trade.get("created_at")
                cur.execute(
                    "SELECT (%s::timestamptz < NOW() - (%s || ' hours')::interval) AS expired",
                    (created_at, str(TRADE_TTL_HOURS)),
                )
                if bool((cur.fetchone() or {}).get("expired")):
                    cur.execute("UPDATE card_trades SET status = 'expired' WHERE trade_id = %s", (trade_id,))
                    conn.commit()
                    return {"ok": False, "error": "trade_expired"}

                if action == "reject":
                    cur.execute("UPDATE card_trades SET status = 'rejected' WHERE trade_id = %s", (trade_id,))
                    conn.commit()
                    return {"ok": True, "status": "rejected"}

                sender_id = int(trade.get("from_user") or 0)
                receiver_id = int(trade.get("to_user") or 0)
                sender_char = int(trade.get("from_character_id") or 0)
                receiver_char = int(trade.get("to_character_id") or 0)

                pairs = sorted(
                    [(sender_id, sender_char), (receiver_id, receiver_char)],
                    key=lambda item: (item[0], item[1]),
                )
                quantities: Dict[tuple[int, int], int] = {}
                for uid, cid in pairs:
                    quantities[(uid, cid)] = _lock_collection_row(cur, uid, cid)

                sender_qty = quantities[(sender_id, sender_char)]
                receiver_qty = quantities[(receiver_id, receiver_char)]
                if sender_qty <= 0 or receiver_qty <= 0:
                    cur.execute("UPDATE card_trades SET status = 'failed' WHERE trade_id = %s", (trade_id,))
                    conn.commit()
                    return {"ok": False, "error": "card_missing"}

                _remove_one_locked(cur, sender_id, sender_char, sender_qty)
                _remove_one_locked(cur, receiver_id, receiver_char, receiver_qty)
                _add_one_locked(cur, sender_id, receiver_char)
                _add_one_locked(cur, receiver_id, sender_char)
                cur.execute("UPDATE card_trades SET status = 'completed' WHERE trade_id = %s", (trade_id,))
                conn.commit()
                return {"ok": True, "status": "completed"}
            except Exception:
                conn.rollback()
                raise


def get_economy_summary(user_id: int, limit: int = 50) -> Dict[str, Any]:
    user_id = int(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(u.coins, 0) AS coins,
                    COALESCE(u.dado_balance, 0) AS dados,
                    COALESCE(up.level, 1) AS level,
                    COALESCE(up.xp, 0) AS xp
                FROM users u
                LEFT JOIN user_progress up ON up.user_id = u.user_id
                WHERE u.user_id = %s
                """,
                (user_id,),
            )
            account = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS received,
                    COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS spent
                FROM shop_transactions
                WHERE user_id = %s
                """,
                (user_id,),
            )
            totals = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT id, type, amount, balance_after, reference_id, metadata, created_at
                FROM shop_transactions
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (user_id, max(1, min(int(limit), 100))),
            )
            history = [dict(row) for row in (cur.fetchall() or [])]
            conn.commit()

    for row in history:
        created_at = row.get("created_at")
        row["created_at"] = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or "")
        metadata = row.get("metadata")
        row["metadata"] = metadata if isinstance(metadata, dict) else {}

    return {
        "coins": int(account.get("coins") or 0),
        "dados": int(account.get("dados") or 0),
        "level": max(1, int(account.get("level") or 1)),
        "xp": int(account.get("xp") or 0),
        "received": int(totals.get("received") or 0),
        "spent": int(totals.get("spent") or 0),
        "transactions": history,
    }
