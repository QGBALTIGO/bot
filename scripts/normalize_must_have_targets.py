from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "catalog_franchise_gaps.must_haves.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_franchise_gaps.json"

# IDs que a auditoria de relações pode associar a uma sequência, embora a carta
# deva pertencer à categoria canônica consolidada no Source.
CANONICAL_TARGETS: dict[int, dict[str, Any]] = {
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


def normalize_targets(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    out = dict(payload)
    additions = [dict(row) for row in (payload.get("character_add_candidates") or []) if isinstance(row, dict)]
    reviews = [dict(row) for row in (payload.get("review_character_add_candidates") or []) if isinstance(row, dict)]

    by_id: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    remapped: list[int] = []
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

        canonical = CANONICAL_TARGETS.get(cid)
        if canonical:
            old_target = int(current.get("target_anime_id") or 0)
            current["target_anime_id"] = int(canonical["target_anime_id"])
            current["target_anime"] = str(canonical["target_anime"])
            current["role"] = str(current.get("role") or canonical.get("role") or "SUPPORTING")
            current["decision"] = "ADD"
            current["franchise_status"] = "MUST_HAVE_FRANCHISE"
            current["catalog_reason"] = "canonical_must_have_target"
            current["source_media_id"] = int(canonical["target_anime_id"])
            if old_target != int(canonical["target_anime_id"]):
                remapped.append(cid)
            if from_review:
                promoted.append(cid)

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
    summary["canonical_must_have_targets_remapped"] = len(set(remapped))
    summary["canonical_must_have_reviews_promoted"] = len(set(promoted))
    out["summary"] = summary
    out["canonical_target_normalization"] = {
        "remapped_ids": sorted(set(remapped)),
        "promoted_from_review_ids": sorted(set(promoted)),
        "canonical_targets": {str(cid): dict(spec) for cid, spec in CANONICAL_TARGETS.items()},
    }
    return out, {
        "remapped": len(set(remapped)),
        "promoted": len(set(promoted)),
        "additions": len(normalized_additions),
        "reviews": len(normalized_reviews),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normaliza personagens must-have para a categoria canônica da franquia.")
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
