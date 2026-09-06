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


resolver = load_module("resolve_catalog_reviews", "scripts/resolve_catalog_reviews.py")


def test_clear_known_supporting_character_is_kept():
    decision, _ = resolver.resolve_review_decision(
        role="SUPPORTING",
        favourites=15,
        relevance_rank=200,
    )
    assert decision == "KEEP"


def test_early_supporting_character_is_kept_even_with_low_favourites():
    decision, _ = resolver.resolve_review_decision(
        role="SUPPORTING",
        favourites=1,
        relevance_rank=5,
    )
    assert decision == "KEEP"


def test_deep_low_interest_supporting_character_is_retired():
    decision, _ = resolver.resolve_review_decision(
        role="SUPPORTING",
        favourites=2,
        relevance_rank=90,
    )
    assert decision == "RETIRE"


def test_ten_favourites_is_never_auto_retired():
    decision, _ = resolver.resolve_review_decision(
        role="SUPPORTING",
        favourites=10,
        relevance_rank=700,
    )
    assert decision == "REVIEW"


def test_low_interest_background_character_is_retired():
    decision, _ = resolver.resolve_review_decision(
        role="BACKGROUND",
        favourites=5,
        relevance_rank=30,
    )
    assert decision == "RETIRE"


def test_high_interest_background_character_is_kept():
    decision, _ = resolver.resolve_review_decision(
        role="BACKGROUND",
        favourites=15,
        relevance_rank=100,
    )
    assert decision == "KEEP"


def test_existing_keep_is_never_downgraded():
    audit = {
        "version": 3,
        "summary": {"definite_add_candidates": 0},
        "global_decisions": {"1": {"decision": "KEEP", "appearances": [{"anime_id": 10, "decision": "KEEP"}]}},
        "anime_reports": {
            "10": {
                "current_characters": [
                    {
                        "id": 1,
                        "name": "Protected by prior decision",
                        "role": "SUPPORTING",
                        "favourites": 0,
                        "relevance_rank": 999,
                        "decision": "KEEP",
                        "decision_reason": "protected_manual",
                    }
                ]
            }
        },
    }
    out, stats = resolver.resolve_reviews(audit)
    assert out["global_decisions"]["1"]["decision"] == "KEEP"
    assert out["keep_ids"] == [1]
    assert out["retire_ids"] == []
    assert stats == {"review_to_keep": 0, "review_to_retire": 0, "review_remaining": 0}


def test_global_review_wins_over_retire_when_character_has_multiple_appearances():
    audit = {
        "version": 3,
        "summary": {"definite_add_candidates": 0},
        "global_decisions": {},
        "anime_reports": {
            "10": {
                "current_characters": [
                    {
                        "id": 50,
                        "name": "Shared Character",
                        "role": "SUPPORTING",
                        "favourites": 1,
                        "relevance_rank": 80,
                        "decision": "REVIEW",
                    }
                ]
            },
            "11": {
                "current_characters": [
                    {
                        "id": 50,
                        "name": "Shared Character",
                        "role": "SUPPORTING",
                        "favourites": 10,
                        "relevance_rank": 500,
                        "decision": "REVIEW",
                    }
                ]
            },
        },
    }
    out, _ = resolver.resolve_reviews(audit)
    assert out["global_decisions"]["50"]["decision"] == "REVIEW"
    assert 50 in out["review_ids"]
    assert 50 not in out["retire_ids"]
