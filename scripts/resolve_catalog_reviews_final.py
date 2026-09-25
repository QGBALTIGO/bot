from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "catalog_cleanup_audit.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_cleanup_audit.final.json"


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def resolve_final_review(
    *,
    roles: set[str],
    favourites: int,
    relevance_rank: int | None,
    media_count: int,
) -> tuple[str, str]:
    """Terceira passada: resolve apenas sinais fortes que sobraram em REVIEW.

    Princípios:
    - 10+ favoritos nunca ficam pendentes: KEEP;
    - personagem recorrente em várias entradas da franquia recebe proteção;
    - coadjuvante muito cedo na obra + algum interesse recebe proteção;
    - aposentadoria automática continua restrita a interesse muito baixo;
    - BACKGROUND ainda conhecido permanece REVIEW, não é apagado à força.
    """
    normalized_roles = {str(role or "").upper() for role in roles if str(role or "").strip()}
    fav = max(0, _int(favourites))
    rank = _int(relevance_rank, 0)
    rank_known = rank > 0
    appearances = max(1, _int(media_count, 1))

    if "MAIN" in normalized_roles:
        return "KEEP", "final_review_main_character"

    if fav >= 10:
        return "KEEP", f"final_review_favourites={fav}>=10"

    if "SUPPORTING" in normalized_roles and rank_known and rank <= 10 and fav >= 5:
        return "KEEP", f"final_review_supporting_rank={rank} favourites={fav}"

    # Recorrência em temporadas/sequências é um sinal forte de relevância.
    if appearances >= 3 and fav >= 2:
        return "KEEP", f"final_review_recurring_media={appearances} favourites={fav}"
    if appearances >= 2 and fav >= 4:
        return "KEEP", f"final_review_recurring_media={appearances} favourites={fav}"

    if normalized_roles == {"BACKGROUND"}:
        if fav <= 8 and (not rank_known or rank > 8):
            return "RETIRE", f"final_review_background_low_interest favourites={fav} rank={rank or 'unknown'}"
        return "REVIEW", "final_review_background_ambiguous"

    # Só personagens de presença única e interesse realmente baixo descem aqui.
    if appearances <= 1:
        if fav <= 1 and (not rank_known or rank > 10):
            return "RETIRE", f"final_review_very_low_interest favourites={fav} rank={rank or 'unknown'}"
        if fav <= 2 and rank_known and rank > 15:
            return "RETIRE", f"final_review_low_interest favourites={fav} rank={rank}"
        if fav <= 3 and rank_known and rank > 30:
            return "RETIRE", f"final_review_low_interest favourites={fav} rank={rank}"

    return "REVIEW", "final_review_still_ambiguous"


def resolve_final_reviews(audit: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    out = deepcopy(audit)
    reports = out.get("anime_reports") or {}

    rows_by_id: dict[int, list[dict[str, Any]]] = {}
    for anime_id, report in reports.items():
        if not isinstance(report, dict):
            continue
        for row in report.get("current_characters") or []:
            if not isinstance(row, dict):
                continue
            cid = _int(row.get("id"))
            if cid <= 0:
                continue
            rows_by_id.setdefault(cid, []).append({**row, "_anime_id": _int(anime_id)})

    original_global = out.get("global_decisions") or {}
    final_decisions: dict[int, tuple[str, str]] = {}
    transitions = {
        "review_to_keep_final": 0,
        "review_to_retire_final": 0,
        "review_remaining_final": 0,
    }

    for cid, rows in rows_by_id.items():
        current_global = str((original_global.get(str(cid)) or {}).get("decision") or "REVIEW").upper()
        if current_global != "REVIEW":
            continue

        roles = {str(row.get("role") or "").upper() for row in rows if str(row.get("role") or "").strip()}
        favourites = max((_int(row.get("favourites")) for row in rows), default=0)
        positive_ranks = [_int(row.get("relevance_rank")) for row in rows if _int(row.get("relevance_rank")) > 0]
        relevance_rank = min(positive_ranks) if positive_ranks else None
        media_count = len({row.get("_anime_id") for row in rows if _int(row.get("_anime_id")) > 0})

        decision, reason = resolve_final_review(
            roles=roles,
            favourites=favourites,
            relevance_rank=relevance_rank,
            media_count=media_count,
        )
        final_decisions[cid] = (decision, reason)
        if decision == "KEEP":
            transitions["review_to_keep_final"] += 1
        elif decision == "RETIRE":
            transitions["review_to_retire_final"] += 1
        else:
            transitions["review_remaining_final"] += 1

    appearances_by_id: dict[int, list[dict[str, Any]]] = {}
    for anime_id, report in reports.items():
        if not isinstance(report, dict):
            continue
        counts = {"KEEP": 0, "REVIEW": 0, "RETIRE": 0}
        new_rows: list[dict[str, Any]] = []
        for row in report.get("current_characters") or []:
            if not isinstance(row, dict):
                continue
            enriched = dict(row)
            cid = _int(row.get("id"))
            decision = str(row.get("decision") or "REVIEW").upper()
            reason = str(row.get("decision_reason") or "")
            if decision == "REVIEW" and cid in final_decisions:
                decision, reason = final_decisions[cid]
                enriched["final_review_resolution_applied"] = True
            enriched["decision"] = decision
            enriched["decision_reason"] = reason
            new_rows.append(enriched)
            counts[decision] = counts.get(decision, 0) + 1
            if cid > 0:
                appearances_by_id.setdefault(cid, []).append({
                    "anime_id": _int(anime_id),
                    "decision": decision,
                    "reason": reason,
                })

        report["current_characters"] = sorted(
            new_rows,
            key=lambda x: (
                {"KEEP": 0, "REVIEW": 1, "RETIRE": 2}.get(str(x.get("decision") or ""), 9),
                -_int(x.get("favourites")),
                str(x.get("name") or "").casefold(),
            ),
        )
        report["counts"] = counts
        report["recommended_total_after_final_review"] = counts.get("KEEP", 0) + counts.get("REVIEW", 0)

    all_ids: set[int] = set(rows_by_id)
    for key in original_global:
        try:
            all_ids.add(int(key))
        except Exception:
            pass

    keep_ids: list[int] = []
    review_ids: list[int] = []
    retire_ids: list[int] = []
    global_decisions: dict[str, Any] = {}
    for cid in sorted(all_ids):
        appearances = appearances_by_id.get(cid) or (original_global.get(str(cid)) or {}).get("appearances") or []
        values = {str(item.get("decision") or "REVIEW").upper() for item in appearances if isinstance(item, dict)}
        if "KEEP" in values:
            decision = "KEEP"
            keep_ids.append(cid)
        elif "REVIEW" in values or not values:
            decision = "REVIEW"
            review_ids.append(cid)
        else:
            decision = "RETIRE"
            retire_ids.append(cid)
        global_decisions[str(cid)] = {"decision": decision, "appearances": appearances}

    summary = dict(out.get("summary") or {})
    summary.update({
        "keep": len(keep_ids),
        "review": len(review_ids),
        "retire_candidates": len(retire_ids),
        "projected_unique_after_retire_before_add": len(all_ids) - len(retire_ids),
        "projected_unique_after_definite_add": len(all_ids) - len(retire_ids) + _int(summary.get("definite_add_candidates")),
        **transitions,
    })
    out["version"] = max(5, _int(out.get("version")))
    out["final_review_resolution"] = {
        "policy": "conservative_third_pass_with_recurring_media_protection",
        "favourites_gte_10_keep": True,
        "recurring_media_protection": True,
        "prior_keep_never_downgraded": True,
        **transitions,
    }
    out["summary"] = summary
    out["keep_ids"] = keep_ids
    out["review_ids"] = review_ids
    out["retire_ids"] = retire_ids
    out["global_decisions"] = global_decisions
    return out, transitions


def main() -> int:
    parser = argparse.ArgumentParser(description="Terceira passada conservadora para reduzir o REVIEW restante.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    audit = json.loads(Path(args.input).read_text(encoding="utf-8"))
    resolved, stats = resolve_final_reviews(audit)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_FINAL_REVIEW_RESOLUTION", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
