from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "normalize_must_have_targets",
    ROOT / "scripts" / "normalize_must_have_targets.py",
)
normalize = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(normalize)


def test_witch_hat_candidates_are_remapped_from_season_two_to_canonical_anime():
    payload = {
        "summary": {},
        "character_add_candidates": [
            {"id": 129840, "name": "Coco", "decision": "ADD", "target_anime_id": 213702, "target_anime": "Witch Hat Atelier Season 2", "favourites": 2000},
            {"id": 129841, "name": "Qifrey", "decision": "ADD", "target_anime_id": 213702, "target_anime": "Witch Hat Atelier Season 2", "favourites": 3000},
        ],
        "review_character_add_candidates": [],
    }
    out, stats = normalize.normalize_targets(payload)
    rows = {int(row["id"]): row for row in out["character_add_candidates"]}
    assert rows[129840]["target_anime_id"] == 147105
    assert rows[129841]["target_anime_id"] == 147105
    assert rows[129840]["target_anime"] == "Witch Hat Atelier"
    assert rows[129840]["franchise_status"] == "MUST_HAVE_FRANCHISE"
    assert stats["remapped"] == 2


def test_review_core_character_is_promoted_to_add_and_deduplicated():
    payload = {
        "summary": {},
        "character_add_candidates": [
            {"id": 129838, "name": "Richeh", "decision": "ADD", "target_anime_id": 213702, "favourites": 1000},
        ],
        "review_character_add_candidates": [
            {"id": 129838, "name": "Richeh", "decision": "REVIEW", "target_anime_id": 213702, "favourites": 1000},
            {"id": 129839, "name": "Tetia", "decision": "REVIEW", "target_anime_id": 213702, "favourites": 700},
        ],
    }
    out, stats = normalize.normalize_targets(payload)
    ids = [int(row["id"]) for row in out["character_add_candidates"]]
    assert ids.count(129838) == 1
    assert 129839 in ids
    assert all(int(row.get("id") or 0) != 129839 for row in out["review_character_add_candidates"])
    assert stats["promoted"] >= 1


def test_unrelated_candidates_are_untouched():
    payload = {
        "summary": {},
        "character_add_candidates": [
            {"id": 53901, "name": "Madara Uchiha", "decision": "ADD", "target_anime_id": 20, "target_anime": "Naruto", "favourites": 4983},
        ],
        "review_character_add_candidates": [],
    }
    out, stats = normalize.normalize_targets(payload)
    row = out["character_add_candidates"][0]
    assert row["target_anime_id"] == 20
    assert row["target_anime"] == "Naruto"
    assert stats["remapped"] == 0
