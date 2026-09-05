from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "materialize_final_catalog_overrides",
    ROOT / "scripts" / "materialize_final_catalog_overrides.py",
)
materialize = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(materialize)


def plan(retire_ids: list[int] | None = None, moved_ids: list[int] | None = None):
    ids = retire_ids or [1, 3]
    moved = [2] if moved_ids is None else moved_ids
    source_candidates = set(ids) | set(moved)
    return {
        "schema": materialize.FINAL_PLAN_SCHEMA,
        "apply_ready": False,
        "requires_explicit_operator_approval": True,
        "source_candidate_ids_sha256": materialize.ids_hash(source_candidates),
        "final_retire_ids_sha256": materialize.ids_hash(ids),
        "retire_ids": ids,
        "moved_to_review_by_collection_impact": [
            {"character_id": cid, "owners": 12, "copies": 12}
            for cid in moved
        ],
        "usage_guard": {"applied": True, "candidate_count": len(source_candidates)},
        "safety": {
            "usage_guard_applied": True,
            "database_mutated": False,
            "catalog_mutated": False,
        },
    }


def test_materialization_preserves_manual_deletions_and_restores_usage_saved_ids():
    base = {
        "deleted_characters": [99],
        "custom_animes": [],
        "custom_characters": [],
    }
    proposal = {
        "deleted_characters": [1, 2, 3, 99],
        "custom_animes": [{"anime_id": 20, "anime": "Naruto"}],
        "custom_characters": [{"id": 17, "anime_id": 20, "name": "Naruto Uzumaki"}],
    }
    out, stats = materialize.build_final_overrides(base, proposal, plan())
    assert out["deleted_characters"] == [1, 3, 99]
    assert 2 not in out["deleted_characters"]
    assert out["custom_animes"] == proposal["custom_animes"]
    assert out["custom_characters"] == proposal["custom_characters"]
    assert stats["restored_from_proposal_by_usage_guard"] == 1
    assert stats["source_candidates_before_usage_guard"] == 3
    assert stats["final_retire"] == 2
    assert out["_catalog_cleanup"]["final_retire_ids_sha256"] == materialize.ids_hash([1, 3])
    assert out["_catalog_cleanup"]["source_candidate_ids_sha256"] == materialize.ids_hash([1, 2, 3])
    assert out["_catalog_cleanup"]["requires_explicit_operator_approval"] is True


def test_manual_deleted_character_stays_deleted_even_if_usage_guard_saved_it():
    base = {"deleted_characters": [2]}
    proposal = {"deleted_characters": [1, 2, 3]}
    out, stats = materialize.build_final_overrides(base, proposal, plan())
    assert out["deleted_characters"] == [1, 2, 3]
    assert stats["restored_from_proposal_by_usage_guard"] == 0


def test_unknown_final_retirement_is_rejected():
    base = {"deleted_characters": []}
    proposal = {"deleted_characters": [1, 2, 3]}
    bad = plan([1, 777])
    with pytest.raises(ValueError, match="fora da proposta/base"):
        materialize.build_final_overrides(base, proposal, bad)


def test_tampered_final_hash_is_rejected():
    base = {"deleted_characters": []}
    proposal = {"deleted_characters": [1, 2, 3]}
    bad = plan()
    bad["final_retire_ids_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash final"):
        materialize.build_final_overrides(base, proposal, bad)


def test_tampered_source_candidate_hash_is_rejected():
    base = {"deleted_characters": []}
    proposal = {"deleted_characters": [1, 2, 3]}
    bad = plan()
    bad["source_candidate_ids_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="candidatos pré-usage-guard"):
        materialize.build_final_overrides(base, proposal, bad)


def test_candidate_count_mismatch_is_rejected():
    base = {"deleted_characters": []}
    proposal = {"deleted_characters": [1, 2, 3]}
    bad = plan()
    bad["usage_guard"]["candidate_count"] = 99
    with pytest.raises(ValueError, match="candidate_count"):
        materialize.build_final_overrides(base, proposal, bad)


def test_missing_usage_guard_is_rejected():
    base = {"deleted_characters": []}
    proposal = {"deleted_characters": [1, 2, 3]}
    bad = plan()
    bad["usage_guard"]["applied"] = False
    with pytest.raises(ValueError, match="usage guard"):
        materialize.build_final_overrides(base, proposal, bad)


def test_plan_must_stay_pre_application():
    base = {"deleted_characters": []}
    proposal = {"deleted_characters": [1, 2, 3]}
    bad = plan()
    bad["apply_ready"] = True
    with pytest.raises(ValueError, match="apply_ready=false"):
        materialize.build_final_overrides(base, proposal, bad)


def test_extra_preview_deletion_not_explained_by_usage_partition_is_rejected():
    base = {"deleted_characters": []}
    proposal = {"deleted_characters": [1, 2, 3, 4]}
    with pytest.raises(ValueError, match="restaurados"):
        materialize.build_final_overrides(base, proposal, plan())
