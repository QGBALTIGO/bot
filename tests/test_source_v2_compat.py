from __future__ import annotations

from webapp_services.source_v2_compat import (
    paginate_items,
    source_character_to_seal,
)


def test_character_mapping_preserves_source_character_id() -> None:
    mapped = source_character_to_seal(
        {
            "character_id": 321,
            "quantity": 2,
            "name": "Monkey D. Luffy",
            "anime": "One Piece",
            "image": "https://cdn.example/luffy.jpg",
        }
    )

    assert mapped["id"] == "321"
    assert mapped["count"] == 2
    assert mapped["owned"] is True
    assert mapped["img_url"] == "https://cdn.example/luffy.jpg"


def test_unowned_gallery_character_keeps_same_identity() -> None:
    mapped = source_character_to_seal(
        {
            "character_id": 321,
            "quantity": 0,
            "name": "Monkey D. Luffy",
            "anime": "One Piece",
            "image": "https://cdn.example/luffy.jpg",
        }
    )

    assert mapped["id"] == "321"
    assert mapped["count"] == 0
    assert mapped["owned"] is False


def test_paginate_items_supports_search_rarity_and_pages() -> None:
    items = [
        {"id": "1", "name": "Luffy", "anime": "One Piece", "rarity": "Standard"},
        {"id": "2", "name": "Zoro", "anime": "One Piece", "rarity": "Standard"},
        {"id": "3", "name": "Rem", "anime": "Re:Zero", "rarity": "Standard"},
    ]

    filtered = paginate_items(items, page=1, limit=10, search="one piece", rarity="standard")
    assert filtered["total"] == 2
    assert [row["id"] for row in filtered["items"]] == ["1", "2"]

    page_two = paginate_items(items, page=2, limit=2)
    assert page_two["total"] == 3
    assert [row["id"] for row in page_two["items"]] == ["3"]


def test_paginate_items_clamps_limit() -> None:
    items = [{"id": str(i), "name": f"Char {i}", "anime": "A", "rarity": "Standard"} for i in range(150)]
    result = paginate_items(items, page=1, limit=999)
    assert result["limit"] == 100
    assert len(result["items"]) == 100
