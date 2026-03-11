import json
import os
import tempfile
import unicodedata
from copy import deepcopy
from threading import RLock
from typing import Any, Dict, List, Optional

from database import (
    get_global_character_image,
    set_global_character_image,
    delete_global_character_image,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CARDS_ASSETS_PATH = os.getenv(
    "CARDS_ASSETS_PATH",
    os.path.join(DATA_DIR, "personagens_anilist.txt"),
).strip()

CARDS_OVERRIDES_PATH = os.getenv(
    "CARDS_OVERRIDES_PATH",
    os.path.join(DATA_DIR, "cards_overrides.json"),
).strip()

_LOCK = RLock()
_CACHE: Optional[Dict[str, Any]] = None


def _default_overrides() -> Dict[str, Any]:
    return {
        "deleted_characters": [],
        "deleted_animes": [],
        "custom_animes": [],
        "custom_characters": [],
        "character_image_overrides": {},
        "character_name_overrides": {},
        "anime_name_overrides": {},
        "anime_banner_overrides": {},
        "anime_cover_overrides": {},
        "subcategories": {},
    }


def _ensure_data_dir() -> None:
    os.makedirs(os.path.dirname(CARDS_OVERRIDES_PATH), exist_ok=True)


def _normalize_text(text: Any) -> str:
    text = str(text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix="cards_",
        suffix=".tmp",
        dir=os.path.dirname(path),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def load_cards_assets_raw() -> List[Dict[str, Any]]:
    if not os.path.exists(CARDS_ASSETS_PATH):
        raise FileNotFoundError(
            f"Arquivo de assets não encontrado: {CARDS_ASSETS_PATH}"
        )

    with open(CARDS_ASSETS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        items = raw.get("items", [])
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    cleaned: List[Dict[str, Any]] = []

    for anime in items:
        if not isinstance(anime, dict):
            continue

        try:
            anime_id = int(anime.get("anime_id"))
        except Exception:
            continue

        anime_name = str(anime.get("anime") or "").strip()
        if not anime_name:
            continue

        banner_image = str(anime.get("banner_image") or "").strip()
        cover_image = str(anime.get("cover_image") or "").strip()

        chars_clean: List[Dict[str, Any]] = []
        seen_ids = set()

        for ch in anime.get("characters", []) or []:
            if not isinstance(ch, dict):
                continue

            try:
                cid = int(ch.get("id"))
            except Exception:
                continue

            if cid in seen_ids:
                continue

            name = str(ch.get("name") or "").strip()
            image = str(ch.get("image") or "").strip()

            if not name:
                continue

            seen_ids.add(cid)

            chars_clean.append(
                {
                    "id": cid,
                    "name": name,
                    "image": image,
                    "anime_id": anime_id,
                    "anime": anime_name,
                }
            )

        chars_clean.sort(key=lambda x: _normalize_text(x["name"]))

        cleaned.append(
            {
                "anime_id": anime_id,
                "anime": anime_name,
                "banner_image": banner_image,
                "cover_image": cover_image,
                "characters": chars_clean,
            }
        )

    cleaned.sort(key=lambda x: _normalize_text(x["anime"]))
    return cleaned


def load_cards_overrides() -> Dict[str, Any]:
    _ensure_data_dir()

    if not os.path.exists(CARDS_OVERRIDES_PATH):
        data = _default_overrides()
        _atomic_write_json(CARDS_OVERRIDES_PATH, data)
        return data

    try:
        with open(CARDS_OVERRIDES_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}

    data = _default_overrides()
    if isinstance(raw, dict):
        data.update(raw)

    for key in ["deleted_characters", "deleted_animes", "custom_animes", "custom_characters"]:
        if not isinstance(data.get(key), list):
            data[key] = []

    for key in [
        "character_image_overrides",
        "character_name_overrides",
        "anime_name_overrides",
        "anime_banner_overrides",
        "anime_cover_overrides",
        "subcategories",
    ]:
        if not isinstance(data.get(key), dict):
            data[key] = {}

    return data


def save_cards_overrides(data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    _atomic_write_json(CARDS_OVERRIDES_PATH, data)
    reload_cards_cache()


def reload_cards_cache() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = None


def build_cards_final_data(force_reload: bool = False) -> Dict[str, Any]:
    global _CACHE

    with _LOCK:
        if _CACHE is not None and not force_reload:
            return _CACHE

        assets = load_cards_assets_raw()
        overrides = load_cards_overrides()

        deleted_animes = {int(x) for x in overrides["deleted_animes"]}
        deleted_characters = {int(x) for x in overrides["deleted_characters"]}

        animes_by_id: Dict[int, Dict[str, Any]] = {}
        characters_by_id: Dict[int, Dict[str, Any]] = {}
        characters_by_anime: Dict[int, List[Dict[str, Any]]] = {}

        for anime in assets:
            anime_id = int(anime["anime_id"])
            if anime_id in deleted_animes:
                continue

            anime_name = overrides["anime_name_overrides"].get(str(anime_id), anime["anime"])
            banner_image = overrides["anime_banner_overrides"].get(
                str(anime_id), anime.get("banner_image", "")
            )
            cover_image = overrides["anime_cover_overrides"].get(
                str(anime_id), anime.get("cover_image", "")
            )

            anime_obj = {
                "anime_id": anime_id,
                "anime": anime_name,
                "banner_image": banner_image,
                "cover_image": cover_image,
                "characters": [],
                "characters_count": 0,
            }

            animes_by_id[anime_id] = anime_obj
            characters_by_anime[anime_id] = []

            for ch in anime.get("characters", []):
                cid = int(ch["id"])
                if cid in deleted_characters:
                    continue

                name = overrides["character_name_overrides"].get(str(cid), ch["name"])

                db_image = get_global_character_image(cid)
                if db_image:
                    image = str(db_image).strip()
                else:
                    image = overrides["character_image_overrides"].get(
                        str(cid), ch.get("image", "")
                    )

                char_obj = {
                    "id": cid,
                    "name": name,
                    "image": image,
                    "anime_id": anime_id,
                    "anime": anime_name,
                }

                characters_by_id[cid] = char_obj
                characters_by_anime[anime_id].append(char_obj)

        for anime in overrides["custom_animes"]:
            if not isinstance(anime, dict):
                continue

            try:
                anime_id = int(anime.get("anime_id"))
            except Exception:
                continue

            if anime_id in deleted_animes:
                continue

            anime_name = str(anime.get("anime") or "").strip()
            if not anime_name:
                continue

            anime_obj = {
                "anime_id": anime_id,
                "anime": anime_name,
                "banner_image": str(anime.get("banner_image") or "").strip(),
                "cover_image": str(anime.get("cover_image") or "").strip(),
                "characters": [],
                "characters_count": 0,
            }

            animes_by_id[anime_id] = anime_obj
            characters_by_anime.setdefault(anime_id, [])

        for ch in overrides["custom_characters"]:
            if not isinstance(ch, dict):
                continue

            try:
                cid = int(ch.get("id"))
                anime_id = int(ch.get("anime_id"))
            except Exception:
                continue

            if cid in deleted_characters:
                continue

            anime_obj = animes_by_id.get(anime_id)
            if not anime_obj:
                anime_name = str(ch.get("anime") or f"Anime {anime_id}").strip()
                anime_obj = {
                    "anime_id": anime_id,
                    "anime": anime_name,
                    "banner_image": "",
                    "cover_image": "",
                    "characters": [],
                    "characters_count": 0,
                }
                animes_by_id[anime_id] = anime_obj
                characters_by_anime.setdefault(anime_id, [])
            else:
                anime_name = anime_obj["anime"]

            name = overrides["character_name_overrides"].get(
                str(cid), str(ch.get("name") or "").strip()
            )

            db_image = get_global_character_image(cid)
            if db_image:
                image = str(db_image).strip()
            else:
                image = overrides["character_image_overrides"].get(
                    str(cid), str(ch.get("image") or "").strip()
                )

            if not name:
                continue

            char_obj = {
                "id": cid,
                "name": name,
                "image": image,
                "anime_id": anime_id,
                "anime": anime_name,
            }

            characters_by_id[cid] = char_obj

            current = characters_by_anime.setdefault(anime_id, [])
            current = [x for x in current if int(x["id"]) != cid]
            current.append(char_obj)
            characters_by_anime[anime_id] = current

        animes_list: List[Dict[str, Any]] = []
        animes_by_name: Dict[str, Dict[str, Any]] = {}

        for anime_id, anime_obj in animes_by_id.items():
            chars = characters_by_anime.get(anime_id, [])
            chars.sort(key=lambda x: _normalize_text(x["name"]))
            anime_obj["characters_count"] = len(chars)

            anime_final = {
                "anime_id": anime_obj["anime_id"],
                "anime": anime_obj["anime"],
                "banner_image": anime_obj.get("banner_image", ""),
                "cover_image": anime_obj.get("cover_image", ""),
                "characters_count": len(chars),
            }

            animes_list.append(anime_final)
            animes_by_name[_normalize_text(anime_final["anime"])] = anime_final

        animes_list.sort(key=lambda x: _normalize_text(x["anime"]))

        subcategories: Dict[str, List[Dict[str, Any]]] = {}
        for subcat_name, ids in overrides["subcategories"].items():
            if not isinstance(ids, list):
                continue

            final_chars = []
            seen = set()

            for cid in ids:
                try:
                    cid = int(cid)
                except Exception:
                    continue

                ch = characters_by_id.get(cid)
                if not ch or cid in seen:
                    continue

                seen.add(cid)
                final_chars.append(deepcopy(ch))

            final_chars.sort(key=lambda x: _normalize_text(x["name"]))
            subcategories[str(subcat_name).strip()] = final_chars

        _CACHE = {
            "animes_list": animes_list,
            "animes_by_id": {x["anime_id"]: x for x in animes_list},
            "animes_by_name": animes_by_name,
            "characters_by_id": characters_by_id,
            "characters_by_anime": characters_by_anime,
            "subcategories": subcategories,
            "overrides": overrides,
        }

        return _CACHE


def find_anime(query: Any) -> Optional[Dict[str, Any]]:
    data = build_cards_final_data()
    q = str(query or "").strip()
    if not q:
        return None

    if q.isdigit():
        anime = data["animes_by_id"].get(int(q))
        if anime:
            return anime

    nq = _normalize_text(q)

    exact = data["animes_by_name"].get(nq)
    if exact:
        return exact

    candidates = []
    for anime in data["animes_list"]:
        name_n = _normalize_text(anime["anime"])
        if nq in name_n:
            candidates.append(anime)

    if candidates:
        candidates.sort(
            key=lambda x: (len(_normalize_text(x["anime"])), _normalize_text(x["anime"]))
        )
        return candidates[0]

    return None


def search_characters(query: str, limit: int = 100) -> List[Dict[str, Any]]:
    data = build_cards_final_data()
    q = _normalize_text(query)
    if not q:
        return []

    results = []
    for ch in data["characters_by_id"].values():
        hay = f"{ch['name']} {ch['anime']}"
        if q in _normalize_text(hay):
            results.append(deepcopy(ch))

    results.sort(key=lambda x: (_normalize_text(x["name"]), _normalize_text(x["anime"])))
    return results[:limit]


def list_subcategories() -> List[Dict[str, Any]]:
    data = build_cards_final_data()
    out = []
    for name, chars in data["subcategories"].items():
        out.append({"name": name, "count": len(chars)})
    out.sort(key=lambda x: _normalize_text(x["name"]))
    return out


def _get_overrides_copy() -> Dict[str, Any]:
    return deepcopy(load_cards_overrides())


def override_delete_character(character_id: int) -> None:
    data = _get_overrides_copy()
    cid = int(character_id)

    if cid not in [int(x) for x in data["deleted_characters"]]:
        data["deleted_characters"].append(cid)

    delete_global_character_image(cid)

    for subcat, ids in data["subcategories"].items():
        data["subcategories"][subcat] = [x for x in ids if int(x) != cid]

    data["custom_characters"] = [
        x for x in data["custom_characters"]
        if int(x.get("id", -1)) != cid
    ]

    save_cards_overrides(data)


def override_set_character_image(character_id: int, image_url: str, updated_by: int = 0) -> None:
    set_global_character_image(
        character_id=int(character_id),
        image_url=str(image_url).strip(),
        updated_by=int(updated_by or 0),
    )
    reload_cards_cache()


def override_delete_character_image(character_id: int) -> None:
    delete_global_character_image(int(character_id))
    reload_cards_cache()


def override_set_character_name(character_id: int, new_name: str) -> None:
    data = _get_overrides_copy()
    data["character_name_overrides"][str(int(character_id))] = str(new_name).strip()
    save_cards_overrides(data)


def override_add_character(
    character_id: int,
    name: str,
    anime_id: int,
    anime_name: str,
    image_url: str,
) -> None:
    data = _get_overrides_copy()
    cid = int(character_id)
    aid = int(anime_id)

    item = {
        "id": cid,
        "name": str(name).strip(),
        "anime_id": aid,
        "anime": str(anime_name).strip(),
        "image": str(image_url).strip(),
    }

    data["custom_characters"] = [
        x for x in data["custom_characters"]
        if int(x.get("id", -1)) != cid
    ]
    data["custom_characters"].append(item)

    data["deleted_characters"] = [x for x in data["deleted_characters"] if int(x) != cid]

    save_cards_overrides(data)


def override_delete_anime(anime_id: int) -> None:
    data = _get_overrides_copy()
    aid = int(anime_id)

    if aid not in [int(x) for x in data["deleted_animes"]]:
        data["deleted_animes"].append(aid)

    data["custom_animes"] = [
        x for x in data["custom_animes"]
        if int(x.get("anime_id", -1)) != aid
    ]

    chars_to_delete = [
        int(x.get("id"))
        for x in data["custom_characters"]
        if int(x.get("anime_id", -1)) == aid and str(x.get("id", "")).isdigit()
    ]
    for cid in chars_to_delete:
        delete_global_character_image(cid)

    data["custom_characters"] = [
        x for x in data["custom_characters"]
        if int(x.get("anime_id", -1)) != aid
    ]

    save_cards_overrides(data)


def override_add_anime(
    anime_id: int,
    anime_name: str,
    banner_image: str = "",
    cover_image: str = "",
) -> None:
    data = _get_overrides_copy()
    aid = int(anime_id)

    item = {
        "anime_id": aid,
        "anime": str(anime_name).strip(),
        "banner_image": str(banner_image).strip(),
        "cover_image": str(cover_image).strip(),
        "characters": [],
    }

    data["custom_animes"] = [
        x for x in data["custom_animes"]
        if int(x.get("anime_id", -1)) != aid
    ]
    data["custom_animes"].append(item)

    data["deleted_animes"] = [x for x in data["deleted_animes"] if int(x) != aid]

    save_cards_overrides(data)


def override_set_anime_banner(anime_id: int, banner_url: str) -> None:
    data = _get_overrides_copy()
    data["anime_banner_overrides"][str(int(anime_id))] = str(banner_url).strip()
    save_cards_overrides(data)


def override_set_anime_cover(anime_id: int, cover_url: str) -> None:
    data = _get_overrides_copy()
    data["anime_cover_overrides"][str(int(anime_id))] = str(cover_url).strip()
    save_cards_overrides(data)


def override_add_subcategory(name: str) -> None:
    data = _get_overrides_copy()
    key = str(name).strip()
    data["subcategories"].setdefault(key, [])
    save_cards_overrides(data)


def override_delete_subcategory(name: str) -> None:
    data = _get_overrides_copy()
    key = str(name).strip()
    if key in data["subcategories"]:
        del data["subcategories"][key]
    save_cards_overrides(data)


def override_subcategory_add_character(name: str, character_id: int) -> None:
    data = _get_overrides_copy()
    key = str(name).strip()
    cid = int(character_id)

    data["subcategories"].setdefault(key, [])

    current_ids = [int(x) for x in data["subcategories"][key]]
    if cid not in current_ids:
        data["subcategories"][key].append(cid)

    save_cards_overrides(data)


def override_subcategory_remove_character(name: str, character_id: int) -> None:
    data = _get_overrides_copy()
    key = str(name).strip()
    cid = int(character_id)

    if key in data["subcategories"]:
        data["subcategories"][key] = [x for x in data["subcategories"][key] if int(x) != cid]

    save_cards_overrides(data)


def get_character_by_id(character_id: int) -> Optional[Dict[str, Any]]:
    data = build_cards_final_data()
    ch = data["characters_by_id"].get(int(character_id))

    if not ch:
        return None

    return {
        "id": int(ch["id"]),
        "name": str(ch.get("name") or "").strip(),
        "anime": str(ch.get("anime") or "").strip(),
        "image": str(ch.get("image") or "").strip(),
        "anime_id": int(ch.get("anime_id") or 0),
    }
