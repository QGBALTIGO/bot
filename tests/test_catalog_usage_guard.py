from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "guard_catalog_retirements_by_usage",
    ROOT / "scripts" / "guard_catalog_retirements_by_usage.py",
)
guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(guard)


def test_high_collection_impact_moves_retirement_to_review():
    retire = {1, 2, 3}
    usage = [
        {"character_id": 1, "owners": 12, "copies": 12},
        {"character_id": 2, "owners": 2, "copies": 25},
        {"character_id": 3, "owners": 2, "copies": 4},
    ]
    final_retire, review, indexed = guard.partition_by_usage(
        retire,
        usage,
        owner_threshold=10,
        copy_threshold=20,
    )
    assert final_retire == {3}
    assert review == {1, 2}
    assert indexed[1]["owners"] == 12
    assert indexed[2]["copies"] == 25


def test_usage_guard_keeps_coin_math_on_final_retire_only():
    audit = {
        "retire_ids": [1, 2, 3],
        "review_ids": [99],
        "summary": {
            "current_unique_characters": 100,
            "definite_add_candidates": 5,
            "retire_candidates": 3,
            "review": 1,
        },
    }
    usage = [
        {"character_id": 1, "owners": 20, "copies": 30},
        {"character_id": 2, "owners": 1, "copies": 2},
        {"character_id": 3, "owners": 0, "copies": 0},
    ]
    guarded, stats = guard.build_guarded_audit(
        audit,
        usage,
        labels={1: {"name": "Popular in Source", "anime": "X"}},
        owner_threshold=10,
        copy_threshold=20,
    )
    assert guarded["retire_ids"] == [2, 3]
    assert set(guarded["review_ids"]) == {1, 99}
    assert stats["moved_to_review"] == 1
    assert stats["coins_required_after_guard"] == 2
    assert guarded["summary"]["projected_unique_after_retire_before_add"] == 98
