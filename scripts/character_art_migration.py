from __future__ import annotations

import argparse
import json
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from cards_service import build_cards_final_data, reload_cards_cache
from database import set_global_character_image
from utils.public_character_image import public_origin


@dataclass(frozen=True)
class MatchResult:
    status: str
    source_name: str
    source_anime: str
    source_image_url: str
    character_id: int | None = None
    source_character_id: str | None = None
    matched_name: str | None = None
    matched_anime: str | None = None
    previous_image_url: str | None = None
    reason: str | None = None


def normalize_identity(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    cleaned = []
    for ch in text:
        cleaned.append(ch if ch.isalnum() else " ")
    return " ".join("".join(cleaned).split())


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("items", [])
    if not isinstance(payload, list):
        raise ValueError("manifest must be a list or an object with an items list")
    return [item for item in payload if isinstance(item, dict)]


def _read_aliases(path: Path | None) -> dict[str, int]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("aliases file must be a JSON object")
    aliases: dict[str, int] = {}
    for raw_key, raw_value in payload.items():
        try:
            character_id = int(raw_value)
        except (TypeError, ValueError):
            continue
        if character_id > 0:
            aliases[normalize_identity(raw_key)] = character_id
    return aliases


def _catalog_indexes() -> tuple[dict[int, dict[str, Any]], dict[tuple[str, str], list[int]], dict[str, list[int]]]:
    characters = build_cards_final_data()["characters_by_id"]
    by_id: dict[int, dict[str, Any]] = {int(cid): dict(meta) for cid, meta in characters.items()}
    by_name_anime: dict[tuple[str, str], list[int]] = {}
    by_name: dict[str, list[int]] = {}

    for cid, meta in by_id.items():
        name_key = normalize_identity(meta.get("name"))
        anime_key = normalize_identity(meta.get("anime"))
        if name_key:
            by_name.setdefault(name_key, []).append(cid)
            if anime_key:
                by_name_anime.setdefault((name_key, anime_key), []).append(cid)

    return by_id, by_name_anime, by_name


def _source_alias_keys(item: dict[str, Any]) -> Iterable[str]:
    name = str(item.get("name") or item.get("character") or "").strip()
    anime = str(item.get("anime") or item.get("series") or "").strip()
    source_id = str(item.get("source_character_id") or item.get("seal_id") or "").strip()
    if source_id:
        yield normalize_identity(f"id:{source_id}")
    if name and anime:
        yield normalize_identity(f"{name} | {anime}")
    if name:
        yield normalize_identity(name)


def plan_character_art_updates(
    manifest: list[dict[str, Any]],
    aliases: dict[str, int] | None = None,
) -> list[MatchResult]:
    aliases = aliases or {}
    by_id, by_name_anime, by_name = _catalog_indexes()
    results: list[MatchResult] = []

    for item in manifest:
        name = str(item.get("name") or item.get("character") or "").strip()
        anime = str(item.get("anime") or item.get("series") or "").strip()
        image_url = str(item.get("image_url") or item.get("img_url") or item.get("image") or "").strip()
        source_id = str(item.get("source_character_id") or item.get("seal_id") or "").strip() or None

        if not image_url.startswith("https://"):
            results.append(MatchResult(
                status="invalid",
                source_name=name,
                source_anime=anime,
                source_image_url=image_url,
                source_character_id=source_id,
                reason="image_url must use https",
            ))
            continue

        explicit_id = item.get("character_id")
        candidate_id: int | None = None
        if explicit_id not in (None, ""):
            try:
                parsed_id = int(explicit_id)
            except (TypeError, ValueError):
                parsed_id = 0
            if parsed_id in by_id:
                candidate_id = parsed_id
            else:
                results.append(MatchResult(
                    status="unmatched",
                    source_name=name,
                    source_anime=anime,
                    source_image_url=image_url,
                    source_character_id=source_id,
                    reason=f"explicit character_id {explicit_id!r} not found in Source catalog",
                ))
                continue

        if candidate_id is None:
            for alias_key in _source_alias_keys(item):
                mapped = aliases.get(alias_key)
                if mapped in by_id:
                    candidate_id = mapped
                    break

        name_key = normalize_identity(name)
        anime_key = normalize_identity(anime)
        if candidate_id is None and name_key and anime_key:
            ids = by_name_anime.get((name_key, anime_key), [])
            if len(ids) == 1:
                candidate_id = ids[0]
            elif len(ids) > 1:
                results.append(MatchResult(
                    status="ambiguous",
                    source_name=name,
                    source_anime=anime,
                    source_image_url=image_url,
                    source_character_id=source_id,
                    reason=f"{len(ids)} Source characters share the same normalized name + anime",
                ))
                continue

        if candidate_id is None and name_key:
            ids = by_name.get(name_key, [])
            if len(ids) == 1:
                candidate_id = ids[0]
            elif len(ids) > 1:
                results.append(MatchResult(
                    status="ambiguous",
                    source_name=name,
                    source_anime=anime,
                    source_image_url=image_url,
                    source_character_id=source_id,
                    reason=f"{len(ids)} Source characters share the normalized name; anime/alias required",
                ))
                continue

        if candidate_id is None:
            results.append(MatchResult(
                status="unmatched",
                source_name=name,
                source_anime=anime,
                source_image_url=image_url,
                source_character_id=source_id,
                reason="no Source character matched",
            ))
            continue

        meta = by_id[candidate_id]
        results.append(MatchResult(
            status="matched",
            source_name=name,
            source_anime=anime,
            source_image_url=image_url,
            character_id=candidate_id,
            source_character_id=source_id,
            matched_name=str(meta.get("name") or ""),
            matched_anime=str(meta.get("anime") or ""),
            previous_image_url=str(meta.get("image") or "") or None,
        ))

    return results


def portrait_proxy_url(source_url: str, origin: str | None = None) -> str:
    base = str(origin or public_origin() or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("BASE_URL/RAILWAY_PUBLIC_DOMAIN is required to build portrait proxy URLs")
    return f"{base}/api/image-proxy?crop=portrait&url={quote(source_url, safe='')}"


def apply_character_art_updates(
    results: Iterable[MatchResult],
    *,
    updated_by: int,
    use_portrait_proxy: bool,
    origin: str | None = None,
) -> int:
    applied = 0
    for result in results:
        if result.status != "matched" or not result.character_id:
            continue
        image_url = result.source_image_url
        if use_portrait_proxy:
            image_url = portrait_proxy_url(image_url, origin=origin)
        set_global_character_image(result.character_id, image_url, int(updated_by))
        applied += 1
    if applied:
        reload_cards_cache()
    return applied


def summarize(results: Iterable[MatchResult]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    return dict(sorted(summary.items()))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Match imported character art to existing Source character IDs without changing ownership.",
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--aliases", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=Path("character_art_migration_report.json"))
    parser.add_argument("--apply", action="store_true", help="write matched image overrides to PostgreSQL")
    parser.add_argument("--updated-by", type=int, default=0)
    parser.add_argument("--portrait-proxy", action="store_true", help="store Source /api/image-proxy 2:3 URLs")
    parser.add_argument("--origin", default=None, help="override Source public origin used by --portrait-proxy")
    args = parser.parse_args()

    manifest = _read_manifest(args.manifest)
    aliases = _read_aliases(args.aliases)
    results = plan_character_art_updates(manifest, aliases=aliases)
    summary = summarize(results)

    report = {
        "summary": summary,
        "ownership_strategy": "preserve character_id; only global image override is changed",
        "items": [asdict(result) for result in results],
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False))
    print(f"report={args.report}")

    if args.apply:
        applied = apply_character_art_updates(
            results,
            updated_by=args.updated_by,
            use_portrait_proxy=args.portrait_proxy,
            origin=args.origin,
        )
        print(f"applied={applied}")


if __name__ == "__main__":
    main()
