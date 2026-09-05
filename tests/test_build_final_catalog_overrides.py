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


builder = _load_module(
    "build_final_catalog_overrides",
    "scripts/build_final_catalog_overrides.py",
)

SOURCE_HASH = "8a6ae15122001229edb8866f56e342af12ae8187203c3e3b33931743e7c0c48d"
FINAL_HASH = "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce"


def base_overrides():
    return {
        "deleted_characters": [50],
        "deleted_animes": [],
        "custom_animes": [],
        "custom_characters": [],
        "character_image_overrides": {},
        "character_name_overrides": {},
        "anime_name_overrides": {},
        "anime_banner_overrides": {},
        "anime_cover_overrides": {},
        "subcategories": {},
    }


def base_audit():
    return {
        "retire_ids": [1, 2, 3],
        "review_ids": [99],
        "add_candidates": [],
    }


def final_plan():
    return {
        "schema": "source.catalog-cleanup.final-plan.v1",
        "apply_ready": False,
        "requires_explicit_operator_approval": True,
        "source_candidate_ids_sha256": SOURCE_HASH,
        "final_retire_ids_sha256": FINAL_HASH,
        "retire_ids": [3],
        "review_ids": [1, 2, 99],
        "usage_guard": {"applied": True},
        "safety": {
            "usage_guard_applied": True,
            "database_mutated": False,
            "catalog_mutated": False,
        },
    }


def test_final_overrides_only_disable_post_usage_guard_retirements():
    proposal, stats = builder.build_final_overrides(
        base_overrides(),
        base_audit(),
        {"missing_franchises": [], "character_add_candidates": []},
        final_plan(),
        base_anime_ids={10},
        base_character_ids={1, 2, 3, 50},
    )
    assert set(proposal["deleted_characters"]) == {3, 50}
    assert 1 not in proposal["deleted_characters"]
    assert 2 not in proposal["deleted_characters"]
    assert stats["source_retire_candidates_before_usage_guard"] == 3
    assert stats["final_retire_candidates"] == 1
    assert stats["saved_by_usage_guard"] == 2
    assert stats["newly_deleted_by_this_cleanup"] == 1
    assert stats["mode"] == "post_usage_guard_final_overrides"


def test_final_overrides_preserve_unrelated_preexisting_deletions():
    overrides = base_overrides()
    overrides["deleted_characters"].append(1)
    proposal, stats = builder.build_final_overrides(
        overrides,
        base_audit(),
        {"missing_franchises": [], "character_add_candidates": []},
        final_plan(),
        base_anime_ids={10},
        base_character_ids={1, 2, 3, 50},
    )
    assert set(proposal["deleted_characters"]) == {1, 3, 50}
    assert stats["baseline_deleted_characters_preserved"] == 2


def test_final_overrides_reject_retire_id_outside_original_audit():
    plan = final_plan()
    plan["retire_ids"] = [3, 777]
    plan["final_retire_ids_sha256"] = builder.ids_hash([3, 777])
    with pytest.raises(ValueError, match="fora da auditoria"):
        builder.build_final_overrides(
            base_overrides(),
            base_audit(),
            {"missing_franchises": [], "character_add_candidates": []},
            plan,
            base_anime_ids={10},
            base_character_ids={1, 2, 3, 50},
        )


def test_final_overrides_reject_wrong_source_snapshot_hash():
    plan = final_plan()
    plan["source_candidate_ids_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash de candidatos"):
        builder.validate_final_plan(base_audit(), plan)


def test_final_overrides_reject_review_retire_overlap():
    plan = final_plan()
    plan["review_ids"] = [1, 2, 3, 99]
    with pytest.raises(ValueError, match="sobrepõe"):
        builder.validate_final_plan(base_audit(), plan)
