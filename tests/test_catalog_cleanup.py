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


audit = load_module("audit_character_catalog", "scripts/audit_character_catalog.py")
retire = load_module("apply_catalog_retirements", "scripts/apply_catalog_retirements.py")


def test_main_character_is_kept_even_with_zero_favourites():
    media = {
        "popularity": 10_000,
        "characters": [
            {"id": 1, "name": "Hero", "role": "MAIN", "favourites": 0, "relevance_rank": 100, "importance_score": audit.importance_score("MAIN", 0, 100)},
        ],
    }
    result = audit.classify_live_characters(media, {1})
    assert result["characters"][1]["decision"] == "KEEP"


def test_obscure_background_character_is_retired():
    characters = []
    for idx in range(1, 81):
        role = "SUPPORTING" if idx <= 45 else "BACKGROUND"
        favourites = max(0, 300 - idx * 5)
        characters.append({
            "id": idx,
            "name": f"Character {idx}",
            "role": role,
            "favourites": favourites,
            "relevance_rank": idx,
            "importance_score": audit.importance_score(role, favourites, idx),
        })
    media = {"popularity": 5_000, "characters": characters}
    result = audit.classify_live_characters(media, set(range(1, 81)))
    assert result["characters"][80]["decision"] == "RETIRE"


def test_missing_main_character_is_definite_add():
    media = {
        "popularity": 100_000,
        "characters": [
            {"id": 500, "name": "Missing Main", "role": "MAIN", "favourites": 3, "relevance_rank": 1, "importance_score": audit.importance_score("MAIN", 3, 1)},
        ],
    }
    result = audit.classify_live_characters(media, set())
    assert result["add_candidates"][0]["id"] == 500
    assert result["add_candidates"][0]["decision"] == "ADD"


def test_manual_override_is_protected_globally():
    overrides = {
        "custom_characters": [{"id": 10, "anime_id": 20, "name": "Manual"}],
        "character_image_overrides": {"11": "https://example.com/a.jpg"},
        "character_name_overrides": {"12": "Alias"},
        "subcategories": {"Evento": [13]},
    }
    assert audit.protected_ids(overrides) == {10, 11, 12, 13}


def test_compensation_is_one_coin_per_removed_copy():
    rows = [
        {"user_id": 1, "character_id": 100, "quantity": 4},
        {"user_id": 1, "character_id": 101, "quantity": 2},
        {"user_id": 2, "character_id": 100, "quantity": 1},
    ]
    summary = retire.summarize_rows(rows)
    assert summary["affected_users"] == 2
    assert summary["removed_copies"] == 7
    assert summary["coins_to_award"] == 7


def test_retirement_hash_is_order_independent():
    assert retire.audit_hash([3, 1, 2]) == retire.audit_hash([2, 3, 1])
