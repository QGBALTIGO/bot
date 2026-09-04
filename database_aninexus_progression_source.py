from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, Iterable

from psycopg.rows import dict_row

from database_core import pool

SEASON_ID = "aninexus-s1"
SEASON_NAME = "Temporada AniNexus 01"
MAX_PASS_LEVEL = 50
PASS_MILESTONES = [1, 3, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

_TABLE_LOCK = Lock()
_TABLE_READY = False


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
                    CREATE TABLE IF NOT EXISTS aninexus_quest_claims (
                        user_id BIGINT NOT NULL,
                        quest_id TEXT NOT NULL,
                        period_key TEXT NOT NULL,
                        reward_coins INTEGER NOT NULL DEFAULT 0,
                        reward_xp INTEGER NOT NULL DEFAULT 0,
                        claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, quest_id, period_key)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_pass_claims (
                        user_id BIGINT NOT NULL,
                        season_id TEXT NOT NULL,
                        level INTEGER NOT NULL,
                        reward_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, season_id, level)
                    )
                    """
                )
                conn.commit()
        _TABLE_READY = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day_start() -> datetime:
    now = _now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _week_start() -> datetime:
    now = _day_start()
    return now - timedelta(days=now.weekday())


def _period_key(period: str) -> str:
    if period == "weekly":
        return _week_start().date().isoformat()
    return _day_start().date().isoformat()


def get_source_profile(user_id: int) -> Dict[str, Any]:
    _ensure_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO users (user_id, coins, created_at, updated_at)
                VALUES (%s, 0, NOW(), NOW())
                ON CONFLICT (user_id) DO NOTHING
                """,
                (int(user_id),),
            )
            cur.execute(
                """
                INSERT INTO user_progress (user_id, xp, level, total_actions, updated_at)
                VALUES (%s, 0, 1, 0, NOW())
                ON CONFLICT (user_id) DO NOTHING
                """,
                (int(user_id),),
            )
            cur.execute(
                """
                SELECT
                    u.coins,
                    COALESCE(u.dado_balance, 0) AS dado_balance,
                    up.xp,
                    up.level,
                    up.total_actions,
                    (
                        SELECT COUNT(*)
                        FROM user_card_collection c
                        WHERE c.user_id = u.user_id AND c.quantity > 0
                    ) AS unique_characters,
                    (
                        SELECT COALESCE(SUM(quantity), 0)
                        FROM user_card_collection c
                        WHERE c.user_id = u.user_id AND c.quantity > 0
                    ) AS total_characters
                FROM users u
                JOIN user_progress up ON up.user_id = u.user_id
                WHERE u.user_id = %s
                """,
                (int(user_id),),
            )
            row = dict(cur.fetchone() or {})
            conn.commit()
            return row


def _count(cur, sql: str, params: tuple[Any, ...]) -> int:
    cur.execute(sql, params)
    return int((cur.fetchone() or {}).get("total") or 0)


def metric_value(user_id: int, metric: str, period: str = "daily") -> int:
    _ensure_tables()
    user_id = int(user_id)
    start = _week_start() if period == "weekly" else _day_start()
    metric = str(metric or "").strip().lower()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if metric == "games_completed":
                value = _count(
                    cur,
                    """
                    SELECT COUNT(*) AS total
                    FROM aninexus_game_sessions
                    WHERE user_id = %s AND status = 'completed' AND completed_at >= %s
                    """,
                    (user_id, start),
                )
            elif metric == "dado_rolls":
                value = _count(
                    cur,
                    """
                    SELECT COUNT(*) AS total
                    FROM dice_rolls
                    WHERE user_id = %s AND created_at >= %s
                    """,
                    (user_id, start),
                )
            elif metric == "unique_collection":
                value = _count(
                    cur,
                    """
                    SELECT COUNT(*) AS total
                    FROM user_card_collection
                    WHERE user_id = %s AND quantity > 0
                    """,
                    (user_id,),
                )
            elif metric == "level":
                cur.execute("SELECT level FROM user_progress WHERE user_id = %s", (user_id,))
                value = int((cur.fetchone() or {}).get("level") or 1)
            else:
                value = 0
            conn.commit()
            return value


def is_quest_claimed(user_id: int, quest_id: str, period: str) -> bool:
    _ensure_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT 1
                FROM aninexus_quest_claims
                WHERE user_id=%s AND quest_id=%s AND period_key=%s
                LIMIT 1
                """,
                (int(user_id), str(quest_id), _period_key(period)),
            )
            return bool(cur.fetchone())


def _level_for_xp(xp: int) -> int:
    xp = max(0, int(xp))
    level = 1
    while True:
        next_level = level + 1
        needed = 80 * (next_level - 1) * (next_level - 1) + 120 * (next_level - 1)
        if xp < needed:
            return level
        level = next_level


def _award_locked(cur, user_id: int, coins: int, xp: int) -> Dict[str, int]:
    user_id = int(user_id)
    coins = max(0, int(coins))
    xp = max(0, int(xp))

    cur.execute(
        """
        INSERT INTO users (user_id, coins, created_at, updated_at)
        VALUES (%s, 0, NOW(), NOW())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id,),
    )
    cur.execute(
        """
        INSERT INTO user_progress (user_id, xp, level, total_actions, updated_at)
        VALUES (%s, 0, 1, 0, NOW())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id,),
    )

    if coins:
        cur.execute(
            """
            UPDATE users SET coins = COALESCE(coins, 0) + %s, updated_at = NOW()
            WHERE user_id = %s
            RETURNING coins
            """,
            (coins, user_id),
        )
    else:
        cur.execute("SELECT coins FROM users WHERE user_id=%s", (user_id,))
    balance = int((cur.fetchone() or {}).get("coins") or 0)

    cur.execute("SELECT xp FROM user_progress WHERE user_id=%s FOR UPDATE", (user_id,))
    current_xp = int((cur.fetchone() or {}).get("xp") or 0)
    new_xp = current_xp + xp
    cur.execute(
        """
        UPDATE user_progress
        SET xp=%s, level=%s, total_actions=COALESCE(total_actions,0)+1, updated_at=NOW()
        WHERE user_id=%s
        """,
        (new_xp, _level_for_xp(new_xp), user_id),
    )
    return {"coins": balance, "xp": new_xp}


def claim_quest(
    user_id: int,
    quest_id: str,
    period: str,
    *,
    metric: str,
    target: int,
    reward_coins: int,
    reward_xp: int,
) -> Dict[str, Any]:
    _ensure_tables()
    user_id = int(user_id)
    quest_id = str(quest_id)
    period_key = _period_key(period)
    progress = metric_value(user_id, metric, period)
    if progress < int(target):
        return {"ok": False, "error": "quest_incomplete", "progress": progress}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO aninexus_quest_claims
                    (user_id, quest_id, period_key, reward_coins, reward_xp)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id, quest_id, period_key) DO NOTHING
                    RETURNING quest_id
                    """,
                    (user_id, quest_id, period_key, int(reward_coins), int(reward_xp)),
                )
                if not cur.fetchone():
                    conn.rollback()
                    return {"ok": False, "error": "already_claimed"}
                totals = _award_locked(cur, user_id, reward_coins, reward_xp)
                conn.commit()
                return {
                    "ok": True,
                    "reward_coins": int(reward_coins),
                    "reward_xp": int(reward_xp),
                    **totals,
                }
            except Exception:
                conn.rollback()
                raise


def source_level_progress(user_id: int) -> Dict[str, int]:
    profile = get_source_profile(user_id)
    xp = max(0, int(profile.get("xp") or 0))
    level = max(1, int(profile.get("level") or 1))
    floor = 80 * (level - 1) * (level - 1) + 120 * (level - 1)
    next_level = level + 1
    next_floor = 80 * (next_level - 1) * (next_level - 1) + 120 * (next_level - 1)
    return {
        "level": min(level, MAX_PASS_LEVEL),
        "xp": xp,
        "xp_current": max(0, xp - floor),
        "xp_needed": max(1, next_floor - floor),
    }


def pass_reward(level: int) -> Dict[str, Any]:
    level = int(level)
    if level in {10, 20, 30, 40, 50}:
        return {"type": "dado", "amount": 1}
    if level in {5, 15, 25, 35, 45}:
        return {"type": "coins", "amount": 1}
    return {"type": "xp", "amount": 5}


def pass_tracks() -> Dict[int, Dict[str, Any]]:
    tracks: Dict[int, Dict[str, Any]] = {}
    for level in PASS_MILESTONES:
        reward = pass_reward(level)
        if reward["type"] == "dado":
            display = {"type": "shards", "amount": 0, "label": "+1 Dado"}
        elif reward["type"] == "coins":
            display = {"type": "shards", "amount": int(reward["amount"])}
        else:
            display = {"type": "shards", "amount": 0, "label": f"+{reward['amount']} XP"}
        tracks[level] = {
            "free": display,
            "premium": display,
            "elite": display,
            "premium_extra_amount": 0,
            "elite_extra_amount": 0,
        }
    return tracks


def claimed_pass_levels(user_id: int) -> list[int]:
    _ensure_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT level FROM aninexus_pass_claims
                WHERE user_id=%s AND season_id=%s
                ORDER BY level
                """,
                (int(user_id), SEASON_ID),
            )
            return [int(row.get("level") or 0) for row in (cur.fetchall() or [])]


def claim_pass_reward(user_id: int, level: int) -> Dict[str, Any]:
    _ensure_tables()
    level = int(level)
    if level not in PASS_MILESTONES:
        return {"ok": False, "error": "invalid_level"}
    current = source_level_progress(user_id)["level"]
    if current < level:
        return {"ok": False, "error": "level_not_reached"}
    reward = pass_reward(level)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO aninexus_pass_claims (user_id, season_id, level, reward_json)
                    VALUES (%s,%s,%s,%s::jsonb)
                    ON CONFLICT (user_id, season_id, level) DO NOTHING
                    RETURNING level
                    """,
                    (int(user_id), SEASON_ID, level, json.dumps(reward, ensure_ascii=False)),
                )
                if not cur.fetchone():
                    conn.rollback()
                    return {"ok": True, "status": "already_claimed", "coins": 0, "xp": 0, "dados": 0}

                coins = int(reward.get("amount") or 0) if reward["type"] == "coins" else 0
                xp = int(reward.get("amount") or 0) if reward["type"] == "xp" else 0
                dados = int(reward.get("amount") or 0) if reward["type"] == "dado" else 0
                _award_locked(cur, int(user_id), coins, xp)
                if dados:
                    cur.execute(
                        """
                        UPDATE users
                        SET dado_balance = LEAST(24, COALESCE(dado_balance,0) + %s), updated_at=NOW()
                        WHERE user_id=%s
                        """,
                        (dados, int(user_id)),
                    )
                conn.commit()
                return {"ok": True, "status": "success", "coins": coins, "xp": xp, "dados": dados}
            except Exception:
                conn.rollback()
                raise
