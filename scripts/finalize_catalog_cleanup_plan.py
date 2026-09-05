from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "data" / "catalog_cleanup_audit.json"
DEFAULT_LIVE_REPORT = ROOT / "data" / "catalog_cleanup_live_impact.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_cleanup_final_plan.json"


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} precisa conter um objeto JSON")
    return raw


def int_set(values: Any) -> set[int]:
    out: set[int] = set()
    for value in values or []:
        try:
            number = int(value)
        except Exception:
            continue
        if number > 0:
            out.add(number)
    return out


def ids_hash(values: Any) -> str:
    canonical = ",".join(str(x) for x in sorted(int_set(values))).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def finalize_plan(audit: dict[str, Any], live_report: dict[str, Any]) -> dict[str, Any]:
    if live_report.get("read_only") is not True:
        raise ValueError("relatório live precisa declarar read_only=true")

    original_retire = int_set(audit.get("retire_ids"))
    final_retire = int_set(live_report.get("final_retire_ids"))
    moved_rows = [x for x in (live_report.get("moved_to_review") or []) if isinstance(x, dict)]
    moved_to_review = {
        int(row.get("character_id") or 0)
        for row in moved_rows
        if int(row.get("character_id") or 0) > 0
    }

    candidate_count = int(live_report.get("candidate_count") or 0)
    if candidate_count != len(original_retire):
        raise ValueError("candidate_count do relatório não corresponde à auditoria")
    if not final_retire.issubset(original_retire):
        raise ValueError("relatório live contém aposentadoria fora da auditoria")
    if not moved_to_review.issubset(original_retire):
        raise ValueError("relatório live contém REVIEW fora da auditoria")
    if final_retire & moved_to_review:
        raise ValueError("um personagem não pode estar em RETIRE e REVIEW ao mesmo tempo")
    if final_retire | moved_to_review != original_retire:
        raise ValueError("relatório live não particiona todos os candidatos originais")

    after_guard = live_report.get("after_guard") or {}
    coins = int(live_report.get("coins_required_after_guard") or 0)
    copies = int(after_guard.get("copies") or 0)
    if coins != copies:
        raise ValueError("Coins precisam ser exatamente 1 por cópia após a trava")

    owner_threshold = max(1, int(live_report.get("owner_review_threshold") or 10))
    copy_threshold = max(1, int(live_report.get("copy_review_threshold") or 20))

    original_review = int_set(audit.get("review_ids"))
    final_review = original_review | moved_to_review
    summary = dict(audit.get("summary") or {})
    summary.update(
        {
            "retire_candidates_before_usage_guard": len(original_retire),
            "retire_candidates": len(final_retire),
            "review": len(final_review),
            "moved_to_review_by_collection_impact": len(moved_to_review),
            "affected_users_after_usage_guard": int(after_guard.get("affected_users") or 0),
            "copies_removed_after_usage_guard": copies,
            "coins_required_after_usage_guard": coins,
        }
    )

    plan = {
        "schema": "source.catalog-cleanup.final-plan.v1",
        "apply_ready": False,
        "requires_explicit_operator_approval": True,
        "source_candidate_ids_sha256": ids_hash(original_retire),
        "final_retire_ids_sha256": ids_hash(final_retire),
        "retire_ids": sorted(final_retire),
        "review_ids": sorted(final_review),
        "moved_to_review_by_collection_impact": moved_rows,
        "summary": summary,
        "usage_guard": {
            "applied": True,
            "candidate_count": candidate_count,
            "owner_review_threshold": owner_threshold,
            "copy_review_threshold": copy_threshold,
            "moved_to_review_count": len(moved_to_review),
            "live_report_generated_at": live_report.get("generated_at"),
        },
        "compensation": {
            "coins_per_removed_copy": 1,
            "affected_users": int(after_guard.get("affected_users") or 0),
            "removed_copies": copies,
            "coins_required": coins,
        },
        "safety": {
            "usage_guard_applied": True,
            "database_mutated": False,
            "catalog_mutated": False,
            "coins_awarded": False,
        },
    }
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fecha o plano da limpeza usando o relatório read-only da coleção, sem aplicar mudanças."
    )
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--live-report", default=str(DEFAULT_LIVE_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    plan = finalize_plan(load_json(Path(args.audit)), load_json(Path(args.live_report)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "CATALOG_FINAL_PLAN",
        json.dumps(
            {
                "retire": len(plan["retire_ids"]),
                "review": len(plan["review_ids"]),
                "coins_required": plan["compensation"]["coins_required"],
                "apply_ready": plan["apply_ready"],
                "final_retire_ids_sha256": plan["final_retire_ids_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
