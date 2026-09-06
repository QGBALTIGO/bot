from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS = ROOT / "data" / "personagens_anilist.txt"
DEFAULT_OVERRIDES = ROOT / "data" / "cards_overrides.json"
DEFAULT_OUTPUT = Path("/tmp/source_dado_catalog.json")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _int_set(values: Any) -> set[int]:
    out: set[int] = set()
    for value in values or []:
        number = _safe_int(value)
        if number > 0:
            out.add(number)
    return out


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        raw = raw.get("items") or []
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="dado_catalog_", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def build_dado_catalog(assets: Any, overrides: dict[str, Any]) -> dict[str, Any]:
    deleted_characters = _int_set(overrides.get("deleted_characters"))
    deleted_animes = _int_set(overrides.get("deleted_animes"))
    character_names = overrides.get("character_name_overrides") or {}
    character_images = overrides.get("character_image_overrides") or {}
    anime_names = overrides.get("anime_name_overrides") or {}
    anime_banners = overrides.get("anime_banner_overrides") or {}
    anime_covers = overrides.get("anime_cover_overrides") or {}

    animes: dict[int, dict[str, Any]] = {}

    for anime in _items(assets):
        aid = _safe_int(anime.get("anime_id"))
        if aid <= 0 or aid in deleted_animes:
            continue
        name = str(anime_names.get(str(aid)) or anime.get("anime") or "").strip()
        if not name:
            continue
        record = animes.setdefault(
            aid,
            {
                "anime_id": aid,
                "anime": name,
                "banner_image": str(anime_banners.get(str(aid)) or anime.get("banner_image") or "").strip(),
                "cover_image": str(anime_covers.get(str(aid)) or anime.get("cover_image") or "").strip(),
                "characters": [],
            },
        )
        # Base pode conter a mesma obra mais de uma vez; mantém metadados mais recentes.
        record["anime"] = name
        for ch in anime.get("characters") or []:
            if not isinstance(ch, dict):
                continue
            cid = _safe_int(ch.get("id"))
            if cid <= 0 or cid in deleted_characters:
                continue
            cname = str(character_names.get(str(cid)) or ch.get("name") or "").strip()
            if not cname:
                continue
            cimage = str(character_images.get(str(cid)) or ch.get("image") or "").strip()
            record["characters"].append(
                {
                    "id": cid,
                    "name": cname,
                    "anime": name,
                    "image": cimage,
                }
            )

    for anime in overrides.get("custom_animes") or []:
        if not isinstance(anime, dict):
            continue
        aid = _safe_int(anime.get("anime_id"))
        if aid <= 0 or aid in deleted_animes:
            continue
        name = str(anime_names.get(str(aid)) or anime.get("anime") or "").strip()
        if not name:
            continue
        current = animes.setdefault(
            aid,
            {"anime_id": aid, "anime": name, "banner_image": "", "cover_image": "", "characters": []},
        )
        current["anime"] = name
        current["banner_image"] = str(
            anime_banners.get(str(aid)) or anime.get("banner_image") or current.get("banner_image") or ""
        ).strip()
        current["cover_image"] = str(
            anime_covers.get(str(aid)) or anime.get("cover_image") or current.get("cover_image") or ""
        ).strip()

    for ch in overrides.get("custom_characters") or []:
        if not isinstance(ch, dict):
            continue
        cid = _safe_int(ch.get("id"))
        aid = _safe_int(ch.get("anime_id"))
        if cid <= 0 or aid <= 0 or cid in deleted_characters or aid in deleted_animes:
            continue
        anime = animes.get(aid)
        if anime is None:
            anime_name = str(ch.get("anime") or f"Anime {aid}").strip()
            anime = {
                "anime_id": aid,
                "anime": anime_name,
                "banner_image": "",
                "cover_image": "",
                "characters": [],
            }
            animes[aid] = anime
        cname = str(character_names.get(str(cid)) or ch.get("name") or "").strip()
        if not cname:
            continue
        cimage = str(character_images.get(str(cid)) or ch.get("image") or "").strip()
        # Substitui o mesmo ID dentro da obra-alvo para não gerar duplicata.
        anime["characters"] = [row for row in anime.get("characters") or [] if _safe_int(row.get("id")) != cid]
        anime["characters"].append(
            {"id": cid, "name": cname, "anime": str(anime.get("anime") or ""), "image": cimage}
        )

    output: list[dict[str, Any]] = []
    seen_global: set[int] = set()
    for aid in sorted(animes, key=lambda value: str(animes[value].get("anime") or "").casefold()):
        anime = animes[aid]
        clean: list[dict[str, Any]] = []
        seen_local: set[int] = set()
        for ch in sorted(anime.get("characters") or [], key=lambda row: str(row.get("name") or "").casefold()):
            cid = _safe_int(ch.get("id"))
            if cid <= 0 or cid in deleted_characters or cid in seen_local:
                continue
            seen_local.add(cid)
            # O Source trata character_id como identidade global. Para o Dado,
            # também evitamos a mesma carta em várias obras na mesma rolagem.
            if cid in seen_global:
                continue
            seen_global.add(cid)
            clean.append(ch)
        if not clean:
            continue
        output.append(
            {
                "anime_id": aid,
                "anime": str(anime.get("anime") or f"Anime {aid}"),
                "banner_image": str(anime.get("banner_image") or ""),
                "cover_image": str(anime.get("cover_image") or ""),
                "characters": clean,
            }
        )

    return {
        "schema": "source.dado-catalog.materialized.v1",
        "items": output,
        "summary": {
            "animes": len(output),
            "characters": sum(len(row.get("characters") or []) for row in output),
            "deleted_characters_applied": len(deleted_characters),
            "deleted_animes_applied": len(deleted_animes),
        },
    }


def configure_dado_catalog_pool(
    *,
    assets_path: Path | None = None,
    overrides_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    assets = assets_path or Path(str(os.getenv("CARDS_ASSETS_PATH") or DEFAULT_ASSETS))
    overrides = overrides_path or Path(str(os.getenv("CARDS_OVERRIDES_PATH") or DEFAULT_OVERRIDES))
    output = output_path or Path(str(os.getenv("DADO_MATERIALIZED_PATH") or DEFAULT_OUTPUT))

    payload = build_dado_catalog(
        _load_json(assets, {}),
        _load_json(overrides, {}),
    )
    _atomic_write_json(output, payload)
    os.environ["CARDS_LOCAL_PATH"] = str(output)
    return {
        "path": str(output),
        **dict(payload.get("summary") or {}),
    }
