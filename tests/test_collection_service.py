from __future__ import annotations

from webapp_services.collection import (
    collection_animes_from_snapshot,
    collection_cards_from_snapshot,
    collection_detail_from_snapshot,
    collection_snapshot,
)


def _cards_data() -> dict:
    char_1 = {
        "id": 1,
        "name": "Beta",
        "anime_id": 10,
        "anime": "Anime A",
        "image": "https://img.anili.st/character/1",
    }
    char_2 = {
        "id": 2,
        "name": "Alpha",
        "anime_id": 10,
        "anime": "Anime A",
        "image": "https://img.anili.st/character/2",
    }
    char_3 = {
        "id": 3,
        "name": "Gamma",
        "anime_id": 20,
        "anime": "Anime B",
        "image": "https://img.anili.st/character/3",
    }
    return {
        "characters_by_id": {1: char_1, 2: char_2, 3: char_3},
        "characters_by_anime": {
            10: [char_1, char_2],
            20: [char_3],
        },
        "animes_by_id": {
            10: {
                "anime": "Anime A",
                "cover_image": "https://img.anili.st/media/10",
                "banner_image": "https://img.anili.st/media/10",
            },
            20: {
                "anime": "Anime B",
                "cover_image": "https://img.anili.st/media/20",
                "banner_image": "https://img.anili.st/media/20",
            },
        },
        "subcategories": {
            "Hero": [{"id": 1}],
            "Duplicate ignored": [{"id": 1}],
            "Support": [{"id": 2}],
            "": [{"id": 3}],
        },
    }


def test_collection_snapshot_aggregates_duplicates_and_ignores_invalid_rows() -> None:
    data = _cards_data()
    received_ids: list[int] = []

    snapshot_data, quantities, subcategories = collection_snapshot(
        77,
        load_collection=lambda uid: received_ids.append(uid) or [
            {"character_id": 1, "quantity": 2},
            {"character_id": "1", "quantity": "3"},
            {"character_id": 2, "quantity": 0},
            {"character_id": 3, "quantity": -1},
            {"character_id": 0, "quantity": 8},
            {"character_id": "bad", "quantity": 1},
        ],
        load_cards_data=lambda: data,
    )

    assert received_ids == [77]
    assert snapshot_data is data
    assert quantities == {1: 5}
    assert subcategories == {1: "Hero", 2: "Support"}


def test_collection_cards_preserve_quantity_metadata_and_sorting() -> None:
    data = _cards_data()
    items = collection_cards_from_snapshot(
        data,
        {3: 1, 1: 2, 2: 4, 999: 3},
        {1: "Hero", 2: "Support"},
    )

    assert [item["character_id"] for item in items] == [2, 1, 3]
    assert items[0] == {
        "character_id": 2,
        "quantity": 4,
        "name": "Alpha",
        "anime_id": 10,
        "anime": "Anime A",
        "image": "https://img.anili.st/character/2",
        "subcategory": "Support",
    }
    assert items[1]["quantity"] == 2
    assert items[2]["subcategory"] == ""


def test_collection_animes_calculate_completion_from_unique_owned_cards() -> None:
    data = _cards_data()
    items = collection_animes_from_snapshot(data, {1: 5, 3: 2})

    assert [item["anime_id"] for item in items] == [10, 20]
    assert items[0]["owned_count"] == 1
    assert items[0]["total_count"] == 2
    assert items[0]["missing_count"] == 1
    assert items[0]["completion_pct"] == 50
    assert items[1]["owned_count"] == 1
    assert items[1]["total_count"] == 1
    assert items[1]["missing_count"] == 0
    assert items[1]["completion_pct"] == 100


def test_collection_detail_preserves_owned_missing_gallery_modes() -> None:
    data = _cards_data()
    quantities = {1: 2}
    subcategories = {1: "Hero", 2: "Support"}

    owned = collection_detail_from_snapshot(data, quantities, subcategories, 10, "owned")
    missing = collection_detail_from_snapshot(data, quantities, subcategories, 10, "missing")
    gallery = collection_detail_from_snapshot(data, quantities, subcategories, 10, "gallery")
    fallback = collection_detail_from_snapshot(data, quantities, subcategories, 10, "invalid")

    assert owned is not None
    assert missing is not None
    assert gallery is not None
    assert fallback is not None

    assert owned["mode"] == "owned"
    assert [item["id"] for item in owned["items"]] == [1]
    assert owned["items"][0]["quantity"] == 2
    assert owned["items"][0]["owned"] is True

    assert missing["mode"] == "missing"
    assert [item["id"] for item in missing["items"]] == [2]
    assert missing["items"][0]["owned"] is False

    assert gallery["mode"] == "gallery"
    assert [item["id"] for item in gallery["items"]] == [2, 1]
    assert gallery["owned_count"] == 1
    assert gallery["total_count"] == 2
    assert gallery["missing_count"] == 1
    assert gallery["completion_pct"] == 50

    assert fallback["mode"] == "owned"
    assert [item["id"] for item in fallback["items"]] == [1]
    assert collection_detail_from_snapshot(data, quantities, subcategories, 999, "owned") is None
