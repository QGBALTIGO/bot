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


builder = load_module(
    "build_catalog_cleanup_overrides_identity_test",
    "scripts/build_catalog_cleanup_overrides.py",
)


def empty_overrides():
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


def test_builder_applies_searchable_name_to_consolidated_identity():
    franchise = {
        "missing_franchises": [
            {
                "status": "MISSING_FRANCHISE",
                "target_anime_id": 20,
                "target_anime": "Naruto",
                "missing_popular_media": [
                    {"anime_id": 20, "popularity_rank": 12, "popularity": 723094}
                ],
            }
        ],
        "character_add_candidates": [
            {
                "id": 3149,
                "name": "Tobi",
                "decision": "ADD",
                "target_anime_id": 20,
                "target_anime": "Naruto",
                "role": "SUPPORTING",
                "favourites": 3040,
                "anilist_image_reference": "https://example.com/tobi.jpg",
            },
            {
                "id": 3180,
                "name": "Pain",
                "decision": "ADD",
                "target_anime_id": 20,
                "target_anime": "Naruto",
                "role": "SUPPORTING",
                "favourites": 5641,
                "anilist_image_reference": "https://example.com/pain.jpg",
            },
        ],
        "identity_display_overrides": {
            "3149": "Obito Uchiha (Tobi)",
            "3180": "Nagato (Pain)",
        },
    }
    proposal, stats = builder.build_proposal(
        empty_overrides(),
        {"retire_ids": [], "add_candidates": []},
        franchise,
        base_anime_ids=set(),
        base_character_ids=set(),
    )
    assert proposal["character_name_overrides"]["3149"] == "Obito Uchiha (Tobi)"
    assert proposal["character_name_overrides"]["3180"] == "Nagato (Pain)"
    assert stats["identity_display_overrides_applied"] == {
        "3149": "Obito Uchiha (Tobi)",
        "3180": "Nagato (Pain)",
    }
    assert len({int(row["id"]) for row in proposal["custom_characters"]}) == 2


def test_existing_manual_name_override_has_priority():
    overrides = empty_overrides()
    overrides["character_name_overrides"] = {"3149": "Meu nome manual"}
    franchise = {
        "missing_franchises": [],
        "character_add_candidates": [],
        "identity_display_overrides": {"3149": "Obito Uchiha (Tobi)"},
    }
    proposal, stats = builder.build_proposal(
        overrides,
        {"retire_ids": [], "add_candidates": []},
        franchise,
        base_anime_ids={20},
        base_character_ids={3149},
    )
    assert proposal["character_name_overrides"]["3149"] == "Meu nome manual"
    assert stats["identity_display_overrides_applied"] == {}
