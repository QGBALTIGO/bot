from __future__ import annotations

from collections.abc import Callable
from typing import Any

from utils.web_image_url import web_image_url

CollectionLoader = Callable[[int], list[dict[str, Any]]]
CharacterLoader = Callable[[int], dict[str, Any] | None]
ImageNormalizer = Callable[[Any], str]


def menu_collection_characters(
    uid: int,
    *,
    get_collection: CollectionLoader | None = None,
    get_character: CharacterLoader | None = None,
    image_url: ImageNormalizer = web_image_url,
) -> list[dict[str, Any]]:
    """Monta a coleção usada pelo Perfil e pela validação de favorito."""

    if get_collection is None:
        from database import get_user_card_collection

        get_collection = get_user_card_collection

    if get_character is None:
        from cards_service import get_character_by_id

        get_character = get_character_by_id

    rows = get_collection(int(uid)) or []
    out: list[dict[str, Any]] = []

    for row in rows:
        cid = int(row.get("character_id") or 0)
        qty = int(row.get("quantity") or 0)
        if cid <= 0 or qty <= 0:
            continue

        try:
            character = get_character(cid)
        except Exception:
            character = None

        if not character:
            continue

        out.append(
            {
                "id": cid,
                "name": str(character.get("name") or "").strip(),
                "anime": str(character.get("anime") or "").strip(),
                "image": image_url(character.get("image")),
                "quantity": qty,
            }
        )

    out.sort(
        key=lambda item: (
            (item["anime"] or "").lower(),
            (item["name"] or "").lower(),
            int(item["id"]),
        )
    )
    return out
