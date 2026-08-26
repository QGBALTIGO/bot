from __future__ import annotations

from typing import Any, Dict

from cards_service import build_cards_final_data
from database import get_user_card_collection


def get_collection_state(user_id: int) -> Dict[str, Any]:
    data = build_cards_final_data()
    rows = get_user_card_collection(int(user_id)) or []
    characters_by_id = data.get("characters_by_id") or {}

    items: list[Dict[str, Any]] = []
    total_copies = 0

    for row in rows:
        try:
            character_id = int(row.get("character_id") or 0)
            quantity = int(row.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
        if character_id <= 0 or quantity <= 0:
            continue

        character = characters_by_id.get(character_id)
        if not character:
            # Keep orphaned ownership visible instead of silently deleting data.
            items.append(
                {
                    "id": character_id,
                    "name": f"Personagem #{character_id}",
                    "anime": "Catálogo indisponível",
                    "image": "",
                    "anime_id": 0,
                    "quantity": quantity,
                    "orphaned": True,
                }
            )
        else:
            items.append(
                {
                    "id": character_id,
                    "name": str(character.get("name") or f"Personagem #{character_id}"),
                    "anime": str(character.get("anime") or ""),
                    "image": str(character.get("image") or ""),
                    "anime_id": int(character.get("anime_id") or 0),
                    "quantity": quantity,
                    "orphaned": False,
                }
            )
        total_copies += quantity

    items.sort(
        key=lambda item: (
            -int(item.get("quantity") or 0),
            str(item.get("anime") or "").casefold(),
            str(item.get("name") or "").casefold(),
        )
    )

    total_catalog = len(characters_by_id)
    unique_owned = len(items)
    duplicates = max(0, total_copies - unique_owned)
    completion = (unique_owned / total_catalog * 100.0) if total_catalog else 0.0

    return {
        "items": items,
        "stats": {
            "unique": unique_owned,
            "copies": total_copies,
            "duplicates": duplicates,
            "catalog_total": total_catalog,
            "completion_percent": round(completion, 2),
        },
    }
