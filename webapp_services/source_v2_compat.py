from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

from level_system import get_level_theme
from webapp_services.collection import (
    collection_cards_from_snapshot,
    collection_snapshot,
)
from webapp_services.profile_overview import build_menu_user_payload


def _admin_ids() -> set[int]:
    values: list[str] = []
    for name in ("BOT_OWNER_ID", "ADMINS", "ADMIN_IDS", "CARD_ADMIN_IDS"):
        raw = str(os.getenv(name, "") or "").strip()
        if raw:
            values.extend(raw.replace(";", ",").split(","))
    ids: set[int] = set()
    for value in values:
        try:
            user_id = int(value.strip())
        except (TypeError, ValueError):
            continue
        if user_id > 0:
            ids.add(user_id)
    return ids


def source_character_to_seal(item: Dict[str, Any], *, owned: bool | None = None) -> Dict[str, Any]:
    quantity = max(0, int(item.get("quantity") or 0))
    is_owned = quantity > 0 if owned is None else bool(owned)
    return {
        "id": str(int(item.get("character_id") or item.get("id") or 0)),
        "name": str(item.get("name") or "Personagem"),
        "anime": str(item.get("anime") or "Obra desconhecida"),
        # Source ainda não possui uma taxonomia de raridade canônica equivalente
        # ao Seal. Mantemos um valor estável até a migration de raridades/sets.
        "rarity": str(item.get("rarity") or "Standard"),
        "img_url": str(item.get("image") or item.get("img_url") or ""),
        "zenith_price": int(item.get("zenith_price") or 0),
        "base_zenith_price": int(item.get("base_zenith_price") or 0),
        "staff_discount": int(item.get("staff_discount") or 0),
        "owned": is_owned,
        "count": quantity,
    }


def _filter_items(
    items: Iterable[Dict[str, Any]],
    *,
    search: str = "",
    rarity: str = "",
) -> List[Dict[str, Any]]:
    search_key = str(search or "").strip().casefold()
    rarity_key = str(rarity or "").strip().casefold()
    out: List[Dict[str, Any]] = []
    for item in items:
        if search_key:
            haystack = f"{item.get('name', '')} {item.get('anime', '')}".casefold()
            if search_key not in haystack:
                continue
        if rarity_key and str(item.get("rarity") or "Standard").casefold() != rarity_key:
            continue
        out.append(item)
    return out


def paginate_items(
    items: Iterable[Dict[str, Any]],
    *,
    page: int = 1,
    limit: int = 24,
    search: str = "",
    rarity: str = "",
) -> Dict[str, Any]:
    filtered = _filter_items(items, search=search, rarity=rarity)
    page = max(1, int(page or 1))
    limit = min(100, max(1, int(limit or 24)))
    start = (page - 1) * limit
    return {
        "items": filtered[start:start + limit],
        "total": len(filtered),
        "page": page,
        "limit": limit,
    }


def build_source_collection(user_id: int) -> tuple[dict, dict[int, int], list[dict]]:
    data, qty_by_char, subcategory_map = collection_snapshot(int(user_id))
    owned_rows = collection_cards_from_snapshot(data, qty_by_char, subcategory_map)
    owned = [source_character_to_seal(row) for row in owned_rows]
    return data, qty_by_char, owned


def build_source_gallery(user_id: int) -> list[dict]:
    data, qty_by_char, _ = collection_snapshot(int(user_id))
    chars_by_id = data.get("characters_by_id") or {}
    items: list[dict] = []
    for raw_id, meta in chars_by_id.items():
        try:
            character_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if character_id <= 0:
            continue
        row = {
            "character_id": character_id,
            "quantity": int(qty_by_char.get(character_id) or 0),
            "name": str((meta or {}).get("name") or f"Personagem {character_id}"),
            "anime": str((meta or {}).get("anime") or "Obra desconhecida"),
            "image": str((meta or {}).get("image") or ""),
        }
        items.append(source_character_to_seal(row))
    items.sort(key=lambda x: (x["anime"].casefold(), x["name"].casefold(), int(x["id"])))
    return items


def build_source_me(user_id: int, identity: Dict[str, Any]) -> Dict[str, Any]:
    from database import (
        get_level_progress_values,
        get_progress_row,
        get_user_level_rank,
    )

    user_id = int(user_id)
    profile_payload = build_menu_user_payload(user_id)
    profile = dict(profile_payload.get("profile") or {})
    data, qty_by_char, characters = build_source_collection(user_id)

    progress_row = get_progress_row(user_id) or {}
    xp = int(progress_row.get("xp") or 0)
    level = int(progress_row.get("level") or 1)
    progress_values = get_level_progress_values(xp) or {}
    rank = int(get_user_level_rank(user_id) or 0)

    total_copies = sum(max(0, int(qty or 0)) for qty in qty_by_char.values())
    unique_characters = len([cid for cid, qty in qty_by_char.items() if int(qty or 0) > 0])
    total_available = len(data.get("characters_by_id") or {})
    completion = round((unique_characters / total_available) * 100, 1) if total_available else 0.0

    full_name = str(identity.get("full_name") or profile.get("display_name") or "").strip()
    first_name = str(identity.get("first_name") or "").strip()
    last_name = str(identity.get("last_name") or "").strip()
    if not first_name and full_name:
        parts = full_name.split(maxsplit=1)
        first_name = parts[0]
        if not last_name and len(parts) > 1:
            last_name = parts[1]
    if not first_name:
        first_name = str(profile.get("nickname") or "User")

    username = str(identity.get("username") or profile.get("username") or "").strip()
    coins = int(profile.get("coins") or 0)
    is_sudo = user_id in _admin_ids()
    theme = get_level_theme(level) or {}

    role = "admin" if is_sudo else "collector"
    role_label = "Source Admin" if is_sudo else "Collector"
    role_tag = "ADMIN" if is_sudo else None

    return {
        "id": user_id,
        "first_name": first_name,
        "last_name": last_name or None,
        "username": username,
        "avatar": str(identity.get("photo_url") or ""),
        "is_sudo": is_sudo,
        "role": role,
        "role_label": role_label,
        "role_tag": role_tag,
        "role_symbol": "◆" if is_sudo else "◇",
        "is_staff": is_sudo,
        "can_upload": is_sudo,
        "can_edit_character": is_sudo,
        "upload_reward": None,
        "role_perks": {},
        "role_benefits": [],
        "balance": coins,
        # Mantido separado de Coins para a futura moeda premium/câmbio.
        "zenith": 0,
        "stats": {
            "level": level,
            "xp": xp,
            "xp_current": int(progress_values.get("xp_current") or 0),
            "xp_needed": max(1, int(progress_values.get("xp_needed") or 1)),
            "streak": 0,
            "points": coins,
            "zenith": 0,
            "badges": [],
            "total_characters": total_copies,
            "unique_characters": unique_characters,
            "total_available_characters": total_available,
            "collection_percent": completion,
            "rank": rank,
            "percentile": 0,
            "pass_type": "free",
            "incubation_slots": 1,
            "active_incubations": 0,
        },
        "achievements": [],
        "titles": {
            "current": str(theme.get("tag") or "COLLECTOR"),
            "all": [str(theme.get("tag") or "COLLECTOR")],
        },
        "characters": characters,
        "current_pet": None,
        "pets": [],
        "eggs": [],
    }
