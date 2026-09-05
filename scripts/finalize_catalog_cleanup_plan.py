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


def _non_negative_int(value: Any, field: str) -> int:
    try:
        number = int(value or 0)
    except Exception as exc:
        raise ValueError(f"{field} precisa ser inteiro") from exc
    if number < 0:
        raise ValueError(f"{field} não pode ser negativo")
    return number


def _manifest_policy(live_report: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
    manifest = live_report.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("relatório live precisa conter o manifesto de candidatos")
    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("manifesto live precisa conter policy")
    owner_threshold = _non_negative_int(
        policy.get("owner_review_threshold"),
        "manifest.policy.owner_review_threshold",
    )
    copy_threshold = _non_negative_int(
        policy.get("copy_review_threshold"),
        "manifest.policy.copy_review_threshold",
    )
    if owner_threshold <= 0 or copy_threshold <= 0:
        raise ValueError("limiares do manifesto precisam ser maiores que zero")
    return manifest, owner_threshold, copy_threshold


def _validate_usage_rows(
    *,
    final_retire: set[int],
    moved_to_review: set[int],
    moved_rows: list[dict[str, Any]],
    retire_rows: list[dict[str, Any]],
    owner_threshold: int,
    copy_threshold: int,
    expected_copies: int,
) -> None:
    moved_row_ids: set[int] = set()
    for row in moved_rows:
        cid = _non_negative_int(row.get("character_id"), "moved_to_review.character_id")
        if cid <= 0:
            raise ValueError("moved_to_review contém character_id inválido")
        if cid in moved_row_ids:
            raise ValueError("moved_to_review contém character_id duplicado")
        moved_row_ids.add(cid)
        owners = _non_negative_int(row.get("owners"), "moved_to_review.owners")
        copies = _non_negative_int(row.get("copies"), "moved_to_review.copies")
        if owners < owner_threshold and copies < copy_threshold:
            raise ValueError("REVIEW por impacto não atinge os limiares do manifesto")
    if moved_row_ids != moved_to_review:
        raise ValueError("linhas de REVIEW por impacto não correspondem à partição")

    retire_row_ids: set[int] = set()
    copies_sum = 0
    for row in retire_rows:
        cid = _non_negative_int(row.get("character_id"), "retirements.character_id")
        if cid <= 0 or cid not in final_retire:
            raise ValueError("retirement com owners contém ID fora do RETIRE final")
        if cid in retire_row_ids:
            raise ValueError("retirements contém character_id duplicado")
        retire_row_ids.add(cid)
        owners = _non_negative_int(row.get("owners"), "retirements.owners")
        copies = _non_negative_int(row.get("copies"), "retirements.copies")
        coins_if_retired = _non_negative_int(
            row.get("coins_if_retired"),
            "retirements.coins_if_retired",
        )
        if copies != coins_if_retired:
            raise ValueError("coins_if_retired precisa ser exatamente 1 por cópia")
        if owners >= owner_threshold or copies >= copy_threshold:
            raise ValueError("RETIRE final viola os limiares de impacto do manifesto")
        copies_sum += copies

    if copies_sum != expected_copies:
        raise ValueError("soma das cópias por personagem não corresponde ao total pós-trava")


def finalize_plan(audit: dict[str, Any], live_report: dict[str, Any]) -> dict[str, Any]:
    if live_report.get("read_only") is not True:
        raise ValueError("relatório live precisa declarar read_only=true")
    if live_report.get("contains_user_ids") is not False:
        raise ValueError("relatório live precisa declarar contains_user_ids=false")

    original_retire = int_set(audit.get("retire_ids"))
    if not original_retire:
        raise ValueError("auditoria não possui candidatos RETIRE")

    source_hash = ids_hash(original_retire)
    manifest, owner_threshold, copy_threshold = _manifest_policy(live_report)
    manifest_count = _non_negative_int(manifest.get("candidate_count"), "manifest.candidate_count")
    manifest_hash = str(manifest.get("candidate_ids_sha256") or "").strip().lower()
    if manifest_count != len(original_retire):
        raise ValueError("candidate_count do manifesto não corresponde à auditoria")
    if manifest_hash != source_hash:
        raise ValueError("SHA-256 do manifesto não corresponde aos candidatos da auditoria")

    report_owner_threshold = _non_negative_int(
        live_report.get("owner_review_threshold"),
        "owner_review_threshold",
    )
    report_copy_threshold = _non_negative_int(
        live_report.get("copy_review_threshold"),
        "copy_review_threshold",
    )
    if report_owner_threshold != owner_threshold or report_copy_threshold != copy_threshold:
        raise ValueError("limiares do relatório live não correspondem ao manifesto")

    final_retire = int_set(live_report.get("final_retire_ids"))
    moved_rows = [x for x in (live_report.get("moved_to_review") or []) if isinstance(x, dict)]
    moved_to_review = {
        int(row.get("character_id") or 0)
        for row in moved_rows
        if int(row.get("character_id") or 0) > 0
    }

    candidate_count = _non_negative_int(live_report.get("candidate_count"), "candidate_count")
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

    after_guard = live_report.get("after_guard")
    if not isinstance(after_guard, dict):
        raise ValueError("relatório live precisa conter after_guard")
    affected_users = _non_negative_int(after_guard.get("affected_users"), "after_guard.affected_users")
    copies = _non_negative_int(after_guard.get("copies"), "after_guard.copies")
    owner_character_links = _non_negative_int(
        after_guard.get("owner_character_links"),
        "after_guard.owner_character_links",
    )
    coins = _non_negative_int(
        live_report.get("coins_required_after_guard"),
        "coins_required_after_guard",
    )
    if coins != copies:
        raise ValueError("Coins precisam ser exatamente 1 por cópia após a trava")

    retire_rows = [
        x
        for x in (live_report.get("retirements_with_existing_owners") or [])
        if isinstance(x, dict)
    ]
    _validate_usage_rows(
        final_retire=final_retire,
        moved_to_review=moved_to_review,
        moved_rows=moved_rows,
        retire_rows=retire_rows,
        owner_threshold=owner_threshold,
        copy_threshold=copy_threshold,
        expected_copies=copies,
    )

    original_review = int_set(audit.get("review_ids"))
    final_review = original_review | moved_to_review
    summary = dict(audit.get("summary") or {})
    summary.update(
        {
            "retire_candidates_before_usage_guard": len(original_retire),
            "retire_candidates": len(final_retire),
            "review": len(final_review),
            "moved_to_review_by_collection_impact": len(moved_to_review),
            "affected_users_after_usage_guard": affected_users,
            "copies_removed_after_usage_guard": copies,
            "coins_required_after_usage_guard": coins,
        }
    )

    plan = {
        "schema": "source.catalog-cleanup.final-plan.v1",
        "apply_ready": False,
        "requires_explicit_operator_approval": True,
        "source_candidate_ids_sha256": source_hash,
        "source_manifest": {
            "candidate_count": manifest_count,
            "candidate_ids_sha256": manifest_hash,
            "catalog_snapshot": str(manifest.get("catalog_snapshot") or ""),
            "owner_review_threshold": owner_threshold,
            "copy_review_threshold": copy_threshold,
        },
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
            "affected_users": affected_users,
            "owner_character_links": owner_character_links,
            "removed_copies": copies,
            "coins_required": coins,
        },
        "safety": {
            "usage_guard_applied": True,
            "manifest_hash_verified": True,
            "usage_thresholds_verified": True,
            "aggregate_copy_math_verified": True,
            "contains_user_ids": False,
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
