from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.catalog_impact_manifest import candidate_ids_hash
from utils.catalog_usage_audit_runtime import _fetch_manifest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN_PATH = ROOT / "data" / "catalog_retirement_final.v1.json"
SUPPORTED_SCHEMA = "source.catalog-retirement-final.v1"


def _load_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("plano final inválido")
    return raw


def load_final_retirement_plan(path: Path = DEFAULT_PLAN_PATH) -> dict[str, Any]:
    raw = _load_object(path)
    if str(raw.get("schema") or "") != SUPPORTED_SCHEMA:
        raise ValueError("schema do plano final inválido")

    _, candidate_ids = _fetch_manifest()
    candidate_set = set(candidate_ids)
    candidate_count = int(raw.get("candidate_count") or 0)
    candidate_hash = str(raw.get("candidate_ids_sha256") or "").strip().lower()
    if candidate_count != len(candidate_ids):
        raise ValueError("candidate_count do plano não confere")
    if candidate_hash != candidate_ids_hash(candidate_ids):
        raise ValueError("candidate hash do plano não confere")

    saved_rows = [row for row in (raw.get("saved_by_collection") or []) if isinstance(row, dict)]
    saved_ids = {
        int(row.get("character_id") or 0)
        for row in saved_rows
        if int(row.get("character_id") or 0) > 0
    }
    if not saved_ids.issubset(candidate_set):
        raise ValueError("plano salva ID fora do manifesto canônico")

    final_ids = sorted(candidate_set - saved_ids)
    expected_final_count = int(raw.get("final_retire_count") or 0)
    expected_final_hash = str(raw.get("final_retire_ids_sha256") or "").strip().lower()
    actual_final_hash = candidate_ids_hash(final_ids)
    if len(final_ids) != expected_final_count:
        raise ValueError("final_retire_count do plano não confere")
    if actual_final_hash != expected_final_hash:
        raise ValueError("final retire hash do plano não confere")

    compensation = raw.get("compensation") or {}
    expected_copies = int(compensation.get("removed_copies") or 0)
    expected_coins = int(compensation.get("coins_required") or 0)
    if int(compensation.get("coins_per_removed_copy") or 0) != 1:
        raise ValueError("plano final não usa 1 Coin por cópia")
    if expected_copies < 0 or expected_coins != expected_copies:
        raise ValueError("matemática de Coins do plano final inválida")

    out = dict(raw)
    out["candidate_ids"] = candidate_ids
    out["saved_ids"] = sorted(saved_ids)
    out["retired_ids"] = final_ids
    out["actual_final_retire_ids_sha256"] = actual_final_hash
    return out
