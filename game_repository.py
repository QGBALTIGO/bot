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
                # a V2 wallet. This makes the migration safe to run repeatedly.
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

                    coins_sql = "COALESCE(coins, 0)" if has_coins else "0"
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


def claim_daily(user_id: int, *, current_date: date | None = None) -> Dict[str, Any]:
    create_or_get_user(int(user_id))
    claim_date = current_date or today_sp()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _wallet_row_locked(cur, int(user_id))

                cur.execute(
                    """
                    SELECT claim_date, streak
                    FROM game_daily_claims
                    WHERE user_id = %s
                    ORDER BY claim_date DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (int(user_id),),
                )
                previous = cur.fetchone()

                if previous and previous.get("claim_date") == claim_date:
                    conn.commit()
                    return {
                        "claimed": False,
                        "already_claimed": True,
                        "wallet": _wallet_payload(wallet),
                        "last_claim": dict(previous),
                    }

                previous_date = previous.get("claim_date") if previous else None
                previous_streak = int((previous or {}).get("streak") or 0)
                streak = next_streak(previous_date, previous_streak, claim_date)
                reward: DailyReward = daily_reward_for_streak(streak)

                cur.execute(
                    """
                    INSERT INTO game_daily_claims
                    (user_id, claim_date, streak, cycle_day, coins, dice, spins)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, claim_date) DO NOTHING
                    RETURNING user_id
                    """,
                    (
                        int(user_id),
                        claim_date,
                        reward.streak,
                        reward.cycle_day,
                        reward.coins,
                        reward.dice,
                        reward.spins,
                    ),
                )
                inserted = cur.fetchone()
                if not inserted:
                    conn.rollback()
                    return claim_daily(int(user_id), current_date=claim_date)

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
                        int(user_id),
                    ),
                )
                wallet = cur.fetchone() or wallet

                reference = f"daily:{claim_date.isoformat()}"
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
                                int(user_id),
                                resource,
                                int(delta),
                                reference,
                                json.dumps({"streak": reward.streak, "cycle_day": reward.cycle_day}),
                            ),
                        )

                conn.commit()
                return {
                    "claimed": True,
                    "already_claimed": False,
                    "reward": {
                        "streak": reward.streak,
                        "cycle_day": reward.cycle_day,
                        "coins": reward.coins,
                        "dice": reward.dice,
                        "spins": reward.spins,
                    },
                    "wallet": _wallet_payload(wallet),
                }
            except Exception:
                conn.rollback()
                raise


def _decode_options(raw: Any) -> list[Dict[str, Any]]:
    if isinstance(raw, list):
        source = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            source = parsed if isinstance(parsed, list) else []
        except Exception:
            source = []
    else:
        source = []

    items: list[Dict[str, Any]] = []
    for item in source:
        if not isinstance(item, dict):
            continue
        try:
            anime_id = int(item.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if anime_id <= 0:
            continue
        items.append(
            {
                "id": anime_id,
                "title": str(item.get("title") or "").strip(),
                "cover": str(item.get("cover") or "").strip(),
            }
        )
    return items


def _roll_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "roll_token": str(row.get("roll_token") or ""),
        "user_id": int(row.get("user_id") or 0),
        "dice_value": int(row.get("dice_value") or 0),
        "options": _decode_options(row.get("options")),
        "status": str(row.get("status") or ""),
        "selected_anime_id": int(row.get("selected_anime_id") or 0) or None,
        "character_id": int(row.get("character_id") or 0) or None,
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        "expires_at": row.get("expires_at").isoformat() if row.get("expires_at") else None,
    }


def get_active_dice_roll(user_id: int) -> Optional[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    UPDATE game_dice_rolls
                    SET status = 'expired'
                    WHERE user_id = %s
                      AND status = 'pending'
                      AND expires_at <= NOW()
                    """,
                    (int(user_id),),
                )
                cur.execute(
                    """
                    SELECT *
                    FROM game_dice_rolls
                    WHERE user_id = %s
                      AND status = 'pending'
                      AND expires_at > NOW()
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (int(user_id),),
                )
                row = cur.fetchone()
                conn.commit()
                return _roll_payload(dict(row)) if row else None
            except Exception:
                conn.rollback()
                raise


def create_dice_roll(user_id: int, dice_value: int, options: list[Dict[str, Any]]) -> Dict[str, Any]:
    create_or_get_user(int(user_id))
    dice_value = int(dice_value)
    if not 1 <= dice_value <= 6:
        raise ValueError("dice_value precisa estar entre 1 e 6")
    if len(options) != dice_value:
        raise ValueError("quantidade de opções precisa ser igual ao valor do dado")

    normalized_options = _decode_options(options)
    if len(normalized_options) != dice_value:
        raise ValueError("opções inválidas ou duplicadas")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _wallet_row_locked(cur, int(user_id))
                cur.execute(
                    """
                    UPDATE game_dice_rolls
                    SET status = 'expired'
                    WHERE user_id = %s
                      AND status = 'pending'
                      AND expires_at <= NOW()
                    """,
                    (int(user_id),),
                )
                cur.execute(
                    """
                    SELECT *
                    FROM game_dice_rolls
                    WHERE user_id = %s
                      AND status = 'pending'
                      AND expires_at > NOW()
                    ORDER BY created_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (int(user_id),),
                )
                active = cur.fetchone()
                if active:
                    conn.commit()
                    raise ActiveDiceRollError(_roll_payload(dict(active)))

                if int(wallet.get("dice") or 0) <= 0:
                    conn.commit()
                    raise NoDiceError("no_dice")

                token = secrets.token_urlsafe(18)
                cur.execute(
                    """
                    UPDATE game_wallets
                    SET dice = dice - 1,
                        updated_at = NOW()
                    WHERE user_id = %s
                    RETURNING user_id, coins, dice, spins, dice_slot, created_at, updated_at
                    """,
                    (int(user_id),),
                )
                wallet = cur.fetchone() or wallet

                cur.execute(
                    """
                    INSERT INTO game_dice_rolls
                    (roll_token, user_id, dice_value, options, expires_at)
                    VALUES (%s, %s, %s, %s::jsonb, NOW() + (%s * INTERVAL '1 minute'))
                    RETURNING *
                    """,
                    (
                        token,
                        int(user_id),
                        dice_value,
                        json.dumps(normalized_options, ensure_ascii=False),
                        DICE_ROLL_TTL_MINUTES,
                    ),
                )
                roll = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO game_ledger
                    (user_id, resource, delta, reason, reference)
                    VALUES (%s, 'dice', -1, 'dice_roll', %s)
                    """,
                    (int(user_id), token),
                )
                conn.commit()
                return {
                    "roll": _roll_payload(dict(roll or {})),
                    "wallet": _wallet_payload(dict(wallet)),
                }
            except (NoDiceError, ActiveDiceRollError):
                raise
            except Exception:
                conn.rollback()
                raise


def resolve_dice_roll(
    user_id: int,
    roll_token: str,
    anime_id: int,
    character_id: int,
) -> Dict[str, Any]:
    roll_token = str(roll_token or "").strip()
    anime_id = int(anime_id)
    character_id = int(character_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT *
                    FROM game_dice_rolls
                    WHERE roll_token = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (roll_token, int(user_id)),
                )
                row = cur.fetchone()
                if not row:
                    raise InvalidDicePickError("roll_not_found")

                status = str(row.get("status") or "")
                if status != "pending":
                    raise InvalidDicePickError("roll_not_pending")
                if row.get("expires_at") and row["expires_at"] <= datetime.now(row["expires_at"].tzinfo):
                    cur.execute(
                        "UPDATE game_dice_rolls SET status = 'expired' WHERE roll_token = %s",
                        (roll_token,),
                    )
                    conn.commit()
                    raise DiceRollExpiredError("roll_expired")

                options = _decode_options(row.get("options"))
                allowed_ids = {int(item["id"]) for item in options}
                if anime_id not in allowed_ids:
                    raise InvalidDicePickError("anime_not_in_roll")

                cur.execute(
                    """
                    INSERT INTO user_card_collection
                    (user_id, character_id, quantity, first_obtained_at, updated_at)
                    VALUES (%s, %s, 1, NOW(), NOW())
                    ON CONFLICT (user_id, character_id)
                    DO UPDATE SET
                        quantity = user_card_collection.quantity + 1,
                        updated_at = NOW()
                    RETURNING quantity
                    """,
                    (int(user_id), character_id),
                )
                collection_row = cur.fetchone() or {}

                cur.execute(
                    """
                    UPDATE game_dice_rolls
                    SET status = 'resolved',
                        selected_anime_id = %s,
                        character_id = %s,
                        resolved_at = NOW()
                    WHERE roll_token = %s
                    RETURNING *
                    """,
                    (anime_id, character_id, roll_token),
                )
                resolved = cur.fetchone()
                conn.commit()
                return {
                    "roll": _roll_payload(dict(resolved or row)),
                    "quantity": int(collection_row.get("quantity") or 1),
                }
            except (InvalidDicePickError, DiceRollExpiredError):
                raise
            except Exception:
                conn.rollback()
                raise


def consume_spin(user_id: int, segment_index: int, reward: SpinReward) -> Dict[str, Any]:
    create_or_get_user(int(user_id))
    if reward.resource not in {"coins", "dice", "spins"}:
        raise ValueError("recurso de giro inválido")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _wallet_row_locked(cur, int(user_id))
                if int(wallet.get("spins") or 0) <= 0:
                    conn.commit()
                    raise NoSpinsError("no_spins")

                token = secrets.token_urlsafe(18)
                coins_delta = reward.amount if reward.resource == "coins" else 0
                dice_delta = reward.amount if reward.resource == "dice" else 0
                spins_delta = reward.amount if reward.resource == "spins" else 0

                cur.execute(
                    """
                    UPDATE game_wallets
                    SET coins = coins + %s,
                        dice = LEAST(%s, dice + %s),
                        spins = spins - 1 + %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    RETURNING user_id, coins, dice, spins, dice_slot, created_at, updated_at
                    """,
                    (
                        coins_delta,
                        DICE_MAX_BALANCE,
                        dice_delta,
                        spins_delta,
                        int(user_id),
                    ),
                )
                wallet = cur.fetchone() or wallet

                cur.execute(
                    """
                    INSERT INTO game_spin_history
                    (spin_token, user_id, segment_index, reward_code, reward_resource, reward_amount)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        token,
                        int(user_id),
                        int(segment_index),
                        reward.code,
                        reward.resource,
                        int(reward.amount),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO game_ledger
                    (user_id, resource, delta, reason, reference, metadata)
                    VALUES (%s, 'spins', -1, 'spin_cost', %s, '{}'::jsonb)
                    """,
                    (int(user_id), token),
                )
                cur.execute(
                    """
                    INSERT INTO game_ledger
                    (user_id, resource, delta, reason, reference, metadata)
                    VALUES (%s, %s, %s, 'spin_reward', %s, %s::jsonb)
                    """,
                    (
                        int(user_id),
                        reward.resource,
                        int(reward.amount),
                        token,
                        json.dumps({"reward_code": reward.code, "segment_index": int(segment_index)}),
                    ),
                )
                conn.commit()
                return {
                    "spin_token": token,
                    "segment_index": int(segment_index),
                    "reward": {
                        "code": reward.code,
                        "label": reward.label,
                        "resource": reward.resource,
                        "amount": int(reward.amount),
                    },
                    "wallet": _wallet_payload(dict(wallet)),
                }
            except NoSpinsError:
                raise
            except Exception:
                conn.rollback()
                raise


def game_state(user_id: int) -> Dict[str, Any]:
    wallet = get_wallet(int(user_id))
    last_claim = get_last_daily_claim(int(user_id))
    active_roll = get_active_dice_roll(int(user_id))
    today = today_sp()

    claimed_today = bool(last_claim and last_claim.get("claim_date") == today)
    streak = int((last_claim or {}).get("streak") or 0)
    cycle_day = int((last_claim or {}).get("cycle_day") or 0)

    return {
        "wallet": wallet,
        "daily": {
            "claimed_today": claimed_today,
            "streak": streak,
            "cycle_day": cycle_day,
            "next_cycle_day": ((streak % 7) + 1) if streak else 1,
        },
        "active_dice_roll": active_roll,
        "timezone": "America/Sao_Paulo",
    }
