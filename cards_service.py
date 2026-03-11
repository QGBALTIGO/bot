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

            chars_clean.append({
                "id": cid,
                "name": name,
                "image": image,
                "anime_id": anime_id,
                "anime": anime_name,
            })

        chars_clean.sort(key=lambda x: _normalize_text(x["name"]))

        cleaned.append({
            "anime_id": anime_id,
            "anime": anime_name,
            "banner_image": banner_image,
            "cover_image": cover_image,
            "characters": chars_clean,
        })

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

    return data


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

        animes_by_id = {}
        characters_by_id = {}
        characters_by_anime = {}

        for anime in assets:

            anime_id = int(anime["anime_id"])
            anime_name = anime["anime"]

            anime_obj = {
                "anime_id": anime_id,
                "anime": anime_name,
                "banner_image": anime.get("banner_image", ""),
                "cover_image": anime.get("cover_image", ""),
                "characters": [],
            }

            animes_by_id[anime_id] = anime_obj
            characters_by_anime[anime_id] = []

            for ch in anime.get("characters", []):

                cid = int(ch["id"])

                name = overrides["character_name_overrides"].get(
                    str(cid), ch["name"]
                )

                db_image = get_global_character_image(cid)

                if db_image:
                    image = db_image
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

        _CACHE = {
            "characters_by_id": characters_by_id,
            "characters_by_anime": characters_by_anime,
            "animes_by_id": animes_by_id,
        }

        return _CACHE


def override_set_character_image(character_id: int, image_url: str, updated_by: int = 0) -> None:

    set_global_character_image(
        character_id=int(character_id),
        image_url=str(image_url).strip(),
        updated_by=int(updated_by),
    )

    reload_cards_cache()


def override_delete_character_image(character_id: int) -> None:

    delete_global_character_image(int(character_id))

    reload_cards_cache()


def get_character_by_id(character_id: int):

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
