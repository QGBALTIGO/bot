from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "finalize_catalog_cleanup_plan",
    ROOT / "scripts" / "finalize_catalog_cleanup_plan.py",
)
finalize = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(finalize)


def base_audit():
    return {
        "retire_ids": [1, 2, 3],
        "review_ids": [99],
        "summary": {"current_unique_characters": 100},
    }


def live_report():
    return {
        "read_only": True,
        "candidate_count": 3,
        "owner_review_threshold": 10,
        "copy_review_threshold": 20,
        "generated_at": "2026-09-05T10:00:00+00:00",
        "final_retire_ids": [3],
        "moved_to_review": [
            {"character_id": 1, "owners": 12, "copies": 12},
            {"character_id": 2, "owners": 2, "copies": 25},
        ],
        "after_guard": {"affected_users": 2, "copies": 4, "owner_character_links": 2},
        "coins_required_after_guard": 4,
    }


def test_final_plan_is_fail_closed_and_keeps_one_coin_per_copy():
    plan = finalize.finalize_plan(base_audit(), live_report())
    assert plan["apply_ready"] is False
    assert plan["requires_explicit_operator_approval"] is True
    assert plan["retire_ids"] == [3]
    assert set(plan["review_ids"]) == {1, 2, 99}
    assert plan["compensation"]["removed_copies"] == 4
    assert plan["compensation"]["coins_required"] == 4
    assert plan["safety"]["database_mutated"] is False
    assert plan["usage_guard"]["applied"] is True
    assert plan["usage_guard"]["owner_review_threshold"] == 10
    assert plan["usage_guard"]["copy_review_threshold"] == 20


def test_final_plan_rejects_incomplete_partition():
    report = live_report()
    report["moved_to_review"] = [{"character_id": 1, "owners": 12, "copies": 12}]
    with pytest.raises(ValueError, match="particiona"):
        finalize.finalize_plan(base_audit(), report)


def test_final_plan_rejects_extra_retirement_id():
    report = live_report()
    report["final_retire_ids"] = [3, 777]
    with pytest.raises(ValueError, match="fora da auditoria"):
        finalize.finalize_plan(base_audit(), report)


def test_final_plan_rejects_wrong_coin_math():
    report = live_report()
    report["coins_required_after_guard"] = 5
    with pytest.raises(ValueError, match="1 por cópia"):
        finalize.finalize_plan(base_audit(), report)
