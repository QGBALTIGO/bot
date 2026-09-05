from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "catalog_franchise_gaps.must_haves.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_franchise_gaps.json"

# Sequências que o Source não quer expor como uma categoria separada. Qualquer
# candidato detectado nelas é associado à categoria canônica da franquia.
CANONICAL_ANIME_TARGETS: dict[int, dict[str, Any]] = {
    213702: {
        "target_anime_id": 147105,
        "target_anime": "Witch Hat Atelier",
        "reason": "consolidate_sequel_into_base_franchise",
    },
}

# Núcleo explicitamente obrigatório. Se algum destes cair em REVIEW por uma
# oscilação de metadados, continua sendo promovido para ADD.
CANONICAL_CHARACTER_TARGETS: dict[int, dict[str, Any]] = {
    129840: {"target_anime_id": 147105, "target_anime": "Witch Hat Atelier", "role": "MAIN"},
    129841: {"target_anime_id": 147105, "target_anime": "Witch Hat Atelier", "role": "MAIN"},
    129842: {"target_anime_id": 147105, "target_anime": "Witch Hat Atelier", "role": "SUPPORTING"},
    129839: {"target_anime_id": 147105, "target_anime": "Witch Hat Atelier", "role": "SUPPORTING"},
    129838: {"target_anime_id": 147105, "target_anime": "Witch Hat Atelier", "role": "SUPPORTING"},
    137972: {"target_anime_id": 147105, "target_anime": "Witch Hat Atelier", "role": "SUPPORTING"},
}


def _cid(row: Any) -> int:
    try:
        return int((row or {}).get("id") or 0)
    except Exception:
        return 0


def _target_id(row: Any) -> int:
    try:
        return int((row or {}).get("target_anime_id") or 0)
    except Exception:
        return 0


def normalize_targets(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    out = dict(payload)
    additions = [dict(row) for row in (payload.get("character_add_candidates") or []) if isinstance(row, dict)]
    reviews = [dict(row) for row in (payload.get("review_character_add_candidates") or []) if isinstance(row, dict)]

    by_id: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    remapped: list[int] = []
    remapped_adds: list[int] = []
    remapped_reviews: list[int] = []
    promoted: list[int] = []

    def absorb(row: dict[str, Any], *, from_review: bool) -> None:
        cid = _cid(row)
        if cid <= 0:
            return
        current = by_id.get(cid)
        if current is None:
            current = dict(row)
            by_id[cid] = current
            order.append(cid)
        elif str(current.get("decision") or "").upper() != "ADD" and str(row.get("decision") or "").upper() == "ADD":
            current.update(row)

        old_target = _target_id(current)
        character_target = CANONICAL_CHARACTER_TARGETS.get(cid)
        anime_target = CANONICAL_ANIME_TARGETS.get(old_target)
        canonical = character_target or anime_target
        if not canonical:
            return

        new_target = int(canonical["target_anime_id"])
        current["target_anime_id"] = new_target
        current["target_anime"] = str(canonical["target_anime"])
        current["source_media_id"] = new_target
        current["franchise_status"] = "MUST_HAVE_FRANCHISE"

        if character_target:
            current["role"] = str(current.get("role") or character_target.get("role") or "SUPPORTING")
            if str(current.get("decision") or "REVIEW").upper() != "ADD":
                current["decision"] = "ADD"
                promoted.append(cid)
            current["catalog_reason"] = "canonical_must_have_target"
        else:
            current["catalog_reason"] = str(anime_target.get("reason") or "canonical_franchise_target")

        if old_target != new_target:
            remapped.append(cid)
            if str(current.get("decision") or "REVIEW").upper() == "ADD":
                remapped_adds.append(cid)
            else:
                remapped_reviews.append(cid)

    for row in additions:
        absorb(row, from_review=False)
    for row in reviews:
        absorb(row, from_review=True)

    normalized_additions: list[dict[str, Any]] = []
    normalized_reviews: list[dict[str, Any]] = []
    for cid in order:
        row = by_id[cid]
        if str(row.get("decision") or "").upper() == "ADD":
            normalized_additions.append(row)
        else:
            normalized_reviews.append(row)

    normalized_additions.sort(key=lambda row: (-int(row.get("favourites") or 0), str(row.get("name") or "").casefold(), _cid(row)))
    normalized_reviews.sort(key=lambda row: (-int(row.get("favourites") or 0), str(row.get("name") or "").casefold(), _cid(row)))

    out["character_add_candidates"] = normalized_additions
    out["review_character_add_candidates"] = normalized_reviews
    summary = dict(out.get("summary") or {})
    summary["definite_character_add_candidates"] = len(normalized_additions)
    summary["review_character_add_candidates"] = len(normalized_reviews)
    summary["canonical_targets_remapped"] = len(set(remapped))
    summary["canonical_add_targets_remapped"] = len(set(remapped_adds))
    summary["canonical_review_targets_remapped"] = len(set(remapped_reviews))
    summary["canonical_must_have_reviews_promoted"] = len(set(promoted))
    out["summary"] = summary
    out["canonical_target_normalization"] = {
        "remapped_ids": sorted(set(remapped)),
        "remapped_add_ids": sorted(set(remapped_adds)),
        "remapped_review_ids": sorted(set(remapped_reviews)),
        "promoted_from_review_ids": sorted(set(promoted)),
        "canonical_anime_targets": {str(aid): dict(spec) for aid, spec in CANONICAL_ANIME_TARGETS.items()},
        "canonical_character_targets": {str(cid): dict(spec) for cid, spec in CANONICAL_CHARACTER_TARGETS.items()},
    }
    return out, {
        "remapped": len(set(remapped)),
        "remapped_adds": len(set(remapped_adds)),
        "remapped_reviews": len(set(remapped_reviews)),
        "promoted": len(set(promoted)),
        "additions": len(normalized_additions),
        "reviews": len(normalized_reviews),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normaliza candidatos para a categoria canônica consolidada da franquia.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    normalized, stats = normalize_targets(payload)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_CANONICAL_TARGETS", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
