from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "apply_catalog_retirements",
    ROOT / "scripts" / "apply_catalog_retirements.py",
)
apply = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(apply)


def final_plan(retire_ids: list[int] | None = None) -> dict:
    ids = retire_ids or [1, 2, 3]
    digest = apply.audit_hash(ids)
    return {
        "schema": apply.FINAL_PLAN_SCHEMA,
        "apply_ready": False,
        "requires_explicit_operator_approval": True,
        "final_retire_ids_sha256": digest,
        "retire_ids": ids,
        "usage_guard": {
            "applied": True,
            "owner_review_threshold": 10,
            "copy_review_threshold": 20,
        },
        "compensation": {
            "coins_per_removed_copy": 1,
            "affected_users": 2,
            "removed_copies": 7,
            "coins_required": 7,
        },
        "safety": {
            "usage_guard_applied": True,
            "database_mutated": False,
            "catalog_mutated": False,
            "coins_awarded": False,
        },
    }


def write_json(tmp_path: Path, payload: object, name: str = "plan.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_apply_requires_final_plan_and_exact_operator_hash(tmp_path: Path):
    payload = final_plan()
    path = write_json(tmp_path, payload)
    expected = apply.load_apply_plan(path, payload["final_retire_ids_sha256"])
    assert expected["retired_ids"] == [1, 2, 3]
    assert expected["final_hash"] == payload["final_retire_ids_sha256"]
    assert expected["expected_affected_users"] == 2
    assert expected["expected_removed_copies"] == 7
    assert expected["owner_review_threshold"] == 10
    assert expected["copy_review_threshold"] == 20


def test_raw_audit_can_never_be_used_for_apply(tmp_path: Path):
    path = write_json(tmp_path, {"retire_ids": [1, 2, 3]})
    with pytest.raises(ValueError, match="final-plan"):
        apply.load_apply_plan(path, apply.audit_hash([1, 2, 3]))


def test_wrong_operator_hash_is_rejected(tmp_path: Path):
    payload = final_plan()
    path = write_json(tmp_path, payload)
    with pytest.raises(ValueError, match="approve-final-hash"):
        apply.load_apply_plan(path, "0" * 64)


def test_plan_without_usage_guard_is_rejected(tmp_path: Path):
    payload = final_plan()
    payload["usage_guard"]["applied"] = False
    path = write_json(tmp_path, payload)
    with pytest.raises(ValueError, match="trava por uso real"):
        apply.load_apply_plan(path, payload["final_retire_ids_sha256"])


def test_plan_with_wrong_coin_math_is_rejected(tmp_path: Path):
    payload = final_plan()
    payload["compensation"]["coins_required"] = 8
    path = write_json(tmp_path, payload)
    with pytest.raises(ValueError, match="matemática de Coins"):
        apply.load_apply_plan(path, payload["final_retire_ids_sha256"])


def test_plan_with_tampered_retire_ids_is_rejected(tmp_path: Path):
    payload = final_plan()
    approved = payload["final_retire_ids_sha256"]
    payload["retire_ids"].append(999)
    path = write_json(tmp_path, payload)
    with pytest.raises(ValueError, match="hash dos retire_ids"):
        apply.load_apply_plan(path, approved)


def test_catalog_guard_requires_every_final_retirement_already_disabled(tmp_path: Path):
    overrides = write_json(
        tmp_path,
        {"deleted_characters": [1, "2", 3, 999]},
        name="cards_overrides.json",
    )
    result = apply.assert_catalog_already_disabled([1, 2, 3], overrides)
    assert result["all_retired_cards_disabled"] is True
    assert result["disabled_character_count"] == 3


def test_catalog_guard_fails_if_even_one_card_can_still_spawn(tmp_path: Path):
    overrides = write_json(
        tmp_path,
        {"deleted_characters": [1, 3]},
        name="cards_overrides.json",
    )
    with pytest.raises(RuntimeError, match="catálogo ativo ainda permite"):
        apply.assert_catalog_already_disabled([1, 2, 3], overrides)


def test_catalog_guard_fails_closed_if_overrides_file_is_missing(tmp_path: Path):
    with pytest.raises(RuntimeError, match="overrides ativo não existe"):
        apply.assert_catalog_already_disabled([1], tmp_path / "missing.json")


class FakeCursor:
    def __init__(self, rowcounts: list[int]):
        self._rowcounts = iter(rowcounts)
        self.rowcount = 0
        self.sql: list[str] = []

    def execute(self, sql, params=None):
        self.sql.append(" ".join(str(sql).split()))
        self.rowcount = next(self._rowcounts)


class RecordingCursor:
    def __init__(self):
        self.rowcount = 0
        self.sql: list[str] = []
        self.params: list[object] = []

    def execute(self, sql, params=None):
        self.sql.append(" ".join(str(sql).split()))
        self.params.append(params)
        self.rowcount = 0


def test_cleanup_closes_legacy_spawns_and_buybacks_too():
    cur = FakeCursor([2, 3, 4, 5, 6])
    result = apply._close_pending_refs(cur, [10, 20])
    combined = "\n".join(cur.sql)
    assert "UPDATE card_trades" in combined
    assert "UPDATE capture_spawns" in combined
    assert "DELETE FROM active_group_spawns" in combined
    assert "DELETE FROM shop_card_sales" in combined
    assert result["pending_trades_cancelled"] == 2
    assert result["active_spawns_expired"] == 3
    assert result["open_purchase_offers_expired"] == 4
    assert result["legacy_active_spawns_removed"] == 5
    assert result["buyback_sales_invalidated"] == 6


def test_cleanup_clears_both_favorite_tables():
    cur = FakeCursor([6, 7])
    result = apply._clear_retired_favorites(cur, [10, 20])
    combined = "\n".join(cur.sql)
    assert "UPDATE user_profile_settings" in combined
    assert "UPDATE user_collection_profile" in combined
    assert result["profile_favorites_cleared"] == 6
    assert result["collection_favorites_cleared"] == 7
    assert result["favorites_cleared"] == 13


def test_migration_installs_database_level_retired_character_guard():
    cur = RecordingCursor()
    apply.ensure_migration_tables(cur)
    combined = "\n".join(cur.sql)
    assert "CREATE TABLE IF NOT EXISTS catalog_retired_characters" in combined
    assert "CREATE OR REPLACE FUNCTION block_retired_character_collection_write" in combined
    assert "CREATE TRIGGER trg_block_retired_character_collection_write" in combined
    assert "BEFORE INSERT OR UPDATE ON user_card_collection" in combined
    assert "character_id % is retired" in combined


def test_retired_ids_are_registered_in_database_guard_inside_batch():
    cur = RecordingCursor()
    count = apply._register_retired_character_guard(cur, [10, 20, 30], "batch-v2")
    combined = "\n".join(cur.sql)
    assert count == 3
    assert "INSERT INTO catalog_retired_characters" in combined
    assert "unnest(%s::bigint[])" in combined
    assert cur.params[-1] == ("batch-v2", [10, 20, 30])
