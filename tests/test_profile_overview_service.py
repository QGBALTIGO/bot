from __future__ import annotations

from webapp_services.profile_overview import build_menu_user_payload


def test_profile_overview_preserves_payload_contract() -> None:
    created: list[int] = []

    payload = build_menu_user_payload(
        123,
        collection_snapshot=lambda uid: ([{"character_id": 1}], {1: 2}, {1: "anime"}),
        collection_cards_from_snapshot=lambda cards, qty, sub: [
            {"id": 1},
            {"id": 2},
            {"id": 3},
        ],
        create_user=lambda uid: created.append(uid),
        get_user=lambda uid: {
            "full_name": "Kayky Sousa",
            "username": "kayky",
            "coins": 87,
        },
        get_progress=lambda uid: {"level": 9},
        get_settings=lambda uid: {
            "nickname": "Kayky_1",
            "favorite_character_id": 44,
            "country_code": "br",
            "language": "PT",
            "private_profile": True,
            "notifications_enabled": False,
        },
        get_character=lambda cid: {
            "name": "Personagem",
            "anime": "Anime",
            "image": "https://example.com/char.jpg",
        },
        image_url=lambda value: f"proxy:{value}",
    )

    assert created == [123]
    assert payload["ok"] is True
    assert payload["profile"] == {
        "user_id": 123,
        "display_name": "Kayky Sousa",
        "username": "kayky",
        "coins": 87,
        "level": 9,
        "collection_total": 3,
        "nickname": "Kayky_1",
        "favorite": {
            "id": 44,
            "name": "Personagem",
            "anime": "Anime",
            "image": "proxy:https://example.com/char.jpg",
        },
        "country_code": "BR",
        "language": "pt",
        "private_profile": True,
        "notifications_enabled": False,
    }
    assert {item["code"] for item in payload["countries"]} == {"BR", "US", "ES", "JP"}
    assert {item["code"] for item in payload["languages"]} == {"pt", "en", "es"}


def test_profile_overview_display_name_fallbacks_are_preserved() -> None:
    common = dict(
        collection_snapshot=lambda uid: ([], {}, {}),
        collection_cards_from_snapshot=lambda cards, qty, sub: [],
        create_user=lambda uid: None,
        get_progress=lambda uid: {},
        get_settings=lambda uid: {},
        get_character=lambda cid: None,
    )

    by_username = build_menu_user_payload(
        10,
        get_user=lambda uid: {"username": "source"},
        **common,
    )
    anonymous = build_menu_user_payload(
        11,
        get_user=lambda uid: {},
        **common,
    )

    assert by_username["profile"]["display_name"] == "@source"
    assert anonymous["profile"]["display_name"] == "User 11"
    assert by_username["profile"]["level"] == 1
    assert by_username["profile"]["country_code"] == "BR"
    assert by_username["profile"]["language"] == "pt"
    assert by_username["profile"]["notifications_enabled"] is True
