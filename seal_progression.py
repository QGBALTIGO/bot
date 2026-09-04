from __future__ import annotations

import math
from typing import Any

# Adaptado de bisug/seal-your-waifu-bot.
# Licença/atribuição upstream preservada em seal_frontend/LICENSE.

CURRENT_PASS_SEASON = "s1"
PASS_SEASON_NAME = "Ascendant Tide"
MAX_PASS_LEVEL = 100
PASS_MILESTONES = [5, 10, 20, 25, 30, 40, 50, 60, 75, 80, 90, 100]
MID_PASS_MILESTONES = {25, 75}
HALFWAY_LEVEL = 50
FINAL_PASS_LEVEL = 100
PASS_TIERS = ("free", "premium", "elite")
PASS_TIER_RANK = {tier: rank for rank, tier in enumerate(PASS_TIERS)}
PASS_STAR_PRICES = {"premium": 24, "elite": 49}
LEVEL_BUY_SHARD_COST = 10_000

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

QUEST_POOL = {
    "catch_master": {
        "name": "Catch Master",
        "description": "Catch 2 characters",
        "target": 2,
        "reward_xp": 50,
        "reward_shards": 500,
        "icon": "◉",
    },
    "guesser": {
        "name": "Quick Thinker",
        "description": "Identify 3 characters in /nguess",
        "target": 3,
        "reward_xp": 60,
        "reward_shards": 600,
        "icon": "🧩",
    },
    "battle_veteran": {
        "name": "Brawler",
        "description": "Win 1 battle",
        "target": 1,
        "reward_xp": 75,
        "reward_shards": 750,
        "icon": "⚔",
    },
    "egg_hunter": {
        "name": "Egg Seeker",
        "description": "Find 1 egg while hunting",
        "target": 1,
        "reward_xp": 40,
        "reward_shards": 400,
        "icon": "🥚",
    },
    "egg_hatcher": {
        "name": "Nurturer",
        "description": "Hatch 1 egg",
        "target": 1,
        "reward_xp": 50,
        "reward_shards": 500,
        "icon": "🐣",
    },
    "generous_soul": {
        "name": "Gift Giver",
        "description": "Gift Coins to a player",
        "target": 1,
        "reward_xp": 40,
        "reward_shards": 400,
        "icon": "🎁",
    },
    "trader": {
        "name": "Deal Maker",
        "description": "Complete a trade",
        "target": 1,
        "reward_xp": 50,
        "reward_shards": 500,
        "icon": "🤝",
    },
    "big_spender": {
        "name": "Big Spender",
        "description": "Spend 1,000 Coins",
        "target": 1000,
        "reward_xp": 100,
        "reward_shards": 1000,
        "icon": "💰",
    },
}

WEEKLY_POOL = {
    "weekly_catch": {
        "name": "Master Collector",
        "description": "Catch 20 characters this week",
        "target": 20,
        "reward_xp": 500,
        "reward_shards": 5000,
        "icon": "❂",
    },
    "weekly_guesser": {
        "name": "Enigma Master",
        "description": "Identify 15 characters in /nguess",
        "target": 15,
        "reward_xp": 600,
        "reward_shards": 6000,
        "icon": "🔮",
    },
    "weekly_hatcher": {
        "name": "Pro Breeder",
        "description": "Hatch 5 eggs this week",
        "target": 5,
        "reward_xp": 500,
        "reward_shards": 5000,
        "icon": "🕊",
    },
    "weekly_battle": {
        "name": "Warlord",
        "description": "Win 10 battles this week",
        "target": 10,
        "reward_xp": 600,
        "reward_shards": 6000,
        "icon": "⚔",
    },
    "weekly_spender": {
        "name": "Tycoon",
        "description": "Spend 10,000 Coins this week",
        "target": 10000,
        "reward_xp": 800,
        "reward_shards": 8000,
        "icon": "💎",
    },
}

PASS_MISSIONS = {
    "pass_battles": {
        "name": "Pass Warlord",
        "description": "Win 20 battles",
        "target": 20,
        "reward_xp": 1000,
        "reward_shards": 10000,
        "icon": "⚔",
    },
    "pass_collector": {
        "name": "Pass Master",
        "description": "Catch 50 characters",
        "target": 50,
        "reward_xp": 1000,
        "reward_shards": 10000,
        "icon": "❂",
    },
    "pass_hatcher": {
        "name": "Pass Hatcher",
        "description": "Hatch 10 eggs",
        "target": 10,
        "reward_xp": 1500,
        "reward_shards": 15000,
        "icon": "🐣",
    },
}

ACHIEVEMENTS = {
    "collector_10": {
        "name": "Novice Collector",
        "description": "Own 10 Characters",
        "reward_xp": 100,
        "reward_shards": 1000,
        "title": "Rookie",
        "icon": "🥉",
        "metric": "unique_characters",
        "target": 10,
    },
    "collector_50": {
        "name": "Gatherer",
        "description": "Own 50 Characters",
        "reward_xp": 500,
        "reward_shards": 5000,
        "title": "Enthusiast",
        "icon": "🥈",
        "metric": "unique_characters",
        "target": 50,
    },
    "collector_100": {
        "name": "Expert Collector",
        "description": "Own 100 Characters",
        "reward_xp": 1000,
        "reward_shards": 10000,
        "title": "Curator",
        "icon": "🥇",
        "metric": "unique_characters",
        "target": 100,
    },
    "collector_250": {
        "name": "Master Collector",
        "description": "Own 250 Characters",
        "reward_xp": 2500,
        "reward_shards": 25000,
        "title": "Hoarder",
        "icon": "🏆",
        "metric": "unique_characters",
        "target": 250,
    },
    "guesser_10": {
        "name": "Sharp Eye",
        "description": "Correctly guess 10 characters",
        "reward_xp": 200,
        "reward_shards": 2000,
        "title": "Observer",
        "icon": "🔍",
        "metric": "guesses",
        "target": 10,
    },
    "hatcher_1": {
        "name": "First Hatch",
        "description": "Hatch your first egg",
        "reward_xp": 150,
        "reward_shards": 1500,
        "title": "Caregiver",
        "icon": "🐣",
        "metric": "hatched_eggs",
        "target": 1,
    },
    "hatcher_10": {
        "name": "Egg Expert",
        "description": "Hatch 10 eggs",
        "reward_xp": 1000,
        "reward_shards": 10000,
        "title": "Breeder",
        "icon": "🥚",
        "metric": "hatched_eggs",
        "target": 10,
    },
    "battle_hardened": {
        "name": "Battle Hardened",
        "description": "Win 50 Battles",
        "reward_xp": 500,
        "reward_shards": 5000,
        "title": "Gladiator",
        "icon": "⚔",
        "metric": "battle_wins",
        "target": 50,
    },
    "rich_vip": {
        "name": "Millionaire",
        "description": "Hold 1,000,000 Coins",
        "reward_xp": 2000,
        "reward_shards": 20000,
        "title": "Tycoon",
        "icon": "✧",
        "metric": "shards",
        "target": 1_000_000,
    },
    "influencer": {
        "name": "Influencer",
        "description": "Invite 10 Users",
        "reward_xp": 1000,
        "reward_shards": 10000,
        "title": "Ambassador",
        "icon": "❃",
        "metric": "referrals",
        "target": 10,
    },
}


def normalize_pass_tier(value: str | None) -> str:
    tier = str(value or "free").strip().lower()
    return tier if tier in PASS_TIER_RANK else "free"


def get_pass_rank(value: str | None) -> int:
    return PASS_TIER_RANK[normalize_pass_tier(value)]


def calculate_pass_upgrade_price(current_tier: str | None, target_tier: str) -> int | None:
    current = normalize_pass_tier(current_tier)
    target = normalize_pass_tier(target_tier)
    if target == "free" or get_pass_rank(current) >= get_pass_rank(target):
        return None
    return max(1, PASS_STAR_PRICES[target] - PASS_STAR_PRICES.get(current, 0))


def get_level_from_xp(xp: int) -> int:
    value = max(0, int(xp or 0))
    if value <= 0:
        return 0
    level = int((-1 + math.sqrt(1 + value / 12.5)) / 2)
    return min(level, MAX_PASS_LEVEL)


def get_xp_for_next_level(current_level: int) -> int:
    level = max(0, int(current_level or 0))
    if level >= MAX_PASS_LEVEL:
        return 0
    return 100 * (level + 1)


def get_progress_values(xp: int) -> dict[str, int]:
    total_xp = max(0, int(xp or 0))
    level = get_level_from_xp(total_xp)
    xp_needed = get_xp_for_next_level(level)
    previous_floor = 50 * level * (level + 1)
    xp_current = 0 if xp_needed == 0 else max(0, total_xp - previous_floor)
    return {
        "level": level,
        "xp": total_xp,
        "xp_current": xp_current,
        "xp_needed": xp_needed,
    }


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


def _milestone_track(level: int) -> dict[str, Any]:
    track = _default_track(level)
    if level % 5 == 0:
        track.update(
            {
                "free": _shards(1_250 + level * 15),
                "premium": _egg(1),
                "elite": _egg(2),
                "premium_extra_amount": 750 + level * 20,
                "elite_extra_amount": 1_500 + level * 35,
            }
        )
    if level % 10 == 0:
        track.update(
            {
                "free": _egg(1),
                "premium": _egg(2),
                "elite": _egg(3),
                "premium_extra_amount": 2_000 + level * 40,
                "elite_extra_amount": 5_000 + level * 70,
            }
        )
    if level in MID_PASS_MILESTONES:
        track.update(
            {
                "free": _egg(2),
                "premium": _egg(3),
                "elite": _egg(4),
                "premium_extra_amount": 5_000 + level * 60,
                "elite_extra_amount": 15_000 + level * 120,
            }
        )
    if level == HALFWAY_LEVEL:
        track.update(
            {
                "free": _egg(3),
                "premium": _egg(4),
                "elite": _egg(5),
                "premium_extra_amount": 15_000,
                "elite_extra_amount": 40_000,
            }
        )
    if level == FINAL_PASS_LEVEL:
        track.update(
            {
                "free": _egg(4),
                "premium": _egg(5),
                "elite": _egg(5),
                "premium_extra_amount": 50_000,
                "elite_extra_amount": 100_000,
            }
        )
    return track


PASS_TRACKS = {level: _milestone_track(level) for level in range(1, MAX_PASS_LEVEL + 1)}


def reward_egg_name(tier: int | str) -> str:
    mapping = {
        "1": "Common Egg",
        "2": "Uncommon Egg",
        "3": "Rare Egg",
        "4": "Epic Egg",
        "5": "Legendary Egg",
    }
    return mapping.get(str(tier), f"Tier {tier} Egg")


def reward_egg_tier(tier: int | str) -> str:
    mapping = {
        "1": "common",
        "2": "uncommon",
        "3": "rare",
        "4": "epic",
        "5": "legendary",
    }
    return mapping.get(str(tier), "common")
