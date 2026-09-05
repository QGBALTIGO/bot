from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "catalog_cleanup_audit_refined.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_cleanup_audit.json"


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def resolve_review_decision(*, role: str | None, favourites: int, relevance_rank: int | None) -> tuple[str, str]:
    """Resolve apenas casos claros que ainda ficaram em REVIEW.

    Política deliberadamente conservadora:
    - nunca rebaixa uma decisão KEEP já existente;
    - nunca aposenta automaticamente personagem com >=10 favoritos;
    - personagens muito cedo na conexão da obra recebem proteção;
    - BACKGROUND exige sinal mais forte para continuar colecionável.
    """
    role_norm = str(role or "").upper()
    fav = max(0, _int(favourites))
    rank = _int(relevance_rank, 0)
    rank_known = rank > 0

    if role_norm == "MAIN":
        return "KEEP", "review_resolution_main_character"

    if role_norm == "BACKGROUND":
        if fav >= 15:
            return "KEEP", f"review_resolution_background_favourites={fav}>=15"
        if fav <= 8 and (not rank_known or rank > 8):
            return "RETIRE", f"review_resolution_background_low_interest favourites={fav} rank={rank or 'unknown'}"
        return "REVIEW", "review_resolution_background_ambiguous"

    if role_norm == "SUPPORTING":
        if fav >= 15:
            return "KEEP", f"review_resolution_favourites={fav}>=15"
        if rank_known and rank <= 8:
            return "KEEP", f"review_resolution_supporting_rank={rank}<=8"
        if rank_known and rank <= 20 and fav >= 8:
            return "KEEP", f"review_resolution_supporting_rank={rank} favourites={fav}"

        # Aposentadoria automática só ocorre abaixo de 10 favoritos.
        if fav <= 2 and (not rank_known or rank > 15):
            return "RETIRE", f"review_resolution_very_low_interest favourites={fav} rank={rank or 'unknown'}"
        if rank_known and rank > 30 and fav <= 4:
            return "RETIRE", f"review_resolution_low_interest favourites={fav} rank={rank}"
        if rank_known and rank > 75 and fav <= 6:
            return "RETIRE", f"review_resolution_low_interest favourites={fav} rank={rank}"
        if rank_known and rank > 200 and fav < 10:
            return "RETIRE", f"review_resolution_deep_catalog favourites={fav} rank={rank}"

        return "REVIEW", "review_resolution_ambiguous"

    # Metadado de papel inesperado: não decide automaticamente.
    return "REVIEW", "review_resolution_unknown_role"


def resolve_reviews(audit: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    out = deepcopy(audit)
    reports = out.get("anime_reports") or {}
    appearances_by_id: dict[int, list[dict[str, Any]]] = {}
    transitions = {"review_to_keep": 0, "review_to_retire": 0, "review_remaining": 0}

    for anime_id, report in reports.items():
        if not isinstance(report, dict):
            continue
        counts = {"KEEP": 0, "REVIEW": 0, "RETIRE": 0}
        rows: list[dict[str, Any]] = []
        for row in report.get("current_characters") or []:
            if not isinstance(row, dict):
                continue
            enriched = dict(row)
            original = str(row.get("decision") or "REVIEW").upper()
            decision = original
            reason = str(row.get("decision_reason") or row.get("reason") or "")
            if original == "REVIEW":
                decision, reason = resolve_review_decision(
                    role=row.get("role"),
                    favourites=_int(row.get("favourites")),
                    relevance_rank=row.get("relevance_rank"),
                )
                if decision == "KEEP":
                    transitions["review_to_keep"] += 1
                elif decision == "RETIRE":
                    transitions["review_to_retire"] += 1
                else:
                    transitions["review_remaining"] += 1
            enriched["decision"] = decision
            enriched["decision_reason"] = reason
            enriched["review_resolution_applied"] = original == "REVIEW"
            rows.append(enriched)
            counts[decision] = counts.get(decision, 0) + 1
            cid = _int(row.get("id"))
            if cid > 0:
                appearances_by_id.setdefault(cid, []).append({
                    "anime_id": _int(anime_id),
                    "decision": decision,
                    "reason": reason,
                })

        report["current_characters"] = sorted(
            rows,
            key=lambda x: (
                {"KEEP": 0, "REVIEW": 1, "RETIRE": 2}.get(str(x.get("decision") or ""), 9),
                -_int(x.get("favourites")),
                str(x.get("name") or "").casefold(),
            ),
        )
        report["counts"] = counts
        report["recommended_total_after_review_resolution"] = counts.get("KEEP", 0) + counts.get("REVIEW", 0)

    original_global = out.get("global_decisions") or {}
    all_ids = set(appearances_by_id)
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
        values = {str(x.get("decision") or "REVIEW").upper() for x in appearances if isinstance(x, dict)}
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
        "review_to_keep": transitions["review_to_keep"],
        "review_to_retire": transitions["review_to_retire"],
        "review_remaining_after_resolution": transitions["review_remaining"],
    })
    out["version"] = max(4, _int(out.get("version")))
    out["review_resolution"] = {
        "policy": "conservative_second_pass",
        "never_auto_retire_favourites_gte": 10,
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
    parser = argparse.ArgumentParser(description="Resolve casos claros do REVIEW sem arriscar personagens reconhecíveis.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    audit = json.loads(Path(args.input).read_text(encoding="utf-8"))
    resolved, stats = resolve_reviews(audit)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_REVIEW_RESOLUTION", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
