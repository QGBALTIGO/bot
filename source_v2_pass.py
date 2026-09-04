from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from source_v2_rewards import apply_reward_locked, level_xp_required


CURRENT_PASS_SEASON = "s1"
PASS_SEASON_NAME = "Ascendant Tide"
MAX_PASS_LEVEL = 100
LEVEL_BUY_COIN_COST = 10_000
PASS_MILESTONES = [5, 10, 20, 25, 30, 40, 50, 60, 75, 80, 90, 100]
PASS_TIERS = ("free", "premium", "elite")
PASS_TIER_RANK = {tier: rank for rank, tier in enumerate(PASS_TIERS)}
PASS_STAR_PRICES = {"premium": 24, "elite": 49}
PASS_TIER_META = {
    "free": {"name": "Free", "summary": "Base seasonal rewards"},
    "premium": {
        "name": "Premium",
        "summary": "Bank unlock, premium missions, better eggs, faster incubation",
    },
    "elite": {
        "name": "Elite",
        "summary": "All tracks, strongest economy, best egg luck, 3 incubators",
    },
}
PASS_BENEFITS = {
    "free": {
        "daily_multiplier": 1.0,
        "weekly_multiplier": 1.0,
        "hunt_multiplier": 1.0,
        "xp_multiplier": 1.0,
        "incubation_multiplier": 1.0,
        "egg_drop_multiplier": 1.0,
        "egg_quality_bonus": 0.0,
        "bonus_egg_chance": 0.0,
        "corruption_resistance": 0.0,
        "incubation_slots": 1,
        "mission_track": False,
    },
    "premium": {
        "daily_multiplier": 1.35,
        "weekly_multiplier": 1.35,
        "hunt_multiplier": 1.35,
        "xp_multiplier": 1.25,
        "incubation_multiplier": 0.65,
        "egg_drop_multiplier": 1.35,
        "egg_quality_bonus": 0.12,
        "bonus_egg_chance": 0.05,
        "corruption_resistance": 0.25,
        "incubation_slots": 2,
        "mission_track": True,
    },
    "elite": {
        "daily_multiplier": 1.75,
        "weekly_multiplier": 1.75,
        "hunt_multiplier": 1.75,
        "xp_multiplier": 1.50,
        "incubation_multiplier": 0.45,
        "egg_drop_multiplier": 1.75,
        "egg_quality_bonus": 0.28,
        "bonus_egg_chance": 0.12,
        "corruption_resistance": 0.50,
        "incubation_slots": 3,
        "mission_track": True,
    },
}

EGG_TIER_NAMES = {1: "gold", 2: "void", 3: "rare", 4: "legendary", 5: "celestial"}
EGG_NAMES = {
    "common": "Common Egg",
    "gold": "Golden Egg",
    "void": "Void Egg",
    "rare": "Rare Egg",
    "legendary": "Legendary Egg",
    "celestial": "Celestial Egg",
}


def normalize_pass_tier(tier: str | None) -> str:
    value = str(tier or "free").lower().strip()
    return value if value in PASS_TIER_RANK else "free"


def pass_rank(tier: str | None) -> int:
    return PASS_TIER_RANK[normalize_pass_tier(tier)]


def calculate_upgrade_price(current_tier: str | None, target_tier: str) -> int | None:
    current = normalize_pass_tier(current_tier)
    target = normalize_pass_tier(target_tier)
    if target == "free" or pass_rank(current) >= pass_rank(target):
        return None
    return max(1, PASS_STAR_PRICES[target] - PASS_STAR_PRICES.get(current, 0))


def _shards(amount: int) -> dict[str, Any]:
    return {"type": "shards", "amount": int(amount)}


def _egg(tier: int) -> dict[str, Any]:
    return {"type": "egg", "tier": int(tier)}


def _default_track(level: int) -> dict[str, Any]:
    return {
        "free": _shards(150 + level * 12),
        "premium": _shards(450 + level * 28),
        "elite": _shards(850 + level * 45),
    }


def _track_for_level(level: int) -> dict[str, Any]:
    track = _default_track(level)
    if level % 5 == 0:
        track.update({
            "free": _shards(1_250 + level * 15),
            "premium": _egg(1),
            "elite": _egg(2),
            "premium_extra_amount": 750 + level * 20,
            "elite_extra_amount": 1_500 + level * 35,
        })
    if level % 10 == 0:
        track.update({
            "free": _egg(1),
            "premium": _egg(2),
            "elite": _egg(3),
            "premium_extra_amount": 2_000 + level * 40,
            "elite_extra_amount": 5_000 + level * 70,
        })
    if level in {25, 75}:
        track.update({
            "free": _egg(2),
            "premium": _egg(3),
            "elite": _egg(4),
            "premium_extra_amount": 5_000 + level * 60,
            "elite_extra_amount": 15_000 + level * 120,
        })
    if level == 50:
        track.update({
            "free": _egg(3),
            "premium": _egg(4),
            "elite": _egg(5),
            "premium_extra_amount": 15_000,
            "elite_extra_amount": 40_000,
        })
    if level == 100:
        track.update({
            "free": _egg(4),
            "premium": _egg(5),
            "elite": _egg(5),
            "premium_extra_amount": 50_000,
            "elite_extra_amount": 100_000,
        })
    return track


PASS_TRACKS = {level: _track_for_level(level) for level in range(1, MAX_PASS_LEVEL + 1)}


def _ensure_state_locked(cur, user_id: int) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO source_v2_pass_state (user_id, season_id, pass_type)
        VALUES (%s, %s, 'free')
        ON CONFLICT (user_id, season_id) DO NOTHING
        """,
        (int(user_id), CURRENT_PASS_SEASON),
    )
    cur.execute(
        """
        SELECT user_id, season_id, pass_type, bank_coins, activated_at
        FROM source_v2_pass_state
        WHERE user_id = %s AND season_id = %s
        FOR UPDATE
        """,
        (int(user_id), CURRENT_PASS_SEASON),
    )
    return dict(cur.fetchone() or {})


def get_pass_type(user_id: int) -> str:
    from database_core import run

    row = run(
        "SELECT pass_type FROM source_v2_pass_state WHERE user_id = %s AND season_id = %s",
        (int(user_id), CURRENT_PASS_SEASON),
        fetch="one",
    ) or {}
    return normalize_pass_tier(row.get("pass_type"))


def _progress_locked(cur, user_id: int) -> dict[str, int]:
    cur.execute(
        """
        INSERT INTO user_progress (user_id, xp, level, total_actions)
        VALUES (%s, 0, 1, 0)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),),
    )
    cur.execute("SELECT xp, level FROM user_progress WHERE user_id = %s FOR UPDATE", (int(user_id),))
    row = cur.fetchone() or {}
    xp = int(row.get("xp") or 0)
    level = max(1, int(row.get("level") or 1))
    current_threshold = level_xp_required(level)
    next_threshold = level_xp_required(level + 1)
    return {
        "xp": xp,
        "level": level,
        "xp_current": max(0, xp - current_threshold),
        "xp_needed": max(1, next_threshold - current_threshold),
    }


def _claimed_levels(cur, user_id: int) -> list[int]:
    cur.execute(
        "SELECT level FROM source_v2_pass_claims WHERE user_id = %s AND season_id = %s ORDER BY level",
        (int(user_id), CURRENT_PASS_SEASON),
    )
    return [int(row["level"]) for row in (cur.fetchall() or [])]


def get_pass_data(user_id: int) -> dict[str, Any]:
    from database_core import pool

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            state = _ensure_state_locked(cur, int(user_id))
            progress = _progress_locked(cur, int(user_id))
            claimed = _claimed_levels(cur, int(user_id))
            conn.commit()

    tier = normalize_pass_tier(state.get("pass_type"))
    bank_coins = max(0, int(state.get("bank_coins") or 0))
    return {
        **progress,
        "season_id": CURRENT_PASS_SEASON,
        "season_name": PASS_SEASON_NAME,
        "pass_type": tier,
        "pass_bank": {"shards": bank_coins},
        "pass_bank_total": bank_coins,
        "claimed_levels": claimed,
        "tracks": PASS_TRACKS,
        "milestones": PASS_MILESTONES,
        "max_level": MAX_PASS_LEVEL,
        "prices": PASS_STAR_PRICES,
        "currency": "XTR",
        "upgrade_prices": {
            candidate: calculate_upgrade_price(tier, candidate)
            for candidate in ("premium", "elite")
        },
        "level_buy_cost": LEVEL_BUY_COIN_COST,
        "benefits": PASS_BENEFITS,
        "tiers": PASS_TIER_META,
    }


def _insert_egg(cur, user_id: int, tier_id: int, source_id: str) -> str:
    tier = EGG_TIER_NAMES.get(int(tier_id), "gold")
    egg_id = f"bp_{uuid.uuid4().hex[:16]}"
    cur.execute(
        """
        INSERT INTO source_v2_eggs
            (egg_id, user_id, tier, name, status, source_type, source_id)
        VALUES (%s, %s, %s, %s, 'fresh', 'pass', %s)
        """,
        (egg_id, int(user_id), tier, EGG_NAMES[tier], source_id),
    )
    return egg_id


def claim_pass_level(user_id: int, level: int) -> dict[str, Any]:
    from database_core import pool

    user_id = int(user_id)
    level = int(level)
    if level < 1 or level > MAX_PASS_LEVEL:
        raise ValueError("invalid_level")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                state = _ensure_state_locked(cur, user_id)
                progress = _progress_locked(cur, user_id)
                if min(MAX_PASS_LEVEL, progress["level"]) < level:
                    raise ValueError("level_not_reached")

                cur.execute(
                    "SELECT 1 FROM source_v2_pass_claims WHERE user_id = %s AND season_id = %s AND level = %s",
                    (user_id, CURRENT_PASS_SEASON, level),
                )
                if cur.fetchone():
                    conn.commit()
                    return {"status": "already_claimed", "shards": 0, "eggs": 0}

                track = PASS_TRACKS[level]
                tier = normalize_pass_tier(state.get("pass_type"))
                rewards = [track["free"]]
                extra_coins = 0
                if pass_rank(tier) >= pass_rank("premium"):
                    rewards.append(track["premium"])
                    extra_coins += int(track.get("premium_extra_amount") or 0)
                if tier == "elite":
                    rewards.append(track["elite"])
                    extra_coins += int(track.get("elite_extra_amount") or 0)

                coins = extra_coins
                egg_tiers: list[int] = []
                for reward in rewards:
                    if reward.get("type") == "shards":
                        coins += max(0, int(reward.get("amount") or 0))
                    elif reward.get("type") == "egg":
                        egg_tiers.append(max(1, int(reward.get("tier") or 1)))

                cur.execute(
                    """
                    INSERT INTO source_v2_pass_claims
                        (user_id, season_id, level, pass_type_at_claim, coins_awarded, eggs_awarded)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, season_id, level) DO NOTHING
                    RETURNING level
                    """,
                    (user_id, CURRENT_PASS_SEASON, level, tier, coins, len(egg_tiers)),
                )
                if not cur.fetchone():
                    conn.rollback()
                    return {"status": "already_claimed", "shards": 0, "eggs": 0}

                if coins:
                    apply_reward_locked(cur, user_id, coins=coins)
                for tier_id in egg_tiers:
                    _insert_egg(cur, user_id, tier_id, f"pass:{CURRENT_PASS_SEASON}:{level}")
                conn.commit()
                return {"status": "success", "shards": coins, "eggs": len(egg_tiers)}
            except ValueError:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def buy_pass_levels(user_id: int, levels: int) -> dict[str, Any]:
    from database_core import pool

    user_id = int(user_id)
    levels = min(50, max(1, int(levels or 1)))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                progress = _progress_locked(cur, user_id)
                current_level = min(MAX_PASS_LEVEL, progress["level"])
                target_level = min(MAX_PASS_LEVEL, current_level + levels)
                actual_levels = target_level - current_level
                if actual_levels <= 0:
                    raise ValueError("max_pass_level_reached")
                cost = actual_levels * LEVEL_BUY_COIN_COST

                cur.execute(
                    "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                    (user_id,),
                )
                cur.execute("SELECT COALESCE(coins, 0) AS coins FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                user = cur.fetchone() or {}
                coins = int(user.get("coins") or 0)
                if coins < cost:
                    raise ValueError("insufficient_coins")

                target_xp = level_xp_required(target_level)
                new_xp = max(progress["xp"], target_xp)
                cur.execute("UPDATE users SET coins = coins - %s, updated_at = NOW() WHERE user_id = %s", (cost, user_id))
                cur.execute(
                    "UPDATE user_progress SET xp = %s, level = %s, updated_at = NOW() WHERE user_id = %s",
                    (new_xp, target_level, user_id),
                )
                conn.commit()
                return {
                    "status": "success",
                    "message": f"Bought {actual_levels} levels for {cost} Coins!",
                    "levels": actual_levels,
                    "cost": cost,
                    "level": target_level,
                    "xp": new_xp,
                }
            except ValueError:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def claim_pass_bank(user_id: int) -> dict[str, Any]:
    from database_core import pool

    user_id = int(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                state = _ensure_state_locked(cur, user_id)
                if normalize_pass_tier(state.get("pass_type")) == "free":
                    raise ValueError("pass_upgrade_required")
                bank = max(0, int(state.get("bank_coins") or 0))
                if bank <= 0:
                    conn.commit()
                    return {"message": "Bank is empty.", "shards": 0, "eggs": 0}
                cur.execute(
                    "UPDATE source_v2_pass_state SET bank_coins = 0, updated_at = NOW() WHERE user_id = %s AND season_id = %s AND bank_coins = %s RETURNING user_id",
                    (user_id, CURRENT_PASS_SEASON, bank),
                )
                if not cur.fetchone():
                    raise ValueError("bank_modified")
                apply_reward_locked(cur, user_id, coins=bank)
                conn.commit()
                return {"message": f"Claimed {bank} Coins!", "shards": bank, "eggs": 0}
            except ValueError:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise
