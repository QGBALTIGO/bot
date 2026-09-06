from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "resolve_catalog_reviews_final",
    ROOT / "scripts" / "resolve_catalog_reviews_final.py",
)
final = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(final)


def decide(*, roles={"SUPPORTING"}, favourites=0, rank=None, media_count=1):
    return final.resolve_final_review(
        roles=set(roles),
        favourites=favourites,
        relevance_rank=rank,
        media_count=media_count,
    )[0]


def test_ten_favourites_is_keep():
    assert decide(favourites=10, rank=500) == "KEEP"


def test_relevant_top_ten_supporting_is_keep_with_some_interest():
    assert decide(favourites=5, rank=10) == "KEEP"


def test_recurring_character_is_protected():
    assert decide(favourites=4, rank=40, media_count=2) == "KEEP"
    assert decide(favourites=2, rank=80, media_count=3) == "KEEP"


def test_single_appearance_very_low_interest_can_retire():
    assert decide(favourites=1, rank=11, media_count=1) == "RETIRE"
    assert decide(favourites=2, rank=16, media_count=1) == "RETIRE"
    assert decide(favourites=3, rank=31, media_count=1) == "RETIRE"


def test_low_interest_recurring_character_is_not_retired_by_single_appearance_rules():
    assert decide(favourites=1, rank=40, media_count=2) == "REVIEW"


def test_background_with_nontrivial_interest_stays_review():
    assert decide(roles={"BACKGROUND"}, favourites=9, rank=50) == "REVIEW"


def test_main_is_always_keep():
    assert decide(roles={"MAIN"}, favourites=0, rank=999) == "KEEP"


def test_global_resolution_never_downgrades_existing_keep():
    audit = {
        "anime_reports": {
            "1": {
                "current_characters": [
                    {"id": 1, "name": "Protected", "role": "SUPPORTING", "favourites": 0, "relevance_rank": 999, "decision": "KEEP", "decision_reason": "already_keep"},
                    {"id": 2, "name": "Weak", "role": "SUPPORTING", "favourites": 1, "relevance_rank": 20, "decision": "REVIEW", "decision_reason": "ambiguous"},
                ]
            }
        },
        "global_decisions": {
            "1": {"decision": "KEEP", "appearances": []},
            "2": {"decision": "REVIEW", "appearances": []},
        },
        "summary": {"definite_add_candidates": 0},
    }
    resolved, stats = final.resolve_final_reviews(audit)
    assert 1 in resolved["keep_ids"]
    assert 2 in resolved["retire_ids"]
    assert stats["review_to_retire_final"] == 1
