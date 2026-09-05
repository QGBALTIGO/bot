from __future__ import annotations

from utils.catalog_usage_audit_runtime import partition_by_usage


def test_usage_guard_saves_by_owners_or_copies_only():
    final_retire, saved = partition_by_usage(
        {1, 2, 3, 4},
        [
            {"character_id": 1, "owners": 10, "copies": 10},
            {"character_id": 2, "owners": 2, "copies": 20},
            {"character_id": 3, "owners": 9, "copies": 19},
            {"character_id": 4, "owners": 0, "copies": 0},
        ],
        owner_threshold=10,
        copy_threshold=20,
    )
    assert final_retire == {3, 4}
    assert {row["character_id"] for row in saved} == {1, 2}


def test_usage_guard_ignores_rows_outside_candidate_manifest():
    final_retire, saved = partition_by_usage(
        {10},
        [{"character_id": 999, "owners": 999, "copies": 999}],
    )
    assert final_retire == {10}
    assert saved == []
