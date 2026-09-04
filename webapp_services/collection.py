from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, List, Optional, Tuple

from utils.web_image_url import web_image_url
from webapp_services.profile_overview import build_menu_user_payload

CollectionLoader = Callable[[int], List[Dict[str, Any]]]
CardsDataLoader = Callable[[], Dict[str, Any]]


def collection_character_subcategory_map(data: Dict[str, Any]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for raw_name, chars in (data.get("subcategories") or {}).items():
        label = str(raw_name or "").strip()
        if not label:
            continue
        for char in chars or []:
            try:
                cid = int((char or {}).get("id") or 0)
            except Exception:
                cid = 0
            if cid > 0 and cid not in out:
                out[cid] = label
    return out


def collection_snapshot(
    user_id: int,
    *,
    load_collection: CollectionLoader | None = None,
    load_cards_data: CardsDataLoader | None = None,
) -> Tuple[Dict[str, Any], Dict[int, int], Dict[int, str]]:
    if load_collection is None:
        from database import get_user_card_collection

        load_collection = get_user_card_collection
    if load_cards_data is None:
        from cards_service import build_cards_final_data

        load_cards_data = build_cards_final_data

    data = load_cards_data()
    raw_rows = load_collection(int(user_id)) or []
    qty_by_char: Dict[int, int] = {}

    for row in raw_rows:
        try:
            cid = int(row.get("character_id") or 0)
            qty = int(row.get("quantity") or 0)
        except Exception:
            continue
        if cid <= 0 or qty <= 0:
            continue
        qty_by_char[cid] = qty_by_char.get(cid, 0) + qty

    return data, qty_by_char, collection_character_subcategory_map(data)


def collection_cards_from_snapshot(
    data: Dict[str, Any],
    qty_by_char: Dict[int, int],
    subcategory_map: Dict[int, str],
) -> List[Dict[str, Any]]:
    chars_by_id = data.get("characters_by_id") or {}
    items: List[Dict[str, Any]] = []

    for cid, qty in qty_by_char.items():
        meta = chars_by_id.get(int(cid)) or {}
        if not meta:
            continue

        items.append({
            "character_id": int(cid),
            "quantity": int(qty),
            "name": str(meta.get("name") or f"Personagem {cid}"),
            "anime_id": int(meta.get("anime_id") or 0),
            "anime": str(meta.get("anime") or "Obra desconhecida"),
            "image": web_image_url(meta.get("image")),
            "subcategory": str(subcategory_map.get(int(cid)) or "").strip(),
        })

    items.sort(key=lambda x: (x["anime"].lower(), x["name"].lower(), int(x["character_id"])))
    return items


def collection_animes_from_snapshot(
    data: Dict[str, Any],
    qty_by_char: Dict[int, int],
) -> List[Dict[str, Any]]:
    chars_by_anime = data.get("characters_by_anime") or {}
    animes_by_id = data.get("animes_by_id") or {}
    anime_owned: Dict[int, set] = {}

    for cid, qty in qty_by_char.items():
        if qty <= 0:
            continue
        meta = (data.get("characters_by_id") or {}).get(int(cid)) or {}
        anime_id = int(meta.get("anime_id") or 0)
        if anime_id <= 0:
            continue
        anime_owned.setdefault(anime_id, set()).add(int(cid))

    items: List[Dict[str, Any]] = []
    for anime_id, owned_ids in anime_owned.items():
        chars = list(chars_by_anime.get(int(anime_id)) or [])
        if not chars:
            continue

        anime_meta = dict(animes_by_id.get(int(anime_id)) or {})
        anime_name = str(anime_meta.get("anime") or chars[0].get("anime") or f"Obra {anime_id}")
        total_count = len(chars)
        owned_count = len(owned_ids)
        missing_count = max(0, total_count - owned_count)
        completion_pct = int(round((owned_count / total_count) * 100)) if total_count else 0

        items.append({
            "anime_id": int(anime_id),
            "anime": anime_name,
            "owned_count": int(owned_count),
            "total_count": int(total_count),
            "missing_count": int(missing_count),
            "completion_pct": int(completion_pct),
            "cover_image": web_image_url(anime_meta.get("cover_image") or anime_meta.get("banner_image")),
            "banner_image": web_image_url(anime_meta.get("banner_image") or anime_meta.get("cover_image")),
        })

    items.sort(key=lambda x: (x["anime"].lower(), int(x["anime_id"])))
    return items


def collection_detail_from_snapshot(
    data: Dict[str, Any],
    qty_by_char: Dict[int, int],
    subcategory_map: Dict[int, str],
    anime_id: int,
    mode: str,
) -> Optional[Dict[str, Any]]:
    anime_id = int(anime_id or 0)
    if anime_id <= 0:
        return None

    chars = list((data.get("characters_by_anime") or {}).get(anime_id) or [])
    if not chars:
        return None

    anime_meta = dict((data.get("animes_by_id") or {}).get(anime_id) or {})
    anime_name = str(anime_meta.get("anime") or chars[0].get("anime") or f"Obra {anime_id}")

    gallery_items: List[Dict[str, Any]] = []
    owned_items: List[Dict[str, Any]] = []
    missing_items: List[Dict[str, Any]] = []

    for meta in chars:
        cid = int(meta.get("id") or 0)
        qty = int(qty_by_char.get(cid) or 0)
        base = {
            "id": cid,
            "character_id": cid,
            "name": str(meta.get("name") or f"Personagem {cid}"),
            "anime_id": anime_id,
            "anime": anime_name,
            "image": web_image_url(meta.get("image")),
            "subcategory": str(subcategory_map.get(cid) or "").strip(),
            "quantity": qty,
            "owned": qty > 0,
        }
        gallery_items.append(base)
        if qty > 0:
            owned_items.append(base)
        else:
            missing_items.append(base)

    gallery_items.sort(key=lambda x: (x["name"].lower(), int(x["id"])))
    owned_items.sort(key=lambda x: (x["name"].lower(), int(x["id"])))
    missing_items.sort(key=lambda x: (x["name"].lower(), int(x["id"])))

    mode_key = str(mode or "owned").strip().lower()
    if mode_key not in {"owned", "missing", "gallery"}:
        mode_key = "owned"

    items_map = {
        "owned": owned_items,
        "missing": missing_items,
        "gallery": gallery_items,
    }

    return {
        "anime": {
            "anime_id": anime_id,
            "anime": anime_name,
            "cover_image": web_image_url(anime_meta.get("cover_image") or anime_meta.get("banner_image")),
            "banner_image": web_image_url(anime_meta.get("banner_image") or anime_meta.get("cover_image")),
        },
        "mode": mode_key,
        "items": items_map[mode_key],
        "owned_count": len(owned_items),
        "total_count": len(gallery_items),
        "missing_count": len(missing_items),
        "completion_pct": int(round((len(owned_items) / len(gallery_items)) * 100)) if gallery_items else 0,
    }


def collection_profile_payload(user_id: int, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = build_menu_user_payload(
        int(user_id),
        collection_snapshot=collection_snapshot,
        collection_cards_from_snapshot=collection_cards_from_snapshot,
    )
    profile = dict((data or {}).get("profile") or {})

    username = str((ctx or {}).get("username") or profile.get("username") or "").strip()
    full_name = str((ctx or {}).get("full_name") or "").strip()
    display_name = str(profile.get("display_name") or "").strip()

    if not display_name:
        display_name = full_name or (f"@{username}" if username else f"User {user_id}")

    profile["user_id"] = int(user_id)
    profile["username"] = username
    profile["full_name"] = full_name
    profile["display_name"] = display_name
    return profile
