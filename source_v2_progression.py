from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row


SOURCE_TZ = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class AchievementDefinition:
    id: str
    name: str
    description: str
    icon: str
    metric: str
    target: int
    reward_xp: int
    reward_coins: int
    title: str | None = None


@dataclass(frozen=True)
class QuestDefinition:
    id: str
    name: str
    description: str
    icon: str
    metric: str
    target: int
    reward_xp: int
    reward_coins: int
    kind: str = "daily"


ACHIEVEMENTS: tuple[AchievementDefinition, ...] = (
    AchievementDefinition("collector_10", "Rookie Collector", "Colecione 10 personagens únicos", "🃏", "unique_characters", 10, 100, 1_000, "Rookie"),
    AchievementDefinition("collector_50", "Growing Collection", "Colecione 50 personagens únicos", "📚", "unique_characters", 50, 500, 5_000, "Enthusiast"),
    AchievementDefinition("collector_100", "Century Club", "Colecione 100 personagens únicos", "💯", "unique_characters", 100, 1_000, 10_000, "Curator"),
    AchievementDefinition("collector_250", "Grand Archive", "Colecione 250 personagens únicos", "🏛️", "unique_characters", 250, 2_500, 25_000, "Hoarder"),
    AchievementDefinition("guesser_10", "Quick Thinker", "Vença 10 partidas de Termo Anime", "🧩", "termo_wins", 10, 200, 2_000, "Observer"),
    AchievementDefinition("hatcher_1", "First Hatch", "Choque seu primeiro ovo", "🐣", "hatches", 1, 150, 1_500, "Caregiver"),
    AchievementDefinition("hatcher_10", "Master Breeder", "Choque 10 ovos", "🕊️", "hatches", 10, 1_000, 10_000, "Breeder"),
    AchievementDefinition("battle_hardened", "Battle Hardened", "Vença 50 duelos", "⚔️", "battle_wins", 50, 500, 5_000, "Gladiator"),
    AchievementDefinition("rich_vip", "Millionaire", "Tenha 1.000.000 Coins", "💰", "coins", 1_000_000, 2_000, 20_000, "Tycoon"),
    AchievementDefinition("influencer", "Influencer", "Convide 10 usuários pelo seu link", "📣", "referrals", 10, 1_000, 10_000, "Ambassador"),
)


DAILY_QUESTS: tuple[QuestDefinition, ...] = (
    QuestDefinition("daily_checkin", "Check-in", "Resgate o Daily de hoje", "🎁", "daily_claims", 1, 40, 400),
    QuestDefinition("catch_master", "Catch Master", "Capture 2 personagens hoje", "◉", "captures", 2, 50, 500),
    QuestDefinition("quick_thinker", "Quick Thinker", "Vença 1 Termo Anime hoje", "🧩", "termo_wins", 1, 60, 600),
    QuestDefinition("dice_explorer", "Dice Explorer", "Conclua 1 rolagem do Dado hoje", "🎲", "dice_rolls", 1, 50, 500),
)


WEEKLY_QUESTS: tuple[QuestDefinition, ...] = (
    QuestDefinition("weekly_catch", "Master Collector", "Capture 20 personagens nesta semana", "❂", "captures", 20, 500, 5_000, "weekly"),
    QuestDefinition("weekly_guesser", "Enigma Master", "Vença 5 Termos Anime nesta semana", "🔮", "termo_wins", 5, 600, 6_000, "weekly"),
    QuestDefinition("weekly_dice", "Fortune Seeker", "Conclua 10 rolagens do Dado nesta semana", "🎲", "dice_rolls", 10, 500, 5_000, "weekly"),
    QuestDefinition("weekly_daily", "Consistent", "Resgate o Daily em 5 dias nesta semana", "🔥", "daily_claims", 5, 500, 5_000, "weekly"),
)


PASS_QUESTS: tuple[QuestDefinition, ...] = (
    QuestDefinition("pass_battles", "Pass Warlord", "Vença 20 duelos na temporada", "⚔️", "battle_wins", 20, 1_000, 10_000, "pass"),
    QuestDefinition("pass_collector", "Pass Master", "Capture 50 personagens na temporada", "❂", "captures", 50, 1_000, 10_000, "pass"),
    QuestDefinition("pass_hatcher", "Pass Hatcher", "Choque 10 ovos na temporada", "🐣", "hatches", 10, 1_500, 15_000, "pass"),
)


def _now() -> datetime:
    return datetime.now(SOURCE_TZ)


def period_bounds(kind: str, now: datetime | None = None) -> tuple[str, datetime | None, datetime | None]:
    current = (now or _now()).astimezone(SOURCE_TZ)
    if kind == "daily":
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return f"daily:{start.date().isoformat()}", start, end
    if kind == "weekly":
        start = (current - timedelta(days=current.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        iso = start.isocalendar()
        return f"weekly:{iso.year}-W{iso.week:02d}", start, end
    # Pass progression becomes season-keyed when the Pass domain is ported.
    return "pass:preview", None, None


def selected_daily_quests(user_id: int, now: datetime | None = None) -> tuple[QuestDefinition, ...]:
    period_key, _, _ = period_bounds("daily", now)
    seed_bytes = hashlib.sha256(f"source-v2:{int(user_id)}:{period_key}".encode("utf-8")).digest()
    seed = int.from_bytes(seed_bytes[:8], "big")
    rng = random.Random(seed)
    return tuple(rng.sample(list(DAILY_QUESTS), k=min(3, len(DAILY_QUESTS))))


def _scalar(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return 0
    if isinstance(row, dict):
        return int(next(iter(row.values())) or 0)
    return int(row[0] or 0)


def _metric_value(cur, user_id: int, metric: str, start: datetime | None = None, end: datetime | None = None) -> int:
    user_id = int(user_id)
    time_clause = ""
    params: list = [user_id]

    if metric == "unique_characters":
        return _scalar(
            cur,
            "SELECT COUNT(*) FROM user_card_collection WHERE user_id = %s AND quantity > 0",
            (user_id,),
        )
    if metric == "coins":
        return _scalar(cur, "SELECT COALESCE(coins, 0) FROM users WHERE user_id = %s", (user_id,))
    if metric == "referrals":
        return _scalar(cur, "SELECT COUNT(*) FROM user_referrals WHERE referrer_user_id = %s", (user_id,))
    if metric == "battle_wins":
        if start is None:
            return _scalar(cur, "SELECT COUNT(*) FROM duels WHERE winner_user_id = %s", (user_id,))
        # Duels expose updated_at in the existing Source combat schema.
        return _scalar(
            cur,
            "SELECT COUNT(*) FROM duels WHERE winner_user_id = %s AND updated_at >= %s AND updated_at < %s",
            (user_id, start, end),
        )
    if metric == "hatches":
        # Hatchery is not live in Source yet. Keeping this explicit prevents fake progress.
        return 0
    if metric == "termo_wins":
        if start is None:
            return _scalar(cur, "SELECT COUNT(*) FROM termo_games WHERE user_id = %s AND status = 'won'", (user_id,))
        return _scalar(
            cur,
            "SELECT COUNT(*) FROM termo_games WHERE user_id = %s AND status = 'won' AND created_at >= %s AND created_at < %s",
            (user_id, start, end),
        )
    if metric == "captures":
        if start is None:
            return _scalar(cur, "SELECT COUNT(*) FROM capture_spawns WHERE winner_user_id = %s AND captured_at IS NOT NULL", (user_id,))
        return _scalar(
            cur,
            "SELECT COUNT(*) FROM capture_spawns WHERE winner_user_id = %s AND captured_at >= %s AND captured_at < %s",
            (user_id, start, end),
        )
    if metric == "dice_rolls":
        if start is None:
            return _scalar(cur, "SELECT COUNT(*) FROM dice_rolls WHERE user_id = %s AND status = 'resolved'", (user_id,))
        # dice_rolls.created_at is epoch bigint; resolved_at is timestamptz and authoritative.
        return _scalar(
            cur,
            "SELECT COUNT(*) FROM dice_rolls WHERE user_id = %s AND status = 'resolved' AND resolved_at >= %s AND resolved_at < %s",
            (user_id, start, end),
        )
    if metric == "daily_claims":
        if start is None:
            return _scalar(cur, "SELECT COUNT(*) FROM daily_rewards WHERE user_id = %s", (user_id,))
        return _scalar(
            cur,
            "SELECT COUNT(*) FROM daily_rewards WHERE user_id = %s AND claimed_at >= %s AND claimed_at < %s",
            (user_id, start, end),
        )
    return 0


def _level_xp_required(level: int) -> int:
    level = max(1, int(level))
    return 80 * (level - 1) * (level - 1) + 120 * (level - 1)


def _xp_to_level(xp: int) -> int:
    xp = max(0, int(xp))
    level = 1
    while xp >= _level_xp_required(level + 1):
        level += 1
    return level


def _ensure_reward_rows(cur, user_id: int) -> None:
    cur.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (int(user_id),))
    cur.execute(
        "INSERT INTO user_progress (user_id, xp, level, total_actions) VALUES (%s, 0, 1, 0) ON CONFLICT (user_id) DO NOTHING",
        (int(user_id),),
    )


def _apply_reward(cur, user_id: int, reward_xp: int, reward_coins: int) -> None:
    _ensure_reward_rows(cur, user_id)
    cur.execute(
        "UPDATE users SET coins = COALESCE(coins, 0) + %s, updated_at = NOW() WHERE user_id = %s",
        (int(reward_coins), int(user_id)),
    )
    cur.execute("SELECT xp FROM user_progress WHERE user_id = %s FOR UPDATE", (int(user_id),))
    row = cur.fetchone()
    old_xp = int((row["xp"] if isinstance(row, dict) else row[0]) if row else 0)
    new_xp = old_xp + max(0, int(reward_xp))
    cur.execute(
        "UPDATE user_progress SET xp = %s, level = %s, updated_at = NOW() WHERE user_id = %s",
        (new_xp, _xp_to_level(new_xp), int(user_id)),
    )


def list_achievements(user_id: int) -> list[dict]:
    from database_core import pool

    user_id = int(user_id)
    output: list[dict] = []
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                for definition in ACHIEVEMENTS:
                    progress = _metric_value(cur, user_id, definition.metric)
                    unlocked = progress >= definition.target
                    if unlocked:
                        cur.execute(
                            """
                            INSERT INTO source_v2_achievement_unlocks
                                (user_id, achievement_id, title, reward_xp, reward_coins)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (user_id, achievement_id) DO NOTHING
                            RETURNING achievement_id
                            """,
                            (user_id, definition.id, definition.title, definition.reward_xp, definition.reward_coins),
                        )
                        inserted = cur.fetchone()
                        if inserted:
                            _apply_reward(cur, user_id, definition.reward_xp, definition.reward_coins)
                            if definition.title:
                                cur.execute(
                                    """
                                    INSERT INTO source_v2_titles (user_id, title, source_type, source_id)
                                    VALUES (%s, %s, 'achievement', %s)
                                    ON CONFLICT (user_id, title) DO NOTHING
                                    """,
                                    (user_id, definition.title, definition.id),
                                )

                    cur.execute(
                        "SELECT unlocked_at FROM source_v2_achievement_unlocks WHERE user_id = %s AND achievement_id = %s",
                        (user_id, definition.id),
                    )
                    unlock_row = cur.fetchone()
                    output.append(
                        {
                            "id": definition.id,
                            "name": definition.name,
                            "description": definition.description,
                            "icon": definition.icon,
                            "reward_xp": definition.reward_xp,
                            "reward_shards": definition.reward_coins,
                            "reward_coins": definition.reward_coins,
                            "progress": min(progress, definition.target),
                            "target": definition.target,
                            "unlocked": bool(unlock_row),
                            "title": definition.title,
                        }
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    return output


def _quest_payload(cur, user_id: int, definition: QuestDefinition, now: datetime) -> dict:
    period_key, start, end = period_bounds(definition.kind, now)
    progress = _metric_value(cur, user_id, definition.metric, start, end)
    cur.execute(
        "SELECT 1 FROM source_v2_quest_claims WHERE user_id = %s AND period_key = %s AND quest_id = %s",
        (int(user_id), period_key, definition.id),
    )
    claimed = bool(cur.fetchone())
    return {
        "id": definition.id,
        "name": definition.name,
        "description": definition.description,
        "icon": definition.icon,
        "reward_xp": definition.reward_xp,
        "reward_shards": definition.reward_coins,
        "reward_coins": definition.reward_coins,
        "progress": min(progress, definition.target),
        "target": definition.target,
        "claimed": claimed,
        "locked": definition.kind == "pass",
        "period_key": period_key,
    }


def get_user_quests(user_id: int, now: datetime | None = None) -> dict:
    from database_core import pool

    current = (now or _now()).astimezone(SOURCE_TZ)
    daily = selected_daily_quests(user_id, current)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return {
                "daily": [_quest_payload(cur, user_id, q, current) for q in daily],
                "weekly": [_quest_payload(cur, user_id, q, current) for q in WEEKLY_QUESTS],
                "pass": [_quest_payload(cur, user_id, q, current) for q in PASS_QUESTS],
                "pass_type": "free",
            }


def _find_active_quest(user_id: int, quest_id: str, now: datetime) -> QuestDefinition | None:
    for definition in selected_daily_quests(user_id, now):
        if definition.id == quest_id:
            return definition
    for definition in WEEKLY_QUESTS:
        if definition.id == quest_id:
            return definition
    # Pass claims remain locked until the pass system itself is ported.
    return None


def claim_quest(user_id: int, quest_id: str, now: datetime | None = None) -> dict:
    from database_core import pool

    user_id = int(user_id)
    current = (now or _now()).astimezone(SOURCE_TZ)
    definition = _find_active_quest(user_id, str(quest_id), current)
    if definition is None:
        raise KeyError("quest_not_found_or_locked")

    period_key, start, end = period_bounds(definition.kind, current)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                progress = _metric_value(cur, user_id, definition.metric, start, end)
                if progress < definition.target:
                    conn.rollback()
                    raise ValueError("quest_not_complete")

                cur.execute(
                    """
                    INSERT INTO source_v2_quest_claims
                        (user_id, period_key, quest_id, reward_xp, reward_coins)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, period_key, quest_id) DO NOTHING
                    RETURNING quest_id
                    """,
                    (user_id, period_key, definition.id, definition.reward_xp, definition.reward_coins),
                )
                if not cur.fetchone():
                    conn.rollback()
                    raise ValueError("quest_already_claimed")

                _apply_reward(cur, user_id, definition.reward_xp, definition.reward_coins)
                conn.commit()
                return {
                    "ok": True,
                    "quest_id": definition.id,
                    "reward_xp": definition.reward_xp,
                    "reward_shards": definition.reward_coins,
                    "reward_coins": definition.reward_coins,
                    "period_key": period_key,
                }
            except (KeyError, ValueError):
                raise
            except Exception:
                conn.rollback()
                raise


def latest_unlocked_title(user_id: int) -> str | None:
    from database_core import run

    row = run(
        """
        SELECT title FROM source_v2_titles
        WHERE user_id = %s
        ORDER BY unlocked_at DESC, title ASC
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one",
    )
    return str((row or {}).get("title") or "").strip() or None
