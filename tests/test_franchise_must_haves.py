from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


must_haves = load_module(
    "ensure_franchise_must_haves",
    "scripts/ensure_franchise_must_haves.py",
)
builder = load_module(
    "build_catalog_cleanup_overrides_extra_tests",
    "scripts/build_catalog_cleanup_overrides.py",
)


def _payload():
    return {
        "summary": {"definite_character_add_candidates": 2},
        "character_add_candidates": [
            {
                "id": 17,
                "name": "Naruto Uzumaki",
                "decision": "ADD",
                "target_anime_id": 20,
                "target_anime": "Naruto",
                "favourites": 20_000,
            },
            {
                "id": 3149,
                "name": "Tobi",
                "decision": "ADD",
                "target_anime_id": 20,
                "target_anime": "Naruto",
                "favourites": 3_000,
            },
        ],
        "review_character_add_candidates": [],
    }


def _empty_overrides():
    return {
        "deleted_characters": [],
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


def test_madara_is_inserted_when_missing():
    fetched = {
        53901: {
            "id": 53901,
            "favourites": 5_123,
            "siteUrl": "https://anilist.co/character/53901/Madara-Uchiha",
            "name": {"full": "Madara Uchiha"},
            "image": {"large": "https://example.com/madara.jpg"},
        }
    }
    out, stats = must_haves.apply_must_haves(_payload(), fetched)
    madara = next(row for row in out["character_add_candidates"] if int(row["id"]) == 53901)
    assert madara["name"] == "Madara Uchiha"
    assert int(madara["target_anime_id"]) == 20
    assert madara["decision"] == "ADD"
    assert madara["catalog_reason"] == "must_have_major_character"
    assert stats == {"inserted": 1, "ids": [53901]}


def test_madara_is_not_duplicated_if_already_present():
    payload = _payload()
    payload["character_add_candidates"].append(
        {
            "id": 53901,
            "name": "Madara Uchiha",
            "decision": "ADD",
            "target_anime_id": 20,
            "target_anime": "Naruto",
            "favourites": 5_000,
        }
    )
    out, stats = must_haves.apply_must_haves(payload, {})
    madaras = [row for row in out["character_add_candidates"] if int(row.get("id") or 0) == 53901]
    assert len(madaras) == 1
    assert stats == {"inserted": 0, "ids": []}


def test_obito_and_nagato_are_aliases_not_duplicate_ids():
    out, _ = must_haves.apply_must_haves(_payload(), {})
    aliases = out["identity_aliases"]
    assert "Obito Uchiha" in aliases["3149"]
    assert "Nagato" in aliases["3180"]
    assert all(int(row.get("id") or 0) not in {0} for row in out["character_add_candidates"])
    # A política representa Obito pelo ID 3149 (Tobi) e Nagato/Pain pelo 3180;
    # não cria um segundo ID artificial para nenhum deles.
    assert len({int(row["id"]) for row in out["character_add_candidates"]}) == len(out["character_add_candidates"])


def test_builder_adds_important_character_missing_from_existing_anime():
    audit = {
        "retire_ids": [],
        "add_candidates": [
            {
                "id": 40881,
                "name": "Mikasa Ackerman",
                "decision": "ADD",
                "anime_id": 16498,
                "anime": "Attack on Titan",
                "role": "MAIN",
                "favourites": 28688,
                "anilist_image": "https://example.com/mikasa.jpg",
            }
        ],
    }
    proposal, stats = builder.build_proposal(
        _empty_overrides(),
        audit,
        {"missing_franchises": [], "character_add_candidates": []},
        base_anime_ids={16498},
        base_character_ids={1, 2, 3},
    )
    mikasa = next(row for row in proposal["custom_characters"] if int(row["id"]) == 40881)
    assert int(mikasa["anime_id"]) == 16498
    assert mikasa["_catalog_source"] == "current_anime_audit_v1"
    assert mikasa["_image_status"] == "temporary_anilist_reference"
    assert stats["audit_characters_added"] == 1
    assert stats["franchise_characters_added"] == 0
    assert stats["new_characters_added"] == 1


def test_builder_deduplicates_same_character_across_audit_and_franchise_sources():
    audit = {
        "retire_ids": [],
        "add_candidates": [
            {
                "id": 40881,
                "name": "Mikasa Ackerman",
                "decision": "ADD",
                "anime_id": 16498,
                "anime": "Attack on Titan",
                "role": "MAIN",
                "favourites": 28688,
                "anilist_image": "https://example.com/mikasa.jpg",
            }
        ],
    }
    franchise = {
        "missing_franchises": [],
        "character_add_candidates": [
            {
                "id": 40881,
                "name": "Mikasa Ackerman",
                "decision": "ADD",
                "target_anime_id": 16498,
                "target_anime": "Attack on Titan",
                "role": "MAIN",
                "favourites": 28688,
                "anilist_image_reference": "https://example.com/mikasa2.jpg",
            }
        ],
    }
    proposal, stats = builder.build_proposal(
        _empty_overrides(),
        audit,
        franchise,
        base_anime_ids={16498},
        base_character_ids=set(),
    )
    rows = [row for row in proposal["custom_characters"] if int(row.get("id") or 0) == 40881]
    assert len(rows) == 1
    assert stats["audit_characters_added"] == 1
    assert stats["franchise_characters_added"] == 0
    assert stats["new_characters_added"] == 1
