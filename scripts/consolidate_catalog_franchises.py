from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "data" / "personagens_anilist.txt"
DEFAULT_AUDIT = ROOT / "data" / "catalog_cleanup_audit.json"
DEFAULT_FRANCHISE = ROOT / "data" / "catalog_franchise_gaps.json"
DEFAULT_PROPOSAL = ROOT / "data" / "cards_overrides.cleanup_proposal.json"
DEFAULT_OUTPUT = ROOT / "data" / "cards_overrides.cleanup_consolidated.json"

CANONICAL_FRANCHISE_NAMES: dict[int, str] = {
    356: "Fate",
    113415: "Jujutsu Kaisen",
}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except Exception:
        return 0
    return number if number > 0 else 0


def _int_set(values: Any) -> set[int]:
    return {number for number in (_positive_int(value) for value in (values or [])) if number > 0}


def dataset_index(dataset: Any) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    items = dataset.get("items", []) if isinstance(dataset, dict) else dataset
    anime_by_id: dict[int, dict[str, Any]] = {}
    char_by_id: dict[int, dict[str, Any]] = {}
    for anime in items or []:
        if not isinstance(anime, dict):
            continue
        aid = _positive_int(anime.get("anime_id"))
        if aid <= 0:
            continue
        anime_by_id[aid] = anime
        for ch in anime.get("characters") or []:
            if not isinstance(ch, dict):
                continue
            cid = _positive_int(ch.get("id"))
            if cid > 0:
                char_by_id.setdefault(cid, ch)
    return anime_by_id, char_by_id


def reliable_audit_rows(audit: dict[str, Any], anime_id: int) -> list[dict[str, Any]] | None:
    report = (audit.get("anime_reports") or {}).get(str(int(anime_id)))
    if not isinstance(report, dict):
        return None
    rows = [row for row in (report.get("current_characters") or []) if isinstance(row, dict)]
    current_count = max(0, int(report.get("current_count") or 0))
    if current_count <= 0 or not rows:
        return None
    row_ids = {_positive_int(row.get("id")) for row in rows if _positive_int(row.get("id")) > 0}
    # Uma resposta parcial do provedor nunca pode autorizar apagar/consolidar.
    if len(row_ids) < current_count:
        return None
    if any(str(row.get("decision") or "").upper() not in {"KEEP", "REVIEW", "RETIRE"} for row in rows):
        return None
    return rows


def retained_character_ids_for_anime(audit: dict[str, Any], anime_id: int) -> list[int] | None:
    rows = reliable_audit_rows(audit, anime_id)
    if rows is None:
        return None
    out = {
        _positive_int(row.get("id"))
        for row in rows
        if str(row.get("decision") or "").upper() in {"KEEP", "REVIEW"}
        and _positive_int(row.get("id")) > 0
    }
    return sorted(out)


def is_reliably_empty_after_audit(audit: dict[str, Any], anime_id: int) -> bool:
    rows = reliable_audit_rows(audit, anime_id)
    if rows is None:
        return False
    return bool(rows) and all(str(row.get("decision") or "").upper() == "RETIRE" for row in rows)


def consolidate(
    proposal: dict[str, Any],
    audit: dict[str, Any],
    franchise: dict[str, Any],
    dataset: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    out = deepcopy(proposal)
    for key, fallback in {
        "deleted_characters": [],
        "deleted_animes": [],
        "custom_animes": [],
        "custom_characters": [],
        "character_name_overrides": {},
        "anime_name_overrides": {},
    }.items():
        if not isinstance(out.get(key), type(fallback)):
            out[key] = deepcopy(fallback)

    anime_by_id, char_by_id = dataset_index(dataset)
    deleted_chars = _int_set(out.get("deleted_characters"))
    deleted_animes = _int_set(out.get("deleted_animes"))

    custom_chars: dict[int, dict[str, Any]] = {}
    for row in out.get("custom_characters") or []:
        if not isinstance(row, dict):
            continue
        cid = _positive_int(row.get("id"))
        if cid > 0:
            custom_chars[cid] = deepcopy(row)

    moved_ids: set[int] = set()
    deleted_duplicate_animes: set[int] = set()
    skipped_duplicate_animes: set[int] = set()
    consolidation_rows: list[dict[str, Any]] = []

    for plan in franchise.get("duplicate_current_franchises") or []:
        if not isinstance(plan, dict):
            continue
        target_id = _positive_int(plan.get("recommended_target_anime_id"))
        current_ids = sorted(_int_set(plan.get("current_anime_ids")))
        if target_id <= 0 or target_id not in current_ids:
            continue

        target_anime = anime_by_id.get(target_id) or {}
        target_name = CANONICAL_FRANCHISE_NAMES.get(
            target_id,
            str(plan.get("target_anime") or target_anime.get("anime") or f"Anime {target_id}").strip(),
        )

        # Só muda o nome da categoria se pelo menos uma origem realmente puder
        # ser consolidada com audit confiável.
        successful_sources: list[tuple[int, list[int]]] = []
        for source_id in current_ids:
            if source_id == target_id:
                continue
            retained_ids = retained_character_ids_for_anime(audit, source_id)
            if retained_ids is None:
                skipped_duplicate_animes.add(source_id)
                continue
            successful_sources.append((source_id, retained_ids))

        if not successful_sources:
            continue
        if target_name:
            out["anime_name_overrides"].setdefault(str(target_id), target_name)

        for source_id, retained_ids in successful_sources:
            source_anime = anime_by_id.get(source_id) or {}
            source_moved: list[int] = []
            for cid in retained_ids:
                if cid in deleted_chars:
                    continue
                base_char = char_by_id.get(cid) or {}
                existing = custom_chars.get(cid) or {}
                image = str(existing.get("image") or base_char.get("image") or "").strip()
                name = str(existing.get("name") or base_char.get("name") or f"Personagem {cid}").strip()
                custom_chars[cid] = {
                    **existing,
                    "id": cid,
                    "anime_id": target_id,
                    "anime": target_name,
                    "name": name,
                    "image": image,
                    "_catalog_source": "franchise_consolidation_v1",
                    "_consolidated_from_anime_id": source_id,
                }
                source_moved.append(cid)
                moved_ids.add(cid)

            deleted_animes.add(source_id)
            deleted_duplicate_animes.add(source_id)
            consolidation_rows.append(
                {
                    "source_anime_id": source_id,
                    "source_anime": str(source_anime.get("anime") or f"Anime {source_id}"),
                    "target_anime_id": target_id,
                    "target_anime": target_name,
                    "retained_characters_moved": len(source_moved),
                    "retained_character_ids": source_moved,
                }
            )

    target_ids_with_custom_chars = {
        _positive_int(row.get("anime_id"))
        for row in custom_chars.values()
        if _positive_int(row.get("anime_id")) > 0
    }
    empty_animes_deleted: set[int] = set()
    for anime_id in anime_by_id:
        if anime_id in deleted_animes or anime_id in target_ids_with_custom_chars:
            continue
        if not is_reliably_empty_after_audit(audit, anime_id):
            continue
        deleted_animes.add(anime_id)
        empty_animes_deleted.add(anime_id)

    out["deleted_animes"] = sorted(deleted_animes)
    out["custom_characters"] = sorted(
        custom_chars.values(),
        key=lambda row: (
            _positive_int(row.get("anime_id")),
            str(row.get("name") or "").casefold(),
            _positive_int(row.get("id")),
        ),
    )

    stats = {
        "duplicate_categories_consolidated": len(deleted_duplicate_animes),
        "duplicate_anime_ids_deleted": sorted(deleted_duplicate_animes),
        "duplicate_anime_ids_skipped_incomplete_audit": sorted(skipped_duplicate_animes),
        "retained_characters_moved": len(moved_ids),
        "retained_character_ids_moved": sorted(moved_ids),
        "empty_categories_deleted": len(empty_animes_deleted),
        "empty_anime_ids_deleted": sorted(empty_animes_deleted),
        "consolidations": consolidation_rows,
        "total_deleted_animes_after_merge": len(deleted_animes),
        "fail_closed_on_incomplete_audit": True,
    }
    return out, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolida categorias duplicadas e remove categorias vazias sem perder KEEP/REVIEW.")
    parser.add_argument("--proposal", default=str(DEFAULT_PROPOSAL))
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--franchise", default=str(DEFAULT_FRANCHISE))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    result, stats = consolidate(
        load_json(Path(args.proposal), {}),
        load_json(Path(args.audit), {}),
        load_json(Path(args.franchise), {}),
        load_json(Path(args.dataset), {}),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_FRANCHISE_CONSOLIDATION", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
