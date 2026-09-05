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
