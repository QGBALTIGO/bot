from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


guard = _load_module(
    "guard_catalog_retirements_by_usage",
    "scripts/guard_catalog_retirements_by_usage.py",
)
manifest_loader = _load_module(
    "catalog_impact_manifest",
    "utils/catalog_impact_manifest.py",
)
runner = _load_module(
    "run_catalog_impact_readonly",
    "scripts/run_catalog_impact_readonly.py",
)


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


def test_compact_candidate_manifest_is_integrity_checked():
    manifest = manifest_loader.load_candidate_manifest(
        ROOT / "data" / "catalog_cleanup_retire_candidates.v1.json"
    )
    assert manifest["schema_version"] == 3
    assert manifest["source_audit_version"] == 5
    assert manifest["candidate_count"] == 4311
    assert len(manifest["candidate_ids"]) == 4311
    assert manifest["candidate_ids_sha256"] == (
        "597fbd838e4ba01be19209c663408d992ccb9dc5b3a947fd69752804d7895dbe"
    )
    assert manifest_loader.candidate_ids_hash(manifest["candidate_ids"]) == manifest["candidate_ids_sha256"]
    assert manifest["candidate_ids"] == sorted(set(manifest["candidate_ids"]))
    assert manifest["policy"]["owner_review_threshold"] == 10
    assert manifest["policy"]["copy_review_threshold"] == 20


def test_manifest_hash_tampering_is_rejected():
    manifest = manifest_loader.load_candidate_manifest(
        ROOT / "data" / "catalog_cleanup_retire_candidates.v1.json"
    )
    bad = {
        key: value
        for key, value in manifest.items()
        if key != "candidate_ids"
    }
    bad["candidate_ids_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        manifest_loader.decode_candidate_manifest(bad)


def test_live_report_uses_exact_distinct_user_summary_after_guard():
    usage = [
        {"character_id": 1, "owners": 12, "copies": 12},
        {"character_id": 2, "owners": 2, "copies": 25},
        {"character_id": 3, "owners": 2, "copies": 4},
    ]
    report = guard.build_live_impact_report(
        {1, 2, 3},
        usage,
        before_summary={
            "affected_users": 13,
            "copies": 41,
            "owner_character_links": 16,
        },
        after_summary={
            "affected_users": 2,
            "copies": 4,
            "owner_character_links": 2,
        },
        labels={
            1: {"name": "Community Favorite", "anime": "A"},
            2: {"name": "Many Copies", "anime": "B"},
            3: {"name": "Low Impact", "anime": "C"},
        },
        owner_threshold=10,
        copy_threshold=20,
    )
    assert report["moved_to_review_count"] == 2
    assert report["final_retire_count"] == 1
    assert report["final_retire_ids"] == [3]
    assert report["after_guard"]["affected_users"] == 2
    assert report["coins_required_after_guard"] == 4
    assert [row["character_id"] for row in report["moved_to_review"]] == [1, 2]


def test_one_shot_runner_keeps_manifest_payload_private_and_summary_aggregate_only():
    manifest = manifest_loader.load_candidate_manifest(
        ROOT / "data" / "catalog_cleanup_retire_candidates.v1.json"
    )
    public = runner.public_manifest(manifest)
    assert "candidate_ids" not in public
    assert "candidate_ids_payload_chunks" not in public
    assert public["candidate_count"] == 4311

    report = {
        "candidate_count": 4311,
        "moved_to_review_count": 12,
        "final_retire_count": 4299,
        "before_guard": {"affected_users": 30, "copies": 100},
        "after_guard": {"affected_users": 20, "copies": 60},
        "coins_required_after_guard": 60,
        "manifest": public,
    }
    summary = runner.compact_summary(report)
    assert summary["read_only"] is True
    assert summary["coins_required_after_guard"] == 60
    assert summary["candidate_ids_sha256"] == public["candidate_ids_sha256"]
    assert "user_id" not in json_text(summary)


def json_text(value):
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
