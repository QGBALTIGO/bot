from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from source_v2_progression import (
    ACHIEVEMENTS,
    DAILY_QUESTS,
    PASS_QUESTS,
    WEEKLY_QUESTS,
    _xp_to_level,
    period_bounds,
    selected_daily_quests,
)


TZ = ZoneInfo("America/Sao_Paulo")


def test_daily_selection_is_stable_for_user_and_day() -> None:
    now = datetime(2026, 9, 4, 12, 30, tzinfo=TZ)
    first = selected_daily_quests(12345, now)
    second = selected_daily_quests(12345, now)

    assert [q.id for q in first] == [q.id for q in second]
    assert len(first) == 3
    assert len({q.id for q in first}) == 3
    assert all(q in DAILY_QUESTS for q in first)


def test_daily_selection_changes_seed_by_day() -> None:
    day_one = datetime(2026, 9, 4, 12, 0, tzinfo=TZ)
    day_two = datetime(2026, 9, 5, 12, 0, tzinfo=TZ)
    # The key must change even if random sampling happens to produce the same set.
    key_one, _, _ = period_bounds("daily", day_one)
    key_two, _, _ = period_bounds("daily", day_two)
    assert key_one != key_two


def test_period_bounds_use_source_timezone() -> None:
    now = datetime(2026, 9, 4, 22, 15, tzinfo=TZ)
    daily_key, daily_start, daily_end = period_bounds("daily", now)
    weekly_key, weekly_start, weekly_end = period_bounds("weekly", now)

    assert daily_key == "daily:2026-09-04"
    assert daily_start.hour == 0
    assert (daily_end - daily_start).days == 1
    assert weekly_key.startswith("weekly:2026-W")
    assert weekly_start.weekday() == 0
    assert (weekly_end - weekly_start).days == 7


def test_progression_catalog_contains_seal_style_systems() -> None:
    achievement_ids = {item.id for item in ACHIEVEMENTS}
    assert {"collector_10", "collector_250", "battle_hardened", "influencer"}.issubset(achievement_ids)
    assert len(WEEKLY_QUESTS) >= 4
    assert {item.id for item in PASS_QUESTS} == {"pass_battles", "pass_collector", "pass_hatcher"}


def test_xp_level_formula_matches_existing_source_progression() -> None:
    assert _xp_to_level(0) == 1
    assert _xp_to_level(200) == 2
    assert _xp_to_level(600) == 3
