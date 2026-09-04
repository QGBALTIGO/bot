from __future__ import annotations

from webapp_services import catalog as catalog_service


def test_catalog_shared_normalizers_preserve_existing_rules() -> None:
    assert catalog_service._normalize_title("  Anime   Name  ") == "Anime Name"
    assert catalog_service._first_letter("Anime") == "A"
    assert catalog_service._first_letter("9 Lives") == "#"
    assert catalog_service._first_letter("- Other") == "#"
    assert catalog_service._safe_int("42") == 42
    assert catalog_service._safe_int(True) is None
    assert catalog_service._safe_int(None) is None


def test_anime_item_coercion_preserves_fields_and_restricted_filter() -> None:
    item = catalog_service._coerce_item({
        "message_id": "7",
        "title_raw": "  My   Anime ",
        "post_url": "https://t.me/example/7",
        "year_post": 2025,
        "anilist": {
            "title_display": "My Anime Display",
            "cover": "https://example.com/cover.jpg",
            "format": "TV",
            "averageScore": 88,
            "seasonYear": 2026,
        },
    })

    assert item == {
        "message_id": 7,
        "titulo": "My Anime Display",
        "letter": "M",
        "link_post": "https://t.me/example/7",
        "cover_url": "https://example.com/cover.jpg",
        "format": "TV",
        "badge": "TV",
        "score": 88,
        "year": 2026,
    }
    assert catalog_service._coerce_item({
        "title": "Hidden",
        "link": "https://t.me/example/8",
        "status_post": "Restrito",
    }) is None


def test_manga_badge_and_item_coercion_preserve_existing_rules() -> None:
    assert catalog_service._detect_manga_badge({}, {"format": "MANGA"}) == "MANGA"
    assert catalog_service._detect_manga_badge({}, {"format": "NOVEL"}) == "NOVEL"
    assert catalog_service._detect_manga_badge({}, {"format": "ONE_SHOT"}) == "ONE-SHOT"
    assert catalog_service._detect_manga_badge({}, {"format": "ONA"}) == "ONA"
    assert catalog_service._detect_manga_badge({"raw_text": "Formato: Manhwa"}, None) == "MANHWA"
    assert catalog_service._detect_manga_badge({"raw_text": "Formato: Manhua"}, None) == "MANHUA"
    assert catalog_service._detect_manga_badge({"raw_text": "Formato: Mangá"}, None) == "MANGA"

    item = catalog_service._coerce_manga_item({
        "message_id": 12,
        "titulo": "Manga Title",
        "link_post": "https://t.me/manga/12",
        "raw_text": "Formato: Manhwa",
    })
    assert item is not None
    assert item["badge"] == "MANHWA"
    assert item["titulo"] == "Manga Title"
    assert item["letter"] == "M"


def test_public_catalog_filters_keep_query_letter_and_limit_contract(monkeypatch) -> None:
    anime_items = [
        {"titulo": "Alpha", "letter": "A"},
        {"titulo": "Beta", "letter": "B"},
        {"titulo": "Alpine", "letter": "A"},
    ]
    manga_items = [
        {"titulo": "Manga Alpha", "letter": "M"},
        {"titulo": "Novel Beta", "letter": "N"},
    ]
    monkeypatch.setattr(catalog_service, "_CATALOG", anime_items)
    monkeypatch.setattr(catalog_service, "_MANGA_CATALOG", manga_items)

    items, total = catalog_service.filter_catalog("alp", "ALL", 200, 0)
    assert total == 2
    assert [item["titulo"] for item in items] == ["Alpha", "Alpine"]

    items, total = catalog_service.filter_catalog("", "A", 1, 1)
    assert total == 2
    assert [item["titulo"] for item in items] == ["Alpine"]

    items, total = catalog_service.filter_manga_catalog("beta", "ALL", 60, 0)
    assert total == 1
    assert [item["titulo"] for item in items] == ["Novel Beta"]


def test_letters_payload_preserves_existing_shape_and_counts(monkeypatch) -> None:
    monkeypatch.setattr(catalog_service, "_TOTAL", 4)
    monkeypatch.setattr(catalog_service, "_LETTER_COUNTS", {"#": 1, "A": 2, "B": 1})
    monkeypatch.setattr(catalog_service, "_MANGA_TOTAL", 2)
    monkeypatch.setattr(catalog_service, "_MANGA_LETTER_COUNTS", {"M": 1, "N": 1})

    anime = catalog_service.catalog_letters_payload()
    manga = catalog_service.manga_letters_payload()

    assert anime["total"] == 4
    assert anime["all_count"] == 4
    assert anime["counts"]["#"] == 1
    # Mantém inclusive a expressão legada `k not in ("ALL")`, que exclui A/L.
    assert "A" not in anime["counts"]
    assert "L" not in anime["counts"]
    assert anime["counts"]["B"] == 1

    assert manga["total"] == 2
    assert manga["all_count"] == 2
    assert manga["counts"]["M"] == 1
    assert manga["counts"]["N"] == 1
