from pathlib import Path
import importlib.util
import sys

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "curate_zerochan_characters.py"
spec = importlib.util.spec_from_file_location("zerochan_curator", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def character(name="Makima", anime="Chainsaw Man", tag="Makima"):
    return {"id": 137080, "name": name, "anime": anime, "zerochan_tag": tag}


def detail(**updates):
    data = {
        "id": 123,
        "primary": "Makima",
        "tags": ["Makima", "Chainsaw Man", "Solo", "Official Art", "Female"],
        "anime": "Chainsaw Man",
        "width": 1800,
        "height": 2700,
        "fav": 250,
        "full": "https://static.zerochan.net/Makima.full.123.png",
        "source": "https://example.com/original",
    }
    data.update(updates)
    return data


def test_official_solo_portrait_is_approved():
    candidate, status = mod.evaluate_candidate(detail(), character())
    assert status == "approved"
    assert candidate is not None
    assert candidate.official is True
    assert candidate.solo is True
    assert candidate.score >= mod.MIN_SCORE


def test_group_is_rejected_even_if_tags_match():
    candidate, status = mod.evaluate_candidate(
        detail(tags=["Makima", "Chainsaw Man", "Duo", "Official Art"]), character()
    )
    assert candidate is None
    assert status.startswith("hard_tag:")


def test_wrong_primary_character_is_rejected():
    candidate, status = mod.evaluate_candidate(detail(primary="Power"), character())
    assert candidate is None
    assert status == "primary_mismatch"


def test_wrong_series_is_rejected():
    candidate, status = mod.evaluate_candidate(
        detail(tags=["Makima", "Solo", "Official Art", "ONE PIECE"], anime="ONE PIECE"), character()
    )
    assert candidate is None
    assert status == "series_mismatch"


def test_low_resolution_is_rejected():
    candidate, status = mod.evaluate_candidate(detail(width=500, height=900), character())
    assert candidate is None
    assert status == "resolution"


def test_fanart_can_pass_but_scores_lower_than_official():
    official, _ = mod.evaluate_candidate(detail(), character())
    fanart, status = mod.evaluate_candidate(
        detail(tags=["Makima", "Chainsaw Man", "Solo", "Fanart"], id=124), character()
    )
    assert status == "approved"
    assert official is not None and fanart is not None
    assert fanart.fanart is True
    assert official.score > fanart.score
