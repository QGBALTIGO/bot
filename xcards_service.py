import hashlib
import json
import os
import re
import unicodedata
from copy import deepcopy
from threading import RLock
from typing import Any, Dict, List, Optional


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

UNIONARENA_CARDS_PATH = os.getenv(
    "UNIONARENA_CARDS_PATH",
    os.path.join(DATA_DIR, "unionarena_cards_pt_br_all.json"),
).strip()

_LOCK = RLock()
_CACHE: Optional[Dict[str, Any]] = None


def _normalize_text(text: Any) -> str:
    text = str(text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _slugify(text: Any) -> str:
    value = _normalize_text(text)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "title"


def _allocate_short_id(prefix: str, value: str, used_ids: set) -> int:
    digest = hashlib.sha1(f"{prefix}:{value}".encode("utf-8")).hexdigest()
    base = (int(digest[:10], 16) % 900000000) + 100000000
    step = (int(digest[10:18], 16) % 9973) + 1
    candidate = base

    while candidate in used_ids:
        candidate += step
        if candidate > 999999999:
            candidate = 100000000 + (candidate % 900000000)

    used_ids.add(candidate)
    return candidate


def _load_raw_payload() -> Dict[str, Any]:
    if not os.path.exists(UNIONARENA_CARDS_PATH):
        raise FileNotFoundError(
            f"Arquivo de xcards não encontrado: {UNIONARENA_CARDS_PATH}"
        )

    with open(UNIONARENA_CARDS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("Payload de xcards inválido.")

    return raw


def reload_xcards_cache() -> None:
    global _CACHE
    _CACHE = None


def build_xcards_data(force_reload: bool = False) -> Dict[str, Any]:
    global _CACHE

    with _LOCK:
        if _CACHE is not None and not force_reload:
            return _CACHE

        raw = _load_raw_payload()
        labels_pt_br = raw.get("labels_pt_br") or {}
        raw_titles = raw.get("titles") or []

        titles_list: List[Dict[str, Any]] = []
        titles_by_id: Dict[int, Dict[str, Any]] = {}
        titles_by_name: Dict[str, Dict[str, Any]] = {}

        characters_list: List[Dict[str, Any]] = []
        characters_by_id: Dict[int, Dict[str, Any]] = {}
        characters_by_title: Dict[int, List[Dict[str, Any]]] = {}
        characters_cards: Dict[int, List[Dict[str, Any]]] = {}

        cards_list: List[Dict[str, Any]] = []
        cards_by_id: Dict[int, Dict[str, Any]] = {}
        cards_by_no: Dict[str, Dict[str, Any]] = {}
        cards_by_title: Dict[int, List[Dict[str, Any]]] = {}
        title_id_by_slug: Dict[str, int] = {}
        character_id_by_key: Dict[str, int] = {}
        used_public_ids = set()

        for raw_title in raw_titles:
            if not isinstance(raw_title, dict):
                continue

            title_name = str(raw_title.get("name") or "").strip()
            if not title_name:
                continue

            title_slug = str(raw_title.get("slug") or "").strip() or _slugify(title_name)
            title_id = title_id_by_slug.get(title_slug)
            if title_id is None:
                title_id = _allocate_short_id("xtitle", title_slug, used_public_ids)
                title_id_by_slug[title_slug] = title_id

            title_logo = str(raw_title.get("logo_image") or "").strip()
            title_cover = ""

            title_obj = {
                "id": title_id,
                "slug": title_slug,
                "name": title_name,
                "logo_image": title_logo,
                "cover_image": "",
                "cards_count": int(raw_title.get("cards_count") or 0),
                "characters_count": int(raw_title.get("characters_count") or 0),
            }

            titles_list.append(title_obj)
            titles_by_id[title_id] = title_obj
            titles_by_name[_normalize_text(title_name)] = title_obj
            characters_by_title.setdefault(title_id, [])
            cards_by_title.setdefault(title_id, [])

            def ensure_character(
                name: str,
                *,
                primary_card_no: str = "",
                primary_image: str = "",
                cards_count: int = 0,
                card_nos: Optional[List[Any]] = None,
            ) -> int:
                char_name_local = str(name or "").strip()
                char_key_local = f"{title_slug}:{_normalize_text(char_name_local)}"
                character_id_local = character_id_by_key.get(char_key_local)

                if character_id_local is not None:
                    existing = characters_by_id.get(character_id_local)
                    if existing:
                        if primary_card_no and not existing.get("primary_card_no"):
                            existing["primary_card_no"] = primary_card_no
                        if primary_image and not existing.get("primary_image"):
                            existing["primary_image"] = primary_image
                        if cards_count and int(existing.get("cards_count") or 0) < int(cards_count):
                            existing["cards_count"] = int(cards_count)
                        if card_nos:
                            merged_nos = list(existing.get("card_nos") or [])
                            for raw_no in card_nos:
                                parsed_no = str(raw_no or "").strip()
                                if parsed_no and parsed_no not in merged_nos:
                                    merged_nos.append(parsed_no)
                            existing["card_nos"] = merged_nos
                    return character_id_local

                character_id_local = _allocate_short_id(
                    "xcharacter", char_key_local, used_public_ids
                )
                character_id_by_key[char_key_local] = character_id_local

                character_obj = {
                    "id": character_id_local,
                    "name": char_name_local,
                    "name_norm": _normalize_text(char_name_local),
                    "title_id": title_id,
                    "title": title_name,
                    "title_slug": title_slug,
                    "primary_card_no": str(primary_card_no or "").strip(),
                    "primary_image": str(primary_image or "").strip(),
                    "cards_count": int(cards_count or 0),
                    "card_nos": [
                        str(raw_no or "").strip()
                        for raw_no in (card_nos or [])
                        if str(raw_no or "").strip()
                    ],
                }

                characters_list.append(character_obj)
                characters_by_id[character_id_local] = character_obj
                characters_by_title[title_id].append(character_obj)
                characters_cards.setdefault(character_id_local, [])
                return character_id_local

            raw_characters = raw_title.get("characters") or []
            for raw_character in raw_characters:
                if not isinstance(raw_character, dict):
                    continue

                char_name = str(raw_character.get("name") or "").strip()
                if not char_name:
                    continue

                primary_card_no = str(raw_character.get("primary_card_no") or "").strip()
                primary_image = str(raw_character.get("primary_image") or "").strip()
                cards_count = int(raw_character.get("cards_count") or 0)
                card_nos = list(raw_character.get("card_nos") or [])

                if not title_cover:
                    title_cover = primary_image

                ensure_character(
                    char_name,
                    primary_card_no=primary_card_no,
                    primary_image=primary_image,
                    cards_count=cards_count,
                    card_nos=card_nos,
                )

            raw_cards = raw_title.get("cards") or []
            for raw_card in raw_cards:
                if not isinstance(raw_card, dict):
                    continue

                card_no = str(raw_card.get("card_no") or "").strip()
                card_name = str(raw_card.get("name") or "").strip()
                if not card_no or not card_name:
                    continue

                character_id = ensure_character(
                    card_name,
                    primary_card_no=card_no,
                    primary_image=str(raw_card.get("image") or "").strip(),
                )
                card_id = _allocate_short_id("xcard", card_no.lower(), used_public_ids)

                pt_br = raw_card.get("pt_br") if isinstance(raw_card.get("pt_br"), dict) else {}
                card_obj = {
                    "id": card_id,
                    "card_no": card_no,
                    "base_card_no": str(raw_card.get("base_card_no") or card_no).strip(),
                    "character_id": character_id,
                    "name": card_name,
                    "name_norm": _normalize_text(card_name),
                    "title_id": title_id,
                    "title": title_name,
                    "title_slug": title_slug,
                    "image": str(raw_card.get("image") or "").strip(),
                    "detail_url": str(raw_card.get("detail_url") or "").strip(),
                    "detail_iframe_url": str(raw_card.get("detail_iframe_url") or "").strip(),
                    "alt_art": bool(raw_card.get("alt_art")),
                    "rarity": str(raw_card.get("rarity") or "").strip(),
                    "product_name": str(raw_card.get("product_name") or "").strip(),
                    "product_card_list_url": str(raw_card.get("product_card_list_url") or "").strip(),
                    "product_info_url": str(raw_card.get("product_info_url") or "").strip(),
                    "required_energy": str(raw_card.get("required_energy") or "").strip(),
                    "required_energy_icons": list(raw_card.get("required_energy_icons") or []),
                    "ap_cost": str(raw_card.get("ap_cost") or "").strip(),
                    "ap_cost_value": raw_card.get("ap_cost_value"),
                    "card_type": str(raw_card.get("card_type") or "").strip(),
                    "bp": str(raw_card.get("bp") or "").strip(),
                    "bp_value": raw_card.get("bp_value"),
                    "affinity": str(raw_card.get("affinity") or "").strip(),
                    "affinities": list(raw_card.get("affinities") or []),
                    "generated_energy": list(raw_card.get("generated_energy") or []),
                    "effect": str(raw_card.get("effect") or "").strip(),
                    "effect_keywords": list(raw_card.get("effect_keywords") or []),
                    "trigger": str(raw_card.get("trigger") or "").strip(),
                    "trigger_keywords": list(raw_card.get("trigger_keywords") or []),
                    "title_logo": str(raw_card.get("title_logo") or title_logo).strip(),
                    "pt_br": deepcopy(pt_br),
                }

                if not title_cover:
                    title_cover = card_obj["image"]

                cards_list.append(card_obj)
                cards_by_id[card_id] = card_obj
                cards_by_no[card_no.lower()] = card_obj
                cards_by_title[title_id].append(card_obj)
                characters_cards.setdefault(character_id, []).append(card_obj)

            if not title_cover:
                title_cover = title_logo
            title_obj["cover_image"] = title_cover

        for character_id, cards in characters_cards.items():
            cards.sort(
                key=lambda item: (
                    1 if str(item.get("product_name") or "").upper().startswith("PROMOTION") else 0,
                    1 if item.get("alt_art") else 0,
                    str(item.get("card_no") or ""),
                )
            )
            ch = characters_by_id.get(character_id)
            if ch:
                if not ch.get("primary_image"):
                    ch["primary_image"] = cards[0].get("image", "") if cards else ""
                if not ch.get("primary_card_no"):
                    ch["primary_card_no"] = cards[0].get("card_no", "") if cards else ""
                ch["cards_count"] = len(cards)
                ch["card_nos"] = [str(card.get("card_no") or "") for card in cards]

        for title_id, chars in characters_by_title.items():
            chars.sort(key=lambda item: (item["name_norm"], str(item["primary_card_no"] or "")))
            title_obj = titles_by_id.get(title_id)
            if title_obj:
                title_obj["characters_count"] = len(chars)
                title_obj["cards_count"] = len(cards_by_title.get(title_id, []))

        titles_list.sort(key=lambda item: _normalize_text(item["name"]))
        characters_list.sort(key=lambda item: (_normalize_text(item["title"]), item["name_norm"]))
        cards_list.sort(
            key=lambda item: (
                _normalize_text(item["title"]),
                item["name_norm"],
                str(item.get("card_no") or ""),
            )
        )

        _CACHE = {
            "labels_pt_br": labels_pt_br,
            "titles_list": titles_list,
            "titles_by_id": titles_by_id,
            "titles_by_name": titles_by_name,
            "characters_list": characters_list,
            "characters_by_id": characters_by_id,
            "characters_by_title": characters_by_title,
            "characters_cards": characters_cards,
            "cards_list": cards_list,
            "cards_by_id": cards_by_id,
            "cards_by_no": cards_by_no,
            "cards_by_title": cards_by_title,
        }

        return _CACHE


def get_xtitle_by_id(title_id: int) -> Optional[Dict[str, Any]]:
    data = build_xcards_data()
    title = data["titles_by_id"].get(int(title_id))
    return deepcopy(title) if title else None


def get_xcharacter_by_id(character_id: int) -> Optional[Dict[str, Any]]:
    data = build_xcards_data()
    character = data["characters_by_id"].get(int(character_id))
    return deepcopy(character) if character else None


def get_xcard_by_id(card_id: int) -> Optional[Dict[str, Any]]:
    data = build_xcards_data()
    card = data["cards_by_id"].get(int(card_id))
    return deepcopy(card) if card else None


def get_xcard_by_no(card_no: str) -> Optional[Dict[str, Any]]:
    data = build_xcards_data()
    card = data["cards_by_no"].get(str(card_no or "").strip().lower())
    return deepcopy(card) if card else None


def get_xcards_for_character(character_id: int) -> List[Dict[str, Any]]:
    data = build_xcards_data()
    cards = data["characters_cards"].get(int(character_id), [])
    return [deepcopy(card) for card in cards]


def get_xcards_for_title(title_id: int) -> List[Dict[str, Any]]:
    data = build_xcards_data()
    cards = data["cards_by_title"].get(int(title_id), [])
    return [deepcopy(card) for card in cards]


def find_xtitle(query: Any) -> Optional[Dict[str, Any]]:
    data = build_xcards_data()
    q = str(query or "").strip()
    if not q:
        return None

    if q.isdigit():
        title = data["titles_by_id"].get(int(q))
        if title:
            return deepcopy(title)

    nq = _normalize_text(q)
    exact = data["titles_by_name"].get(nq)
    if exact:
        return deepcopy(exact)

    candidates = []
    for title in data["titles_list"]:
        name_n = _normalize_text(title["name"])
        if nq in name_n:
            candidates.append(title)

    if candidates:
        candidates.sort(key=lambda item: (len(_normalize_text(item["name"])), _normalize_text(item["name"])))
        return deepcopy(candidates[0])

    return None


def search_xcharacters(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    data = build_xcards_data()
    q = _normalize_text(query)
    if not q:
        return []

    results = []
    for item in data["characters_list"]:
        hay = f"{item['name']} {item['title']}"
        if q in _normalize_text(hay):
            results.append(deepcopy(item))

    results.sort(key=lambda item: (item["name_norm"], _normalize_text(item["title"])))
    return results[:limit]


def search_xcards(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    data = build_xcards_data()
    q = _normalize_text(query)
    if not q:
        return []

    results = []
    for item in data["cards_list"]:
        hay = f"{item['card_no']} {item['name']} {item['title']}"
        if q in _normalize_text(hay):
            results.append(deepcopy(item))

    results.sort(
        key=lambda item: (
            _normalize_text(item["title"]),
            item["name_norm"],
            str(item["card_no"]),
        )
    )
    return results[:limit]


def resolve_xcard_query(query: str) -> Dict[str, Any]:
    value = str(query or "").strip()
    if not value:
        return {"type": "none"}

    exact_card = get_xcard_by_no(value)
    if exact_card:
        return {"type": "card", "card": exact_card}

    if value.isdigit():
        numeric = int(value)
        exact_card = get_xcard_by_id(numeric)
        if exact_card:
            return {"type": "card", "card": exact_card}

        exact_character = get_xcharacter_by_id(numeric)
        if exact_character:
            return {"type": "character", "character": exact_character}

    results = search_xcharacters(value, limit=25)
    if not results:
        cards = search_xcards(value, limit=25)
        if cards:
            return {"type": "card", "card": cards[0]}
        return {"type": "none"}

    nq = _normalize_text(value)

    def _score(item: Dict[str, Any]) -> tuple:
        name = item["name_norm"]
        title = _normalize_text(item["title"])
        hay = f"{name} {title}"

        if name == nq:
            return (0, len(name), len(title))
        if hay == nq:
            return (1, len(name), len(title))
        if name.startswith(nq):
            return (2, len(name), len(title))
        if hay.startswith(nq):
            return (3, len(name), len(title))
        if nq in name:
            return (4, len(name), len(title))
        return (5, len(name), len(title))

    results.sort(key=_score)
    return {"type": "character", "character": results[0]}
