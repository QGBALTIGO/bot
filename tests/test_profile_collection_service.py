from __future__ import annotations

from webapp_services.profile_collection import menu_collection_characters


def test_collection_service_filters_missing_and_invalid_rows_and_sorts() -> None:
    rows = [
        {"character_id": 30, "quantity": 2},
        {"character_id": 10, "quantity": 1},
        {"character_id": 20, "quantity": 3},
        {"character_id": 0, "quantity": 5},
        {"character_id": 40, "quantity": 0},
        {"character_id": 50, "quantity": 1},
    ]
    characters = {
        10: {"name": "Beta", "anime": "Anime A", "image": "img-10"},
        20: {"name": "Alpha", "anime": "Anime A", "image": "img-20"},
        30: {"name": "Gamma", "anime": "Anime B", "image": "img-30"},
    }

    result = menu_collection_characters(
        123,
        get_collection=lambda uid: rows if uid == 123 else [],
        get_character=lambda cid: characters.get(cid),
        image_url=lambda value: f"normalized:{value}",
    )

    assert [item["id"] for item in result] == [20, 10, 30]
    assert [item["quantity"] for item in result] == [3, 1, 2]
    assert result[0]["image"] == "normalized:img-20"


def test_collection_service_skips_character_loader_failures() -> None:
    def get_character(_cid: int):
        raise RuntimeError("catalog unavailable")

    result = menu_collection_characters(
        7,
        get_collection=lambda _uid: [{"character_id": 99, "quantity": 1}],
        get_character=get_character,
        image_url=str,
    )

    assert result == []
