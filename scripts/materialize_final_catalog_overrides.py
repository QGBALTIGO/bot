from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "data" / "cards_overrides.json"
DEFAULT_PROPOSAL = ROOT / "data" / "cards_overrides.cleanup_proposal.json"
DEFAULT_PLAN = ROOT / "data" / "catalog_cleanup_final_plan.json"
DEFAULT_OUTPUT = ROOT / "data" / "cards_overrides.final.json"
FINAL_PLAN_SCHEMA = "source.catalog-cleanup.final-plan.v1"


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


def _moved_to_review_ids(plan: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    for row in plan.get("moved_to_review_by_collection_impact") or []:
        if not isinstance(row, dict):
            continue
        try:
            cid = int(row.get("character_id") or 0)
        except Exception:
            continue
        if cid > 0:
            ids.add(cid)
    return ids


def build_final_overrides(
    base: dict[str, Any],
    proposal: dict[str, Any],
    plan: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if str(plan.get("schema") or "") != FINAL_PLAN_SCHEMA:
        raise ValueError("plano precisa ser source.catalog-cleanup.final-plan.v1")
    if plan.get("apply_ready") is not False:
        raise ValueError("plano final precisa continuar apply_ready=false")
    if plan.get("requires_explicit_operator_approval") is not True:
        raise ValueError("plano não declara aprovação explícita")

    safety = plan.get("safety") or {}
    usage_guard = plan.get("usage_guard") or {}
    if safety.get("usage_guard_applied") is not True or usage_guard.get("applied") is not True:
        raise ValueError("plano não confirma usage guard")
    if safety.get("database_mutated") is not False or safety.get("catalog_mutated") is not False:
        raise ValueError("plano final não está em estado pré-aplicação")

    final_retire = int_set(plan.get("retire_ids"))
    if not final_retire:
        raise ValueError("plano final sem retire_ids")
    final_hash = str(plan.get("final_retire_ids_sha256") or "").strip().lower()
    actual_final_hash = ids_hash(final_retire)
    if not final_hash or final_hash != actual_final_hash:
        raise ValueError("hash final dos retire_ids não confere")

    moved_to_review = _moved_to_review_ids(plan)
    if final_retire & moved_to_review:
        raise ValueError("plano sobrepõe RETIRE final e REVIEW por impacto")

    source_candidates = final_retire | moved_to_review
    declared_source_hash = str(plan.get("source_candidate_ids_sha256") or "").strip().lower()
    actual_source_hash = ids_hash(source_candidates)
    if not declared_source_hash or declared_source_hash != actual_source_hash:
        raise ValueError("hash dos candidatos pré-usage-guard não confere")

    candidate_count = int(usage_guard.get("candidate_count") or len(source_candidates))
    if candidate_count != len(source_candidates):
        raise ValueError("candidate_count do usage guard não corresponde à partição final")

    base_deleted = int_set(base.get("deleted_characters"))
    proposal_deleted = int_set(proposal.get("deleted_characters"))

    # Todo candidato do relatório live deve existir na proposta pré-live ou já
    # estar manualmente desativado no arquivo-base. Isso amarra as três etapas:
    # proposta -> usage guard -> materialização final.
    unknown_source = source_candidates - (proposal_deleted | base_deleted)
    if unknown_source:
        raise ValueError(
            "plano live contém candidatos fora da proposta/base: "
            f"{sorted(unknown_source)[:20]}"
        )

    # Todo RETIRE final deve ter vindo da proposta de limpeza ou já estar
    # manualmente desativado no arquivo-base. Um ID estranho aborta a geração.
    unknown_final = final_retire - (proposal_deleted | base_deleted)
    if unknown_final:
        raise ValueError(f"plano final contém IDs fora da proposta/base: {sorted(unknown_final)[:20]}")

    # Mantém deleções manuais antigas e substitui os candidatos automáticos pelo
    # RETIRE final pós-usage-guard. IDs salvos pela coleção voltam ao catálogo,
    # exceto se já eram uma deleção manual anterior.
    final_deleted = base_deleted | final_retire
    restored_by_usage_guard = (proposal_deleted - final_retire) - base_deleted
    expected_restored = moved_to_review - base_deleted
    if restored_by_usage_guard != expected_restored:
        raise ValueError(
            "IDs restaurados do preview não correspondem exatamente ao REVIEW por impacto"
        )

    protected_review_still_deleted = (moved_to_review & final_deleted) - base_deleted
    if protected_review_still_deleted:
        raise ValueError(
            "usage guard salvou personagens que continuam desabilitados: "
            f"{sorted(protected_review_still_deleted)[:20]}"
        )

    out = deepcopy(proposal)
    out["deleted_characters"] = sorted(final_deleted)
    out["_catalog_cleanup"] = {
        "schema": "source.catalog-cleanup.overrides-materialization.v1",
        "source_final_plan_schema": FINAL_PLAN_SCHEMA,
        "source_candidate_ids_sha256": actual_source_hash,
        "source_candidate_count": len(source_candidates),
        "final_retire_ids_sha256": actual_final_hash,
        "final_retire_count": len(final_retire),
        "moved_to_review_by_collection_impact_count": len(moved_to_review),
        "restored_from_proposal_by_usage_guard_count": len(restored_by_usage_guard),
        "base_manual_deleted_preserved": len(base_deleted),
        "ready_to_disable_final_retirements": True,
        "requires_explicit_operator_approval": True,
        "database_mutated": False,
        "coins_awarded": False,
    }

    stats = {
        "base_deleted_preserved": len(base_deleted),
        "proposal_deleted_before_usage_guard": len(proposal_deleted),
        "source_candidates_before_usage_guard": len(source_candidates),
        "final_retire": len(final_retire),
        "final_deleted_total": len(final_deleted),
        "moved_to_review_by_collection_impact": len(moved_to_review),
        "restored_from_proposal_by_usage_guard": len(restored_by_usage_guard),
        "custom_animes": len(out.get("custom_animes") or []),
        "custom_characters": len(out.get("custom_characters") or []),
        "source_candidate_ids_sha256": actual_source_hash,
        "final_retire_ids_sha256": actual_final_hash,
    }
    return out, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materializa o cards_overrides final depois da auditoria live, sem alterar o arquivo de produção."
    )
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    parser.add_argument("--proposal", default=str(DEFAULT_PROPOSAL))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    final, stats = build_final_overrides(
        load_json(Path(args.base)),
        load_json(Path(args.proposal)),
        load_json(Path(args.plan)),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_FINAL_OVERRIDES", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
