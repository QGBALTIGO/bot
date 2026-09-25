from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "consolidate_catalog_franchises",
    ROOT / "scripts" / "consolidate_catalog_franchises.py",
)
consolidate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(consolidate)

# This assertion suite is also used as a deliberate canonical full-audit trigger.

def proposal():
    return {
        "deleted_characters": [99],
        "deleted_animes": [],
        "custom_animes": [],
        "custom_characters": [
            {"id": 5000, "anime_id": 1, "anime": "A", "name": "Existing", "image": "x"},
        ],
        "character_name_overrides": {},
        "anime_name_overrides": {},
    }


def dataset():
    return {
        "items": [
            {"anime_id": 1, "anime": "Fate/stay night", "characters": [{"id": 1, "name": "Stay", "image": "stay.jpg"}]},
            {"anime_id": 2, "anime": "Fate/Zero", "characters": [{"id": 2, "name": "Zero Keep", "image": "zero.jpg"}, {"id": 3, "name": "Zero Retire", "image": "retire.jpg"}]},
            {"anime_id": 3, "anime": "Empty Movie", "characters": [{"id": 4, "name": "Background", "image": "bg.jpg"}]},
            {"anime_id": 4, "anime": "Receives New Character", "characters": [{"id": 5, "name": "Old Retire", "image": "old.jpg"}]},
        ]
    }


def audit():
    return {
        "anime_reports": {
            "1": {"current_count": 1, "counts": {"KEEP": 1, "REVIEW": 0, "RETIRE": 0}, "current_characters": [{"id": 1, "decision": "KEEP"}]},
            "2": {"current_count": 2, "counts": {"KEEP": 1, "REVIEW": 0, "RETIRE": 1}, "current_characters": [{"id": 2, "decision": "KEEP"}, {"id": 3, "decision": "RETIRE"}]},
            "3": {"current_count": 1, "counts": {"KEEP": 0, "REVIEW": 0, "RETIRE": 1}, "current_characters": [{"id": 4, "decision": "RETIRE"}]},
            "4": {"current_count": 1, "counts": {"KEEP": 0, "REVIEW": 0, "RETIRE": 1}, "current_characters": [{"id": 5, "decision": "RETIRE"}]},
        }
    }


def franchise():
    return {"duplicate_current_franchises": [{"current_anime_ids": [1, 2], "recommended_target_anime_id": 1, "target_anime": "Fate/stay night"}]}


def test_duplicate_component_is_deleted_and_retained_character_is_moved():
    result, stats = consolidate.consolidate(proposal(), audit(), franchise(), dataset())
    assert 2 in result["deleted_animes"]
    assert result["anime_name_overrides"]["1"] == "Fate/stay night"
    moved = next(row for row in result["custom_characters"] if int(row["id"]) == 2)
    assert moved["anime_id"] == 1
    assert moved["name"] == "Zero Keep"
    assert moved["image"] == "zero.jpg"
    assert all(int(row.get("id") or 0) != 3 for row in result["custom_characters"])
    assert stats["retained_characters_moved"] == 1


def test_empty_category_is_deleted_but_category_receiving_custom_character_survives():
    p = proposal()
    p["custom_characters"].append({"id": 50, "anime_id": 4, "anime": "Receives New Character", "name": "New", "image": "new.jpg"})
    result, stats = consolidate.consolidate(p, audit(), {"duplicate_current_franchises": []}, dataset())
    assert 3 in result["deleted_animes"]
    assert 4 not in result["deleted_animes"]
    assert stats["empty_categories_deleted"] == 1


def test_incomplete_or_missing_audit_never_deletes_or_consolidates_those_categories():
    au = audit()
    au["anime_reports"].pop("3")
    au["anime_reports"]["2"]["current_count"] = 3  # only two rows => partial
    result, stats = consolidate.consolidate(proposal(), au, franchise(), dataset())
    assert 2 not in result["deleted_animes"]
    assert 3 not in result["deleted_animes"]
    assert 4 in result["deleted_animes"]  # unrelated category still has a complete all-RETIRE audit
    assert stats["duplicate_categories_consolidated"] == 0
    assert stats["duplicate_anime_ids_skipped_incomplete_audit"] == [2]
    assert stats["empty_categories_deleted"] == 1
    assert stats["empty_anime_ids_deleted"] == [4]
    assert stats["fail_closed_on_incomplete_audit"] is True


def test_production_canonical_names_are_generalized():
    p = proposal()
    ds = {
        "items": [
            {"anime_id": 356, "anime": "Fate/stay night", "characters": []},
            {"anime_id": 10087, "anime": "Fate/Zero", "characters": [{"id": 16021, "name": "Iskandar", "image": "iskandar.jpg"}]},
            {"anime_id": 113415, "anime": "JUJUTSU KAISEN", "characters": []},
            {"anime_id": 172463, "anime": "JUJUTSU KAISEN Season 3", "characters": [{"id": 248818, "name": "Hiromi Higuruma", "image": "h.jpg"}]},
        ]
    }
    au = {
        "anime_reports": {
            "356": {"current_count": 1, "counts": {"KEEP": 1}, "current_characters": [{"id": 1, "decision": "KEEP"}]},
            "10087": {"current_count": 1, "counts": {"KEEP": 1}, "current_characters": [{"id": 16021, "decision": "KEEP"}]},
            "113415": {"current_count": 1, "counts": {"KEEP": 1}, "current_characters": [{"id": 2, "decision": "KEEP"}]},
            "172463": {"current_count": 1, "counts": {"KEEP": 1}, "current_characters": [{"id": 248818, "decision": "KEEP"}]},
        }
    }
    fr = {
        "duplicate_current_franchises": [
            {"current_anime_ids": [356,10087], "recommended_target_anime_id": 356, "target_anime": "Fate/stay night"},
            {"current_anime_ids": [113415,172463], "recommended_target_anime_id": 113415, "target_anime": "Jujutsu Kaisen"},
        ]
    }
    result, stats = consolidate.consolidate(p, au, fr, ds)
    assert result["anime_name_overrides"]["356"] == "Fate"
    assert result["anime_name_overrides"]["113415"] == "Jujutsu Kaisen"
    assert {10087,172463}.issubset(set(result["deleted_animes"]))
    by_id={int(row["id"]):row for row in result["custom_characters"]}
    assert by_id[16021]["anime_id"] == 356
    assert by_id[248818]["anime_id"] == 113415
    assert stats["duplicate_categories_consolidated"] == 2
