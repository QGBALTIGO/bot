from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from psycopg.rows import dict_row

from database import create_or_get_user, pool
from game_rules import (
    DICE_INITIAL_BALANCE,
    DICE_MAX_BALANCE,
    DICE_ROLL_TTL_MINUTES,
    DailyReward,
    SpinReward,
    daily_reward_for_streak,
    dice_slot_number,
    next_dice_recharge,
    next_streak,
    now_sp,
    recharged_dice_balance,
    today_sp,
)


class GameRepositoryError(RuntimeError):
    pass


class NoDiceError(GameRepositoryError):
    pass


class NoSpinsError(GameRepositoryError):
    pass


class ActiveDiceRollError(GameRepositoryError):
    def __init__(self, roll: Dict[str, Any]):
        super().__init__("active_dice_roll")
        self.roll = roll


class InvalidDicePickError(GameRepositoryError):
    pass


class DiceRollExpiredError(GameRepositoryError):
    pass


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name = %s
        ) AS exists
        """,
        (str(table), str(column)),
    )
    row = cur.fetchone() or {}
    return bool(row.get("exists"))


def create_game_tables() -> None:
    current_slot = dice_slot_number()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS game_wallets (
                        user_id BIGINT PRIMARY KEY,
                        coins BIGINT NOT NULL DEFAULT 0 CHECK (coins >= 0),
                        dice INTEGER NOT NULL DEFAULT 4 CHECK (dice >= 0),
                        spins INTEGER NOT NULL DEFAULT 0 CHECK (spins >= 0),
                        dice_slot BIGINT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS game_daily_claims (
                        user_id BIGINT NOT NULL,
                        claim_date DATE NOT NULL,
                        streak INTEGER NOT NULL DEFAULT 1,
                        cycle_day INTEGER NOT NULL DEFAULT 1,
                        coins INTEGER NOT NULL DEFAULT 0,
                        dice INTEGER NOT NULL DEFAULT 0,
                        spins INTEGER NOT NULL DEFAULT 0,
                        claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, claim_date)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_game_daily_claims_user_date
                    ON game_daily_claims (user_id, claim_date DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS game_dice_rolls (
                        roll_token TEXT PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        dice_value INTEGER NOT NULL CHECK (dice_value BETWEEN 1 AND 6),
                        options JSONB NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        selected_anime_id BIGINT,
                        character_id BIGINT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        resolved_at TIMESTAMPTZ
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_game_dice_rolls_user_status
                    ON game_dice_rolls (user_id, status, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS game_spin_history (
                        id BIGSERIAL PRIMARY KEY,
                        spin_token TEXT NOT NULL UNIQUE,
                        user_id BIGINT NOT NULL,
                        segment_index INTEGER NOT NULL,
                        reward_code TEXT NOT NULL,
                        reward_resource TEXT NOT NULL,
                        reward_amount INTEGER NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_game_spin_history_user_created
                    ON game_spin_history (user_id, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS game_ledger (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        resource TEXT NOT NULL,
                        delta BIGINT NOT NULL,
                        reason TEXT NOT NULL,
                        reference TEXT,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_game_ledger_user_created
                    ON game_ledger (user_id, created_at DESC)
                    """
                )

                # Import legacy balances only for users that do not already have
                # a V2 wallet. Legacy systems could contain invalid/negative balances,
                # so values are sanitized to the V2 domain before insertion.
                users_exists = False
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = current_schema()
                          AND table_name = 'users'
                    ) AS exists
                    """
                )
                users_exists = bool((cur.fetchone() or {}).get("exists"))

                if users_exists:
                    has_coins = _column_exists(cur, "users", "coins")
                    has_dice = _column_exists(cur, "users", "dado_balance")
                    has_slot = _column_exists(cur, "users", "dado_slot")

                    coins_sql = "GREATEST(0, COALESCE(coins, 0))" if has_coins else "0"
                    dice_sql = (
                        f"LEAST({DICE_MAX_BALANCE}, GREATEST(0, COALESCE(dado_balance, {DICE_INITIAL_BALANCE})))"
                        if has_dice
                        else str(DICE_INITIAL_BALANCE)
                    )
                    slot_sql = "COALESCE(dado_slot, %s)" if has_slot else "%s"

                    cur.execute(
                        f"""
                        INSERT INTO game_wallets (user_id, coins, dice, spins, dice_slot)
                        SELECT user_id, {coins_sql}, {dice_sql}, 0, {slot_sql}
                        FROM users
                        ON CONFLICT (user_id) DO NOTHING
                        """,
                        (current_slot,),
                    )

                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _wallet_row_locked(cur, user_id: int) -> Dict[str, Any]:
    current_slot = dice_slot_number()
    cur.execute(
        """
        INSERT INTO game_wallets (user_id, coins, dice, spins, dice_slot)
        VALUES (%s, 0, %s, 0, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id), DICE_INITIAL_BALANCE, current_slot),
    )
    cur.execute(
        """
        SELECT user_id, coins, dice, spins, dice_slot, created_at, updated_at
        FROM game_wallets
        WHERE user_id = %s
        FOR UPDATE
        """,
        (int(user_id),),
    )
    row = cur.fetchone()
    if not row:
        raise GameRepositoryError("wallet_missing")

    balance, new_slot = recharged_dice_balance(
        int(row.get("dice") or 0),
        int(row.get("dice_slot")) if row.get("dice_slot") is not None else None,
        current_slot,
    )
    if balance != int(row.get("dice") or 0) or new_slot != int(row.get("dice_slot") or 0):
        cur.execute(
            """
            UPDATE game_wallets
            SET dice = %s,
                dice_slot = %s,
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING user_id, coins, dice, spins, dice_slot, created_at, updated_at
            """,
            (balance, new_slot, int(user_id)),
        )
        row = cur.fetchone() or row

    return dict(row)


def _wallet_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    next_dt = next_dice_recharge()
    return {
        "user_id": int(row.get("user_id") or 0),
        "coins": int(row.get("coins") or 0),
        "dice": int(row.get("dice") or 0),
        "spins": int(row.get("spins") or 0),
        "dice_max": DICE_MAX_BALANCE,
        "next_dice_recharge_iso": next_dt.isoformat(),
        "next_dice_recharge_hhmm": next_dt.strftime("%H:%M"),
    }


def get_wallet(user_id: int) -> Dict[str, Any]:
    create_or_get_user(int(user_id))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                row = _wallet_row_locked(cur, int(user_id))
                conn.commit()
                return _wallet_payload(row)
            except Exception:
                conn.rollback()
                raise


def game_state(user_id: int) -> Dict[str, Any]:
    wallet = get_wallet(int(user_id))
    claim = get_last_daily_claim(int(user_id))
    today = today_sp()
    return {
        "wallet": wallet,
        "daily": {
            "claimed_today": bool(claim and claim.get("claim_date") == today),
            "streak": int(claim.get("streak") or 0) if claim else 0,
            "cycle_day": int(claim.get("cycle_day") or 0) if claim else 0,
            "next_reward": daily_reward_for_streak(next_streak(claim.get("claim_date") if claim else None, int(claim.get("streak") or 0) if claim else 0, today)).as_dict(),
        },
    }


def get_last_daily_claim(user_id: int) -> Optional[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT user_id, claim_date, streak, cycle_day, coins, dice, spins, claimed_at
                FROM game_daily_claims
                WHERE user_id = %s
                ORDER BY claim_date DESC
                LIMIT 1
                """,
                (int(user_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def claim_daily(user_id: int) -> Dict[str, Any]:
    user_id = int(user_id)
    create_or_get_user(user_id)
    current_date = today_sp()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
                row = _wallet_row_locked(cur, user_id)

                cur.execute(
                    """
                    SELECT user_id, claim_date, streak, cycle_day, coins, dice, spins, claimed_at
                    FROM game_daily_claims
                    WHERE user_id = %s
                    ORDER BY claim_date DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                last = cur.fetchone()
                last_dict = dict(last) if last else None

                if last_dict and last_dict.get("claim_date") == current_date:
                    conn.commit()
                    return {
                        "already_claimed": True,
                        "reward": {
                            "coins": int(last_dict.get("coins") or 0),
                            "dice": int(last_dict.get("dice") or 0),
                            "spins": int(last_dict.get("spins") or 0),
                        },
                        "streak": int(last_dict.get("streak") or 0),
                        "cycle_day": int(last_dict.get("cycle_day") or 0),
                        "wallet": _wallet_payload(row),
                    }

                streak = next_streak(
                    last_dict.get("claim_date") if last_dict else None,
                    int(last_dict.get("streak") or 0) if last_dict else 0,
                    current_date,
                )
                reward: DailyReward = daily_reward_for_streak(streak)

                cur.execute(
                    """
                    UPDATE game_wallets
                    SET coins = coins + %s,
                        dice = LEAST(%s, dice + %s),
                        spins = spins + %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    RETURNING user_id, coins, dice, spins, dice_slot, created_at, updated_at
                    """,
                    (
                        reward.coins,
                        DICE_MAX_BALANCE,
                        reward.dice,
                        reward.spins,
                        user_id,
                    ),
                )
                row = cur.fetchone() or row

                cur.execute(
                    """
                    INSERT INTO game_daily_claims
                        (user_id, claim_date, streak, cycle_day, coins, dice, spins)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        current_date,
                        streak,
                        reward.cycle_day,
                        reward.coins,
                        reward.dice,
                        reward.spins,
                    ),
                )
                for resource, delta in (
                    ("coins", reward.coins),
                    ("dice", reward.dice),
                    ("spins", reward.spins),
                ):
                    if delta:
                        cur.execute(
                            """
                            INSERT INTO game_ledger
                                (user_id, resource, delta, reason, reference, metadata)
                            VALUES (%s, %s, %s, 'daily', %s, %s::jsonb)
                            """,
                            (
                                user_id,
                                resource,
                                delta,
                                current_date.isoformat(),
                                json.dumps(
                                    {"streak": streak, "cycle_day": reward.cycle_day},
                                    ensure_ascii=False,
                                ),
                            ),
                        )

                conn.commit()
                return {
                    "already_claimed": False,
                    "reward": reward.as_dict(),
                    "streak": streak,
                    "cycle_day": reward.cycle_day,
                    "wallet": _wallet_payload(row),
                }
            except Exception:
                conn.rollback()
                raise


def get_active_dice_roll(user_id: int) -> Optional[Dict[str, Any]]:
    now = datetime.now().astimezone()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT roll_token, user_id, dice_value, options, status,
                       selected_anime_id, character_id, created_at, expires_at, resolved_at
                FROM game_dice_rolls
                WHERE user_id = %s
                  AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (int(user_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row)
            expires_at = data.get("expires_at")
            if expires_at and expires_at <= now:
                with conn.cursor() as update_cur:
                    update_cur.execute(
                        """
                        UPDATE game_dice_rolls
                        SET status = 'expired', resolved_at = NOW()
                        WHERE roll_token = %s AND status = 'pending'
                        """,
                        (str(data.get("roll_token") or ""),),
                    )
                conn.commit()
                return None
            return data


def create_dice_roll(user_id: int, dice_value: int, options: list[Dict[str, Any]]) -> Dict[str, Any]:
    user_id = int(user_id)
    create_or_get_user(user_id)
    token = secrets.token_urlsafe(24)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
                wallet = _wallet_row_locked(cur, user_id)

                cur.execute(
                    """
                    SELECT roll_token, user_id, dice_value, options, status, created_at, expires_at
                    FROM game_dice_rolls
                    WHERE user_id = %s
                      AND status = 'pending'
                      AND expires_at > NOW()
                    ORDER BY created_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                active = cur.fetchone()
                if active:
                    raise ActiveDiceRollError(dict(active))

                if int(wallet.get("dice") or 0) <= 0:
                    raise NoDiceError("no_dice")

                expires_at = datetime.now().astimezone() + timedelta(minutes=DICE_ROLL_TTL_MINUTES)
                cur.execute(
                    """
                    UPDATE game_wallets
                    SET dice = dice - 1,
                        updated_at = NOW()
                    WHERE user_id = %s AND dice > 0
                    RETURNING user_id, coins, dice, spins, dice_slot, created_at, updated_at
                    """,
                    (user_id,),
                )
                wallet = cur.fetchone()
                if not wallet:
                    raise NoDiceError("no_dice")

                cur.execute(
                    """
                    INSERT INTO game_dice_rolls
                        (roll_token, user_id, dice_value, options, expires_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        token,
                        user_id,
                        int(dice_value),
                        json.dumps(options, ensure_ascii=False),
                        expires_at,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO game_ledger
                        (user_id, resource, delta, reason, reference, metadata)
                    VALUES (%s, 'dice', -1, 'dice_roll', %s, %s::jsonb)
                    """,
                    (
                        user_id,
                        token,
                        json.dumps({"dice_value": int(dice_value)}, ensure_ascii=False),
                    ),
                )
                conn.commit()
                return {
                    "roll_token": token,
                    "dice_value": int(dice_value),
                    "options": options,
                    "expires_at": expires_at.isoformat(),
                    "wallet": _wallet_payload(dict(wallet)),
                }
            except Exception:
                conn.rollback()
                raise


def resolve_dice_roll(
    user_id: int,
    roll_token: str,
    anime_id: int,
    character_id: int,
) -> Dict[str, Any]:
    user_id = int(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
                cur.execute(
                    """
                    SELECT roll_token, user_id, options, status, expires_at
                    FROM game_dice_rolls
                    WHERE roll_token = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (str(roll_token), user_id),
                )
                row = cur.fetchone()
                if not row:
                    raise InvalidDicePickError("roll_not_found")

                data = dict(row)
                if data.get("status") != "pending":
                    raise InvalidDicePickError("roll_not_pending")
                if data.get("expires_at") and data["expires_at"] <= datetime.now().astimezone():
                    cur.execute(
                        """
                        UPDATE game_dice_rolls
                        SET status = 'expired', resolved_at = NOW()
                        WHERE roll_token = %s
                        """,
                        (str(roll_token),),
                    )
                    raise DiceRollExpiredError("roll_expired")

                options = data.get("options") or []
                if isinstance(options, str):
                    try:
                        options = json.loads(options)
                    except json.JSONDecodeError:
                        options = []

                allowed_ids = {
                    int(item.get("id") or 0)
                    for item in options
                    if isinstance(item, dict)
                }
                if int(anime_id) not in allowed_ids:
                    raise InvalidDicePickError("anime_not_in_roll")

                cur.execute(
                    """
                    UPDATE game_dice_rolls
                    SET status = 'resolved',
                        selected_anime_id = %s,
                        character_id = %s,
                        resolved_at = NOW()
                    WHERE roll_token = %s AND status = 'pending'
                    RETURNING roll_token
                    """,
                    (int(anime_id), int(character_id), str(roll_token)),
                )
                if not cur.fetchone():
                    raise InvalidDicePickError("roll_race_lost")

                cur.execute(
                    """
                    INSERT INTO user_card_collection (user_id, character_id, quantity)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (user_id, character_id)
                    DO UPDATE SET quantity = user_card_collection.quantity + 1
                    RETURNING quantity
                    """,
                    (user_id, int(character_id)),
                )
                quantity_row = cur.fetchone() or {}
                conn.commit()
                return {
                    "roll_token": str(roll_token),
                    "anime_id": int(anime_id),
                    "character_id": int(character_id),
                    "quantity": int(quantity_row.get("quantity") or 1),
                }
            except Exception:
                conn.rollback()
                raise


def consume_spin(
    user_id: int,
    segment_index: int,
    reward: SpinReward,
) -> Dict[str, Any]:
    user_id = int(user_id)
    create_or_get_user(user_id)
    spin_token = secrets.token_urlsafe(20)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
                wallet = _wallet_row_locked(cur, user_id)
                if int(wallet.get("spins") or 0) <= 0:
                    raise NoSpinsError("no_spins")

                resource = str(reward.resource)
                if resource not in {"coins", "dice", "spins"}:
                    raise GameRepositoryError("invalid_spin_resource")

                reward_amount = int(reward.amount)
                if reward_amount < 0:
                    raise GameRepositoryError("invalid_spin_amount")

                dice_delta = reward_amount if resource == "dice" else 0
                coins_delta = reward_amount if resource == "coins" else 0
                spins_reward = reward_amount if resource == "spins" else 0
                spins_delta = spins_reward - 1

                cur.execute(
                    """
                    UPDATE game_wallets
                    SET coins = coins + %s,
                        dice = LEAST(%s, dice + %s),
                        spins = spins + %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                      AND spins > 0
                    RETURNING user_id, coins, dice, spins, dice_slot, created_at, updated_at
                    """,
                    (
                        coins_delta,
                        DICE_MAX_BALANCE,
                        dice_delta,
                        spins_delta,
                        user_id,
                    ),
                )
                updated = cur.fetchone()
                if not updated:
                    raise NoSpinsError("no_spins")

                cur.execute(
                    """
                    INSERT INTO game_spin_history
                        (spin_token, user_id, segment_index, reward_code, reward_resource, reward_amount)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        spin_token,
                        user_id,
                        int(segment_index),
                        str(reward.code),
                        resource,
                        reward_amount,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO game_ledger
                        (user_id, resource, delta, reason, reference, metadata)
                    VALUES (%s, 'spins', -1, 'spin_consume', %s, '{}'::jsonb)
                    """,
                    (user_id, spin_token),
                )
                if reward_amount:
                    effective_reward = reward_amount
                    if resource == "dice":
                        effective_reward = max(
                            0,
                            int(updated.get("dice") or 0) - int(wallet.get("dice") or 0),
                        )
                    if effective_reward:
                        cur.execute(
                            """
                            INSERT INTO game_ledger
                                (user_id, resource, delta, reason, reference, metadata)
                            VALUES (%s, %s, %s, 'spin_reward', %s, %s::jsonb)
                            """,
                            (
                                user_id,
                                resource,
                                effective_reward,
                                spin_token,
                                json.dumps(
                                    {"reward_code": reward.code, "segment_index": int(segment_index)},
                                    ensure_ascii=False,
                                ),
                            ),
                        )
                conn.commit()
                return {
                    "spin_token": spin_token,
                    "segment_index": int(segment_index),
                    "reward": reward.as_dict(),
                    "wallet": _wallet_payload(dict(updated)),
                }
            except Exception:
                conn.rollback()
                raise
