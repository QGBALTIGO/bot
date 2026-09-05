from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERRIDES = ROOT / "data" / "cards_overrides.json"
DEFAULT_DATASET = ROOT / "data" / "personagens_anilist.txt"
DEFAULT_AUDIT = ROOT / "data" / "catalog_cleanup_audit.json"
DEFAULT_FRANCHISE = ROOT / "data" / "catalog_franchise_gaps.json"
DEFAULT_OUTPUT = ROOT / "data" / "cards_overrides.cleanup_proposal.json"

# Só cria categoria nova automaticamente para franquias realmente populares.
# O restante continua no relatório para revisão manual.
AUTO_NEW_ANIME_MAX_RANK = 125
AUTO_NEW_ANIME_MIN_POPULARITY = 300_000


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def _int_set(values: Any) -> set[int]:
    out: set[int] = set()
    for value in values or []:
        try:
            number = int(value)
        except Exception:
            continue
        if number > 0:
            out.add(number)
    return out


def base_catalog_ids(dataset_path: Path = DEFAULT_DATASET) -> tuple[set[int], set[int]]:
    raw = load_json(dataset_path, {})
    items = raw.get("items", []) if isinstance(raw, dict) else raw
    anime_ids: set[int] = set()
    character_ids: set[int] = set()
    for anime in items or []:
        if not isinstance(anime, dict):
            continue
        try:
            aid = int(anime.get("anime_id") or 0)
        except Exception:
            aid = 0
        if aid > 0:
            anime_ids.add(aid)
        for ch in anime.get("characters", []) or []:
            if not isinstance(ch, dict):
                continue
            try:
                cid = int(ch.get("id") or 0)
            except Exception:
                cid = 0
            if cid > 0:
                character_ids.add(cid)
    return anime_ids, character_ids


def _missing_franchise_is_high_confidence(plan: dict[str, Any]) -> bool:
    media = plan.get("missing_popular_media") or plan.get("component_media") or []
    if not media:
        return False
    best = min(
        (row for row in media if isinstance(row, dict)),
        key=lambda row: int(row.get("popularity_rank") or 999999),
        default=None,
    )
    if not best:
        return False
    rank = int(best.get("popularity_rank") or 999999)
    popularity = int(best.get("popularity") or 0)
    return rank <= AUTO_NEW_ANIME_MAX_RANK or popularity >= AUTO_NEW_ANIME_MIN_POPULARITY


def build_proposal(
    overrides: dict[str, Any],
    audit: dict[str, Any],
    franchise: dict[str, Any],
    *,
    base_anime_ids: set[int],
    base_character_ids: set[int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposal = deepcopy(overrides) if isinstance(overrides, dict) else {}
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
        if not isinstance(proposal.get(key), type(fallback)):
            proposal[key] = deepcopy(fallback)

    existing_custom_animes: dict[int, dict[str, Any]] = {}
    for row in proposal.get("custom_animes") or []:
        if not isinstance(row, dict):
            continue
        try:
            aid = int(row.get("anime_id") or 0)
        except Exception:
            aid = 0
        if aid > 0:
            existing_custom_animes[aid] = deepcopy(row)

    existing_custom_chars: dict[int, dict[str, Any]] = {}
    for row in proposal.get("custom_characters") or []:
        if not isinstance(row, dict):
            continue
        try:
            cid = int(row.get("id") or 0)
        except Exception:
            cid = 0
        if cid > 0:
            existing_custom_chars[cid] = deepcopy(row)

    deleted = _int_set(proposal.get("deleted_characters"))
    refined_retire = _int_set(audit.get("retire_ids"))
    deleted.update(refined_retire)

    current_anime_ids = set(base_anime_ids) | set(existing_custom_animes)
    current_character_ids = set(base_character_ids) | set(existing_custom_chars)

    new_anime_ids: set[int] = set()
    skipped_missing_animes: list[dict[str, Any]] = []
    for plan in franchise.get("missing_franchises") or []:
        if not isinstance(plan, dict) or str(plan.get("status") or "") != "MISSING_FRANCHISE":
            continue
        try:
            target_id = int(plan.get("target_anime_id") or 0)
        except Exception:
            continue
        if target_id <= 0 or target_id in current_anime_ids:
            continue
        if not _missing_franchise_is_high_confidence(plan):
            skipped_missing_animes.append({
                "anime_id": target_id,
                "anime": str(plan.get("target_anime") or f"Anime {target_id}"),
                "reason": "below_auto_popularity_threshold",
            })
            continue
        existing_custom_animes[target_id] = {
            "anime_id": target_id,
            "anime": str(plan.get("target_anime") or f"Anime {target_id}").strip(),
            "banner_image": "",
            "cover_image": "",
            "_catalog_source": "franchise_cleanup_v1",
        }
        current_anime_ids.add(target_id)
        new_anime_ids.add(target_id)

    added_char_ids: set[int] = set()
    skipped_chars: list[dict[str, Any]] = []
    for row in franchise.get("character_add_candidates") or []:
        if not isinstance(row, dict) or str(row.get("decision") or "") != "ADD":
            continue
        try:
            cid = int(row.get("id") or 0)
            aid = int(row.get("target_anime_id") or 0)
        except Exception:
            continue
        if cid <= 0 or aid <= 0:
            continue
        if cid in current_character_ids:
            continue
        if aid not in current_anime_ids:
            skipped_chars.append({
                "id": cid,
                "name": str(row.get("name") or cid),
                "target_anime_id": aid,
                "reason": "target_anime_not_auto_added",
            })
            continue
        name = str(row.get("name") or f"Personagem {cid}").strip()
        image = str(row.get("anilist_image_reference") or "").strip()
        existing_custom_chars[cid] = {
            "id": cid,
            "anime_id": aid,
            "anime": str(row.get("target_anime") or f"Anime {aid}").strip(),
            "name": name,
            # Temporário: o Image Curator substituirá. AniList não é a fonte final.
            "image": image,
            "_catalog_source": "franchise_cleanup_v1",
            "_image_status": "temporary_anilist_reference" if image else "missing_image_pending_curator",
            "_role": str(row.get("role") or ""),
            "_favourites": int(row.get("favourites") or 0),
        }
        current_character_ids.add(cid)
        added_char_ids.add(cid)
        # Um personagem que estamos adicionando nunca pode permanecer aposentado.
        deleted.discard(cid)

    proposal["deleted_characters"] = sorted(deleted)
    proposal["custom_animes"] = sorted(existing_custom_animes.values(), key=lambda row: (str(row.get("anime") or "").casefold(), int(row.get("anime_id") or 0)))
    proposal["custom_characters"] = sorted(existing_custom_chars.values(), key=lambda row: (int(row.get("anime_id") or 0), str(row.get("name") or "").casefold(), int(row.get("id") or 0)))

    stats = {
        "refined_retire_candidates": len(refined_retire),
        "total_deleted_characters_after_merge": len(deleted),
        "new_anime_ids": sorted(new_anime_ids),
        "new_animes_added": len(new_anime_ids),
        "new_character_ids": sorted(added_char_ids),
        "new_characters_added": len(added_char_ids),
        "missing_animes_left_for_review": skipped_missing_animes,
        "characters_left_for_review": skipped_chars,
        "anilist_images_are_temporary_only": True,
    }
    return proposal, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Monta proposta de cards_overrides com aposentadorias refinadas e lacunas de franquia, sem alterar produção.")
    parser.add_argument("--overrides", default=str(DEFAULT_OVERRIDES))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--franchise", default=str(DEFAULT_FRANCHISE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    overrides = load_json(Path(args.overrides), {})
    audit = load_json(Path(args.audit), {})
    franchise = load_json(Path(args.franchise), {})
    base_anime_ids, base_character_ids = base_catalog_ids(Path(args.dataset))
    proposal, stats = build_proposal(
        overrides,
        audit,
        franchise,
        base_anime_ids=base_anime_ids,
        base_character_ids=base_character_ids,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_OVERRIDE_PROPOSAL", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
