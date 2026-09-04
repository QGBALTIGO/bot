from __future__ import annotations

import json
import os
import random
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row

from seal_progression import (
    ACHIEVEMENTS,
    CURRENT_PASS_SEASON,
    PASS_MISSIONS,
    PASS_TRACKS,
    QUEST_POOL,
    WEEKLY_POOL,
    get_pass_rank,
    normalize_pass_tier,
    reward_egg_name,
    reward_egg_tier,
)

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False
INITIAL_SHARD_MULTIPLIER = max(1, int(os.getenv("SEAL_INITIAL_SHARD_MULTIPLIER", "1000")))


def _core():
    from database_core import pool, run

    return pool, run


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        _pool, run = _core()
        run(
            """
            CREATE TABLE IF NOT EXISTS seal_wallet (
                user_id BIGINT PRIMARY KEY,
                source_user_created_at TIMESTAMPTZ NOT NULL,
                shards BIGINT NOT NULL DEFAULT 0 CHECK (shards >= 0),
                zenith BIGINT NOT NULL DEFAULT 0 CHECK (zenith >= 0),
                xp BIGINT NOT NULL DEFAULT 0 CHECK (xp >= 0),
                initialized_source_coins BIGINT NOT NULL DEFAULT 0,
                initialized_source_xp BIGINT NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        run(
            """
            CREATE TABLE IF NOT EXISTS seal_wallet_transactions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                source_user_created_at TIMESTAMPTZ NOT NULL,
                tx_type TEXT NOT NULL,
                amount BIGINT NOT NULL,
                balance_after BIGINT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        run(
            """
            CREATE INDEX IF NOT EXISTS idx_seal_wallet_transactions_user_created
            ON seal_wallet_transactions (user_id, created_at DESC)
            """
        )
        run(
            """
            CREATE TABLE IF NOT EXISTS seal_daily_quest_selection (
                user_id BIGINT NOT NULL,
                source_user_created_at TIMESTAMPTZ NOT NULL,
                day_key DATE NOT NULL,
                quest_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, day_key)
            )
            """
        )
        run(
            """
            CREATE TABLE IF NOT EXISTS seal_quest_claims (
                user_id BIGINT NOT NULL,
                source_user_created_at TIMESTAMPTZ NOT NULL,
                cycle_key TEXT NOT NULL,
                quest_id TEXT NOT NULL,
                reward_xp BIGINT NOT NULL DEFAULT 0,
                reward_shards BIGINT NOT NULL DEFAULT 0,
                claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, cycle_key, quest_id)
            )
            """
        )
        run(
            """
            CREATE INDEX IF NOT EXISTS idx_seal_quest_claims_user
            ON seal_quest_claims (user_id, claimed_at DESC)
            """
        )
        run(
            """
            CREATE TABLE IF NOT EXISTS seal_achievement_unlocks (
                user_id BIGINT NOT NULL,
                source_user_created_at TIMESTAMPTZ NOT NULL,
                achievement_id TEXT NOT NULL,
                title TEXT,
                reward_xp BIGINT NOT NULL DEFAULT 0,
                reward_shards BIGINT NOT NULL DEFAULT 0,
                unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, achievement_id)
            )
            """
        )
        run(
            """
            CREATE TABLE IF NOT EXISTS seal_pass_state (
                user_id BIGINT NOT NULL,
                source_user_created_at TIMESTAMPTZ NOT NULL,
                season_id TEXT NOT NULL,
                pass_type TEXT NOT NULL DEFAULT 'free',
                claimed_levels INTEGER[] NOT NULL DEFAULT '{}',
                pass_bank JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, season_id)
            )
            """
        )
        run(
            """
            CREATE TABLE IF NOT EXISTS seal_eggs (
                egg_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                source_user_created_at TIMESTAMPTZ NOT NULL,
                tier TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'fresh',
                origin TEXT,
                hatch_time TIMESTAMPTZ,
                incubation_started_at TIMESTAMPTZ,
                incubation_base_minutes INTEGER,
                incubation_minutes INTEGER,
                hatched_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        run(
            """
            CREATE INDEX IF NOT EXISTS idx_seal_eggs_user_status
            ON seal_eggs (user_id, status, created_at DESC)
            """
        )
        _SCHEMA_READY = True


def _prepare_source_user(user_id: int) -> None:
    from database import create_or_get_user, ensure_progress_row

    create_or_get_user(int(user_id))
    ensure_progress_row(int(user_id))


def _source_snapshot_locked(cur, user_id: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
            u.user_id,
            u.created_at,
            COALESCE(u.coins, 0) AS coins,
            COALESCE(up.xp, 0) AS xp
        FROM users u
        LEFT JOIN user_progress up ON up.user_id = u.user_id
        WHERE u.user_id = %s
        FOR UPDATE OF u
        """,
        (int(user_id),),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("source_user_missing")
    return dict(row)


def _purge_stale_generation_locked(cur, user_id: int, generation: datetime) -> None:
    for table in (
        "seal_wallet_transactions",
        "seal_daily_quest_selection",
        "seal_quest_claims",
        "seal_achievement_unlocks",
        "seal_pass_state",
        "seal_eggs",
    ):
        cur.execute(
            f"DELETE FROM {table} WHERE user_id = %s AND source_user_created_at <> %s",
            (int(user_id), generation),
        )


def _ensure_wallet_locked(cur, user_id: int) -> dict[str, Any]:
    source = _source_snapshot_locked(cur, user_id)
    generation = source["created_at"]
    cur.execute(
        "SELECT * FROM seal_wallet WHERE user_id = %s FOR UPDATE",
        (int(user_id),),
    )
    wallet = cur.fetchone()
    initial_shards = max(0, int(source.get("coins") or 0)) * INITIAL_SHARD_MULTIPLIER
    initial_xp = max(0, int(source.get("xp") or 0))

    if not wallet:
        cur.execute(
            """
            INSERT INTO seal_wallet (
                user_id, source_user_created_at, shards, zenith, xp,
                initialized_source_coins, initialized_source_xp
            )
            VALUES (%s, %s, %s, 0, %s, %s, %s)
            RETURNING *
            """,
            (
                int(user_id),
                generation,
                initial_shards,
                initial_xp,
                int(source.get("coins") or 0),
                initial_xp,
            ),
        )
        wallet = cur.fetchone()
    elif wallet.get("source_user_created_at") != generation:
        _purge_stale_generation_locked(cur, user_id, generation)
        cur.execute(
            """
            UPDATE seal_wallet
            SET source_user_created_at = %s,
                shards = %s,
                zenith = 0,
                xp = %s,
                initialized_source_coins = %s,
                initialized_source_xp = %s,
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING *
            """,
            (
                generation,
                initial_shards,
                initial_xp,
                int(source.get("coins") or 0),
                initial_xp,
                int(user_id),
            ),
        )
        wallet = cur.fetchone()

    return dict(wallet or {})


def _ensure_pass_locked(cur, user_id: int, generation: datetime) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO seal_pass_state (
            user_id, source_user_created_at, season_id, pass_type
        )
        VALUES (%s, %s, %s, 'free')
        ON CONFLICT (user_id, season_id) DO NOTHING
        """,
        (int(user_id), generation, CURRENT_PASS_SEASON),
    )
    cur.execute(
        """
        SELECT * FROM seal_pass_state
        WHERE user_id = %s AND season_id = %s
        FOR UPDATE
        """,
        (int(user_id), CURRENT_PASS_SEASON),
    )
    row = cur.fetchone() or {}
    if row and row.get("source_user_created_at") != generation:
        cur.execute(
            """
            UPDATE seal_pass_state
            SET source_user_created_at = %s,
                pass_type = 'free',
                claimed_levels = '{}',
                pass_bank = '{}'::jsonb,
                updated_at = NOW()
            WHERE user_id = %s AND season_id = %s
            RETURNING *
            """,
            (generation, int(user_id), CURRENT_PASS_SEASON),
        )
        row = cur.fetchone() or {}
    return dict(row)


def get_wallet(user_id: int) -> dict[str, Any]:
    ensure_schema()
    _prepare_source_user(user_id)
    pool, _run = _core()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _ensure_wallet_locked(cur, int(user_id))
                conn.commit()
                return wallet
            except Exception:
                conn.rollback()
                raise


def get_pass_state(user_id: int) -> dict[str, Any]:
    ensure_schema()
    _prepare_source_user(user_id)
    pool, _run = _core()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _ensure_wallet_locked(cur, int(user_id))
                row = _ensure_pass_locked(cur, int(user_id), wallet["source_user_created_at"])
                conn.commit()
                row["pass_type"] = normalize_pass_tier(row.get("pass_type"))
                row["claimed_levels"] = [int(x) for x in (row.get("claimed_levels") or [])]
                row["pass_bank"] = dict(row.get("pass_bank") or {})
                return row
            except Exception:
                conn.rollback()
                raise


def get_eggs(user_id: int) -> list[dict[str, Any]]:
    ensure_schema()
    wallet = get_wallet(user_id)
    _pool, run = _core()
    rows = run(
        """
        SELECT egg_id, tier, name, status, hatch_time,
               incubation_started_at, incubation_base_minutes, incubation_minutes,
               created_at
        FROM seal_eggs
        WHERE user_id = %s AND source_user_created_at = %s
        ORDER BY created_at DESC
        """,
        (int(user_id), wallet["source_user_created_at"]),
        fetch="all",
    ) or []
    out = []
    for row in rows:
        item = dict(row)
        item["id"] = str(item.pop("egg_id"))
        for key in ("hatch_time", "incubation_started_at", "created_at"):
            value = item.get(key)
            if value is not None and hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        out.append(item)
    return out


def _day_bounds(now: datetime | None = None) -> tuple[datetime, datetime, str]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1), start.date().isoformat()


def _week_bounds(now: datetime | None = None) -> tuple[datetime, datetime, str]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = (current - timedelta(days=current.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    iso = current.isocalendar()
    return start, start + timedelta(days=7), f"{iso.year}-W{iso.week:02d}"


def get_daily_selection(user_id: int, now: datetime | None = None) -> list[str]:
    ensure_schema()
    wallet = get_wallet(user_id)
    start, _end, day_key = _day_bounds(now)
    _pool, run = _core()
    row = run(
        """
        SELECT quest_ids, source_user_created_at
        FROM seal_daily_quest_selection
        WHERE user_id = %s AND day_key = %s
        """,
        (int(user_id), start.date()),
        fetch="one",
    )
    generation = wallet["source_user_created_at"]
    if row and row.get("source_user_created_at") == generation:
        return [str(x) for x in (row.get("quest_ids") or []) if str(x) in QUEST_POOL]

    selected = random.sample(list(QUEST_POOL.keys()), min(3, len(QUEST_POOL)))
    run(
        """
        INSERT INTO seal_daily_quest_selection (
            user_id, source_user_created_at, day_key, quest_ids
        )
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (user_id, day_key) DO UPDATE
        SET source_user_created_at = EXCLUDED.source_user_created_at,
            quest_ids = EXCLUDED.quest_ids,
            created_at = NOW()
        """,
        (int(user_id), generation, start.date(), json.dumps(selected)),
    )
    return selected


def quest_cycle(quest_id: str, now: datetime | None = None) -> tuple[str, datetime | None, datetime | None]:
    if quest_id in QUEST_POOL:
        start, end, key = _day_bounds(now)
        return f"daily:{key}", start, end
    if quest_id in WEEKLY_POOL:
        start, end, key = _week_bounds(now)
        return f"weekly:{key}", start, end
    if quest_id in PASS_MISSIONS:
        return f"pass:{CURRENT_PASS_SEASON}", None, None
    raise KeyError(quest_id)


def _scalar(sql: str, params: tuple[Any, ...]) -> int:
    _pool, run = _core()
    row = run(sql, params, fetch="one") or {}
    return int(row.get("value") or 0)


def _time_filter(column: str, start: datetime | None, end: datetime | None) -> tuple[str, list[Any]]:
    if start is None or end is None:
        return "", []
    return f" AND {column} >= %s AND {column} < %s", [start, end]


def quest_progress(user_id: int, quest_id: str, now: datetime | None = None) -> int:
    _cycle, start, end = quest_cycle(quest_id, now)

    if quest_id in {"catch_master", "weekly_catch", "pass_collector"}:
        clause, params = _time_filter("captured_at", start, end)
        return _scalar(
            f"""
            SELECT COUNT(*) AS value
            FROM capture_spawns
            WHERE winner_user_id = %s
              AND captured_at IS NOT NULL
              {clause}
            """,
            (int(user_id), *params),
        )

    if quest_id in {"battle_veteran", "weekly_battle", "pass_battles"}:
        clause, params = _time_filter("finished_at", start, end)
        return _scalar(
            f"""
            SELECT COUNT(*) AS value
            FROM duels
            WHERE winner_user_id = %s
              AND finished_at IS NOT NULL
              {clause}
            """,
            (int(user_id), *params),
        )

    if quest_id == "trader":
        clause, params = _time_filter("created_at", start, end)
        return _scalar(
            f"""
            SELECT COUNT(*) AS value
            FROM card_trades
            WHERE status = 'completed'
              AND (from_user = %s OR to_user = %s)
              {clause}
            """,
            (int(user_id), int(user_id), *params),
        )

    if quest_id in {"big_spender", "weekly_spender"}:
        clause, params = _time_filter("created_at", start, end)
        return _scalar(
            f"""
            SELECT COALESCE(SUM(-amount), 0) AS value
            FROM seal_wallet_transactions
            WHERE user_id = %s
              AND amount < 0
              {clause}
            """,
            (int(user_id), *params),
        )

    if quest_id in {"egg_hatcher", "weekly_hatcher", "pass_hatcher"}:
        clause, params = _time_filter("hatched_at", start, end)
        return _scalar(
            f"""
            SELECT COUNT(*) AS value
            FROM seal_eggs
            WHERE user_id = %s
              AND status = 'hatched'
              AND hatched_at IS NOT NULL
              {clause}
            """,
            (int(user_id), *params),
        )

    # /nguess, hunting egg drops and direct Coin gifting do not have a Source
    # equivalent yet. They remain at zero until those exact systems are ported.
    return 0


def is_quest_claimed(user_id: int, quest_id: str, now: datetime | None = None) -> bool:
    ensure_schema()
    wallet = get_wallet(user_id)
    cycle_key, _start, _end = quest_cycle(quest_id, now)
    _pool, run = _core()
    row = run(
        """
        SELECT 1 AS value
        FROM seal_quest_claims
        WHERE user_id = %s
          AND source_user_created_at = %s
          AND cycle_key = %s
          AND quest_id = %s
        LIMIT 1
        """,
        (int(user_id), wallet["source_user_created_at"], cycle_key, quest_id),
        fetch="one",
    )
    return bool(row)


def claim_quest(user_id: int, quest_id: str, now: datetime | None = None) -> dict[str, Any]:
    ensure_schema()
    if quest_id in QUEST_POOL:
        if quest_id not in get_daily_selection(user_id, now):
            return {"ok": False, "error": "quest_not_active"}
        definition = QUEST_POOL[quest_id]
    elif quest_id in WEEKLY_POOL:
        definition = WEEKLY_POOL[quest_id]
    elif quest_id in PASS_MISSIONS:
        definition = PASS_MISSIONS[quest_id]
        if normalize_pass_tier(get_pass_state(user_id).get("pass_type")) == "free":
            return {"ok": False, "error": "pass_required"}
    else:
        return {"ok": False, "error": "quest_not_found"}

    progress = quest_progress(user_id, quest_id, now)
    if progress < int(definition["target"]):
        return {"ok": False, "error": "quest_incomplete", "progress": progress}

    cycle_key, _start, _end = quest_cycle(quest_id, now)
    _prepare_source_user(user_id)
    pool, _run = _core()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _ensure_wallet_locked(cur, int(user_id))
                generation = wallet["source_user_created_at"]
                cur.execute(
                    """
                    INSERT INTO seal_quest_claims (
                        user_id, source_user_created_at, cycle_key, quest_id,
                        reward_xp, reward_shards
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, cycle_key, quest_id) DO NOTHING
                    RETURNING quest_id
                    """,
                    (
                        int(user_id),
                        generation,
                        cycle_key,
                        quest_id,
                        int(definition["reward_xp"]),
                        int(definition["reward_shards"]),
                    ),
                )
                if not cur.fetchone():
                    conn.rollback()
                    return {"ok": False, "error": "already_claimed"}

                new_shards = int(wallet.get("shards") or 0) + int(definition["reward_shards"])
                new_xp = int(wallet.get("xp") or 0) + int(definition["reward_xp"])
                cur.execute(
                    """
                    UPDATE seal_wallet
                    SET shards = %s, xp = %s, updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (new_shards, new_xp, int(user_id)),
                )
                cur.execute(
                    """
                    INSERT INTO seal_wallet_transactions (
                        user_id, source_user_created_at, tx_type, amount,
                        balance_after, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        int(user_id),
                        generation,
                        f"quest:{quest_id}",
                        int(definition["reward_shards"]),
                        new_shards,
                        json.dumps({"cycle_key": cycle_key, "reward_xp": definition["reward_xp"]}),
                    ),
                )
                conn.commit()
                return {
                    "ok": True,
                    "reward_xp": int(definition["reward_xp"]),
                    "reward_shards": int(definition["reward_shards"]),
                }
            except Exception:
                conn.rollback()
                raise


def get_achievement_metrics(user_id: int) -> dict[str, int]:
    wallet = get_wallet(user_id)
    _pool, run = _core()
    unique_characters = _scalar(
        """
        SELECT COUNT(*) AS value
        FROM user_card_collection
        WHERE user_id = %s AND quantity > 0
        """,
        (int(user_id),),
    )
    guesses = _scalar(
        "SELECT COALESCE(wins, 0) AS value FROM termo_stats WHERE user_id = %s",
        (int(user_id),),
    )
    battle_wins = _scalar(
        "SELECT COALESCE(wins, 0) AS value FROM duel_stats WHERE user_id = %s",
        (int(user_id),),
    )
    referrals = _scalar(
        "SELECT COUNT(*) AS value FROM user_referrals WHERE referrer_user_id = %s",
        (int(user_id),),
    )
    hatched_eggs = _scalar(
        "SELECT COUNT(*) AS value FROM seal_eggs WHERE user_id = %s AND status = 'hatched'",
        (int(user_id),),
    )
    return {
        "unique_characters": unique_characters,
        "guesses": guesses,
        "hatched_eggs": hatched_eggs,
        "battle_wins": battle_wins,
        "shards": int(wallet.get("shards") or 0),
        "referrals": referrals,
    }


def sync_achievements(user_id: int) -> list[str]:
    ensure_schema()
    metrics = get_achievement_metrics(user_id)
    _prepare_source_user(user_id)
    pool, _run = _core()
    unlocked_now: list[str] = []
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _ensure_wallet_locked(cur, int(user_id))
                generation = wallet["source_user_created_at"]
                cur.execute(
                    """
                    SELECT achievement_id
                    FROM seal_achievement_unlocks
                    WHERE user_id = %s AND source_user_created_at = %s
                    """,
                    (int(user_id), generation),
                )
                existing = {str(row["achievement_id"]) for row in (cur.fetchall() or [])}
                reward_xp = 0
                reward_shards = 0
                for achievement_id, definition in ACHIEVEMENTS.items():
                    if achievement_id in existing:
                        continue
                    if int(metrics.get(str(definition["metric"]), 0)) < int(definition["target"]):
                        continue
                    cur.execute(
                        """
                        INSERT INTO seal_achievement_unlocks (
                            user_id, source_user_created_at, achievement_id, title,
                            reward_xp, reward_shards
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, achievement_id) DO NOTHING
                        RETURNING achievement_id
                        """,
                        (
                            int(user_id),
                            generation,
                            achievement_id,
                            str(definition.get("title") or ""),
                            int(definition["reward_xp"]),
                            int(definition["reward_shards"]),
                        ),
                    )
                    if cur.fetchone():
                        unlocked_now.append(achievement_id)
                        reward_xp += int(definition["reward_xp"])
                        reward_shards += int(definition["reward_shards"])

                if unlocked_now:
                    new_shards = int(wallet.get("shards") or 0) + reward_shards
                    new_xp = int(wallet.get("xp") or 0) + reward_xp
                    cur.execute(
                        "UPDATE seal_wallet SET shards = %s, xp = %s, updated_at = NOW() WHERE user_id = %s",
                        (new_shards, new_xp, int(user_id)),
                    )
                    cur.execute(
                        """
                        INSERT INTO seal_wallet_transactions (
                            user_id, source_user_created_at, tx_type, amount, balance_after, metadata
                        ) VALUES (%s, %s, 'achievement_unlocks', %s, %s, %s::jsonb)
                        """,
                        (
                            int(user_id),
                            generation,
                            reward_shards,
                            new_shards,
                            json.dumps({"achievement_ids": unlocked_now, "reward_xp": reward_xp}),
                        ),
                    )
                conn.commit()
                return unlocked_now
            except Exception:
                conn.rollback()
                raise


def get_unlocked_achievement_ids(user_id: int) -> set[str]:
    ensure_schema()
    wallet = get_wallet(user_id)
    _pool, run = _core()
    rows = run(
        """
        SELECT achievement_id
        FROM seal_achievement_unlocks
        WHERE user_id = %s AND source_user_created_at = %s
        """,
        (int(user_id), wallet["source_user_created_at"]),
        fetch="all",
    ) or []
    return {str(row["achievement_id"]) for row in rows}


def get_titles(user_id: int) -> list[str]:
    ensure_schema()
    wallet = get_wallet(user_id)
    _pool, run = _core()
    rows = run(
        """
        SELECT title
        FROM seal_achievement_unlocks
        WHERE user_id = %s
          AND source_user_created_at = %s
          AND COALESCE(title, '') <> ''
        ORDER BY unlocked_at ASC
        """,
        (int(user_id), wallet["source_user_created_at"]),
        fetch="all",
    ) or []
    return [str(row["title"]) for row in rows]


def claim_pass_level(user_id: int, level: int) -> dict[str, Any]:
    ensure_schema()
    level = int(level)
    if level < 1 or level not in PASS_TRACKS:
        return {"ok": False, "error": "invalid_level"}

    from seal_progression import get_level_from_xp

    _prepare_source_user(user_id)
    pool, _run = _core()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _ensure_wallet_locked(cur, int(user_id))
                if get_level_from_xp(int(wallet.get("xp") or 0)) < level:
                    conn.rollback()
                    return {"ok": False, "error": "level_not_reached"}
                generation = wallet["source_user_created_at"]
                pass_state = _ensure_pass_locked(cur, int(user_id), generation)
                claimed_levels = [int(x) for x in (pass_state.get("claimed_levels") or [])]
                if level in claimed_levels:
                    conn.commit()
                    return {"ok": True, "status": "already_claimed", "shards": 0, "eggs": 0}

                pass_type = normalize_pass_tier(pass_state.get("pass_type"))
                reward_data = PASS_TRACKS[level]
                rewards = [reward_data["free"]]
                extra_shards = 0
                if get_pass_rank(pass_type) >= get_pass_rank("premium"):
                    rewards.append(reward_data["premium"])
                    extra_shards += int(reward_data.get("premium_extra_amount") or 0)
                if pass_type == "elite":
                    rewards.append(reward_data["elite"])
                    extra_shards += int(reward_data.get("elite_extra_amount") or 0)

                shard_reward = extra_shards
                eggs_created = 0
                for reward in rewards:
                    if reward.get("type") == "shards":
                        shard_reward += int(reward.get("amount") or 0)
                    elif reward.get("type") == "egg":
                        tier_id = int(reward.get("tier") or 1)
                        cur.execute(
                            """
                            INSERT INTO seal_eggs (
                                egg_id, user_id, source_user_created_at, tier, name,
                                status, origin
                            ) VALUES (%s, %s, %s, %s, %s, 'fresh', %s)
                            """,
                            (
                                f"bp_{level}_{uuid.uuid4().hex[:10]}",
                                int(user_id),
                                generation,
                                reward_egg_tier(tier_id),
                                reward_egg_name(tier_id),
                                f"pass:{CURRENT_PASS_SEASON}:level:{level}",
                            ),
                        )
                        eggs_created += 1

                new_shards = int(wallet.get("shards") or 0) + shard_reward
                cur.execute(
                    "UPDATE seal_wallet SET shards = %s, updated_at = NOW() WHERE user_id = %s",
                    (new_shards, int(user_id)),
                )
                cur.execute(
                    """
                    UPDATE seal_pass_state
                    SET claimed_levels = array_append(claimed_levels, %s), updated_at = NOW()
                    WHERE user_id = %s AND season_id = %s
                    """,
                    (level, int(user_id), CURRENT_PASS_SEASON),
                )
                if shard_reward:
                    cur.execute(
                        """
                        INSERT INTO seal_wallet_transactions (
                            user_id, source_user_created_at, tx_type, amount, balance_after, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            int(user_id),
                            generation,
                            f"pass_level:{level}",
                            shard_reward,
                            new_shards,
                            json.dumps({"season": CURRENT_PASS_SEASON, "eggs": eggs_created}),
                        ),
                    )
                conn.commit()
                return {"ok": True, "status": "success", "shards": shard_reward, "eggs": eggs_created}
            except Exception:
                conn.rollback()
                raise


def buy_pass_levels(user_id: int, levels: int) -> dict[str, Any]:
    ensure_schema()
    levels = max(1, min(50, int(levels)))
    cost = levels * 10_000
    _prepare_source_user(user_id)
    pool, _run = _core()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _ensure_wallet_locked(cur, int(user_id))
                shards = int(wallet.get("shards") or 0)
                if shards < cost:
                    conn.rollback()
                    return {"ok": False, "error": "insufficient_shards", "cost": cost}
                new_shards = shards - cost
                new_xp = int(wallet.get("xp") or 0) + levels * 100
                cur.execute(
                    "UPDATE seal_wallet SET shards = %s, xp = %s, updated_at = NOW() WHERE user_id = %s",
                    (new_shards, new_xp, int(user_id)),
                )
                cur.execute(
                    """
                    INSERT INTO seal_wallet_transactions (
                        user_id, source_user_created_at, tx_type, amount, balance_after, metadata
                    ) VALUES (%s, %s, 'pass_buy_level', %s, %s, %s::jsonb)
                    """,
                    (
                        int(user_id),
                        wallet["source_user_created_at"],
                        -cost,
                        new_shards,
                        json.dumps({"levels": levels, "xp_added": levels * 100}),
                    ),
                )
                conn.commit()
                return {"ok": True, "cost": cost, "levels": levels, "xp": new_xp, "shards": new_shards}
            except Exception:
                conn.rollback()
                raise
