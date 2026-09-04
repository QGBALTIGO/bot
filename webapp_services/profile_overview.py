from __future__ import annotations

from collections.abc import Callable
from typing import Any

from utils.profile_options import COUNTRY_OPTIONS, LANGUAGE_OPTIONS
from utils.web_image_url import web_image_url

CollectionSnapshot = Callable[[int], tuple[Any, Any, Any]]
CollectionCardsBuilder = Callable[[Any, Any, Any], list[dict[str, Any]]]
UserCreator = Callable[[int], Any]
RowLoader = Callable[[int], dict[str, Any] | None]
CharacterLoader = Callable[[int], dict[str, Any] | None]
ImageNormalizer = Callable[[Any], str]


def build_menu_user_payload(
    uid: int,
    *,
    collection_snapshot: CollectionSnapshot,
    collection_cards_from_snapshot: CollectionCardsBuilder,
    create_user: UserCreator | None = None,
    get_user: RowLoader | None = None,
    get_progress: RowLoader | None = None,
    get_settings: RowLoader | None = None,
    get_character: CharacterLoader | None = None,
    image_url: ImageNormalizer = web_image_url,
) -> dict[str, Any]:
    """Monta o payload completo do Perfil sem acoplar o serviço ao entrypoint HTTP."""

    if create_user is None:
        from database import create_or_get_user

        create_user = create_or_get_user
    if get_user is None:
        from database import get_user_status

        get_user = get_user_status
    if get_progress is None:
        from database import get_progress_row

        get_progress = get_progress_row
    if get_settings is None:
        from database_profile import get_profile_settings

        get_settings = get_profile_settings
    if get_character is None:
        from cards_service import get_character_by_id

        get_character = get_character_by_id

    uid = int(uid)
    create_user(uid)

    user = get_user(uid) or {}
    progress = get_progress(uid) or {}
    settings = get_settings(uid) or {}
    cards_data, qty_by_char, subcategory_map = collection_snapshot(uid)
    cards = collection_cards_from_snapshot(cards_data, qty_by_char, subcategory_map)

    favorite = None
    favorite_id = settings.get("favorite_character_id")
    if favorite_id:
        try:
            character = get_character(int(favorite_id))
        except Exception:
            character = None

        if character:
            favorite = {
                "id": int(favorite_id),
                "name": str(character.get("name") or "").strip(),
                "anime": str(character.get("anime") or "").strip(),
                "image": image_url(character.get("image")),
            }

    full_name = str(user.get("full_name") or "").strip()
    username = str(user.get("username") or "").strip()
    display_name = full_name or (f"@{username}" if username else f"User {uid}")

    return {
        "ok": True,
        "profile": {
            "user_id": uid,
            "display_name": display_name,
            "username": username,
            "coins": int(user.get("coins") or 0),
            "level": int(progress.get("level") or 1),
            "collection_total": len(cards),
            "nickname": str(settings.get("nickname") or "").strip(),
            "favorite": favorite,
            "country_code": str(settings.get("country_code") or "BR").strip().upper(),
            "language": str(settings.get("language") or "pt").strip().lower(),
            "private_profile": bool(settings.get("private_profile")),
            "notifications_enabled": bool(settings.get("notifications_enabled", True)),
        },
        "countries": COUNTRY_OPTIONS,
        "languages": LANGUAGE_OPTIONS,
    }
