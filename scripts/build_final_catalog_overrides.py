from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from scripts.build_catalog_cleanup_overrides import (
    DEFAULT_DATASET,
    DEFAULT_FRANCHISE,
    DEFAULT_OVERRIDES,
    base_catalog_ids,
    build_proposal,
    load_json,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "data" / "catalog_cleanup_audit.json"
DEFAULT_FINAL_PLAN = ROOT / "data" / "catalog_cleanup_final_plan.json"
DEFAULT_OUTPUT = ROOT / "data" / "cards_overrides.cleanup_final.json"
FINAL_PLAN_SCHEMA = "source.catalog-cleanup.final-plan.v1"


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


def validate_final_plan(audit: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    if str(plan.get("schema") or "") != FINAL_PLAN_SCHEMA:
        raise ValueError("builder final exige source.catalog-cleanup.final-plan.v1")
    if plan.get("apply_ready") is not False:
        raise ValueError("plano final precisa continuar apply_ready=false")
    if plan.get("requires_explicit_operator_approval") is not True:
        raise ValueError("plano final precisa exigir aprovação explícita")

    safety = plan.get("safety") or {}
    usage_guard = plan.get("usage_guard") or {}
    if safety.get("usage_guard_applied") is not True or usage_guard.get("applied") is not True:
        raise ValueError("plano final não confirma usage guard")
    if safety.get("database_mutated") is not False or safety.get("catalog_mutated") is not False:
        raise ValueError("plano final precisa estar em estado pré-aplicação")

    original_retire = int_set(audit.get("retire_ids"))
    final_retire = int_set(plan.get("retire_ids"))
    if not original_retire:
        raise ValueError("auditoria não contém retire_ids")
    if not final_retire:
        raise ValueError("plano final não contém retire_ids")
    if not final_retire.issubset(original_retire):
        raise ValueError("plano final contém RETIRE fora da auditoria")

    declared_source_hash = str(plan.get("source_candidate_ids_sha256") or "").strip().lower()
    if declared_source_hash != ids_hash(original_retire):
        raise ValueError("hash de candidatos do plano final não corresponde à auditoria")

    declared_final_hash = str(plan.get("final_retire_ids_sha256") or "").strip().lower()
    if declared_final_hash != ids_hash(final_retire):
        raise ValueError("hash de retire_ids do plano final é inválido")

    final_review = int_set(plan.get("review_ids"))
    if final_retire & final_review:
        raise ValueError("plano final sobrepõe RETIRE e REVIEW")

    return {
        "original_retire_ids": original_retire,
        "final_retire_ids": final_retire,
        "final_review_ids": final_review,
        "source_candidate_ids_sha256": declared_source_hash,
        "final_retire_ids_sha256": declared_final_hash,
    }


def build_final_overrides(
    overrides: dict[str, Any],
    audit: dict[str, Any],
    franchise: dict[str, Any],
    final_plan: dict[str, Any],
    *,
    base_anime_ids: set[int],
    base_character_ids: set[int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    validated = validate_final_plan(audit, final_plan)
    original_retire = validated["original_retire_ids"]
    final_retire = validated["final_retire_ids"]
    final_review = validated["final_review_ids"]

    baseline_deleted = int_set((overrides or {}).get("deleted_characters"))
    audit_for_builder = deepcopy(audit)
    audit_for_builder["retire_ids"] = sorted(final_retire)

    proposal, stats = build_proposal(
        overrides,
        audit_for_builder,
        franchise,
        base_anime_ids=base_anime_ids,
        base_character_ids=base_character_ids,
    )
    final_deleted = int_set(proposal.get("deleted_characters"))

    missing_final_retire = final_retire - final_deleted
    if missing_final_retire:
        raise ValueError(
            f"overrides final não desabilitou todos os RETIRE: {sorted(missing_final_retire)[:20]}"
        )

    newly_deleted = final_deleted - baseline_deleted
    unexpected_new_deletions = newly_deleted - final_retire
    if unexpected_new_deletions:
        raise ValueError(
            "overrides final criou aposentadorias fora do plano: "
            f"{sorted(unexpected_new_deletions)[:20]}"
        )

    protected_review_deleted = (final_review & final_deleted) - baseline_deleted
    if protected_review_deleted:
        raise ValueError(
            "personagens REVIEW foram desabilitados pelo cleanup final: "
            f"{sorted(protected_review_deleted)[:20]}"
        )

    newly_reenabled_by_usage_guard = (original_retire - final_retire) - baseline_deleted
    if newly_reenabled_by_usage_guard & final_deleted:
        raise ValueError("usage guard salvou personagens que continuam em deleted_characters")

    stats = {
        **stats,
        "mode": "post_usage_guard_final_overrides",
        "source_retire_candidates_before_usage_guard": len(original_retire),
        "final_retire_candidates": len(final_retire),
        "saved_by_usage_guard": len(original_retire - final_retire),
        "source_candidate_ids_sha256": validated["source_candidate_ids_sha256"],
        "final_retire_ids_sha256": validated["final_retire_ids_sha256"],
        "newly_deleted_by_this_cleanup": len(newly_deleted),
        "baseline_deleted_characters_preserved": len(baseline_deleted),
        "final_plan_apply_ready": bool(final_plan.get("apply_ready")),
        "requires_explicit_operator_approval": True,
    }
    return proposal, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Monta o cards_overrides FINAL somente com os RETIRE pós-usage-guard. "
            "Não altera o arquivo ativo nem o banco."
        )
    )
    parser.add_argument("--overrides", default=str(DEFAULT_OVERRIDES))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--franchise", default=str(DEFAULT_FRANCHISE))
    parser.add_argument("--final-plan", default=str(DEFAULT_FINAL_PLAN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    overrides = load_json(Path(args.overrides), {})
    audit = load_json(Path(args.audit), {})
    franchise = load_json(Path(args.franchise), {})
    final_plan = load_json(Path(args.final_plan), {})
    base_anime_ids, base_character_ids = base_catalog_ids(Path(args.dataset))

    proposal, stats = build_final_overrides(
        overrides,
        audit,
        franchise,
        final_plan,
        base_anime_ids=base_anime_ids,
        base_character_ids=base_character_ids,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_FINAL_OVERRIDES", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    print(f"CATALOG_FINAL_OVERRIDES_OUTPUT {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
