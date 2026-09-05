from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "catalog_safe_additions" / "manifest.json"
DEFAULT_BASE_OVERRIDES = ROOT / "data" / "cards_overrides.json"
DEFAULT_RUNTIME_OVERRIDES = Path("/tmp/cards_overrides.safe-runtime.json")
SUPPORTED_SCHEMA = "source.catalog-safe-additions.v1"


def _load_object(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _resolve_path(raw: str | None, fallback: Path) -> Path:
    value = str(raw or "").strip()
    if not value:
        return fallback
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except Exception:
        return 0
    return number if number > 0 else 0


def _flag_enabled(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def load_safe_additions(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = _load_object(manifest_path)
    if manifest.get("enabled") is not True:
        return {}
    if str(manifest.get("schema") or "") != SUPPORTED_SCHEMA:
        return {}

    custom_animes: list[dict[str, Any]] = []
    seen_animes: set[int] = set()
    for row in manifest.get("custom_animes") or []:
        if not isinstance(row, dict):
            continue
        anime_id = _positive_int(row.get("anime_id"))
        anime_name = str(row.get("anime") or "").strip()
        if anime_id <= 0 or not anime_name or anime_id in seen_animes:
            continue
        seen_animes.add(anime_id)
        custom_animes.append(
            {
                "anime_id": anime_id,
                "anime": anime_name,
                "banner_image": str(row.get("banner_image") or "").strip(),
                "cover_image": str(row.get("cover_image") or "").strip(),
            }
        )

    characters: list[dict[str, Any]] = []
    seen_characters: set[int] = set()
    base_dir = manifest_path.parent
    for file_name_raw in manifest.get("part_files") or []:
        file_name = str(file_name_raw or "").strip()
        if not file_name or Path(file_name).name != file_name or not file_name.endswith(".json"):
            return {}
        part = _load_object(base_dir / file_name)
        rows = part.get("characters") or []
        if not isinstance(rows, list):
            return {}
        for row in rows:
            if not isinstance(row, list) or len(row) < 4:
                return {}
            character_id = _positive_int(row[0])
            anime_id = _positive_int(row[1])
            name = str(row[2] or "").strip()
            image = str(row[3] or "").strip()
            if character_id <= 0 or anime_id <= 0 or not name or not image.startswith("https://"):
                return {}
            if character_id in seen_characters:
                return {}
            seen_characters.add(character_id)
            characters.append(
                {
                    "id": character_id,
                    "anime_id": anime_id,
                    "name": name,
                    "image": image,
                }
            )

    declared_count = _positive_int(manifest.get("character_count"))
    if declared_count <= 0 or declared_count != len(characters):
        return {}

    name_overrides: dict[str, str] = {}
    raw_names = manifest.get("character_name_overrides") or {}
    if isinstance(raw_names, dict):
        for character_id_raw, name_raw in raw_names.items():
            character_id = _positive_int(character_id_raw)
            name = str(name_raw or "").strip()
            if character_id > 0 and name:
                name_overrides[str(character_id)] = name

    return {
        "custom_animes": custom_animes,
        "custom_characters": characters,
        "character_name_overrides": name_overrides,
        "character_count": len(characters),
    }


def merge_safe_additions(base: dict[str, Any], safe: dict[str, Any]) -> dict[str, Any]:
    if not safe:
        return deepcopy(base)
    out = deepcopy(base) if isinstance(base, dict) else {}

    for key, fallback in {
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
    }.items():
        if not isinstance(out.get(key), type(fallback)):
            out[key] = deepcopy(fallback)

    manual_anime_ids = {
        _positive_int(row.get("anime_id"))
        for row in out["custom_animes"]
        if isinstance(row, dict)
    }
    for anime in safe.get("custom_animes") or []:
        anime_id = _positive_int(anime.get("anime_id"))
        if anime_id > 0 and anime_id not in manual_anime_ids:
            out["custom_animes"].append(deepcopy(anime))
            manual_anime_ids.add(anime_id)

    manual_character_ids = {
        _positive_int(row.get("id"))
        for row in out["custom_characters"]
        if isinstance(row, dict)
    }
    for character in safe.get("custom_characters") or []:
        character_id = _positive_int(character.get("id"))
        if character_id > 0 and character_id not in manual_character_ids:
            out["custom_characters"].append(deepcopy(character))
            manual_character_ids.add(character_id)

    for character_id, name in (safe.get("character_name_overrides") or {}).items():
        out["character_name_overrides"].setdefault(str(character_id), str(name))

    out["_safe_catalog_rollout"] = {
        "phase": "additions_only",
        "character_count": int(safe.get("character_count") or 0),
        "retirements_disabled": 0,
        "coins_awarded": 0,
    }
    return out


def apply_final_retirement_disables(merged: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(merged)
    existing = {
        _positive_int(value)
        for value in (out.get("deleted_characters") or [])
        if _positive_int(value) > 0
    }
    retired_ids = {
        _positive_int(value)
        for value in (plan.get("retired_ids") or [])
        if _positive_int(value) > 0
    }
    saved_ids = {
        _positive_int(value)
        for value in (plan.get("saved_ids") or [])
        if _positive_int(value) > 0
    }
    if not retired_ids or retired_ids & saved_ids:
        raise ValueError("plano final de aposentadoria inválido para materialização")

    out["deleted_characters"] = sorted(existing | retired_ids)
    metadata = dict(out.get("_safe_catalog_rollout") or {})
    metadata.update(
        {
            "phase": "additions_plus_final_catalog_disabled",
            "retirements_disabled": len(retired_ids),
            "retirement_final_hash": str(plan.get("actual_final_retire_ids_sha256") or ""),
            "saved_by_collection_count": len(saved_ids),
            "coins_awarded": 0,
        }
    )
    out["_safe_catalog_rollout"] = metadata
    return out


def prepare_runtime_safe_catalog() -> bool:
    manifest_path = _resolve_path(
        os.getenv("CATALOG_SAFE_ADDITIONS_MANIFEST_PATH"),
        DEFAULT_MANIFEST,
    )
    safe = load_safe_additions(manifest_path)
    if not safe:
        print("CATALOG_SAFE_ROLLOUT disabled_or_invalid", flush=True)
        return False

    base_path = _resolve_path(os.getenv("CARDS_OVERRIDES_PATH"), DEFAULT_BASE_OVERRIDES)
    base = _load_object(base_path)
    merged = merge_safe_additions(base, safe)

    retired_count = 0
    if _flag_enabled("SOURCE_CATALOG_RETIREMENTS_ENABLED"):
        from utils.catalog_retirement_plan import load_final_retirement_plan

        plan = load_final_retirement_plan()
        merged = apply_final_retirement_disables(merged, plan)
        retired_count = len(plan["retired_ids"])

    output_path = _resolve_path(
        os.getenv("CATALOG_SAFE_RUNTIME_OVERRIDES_PATH"),
        DEFAULT_RUNTIME_OVERRIDES,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="catalog_safe_", suffix=".json", dir=str(output_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp_name, output_path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)

    os.environ["CARDS_OVERRIDES_PATH"] = str(output_path)
    print(
        f"CATALOG_SAFE_ROLLOUT active characters={safe['character_count']} "
        f"animes={len(safe['custom_animes'])} retirements_disabled={retired_count}",
        flush=True,
    )
    return True
