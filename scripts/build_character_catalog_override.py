from __future__ import annotations

import argparse
import json
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERRIDES = ROOT / "data" / "cards_overrides.json"
DEFAULT_RETIREMENT_MANIFEST = ROOT / "data" / "character_catalog_retirements_v1.json"

GENERIC_CHARACTER_NAMES = {
    "narrator",
    "announcer",
    "commentator",
    "spectator",
    "male student",
    "female student",
    "student",
    "teacher",
    "boy",
    "girl",
    "man",
    "woman",
    "citizen",
    "villager",
}


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected JSON object: {path}")
    return raw


def default_overrides() -> dict[str, Any]:
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


def clean_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    out = default_overrides()
    out.update(raw or {})
    for key in ("deleted_characters", "deleted_animes", "custom_animes", "custom_characters"):
        if not isinstance(out.get(key), list):
            out[key] = []
    for key in (
        "character_image_overrides",
        "character_name_overrides",
        "anime_name_overrides",
        "anime_banner_overrides",
        "anime_cover_overrides",
        "subcategories",
    ):
        if not isinstance(out.get(key), dict):
            out[key] = {}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge catalog plans into cards_overrides without editing the raw AniList dataset.")
    parser.add_argument("--cleanup-plan", required=True)
    parser.add_argument("--missing-anime-plan", required=True)
    parser.add_argument("--overrides", default=str(DEFAULT_OVERRIDES))
    parser.add_argument("--retirement-manifest", default=str(DEFAULT_RETIREMENT_MANIFEST))
    parser.add_argument("--batch-key", default="catalog-curation-pilot-v1")
    parser.add_argument("--skip-character-id", action="append", type=int, default=[])
    args = parser.parse_args()

    cleanup = load_json(Path(args.cleanup_plan))
    missing_anime = load_json(Path(args.missing_anime_plan))
    overrides_path = Path(args.overrides)
    overrides = clean_overrides(load_json(overrides_path) if overrides_path.exists() else {})
    skipped_ids = {int(x) for x in args.skip_character_id or []}

    retired_meta: dict[int, dict[str, Any]] = {}
    for row in cleanup.get("retired_characters") or []:
        if not isinstance(row, dict):
            continue
        cid = int(row.get("id") or 0)
        if cid <= 0 or cid in skipped_ids:
            continue
        retired_meta[cid] = {
            "id": cid,
            "name": str(row.get("name") or "").strip(),
            "anime_id": int(row.get("anime_id") or 0),
            "anime": str(row.get("anime") or "").strip(),
            "reason": str(row.get("reason") or "curation").strip(),
        }

    existing_deleted = {int(x) for x in overrides.get("deleted_characters") or [] if str(x).isdigit()}
    retired_ids = set(retired_meta)
    overrides["deleted_characters"] = sorted(existing_deleted | retired_ids)

    # Missing characters discovered inside an anime that already exists (e.g. an iconic
    # character omitted from the original dump).
    additions: list[dict[str, Any]] = []
    for row in cleanup.get("missing_important_characters") or []:
        if not isinstance(row, dict):
            continue
        cid = int(row.get("id") or 0)
        name = str(row.get("name") or "").strip()
        if cid <= 0 or cid in skipped_ids or normalize(name) in GENERIC_CHARACTER_NAMES:
            continue
        additions.append({
            "id": cid,
            "name": name,
            "anime_id": int(row.get("anime_id") or 0),
            "anime": str(row.get("anime") or "").strip(),
            "image": str(row.get("image") or "").strip(),
        })

    existing_custom_animes = {
        int(x.get("anime_id") or 0): x
        for x in overrides.get("custom_animes") or []
        if isinstance(x, dict) and int(x.get("anime_id") or 0) > 0
    }

    for anime in missing_anime.get("animes") or []:
        if not isinstance(anime, dict) or anime.get("error"):
            continue
        aid = int(anime.get("anime_id") or 0)
        title = str(anime.get("anime") or "").strip()
        if aid <= 0 or not title:
            continue
        if not bool(anime.get("already_in_catalog")):
            existing_custom_animes[aid] = {
                "anime_id": aid,
                "anime": title,
                "banner_image": str(anime.get("banner_image") or "").strip(),
                "cover_image": str(anime.get("cover_image") or "").strip(),
                "characters": [],
            }
        for ch in anime.get("characters") or []:
            if not isinstance(ch, dict):
                continue
            cid = int(ch.get("id") or 0)
            name = str(ch.get("name") or "").strip()
            if cid <= 0 or cid in skipped_ids or normalize(name) in GENERIC_CHARACTER_NAMES:
                continue
            additions.append({
                "id": cid,
                "name": name,
                "anime_id": aid,
                "anime": title,
                "image": str(ch.get("image") or "").strip(),
            })

    overrides["custom_animes"] = [existing_custom_animes[k] for k in sorted(existing_custom_animes)]

    # Preserve existing custom records, then append planned records. De-duplicate only the
    # exact (character, anime) association: the same AniList character may legitimately be
    # visible under Naruto and Naruto Shippuden while remaining one global collectible ID.
    custom_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
    for row in list(overrides.get("custom_characters") or []) + additions:
        if not isinstance(row, dict):
            continue
        cid = int(row.get("id") or 0)
        aid = int(row.get("anime_id") or 0)
        if cid <= 0 or aid <= 0 or cid in retired_ids:
            continue
        custom_by_pair[(cid, aid)] = {
            "id": cid,
            "name": str(row.get("name") or "").strip(),
            "anime_id": aid,
            "anime": str(row.get("anime") or "").strip(),
            "image": str(row.get("image") or "").strip(),
        }
    overrides["custom_characters"] = [custom_by_pair[k] for k in sorted(custom_by_pair, key=lambda x: (x[1], x[0]))]

    # Never leave a planned addition hidden by a previous deletion marker.
    added_ids = {int(x["id"]) for x in overrides["custom_characters"]}
    overrides["deleted_characters"] = [x for x in overrides["deleted_characters"] if int(x) not in added_ids]

    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "version": 1,
        "batch_key": str(args.batch_key),
        "generated_at_epoch": int(time.time()),
        "refund_coins_per_copy": 1,
        "retired_character_ids": sorted(retired_ids),
        "retired_characters": [retired_meta[cid] for cid in sorted(retired_meta)],
        "notes": "1 Coin is refunded for each owned copy removed. Apply with scripts/apply_character_catalog_retirement.py after catalog activation.",
    }
    manifest_path = Path(args.retirement_manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "retired_characters": len(retired_ids),
        "custom_animes_total": len(overrides["custom_animes"]),
        "custom_character_associations_total": len(overrides["custom_characters"]),
        "unique_custom_characters": len({int(x["id"]) for x in overrides["custom_characters"]}),
        "skipped_character_ids": sorted(skipped_ids),
        "overrides_path": str(overrides_path),
        "retirement_manifest": str(manifest_path),
    }
    print("CATALOG_OVERRIDE_SUMMARY", json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
