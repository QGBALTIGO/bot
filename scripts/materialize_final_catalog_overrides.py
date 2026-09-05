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
DEFAULT_DATASET = ROOT / "data" / "personagens_anilist.txt"
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


def _positive_int(value: Any) -> int:
    try:
        number = int(value or 0)
    except Exception:
        return 0
    return number if number > 0 else 0


def ids_hash(values: Any) -> str:
    canonical = ",".join(str(x) for x in sorted(int_set(values))).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _moved_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in (plan.get("moved_to_review_by_collection_impact") or [])
        if isinstance(row, dict) and _positive_int(row.get("character_id")) > 0
    ]


def _moved_to_review_ids(plan: dict[str, Any]) -> set[int]:
    return {_positive_int(row.get("character_id")) for row in _moved_rows(plan)}


def _dataset_indexes(dataset: dict[str, Any] | None) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    if not isinstance(dataset, dict):
        return {}, {}
    items = dataset.get("items", [])
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
            if cid <= 0:
                continue
            char_by_id.setdefault(
                cid,
                {
                    **ch,
                    "anime_id": aid,
                    "anime": str(anime.get("anime") or "").strip(),
                },
            )
    return anime_by_id, char_by_id


def _consolidation_targets(proposal: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Reconstrói source anime -> categoria canônica pelos personagens já movidos."""
    targets: dict[int, dict[str, Any]] = {}
    for row in proposal.get("custom_characters") or []:
        if not isinstance(row, dict):
            continue
        source_id = _positive_int(row.get("_consolidated_from_anime_id"))
        target_id = _positive_int(row.get("anime_id"))
        if source_id <= 0 or target_id <= 0:
            continue
        target = {
            "anime_id": target_id,
            "anime": str(row.get("anime") or f"Anime {target_id}").strip(),
        }
        existing = targets.get(source_id)
        if existing and existing != target:
            raise ValueError(
                f"consolidação inconsistente para anime {source_id}: {existing} != {target}"
            )
        targets[source_id] = target
    return targets


def _restore_catalog_visibility_for_usage_saved(
    *,
    out: dict[str, Any],
    base: dict[str, Any],
    proposal: dict[str, Any],
    plan: dict[str, Any],
    dataset: dict[str, Any] | None,
    base_deleted_characters: set[int],
) -> dict[str, Any]:
    """Evita salvar a carta no DB e deixá-la invisível por causa da categoria.

    Categorias vazias são reabertas se o usage guard salvar um personagem.
    Categorias duplicadas permanecem fechadas; nesses casos a carta salva é
    realocada para a categoria canônica usando o mesmo character_id.
    Deleções manuais do arquivo-base nunca são revertidas automaticamente.
    """
    moved_rows = _moved_rows(plan)
    proposal_deleted_animes = int_set(proposal.get("deleted_animes"))
    base_deleted_animes = int_set(base.get("deleted_animes"))
    final_deleted_animes = set(proposal_deleted_animes) | set(base_deleted_animes)
    consolidation_targets = _consolidation_targets(proposal)
    _, char_by_id = _dataset_indexes(dataset)

    custom_by_id: dict[int, dict[str, Any]] = {}
    for row in out.get("custom_characters") or []:
        if not isinstance(row, dict):
            continue
        cid = _positive_int(row.get("id"))
        if cid > 0:
            custom_by_id[cid] = deepcopy(row)

    restored_empty_animes: set[int] = set()
    relocated_from_consolidated: set[int] = set()
    manual_anime_deletions_preserved: set[int] = set()

    for moved in moved_rows:
        cid = _positive_int(moved.get("character_id"))
        if cid <= 0 or cid in base_deleted_characters:
            continue

        source = char_by_id.get(cid) or {}
        source_anime_id = _positive_int(moved.get("anime_id")) or _positive_int(source.get("anime_id"))
        if source_anime_id <= 0 or source_anime_id not in proposal_deleted_animes:
            continue

        if source_anime_id in base_deleted_animes:
            manual_anime_deletions_preserved.add(source_anime_id)
            continue

        target = consolidation_targets.get(source_anime_id)
        if target:
            # Não ressuscita Fate/Zero/JJK S3 etc. A carta salva vai para a
            # categoria consolidada, preservando o character_id da coleção.
            if not source:
                raise ValueError(
                    "personagem salvo de categoria consolidada não foi encontrado no dataset: "
                    f"character_id={cid} anime_id={source_anime_id}"
                )
            existing = custom_by_id.get(cid) or {}
            target_id = _positive_int(target.get("anime_id"))
            target_name = str(target.get("anime") or f"Anime {target_id}").strip()
            name = str(existing.get("name") or moved.get("name") or source.get("name") or f"Personagem {cid}").strip()
            image = str(existing.get("image") or source.get("image") or "").strip()
            custom_by_id[cid] = {
                **existing,
                "id": cid,
                "anime_id": target_id,
                "anime": target_name,
                "name": name,
                "image": image,
                "_catalog_source": "franchise_consolidation_usage_guard_v1",
                "_consolidated_from_anime_id": source_anime_id,
                "_restored_by_collection_impact": True,
            }
            relocated_from_consolidated.add(cid)
            continue

        # Se a categoria só tinha sido excluída porque todos os personagens
        # seriam aposentados, um personagem salvo pela comunidade a torna
        # não-vazia novamente. Reabre a categoria original.
        final_deleted_animes.discard(source_anime_id)
        restored_empty_animes.add(source_anime_id)

    out["deleted_animes"] = sorted(final_deleted_animes)
    out["custom_characters"] = sorted(
        custom_by_id.values(),
        key=lambda row: (
            _positive_int(row.get("anime_id")),
            str(row.get("name") or "").casefold(),
            _positive_int(row.get("id")),
        ),
    )
    return {
        "restored_empty_anime_ids": sorted(restored_empty_animes),
        "restored_empty_animes": len(restored_empty_animes),
        "relocated_saved_character_ids": sorted(relocated_from_consolidated),
        "relocated_saved_characters": len(relocated_from_consolidated),
        "manual_deleted_anime_ids_preserved": sorted(manual_anime_deletions_preserved),
        "manual_deleted_animes_preserved": len(manual_anime_deletions_preserved),
        "final_deleted_animes": len(final_deleted_animes),
    }


def build_final_overrides(
    base: dict[str, Any],
    proposal: dict[str, Any],
    plan: dict[str, Any],
    dataset: dict[str, Any] | None = None,
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

    unknown_source = source_candidates - (proposal_deleted | base_deleted)
    if unknown_source:
        raise ValueError(
            "plano live contém candidatos fora da proposta/base: "
            f"{sorted(unknown_source)[:20]}"
        )

    unknown_final = final_retire - (proposal_deleted | base_deleted)
    if unknown_final:
        raise ValueError(f"plano final contém IDs fora da proposta/base: {sorted(unknown_final)[:20]}")

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
    visibility_stats = _restore_catalog_visibility_for_usage_saved(
        out=out,
        base=base,
        proposal=proposal,
        plan=plan,
        dataset=dataset,
        base_deleted_characters=base_deleted,
    )

    out["_catalog_cleanup"] = {
        "schema": "source.catalog-cleanup.overrides-materialization.v2",
        "source_final_plan_schema": FINAL_PLAN_SCHEMA,
        "source_candidate_ids_sha256": actual_source_hash,
        "source_candidate_count": len(source_candidates),
        "final_retire_ids_sha256": actual_final_hash,
        "final_retire_count": len(final_retire),
        "moved_to_review_by_collection_impact_count": len(moved_to_review),
        "restored_from_proposal_by_usage_guard_count": len(restored_by_usage_guard),
        "restored_empty_anime_ids": visibility_stats["restored_empty_anime_ids"],
        "relocated_saved_character_ids": visibility_stats["relocated_saved_character_ids"],
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
        **visibility_stats,
    }
    return out, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materializa o cards_overrides final depois da auditoria live, sem alterar o arquivo de produção."
    )
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    parser.add_argument("--proposal", default=str(DEFAULT_PROPOSAL))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    final, stats = build_final_overrides(
        load_json(Path(args.base)),
        load_json(Path(args.proposal)),
        load_json(Path(args.plan)),
        load_json(Path(args.dataset)),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_FINAL_OVERRIDES", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
