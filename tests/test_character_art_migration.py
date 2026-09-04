from __future__ import annotations

from scripts.character_art_migration import (
    catalog_indexes_from_characters,
    normalize_identity,
    plan_character_art_updates,
    portrait_proxy_url,
    summarize,
)


def _catalog():
    characters = {
        10: {"id": 10, "name": "Monkey D. Luffy", "anime": "One Piece", "image": "https://old/luffy.jpg"},
        20: {"id": 20, "name": "Rem", "anime": "Re:Zero", "image": "https://old/rem.jpg"},
        30: {"id": 30, "name": "Rem", "anime": "Death Note", "image": "https://old/rem-death-note.jpg"},
    }
    return catalog_indexes_from_characters(characters)


def test_normalize_identity_handles_accents_and_punctuation() -> None:
    assert normalize_identity("  Mönkey D. Luffy!! ") == "monkey d luffy"


def test_matches_by_name_and_anime_without_changing_character_id() -> None:
    results = plan_character_art_updates(
        [{
            "name": "Monkey D. Luffy",
            "anime": "One Piece",
            "image_url": "https://cdn.example/luffy-new.jpg",
        }],
        catalog_indexes=_catalog(),
    )

    assert len(results) == 1
    assert results[0].status == "matched"
    assert results[0].character_id == 10
    assert results[0].previous_image_url == "https://old/luffy.jpg"


def test_explicit_source_alias_can_resolve_different_spelling() -> None:
    aliases = {normalize_identity("id:seal-777"): 10}
    results = plan_character_art_updates(
        [{
            "source_character_id": "seal-777",
            "name": "Luffy",
            "anime": "OP",
            "image_url": "https://cdn.example/luffy.jpg",
        }],
        aliases=aliases,
        catalog_indexes=_catalog(),
    )

    assert results[0].status == "matched"
    assert results[0].character_id == 10


def test_ambiguous_name_requires_anime_or_alias() -> None:
    results = plan_character_art_updates(
        [{"name": "Rem", "image_url": "https://cdn.example/rem.jpg"}],
        catalog_indexes=_catalog(),
    )

    assert results[0].status == "ambiguous"
    assert results[0].character_id is None


def test_invalid_or_unknown_items_are_never_applied_as_matches() -> None:
    results = plan_character_art_updates(
        [
            {"name": "Nobody", "anime": "Unknown", "image_url": "https://cdn.example/x.jpg"},
            {"name": "Monkey D. Luffy", "anime": "One Piece", "image_url": "http://insecure.example/x.jpg"},
        ],
        catalog_indexes=_catalog(),
    )

    assert summarize(results) == {"invalid": 1, "unmatched": 1}


def test_portrait_proxy_is_always_requested_in_2_by_3_mode() -> None:
    url = portrait_proxy_url(
        "https://cdn.example/art/luffy portrait.jpg",
        origin="https://source.example/",
    )
    assert url.startswith("https://source.example/api/image-proxy?crop=portrait&url=")
    assert "luffy%20portrait.jpg" in url
