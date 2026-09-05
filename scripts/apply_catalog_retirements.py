from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "data" / "catalog_cleanup_audit.json"
COINS_PER_REMOVED_COPY = 1
FINAL_PLAN_SCHEMA = "source.catalog-cleanup.final-plan.v1"


def load_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} precisa conter um objeto JSON")
    return raw


def load_retired_ids(path: Path) -> list[int]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    values: Any
    if isinstance(raw, dict):
        values = raw.get("retire_ids") or raw.get("deleted_characters") or []
    elif isinstance(raw, list):
        values = raw
    else:
        values = []
    out: list[int] = []
    seen: set[int] = set()
    for value in values or []:
        try:
            cid = int(value)
        except Exception:
            continue
        if cid > 0 and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def audit_hash(retired_ids: list[int]) -> str:
    payload = ",".join(str(x) for x in sorted(retired_ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_apply_plan(path: Path, approved_hash: str) -> dict[str, Any]:
    """Valida o plano final antes de permitir qualquer mutação.

    Um audit bruto ou uma lista de IDs pode ser usado para dry-run, mas nunca
    para --apply. A aplicação exige o final-plan gerado após o usage guard e o
    hash final informado explicitamente pelo operador.
    """
    plan = load_json_object(path)
    if str(plan.get("schema") or "") != FINAL_PLAN_SCHEMA:
        raise ValueError("--apply exige source.catalog-cleanup.final-plan.v1")
    if plan.get("requires_explicit_operator_approval") is not True:
        raise ValueError("plano não exige aprovação explícita; recusando aplicação")

    safety = plan.get("safety") or {}
    usage_guard = plan.get("usage_guard") or {}
    if safety.get("usage_guard_applied") is not True or usage_guard.get("applied") is not True:
        raise ValueError("plano final não confirma a trava por uso real")
    if safety.get("database_mutated") is not False or safety.get("catalog_mutated") is not False:
        raise ValueError("plano final não está em estado pré-aplicação")

    retired_ids = load_retired_ids(path)
    if not retired_ids:
        raise ValueError("plano final não contém retire_ids")
    actual_hash = audit_hash(retired_ids)
    declared_hash = str(plan.get("final_retire_ids_sha256") or "").strip().lower()
    approval = str(approved_hash or "").strip().lower()
    if not declared_hash or declared_hash != actual_hash:
        raise ValueError("hash dos retire_ids não corresponde ao plano final")
    if not approval or approval != actual_hash:
        raise ValueError("--approve-final-hash precisa ser exatamente o hash final do plano")

    compensation = plan.get("compensation") or {}
    if int(compensation.get("coins_per_removed_copy") or 0) != COINS_PER_REMOVED_COPY:
        raise ValueError("plano final não usa 1 Coin por cópia")
    expected_copies = max(0, int(compensation.get("removed_copies") or 0))
    expected_coins = max(0, int(compensation.get("coins_required") or 0))
    if expected_copies != expected_coins:
        raise ValueError("plano final tem matemática de Coins inconsistente")

    return {
        "retired_ids": retired_ids,
        "final_hash": actual_hash,
        "expected_affected_users": max(0, int(compensation.get("affected_users") or 0)),
        "expected_removed_copies": expected_copies,
        "owner_review_threshold": max(1, int(usage_guard.get("owner_review_threshold") or 10)),
        "copy_review_threshold": max(1, int(usage_guard.get("copy_review_threshold") or 20)),
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    copies = sum(max(0, int(row.get("quantity") or 0)) for row in rows)
    users = {int(row.get("user_id") or 0) for row in rows if int(row.get("user_id") or 0) > 0}
    chars = {int(row.get("character_id") or 0) for row in rows if int(row.get("character_id") or 0) > 0}
    return {
        "affected_users": len(users),
        "owned_retired_character_ids": len(chars),
        "removed_copies": copies,
        "coins_to_award": copies * COINS_PER_REMOVED_COPY,
    }


def ensure_migration_tables(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_retirement_batches (
            batch_id TEXT PRIMARY KEY,
            audit_hash TEXT NOT NULL,
            retire_character_count INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_retirement_compensations (
            batch_id TEXT NOT NULL REFERENCES catalog_retirement_batches(batch_id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            character_id BIGINT NOT NULL,
            quantity INTEGER NOT NULL,
            coins_awarded INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (batch_id, user_id, character_id)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_catalog_retirement_comp_user
        ON catalog_retirement_compensations (user_id, created_at DESC)
        """
    )


def load_owned_rows(cur, retired_ids: list[int], *, for_update: bool = False) -> list[dict[str, Any]]:
    if not retired_ids:
        return []
    suffix = " FOR UPDATE" if for_update else ""
    cur.execute(
        f"""
        SELECT user_id, character_id, quantity
        FROM user_card_collection
        WHERE quantity > 0
          AND character_id = ANY(%s)
        ORDER BY user_id, character_id{suffix}
        """,
        (retired_ids,),
    )
    return [dict(row) for row in (cur.fetchall() or [])]


def _count_one(cur, sql: str, params: tuple[Any, ...]) -> int:
    cur.execute(sql, params)
    return max(0, int((cur.fetchone() or {}).get("total") or 0))


def _count_pending_refs(cur, retired_ids: list[int]) -> dict[str, int]:
    pending_trades = _count_one(
        cur,
        """
        SELECT COUNT(*) AS total
        FROM card_trades
        WHERE status = 'pending'
          AND (from_character_id = ANY(%s) OR to_character_id = ANY(%s))
        """,
        (retired_ids, retired_ids),
    )
    active_spawns = _count_one(
        cur,
        """
        SELECT COUNT(*) AS total
        FROM capture_spawns
        WHERE character_id = ANY(%s)
          AND status = 'active'
        """,
        (retired_ids,),
    )
    open_purchase_offers = _count_one(
        cur,
        """
        SELECT COUNT(*) AS total
        FROM capture_spawns
        WHERE character_id = ANY(%s)
          AND status = 'captured_offer_open'
        """,
        (retired_ids,),
    )
    legacy_active_spawns = _count_one(
        cur,
        """
        SELECT COUNT(*) AS total
        FROM active_group_spawns
        WHERE character_id = ANY(%s)
        """,
        (retired_ids,),
    )
    profile_favorites = _count_one(
        cur,
        """
        SELECT COUNT(*) AS total
        FROM user_profile_settings
        WHERE favorite_character_id = ANY(%s)
        """,
        (retired_ids,),
    )
    collection_favorites = _count_one(
        cur,
        """
        SELECT COUNT(*) AS total
        FROM user_collection_profile
        WHERE favorite_character_id = ANY(%s)
        """,
        (retired_ids,),
    )

    return {
        "pending_trades_to_cancel": pending_trades,
        "active_spawns_to_expire": active_spawns,
        "open_purchase_offers_to_expire": open_purchase_offers,
        "legacy_active_spawns_to_remove": legacy_active_spawns,
        "profile_favorites_to_clear": profile_favorites,
        "collection_favorites_to_clear": collection_favorites,
    }


def dry_run(retired_ids: list[int]) -> dict[str, Any]:
    from database_core import pool

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = load_owned_rows(cur, retired_ids)
            summary = summarize_rows(rows)
            summary.update(_count_pending_refs(cur, retired_ids))
            summary["retire_character_count"] = len(retired_ids)
            summary["apply"] = False
            return summary


def _lock_catalog_mutation_tables(cur) -> None:
    # Uma migração é rara e curta. Bloquear writes nessas tabelas evita que
    # coleção/troca/spawn/favorito mude entre a rechecagem e o COMMIT.
    cur.execute(
        """
        LOCK TABLE
            user_card_collection,
            card_trades,
            capture_spawns,
            active_group_spawns,
            user_profile_settings,
            user_collection_profile
        IN SHARE ROW EXCLUSIVE MODE
        """
    )


def _high_impact_rows(cur, retired_ids: list[int], owner_threshold: int, copy_threshold: int) -> list[dict[str, Any]]:
    if not retired_ids:
        return []
    cur.execute(
        """
        SELECT
            character_id,
            COUNT(DISTINCT user_id)::BIGINT AS owners,
            COALESCE(SUM(quantity), 0)::BIGINT AS copies
        FROM user_card_collection
        WHERE quantity > 0
          AND character_id = ANY(%s)
        GROUP BY character_id
        HAVING COUNT(DISTINCT user_id) >= %s
            OR COALESCE(SUM(quantity), 0) >= %s
        ORDER BY owners DESC, copies DESC, character_id
        """,
        (retired_ids, int(owner_threshold), int(copy_threshold)),
    )
    return [dict(row) for row in (cur.fetchall() or [])]


def _assert_live_plan_still_current(cur, retired_ids: list[int], expected: dict[str, Any]) -> dict[str, Any]:
    high_impact = _high_impact_rows(
        cur,
        retired_ids,
        int(expected["owner_review_threshold"]),
        int(expected["copy_review_threshold"]),
    )
    if high_impact:
        ids = [int(row.get("character_id") or 0) for row in high_impact[:20]]
        raise RuntimeError(
            "impacto da coleção mudou desde o relatório live; "
            f"personagens cruzaram a trava de uso real: {ids}. Rode /health catalog novamente."
        )

    owned_rows = load_owned_rows(cur, retired_ids, for_update=True)
    current = summarize_rows(owned_rows)
    if int(current["affected_users"]) != int(expected["expected_affected_users"]):
        raise RuntimeError(
            "quantidade de usuários afetados mudou desde o relatório live; rode a auditoria novamente"
        )
    if int(current["removed_copies"]) != int(expected["expected_removed_copies"]):
        raise RuntimeError(
            "quantidade de cópias/Coins mudou desde o relatório live; rode a auditoria novamente"
        )
    return {"rows": owned_rows, "summary": current}


def _close_pending_refs(cur, retired_ids: list[int]) -> dict[str, int]:
    cur.execute(
        """
        UPDATE card_trades
        SET status = 'cancelled'
        WHERE status = 'pending'
          AND (from_character_id = ANY(%s) OR to_character_id = ANY(%s))
        """,
        (retired_ids, retired_ids),
    )
    trades_cancelled = int(cur.rowcount or 0)

    cur.execute(
        """
        UPDATE capture_spawns
        SET status = 'escaped',
            updated_at = NOW(),
            expires_at = LEAST(expires_at, NOW())
        WHERE character_id = ANY(%s)
          AND status = 'active'
        """,
        (retired_ids,),
    )
    spawns_expired = int(cur.rowcount or 0)

    cur.execute(
        """
        UPDATE capture_spawns
        SET status = 'captured_offer_expired',
            purchase_expires_at = NOW(),
            updated_at = NOW()
        WHERE character_id = ANY(%s)
          AND status = 'captured_offer_open'
        """,
        (retired_ids,),
    )
    offers_expired = int(cur.rowcount or 0)

    # Tabela legada ainda pode manter o card ativo por chat; não possui coluna
    # de status, então a forma segura de encerrá-lo é remover a linha ativa.
    cur.execute(
        """
        DELETE FROM active_group_spawns
        WHERE character_id = ANY(%s)
        """,
        (retired_ids,),
    )
    legacy_spawns_removed = int(cur.rowcount or 0)

    return {
        "pending_trades_cancelled": trades_cancelled,
        "active_spawns_expired": spawns_expired,
        "open_purchase_offers_expired": offers_expired,
        "legacy_active_spawns_removed": legacy_spawns_removed,
    }


def _clear_retired_favorites(cur, retired_ids: list[int]) -> dict[str, int]:
    cur.execute(
        """
        UPDATE user_profile_settings
        SET favorite_character_id = NULL,
            updated_at = NOW()
        WHERE favorite_character_id = ANY(%s)
        """,
        (retired_ids,),
    )
    profile = int(cur.rowcount or 0)

    cur.execute(
        """
        UPDATE user_collection_profile
        SET favorite_character_id = NULL,
            updated_at = NOW()
        WHERE favorite_character_id = ANY(%s)
        """,
        (retired_ids,),
    )
    collection = int(cur.rowcount or 0)
    return {
        "profile_favorites_cleared": profile,
        "collection_favorites_cleared": collection,
        "favorites_cleared": profile + collection,
    }


def _record_compensation_transaction(cur, user_id: int, amount: int, balance_after: int, batch_id: str) -> None:
    cur.execute(
        """
        INSERT INTO shop_transactions
            (user_id, type, amount, balance_after, reference_id, metadata)
        VALUES (%s, 'catalog_retirement_compensation', %s, %s, NULL, %s::jsonb)
        """,
        (
            int(user_id),
            int(amount),
            int(balance_after),
            json.dumps({"batch_id": batch_id, "reason": "retired_character_compensation"}, ensure_ascii=False),
        ),
    )


def apply_batch(retired_ids: list[int], batch_id: str, *, expected: dict[str, Any]) -> dict[str, Any]:
    from database_core import pool

    digest = audit_hash(retired_ids)
    if digest != str(expected.get("final_hash") or ""):
        raise RuntimeError("hash do lote não corresponde ao plano final aprovado")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                ensure_migration_tables(cur)
                cur.execute(
                    "SELECT batch_id, audit_hash, status FROM catalog_retirement_batches WHERE batch_id = %s FOR UPDATE",
                    (batch_id,),
                )
                existing = cur.fetchone()
                if existing:
                    if str(existing.get("audit_hash") or "") != digest:
                        raise RuntimeError("batch_id já existe com outro conjunto de personagens")
                    if str(existing.get("status") or "") == "completed":
                        conn.rollback()
                        return {
                            "ok": True,
                            "already_completed": True,
                            "batch_id": batch_id,
                            "retire_character_count": len(retired_ids),
                        }
                else:
                    cur.execute(
                        """
                        INSERT INTO catalog_retirement_batches (
                            batch_id, audit_hash, retire_character_count, status, started_at
                        ) VALUES (%s, %s, %s, 'running', NOW())
                        """,
                        (batch_id, digest, len(retired_ids)),
                    )

                _lock_catalog_mutation_tables(cur)
                checked = _assert_live_plan_still_current(cur, retired_ids, expected)
                owned_rows = checked["rows"]
                before = checked["summary"]

                closed_refs = _close_pending_refs(cur, retired_ids)
                awards_by_user: dict[int, int] = defaultdict(int)
                inserted_rows = 0

                for row in owned_rows:
                    user_id = int(row.get("user_id") or 0)
                    character_id = int(row.get("character_id") or 0)
                    quantity = max(0, int(row.get("quantity") or 0))
                    if user_id <= 0 or character_id <= 0 or quantity <= 0:
                        continue
                    coins = quantity * COINS_PER_REMOVED_COPY
                    cur.execute(
                        """
                        INSERT INTO catalog_retirement_compensations (
                            batch_id, user_id, character_id, quantity, coins_awarded, created_at
                        ) VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (batch_id, user_id, character_id) DO NOTHING
                        RETURNING coins_awarded
                        """,
                        (batch_id, user_id, character_id, quantity, coins),
                    )
                    inserted = cur.fetchone()
                    if inserted:
                        inserted_rows += 1
                        awards_by_user[user_id] += int(inserted.get("coins_awarded") or 0)

                total_awarded = 0
                for user_id, amount in awards_by_user.items():
                    if amount <= 0:
                        continue
                    cur.execute(
                        """
                        UPDATE users
                        SET coins = COALESCE(coins, 0) + %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        RETURNING coins
                        """,
                        (amount, user_id),
                    )
                    updated_user = cur.fetchone() or {}
                    if not updated_user:
                        raise RuntimeError(f"usuário {user_id} da coleção não existe em users")
                    balance_after = int(updated_user.get("coins") or 0)
                    _record_compensation_transaction(cur, user_id, amount, balance_after, batch_id)
                    total_awarded += amount

                if total_awarded != int(expected["expected_removed_copies"]):
                    raise RuntimeError("total de Coins calculado divergiu do plano final; abortando")

                cur.execute(
                    """
                    DELETE FROM user_card_collection uc
                    WHERE uc.character_id = ANY(%s)
                      AND EXISTS (
                          SELECT 1
                          FROM catalog_retirement_compensations c
                          WHERE c.batch_id = %s
                            AND c.user_id = uc.user_id
                            AND c.character_id = uc.character_id
                      )
                    """,
                    (retired_ids, batch_id),
                )
                deleted_collection_rows = int(cur.rowcount or 0)

                favorite_result = _clear_retired_favorites(cur, retired_ids)

                cur.execute(
                    """
                    UPDATE catalog_retirement_batches
                    SET status = 'completed', completed_at = NOW()
                    WHERE batch_id = %s
                    """,
                    (batch_id,),
                )
                conn.commit()
                return {
                    "ok": True,
                    "already_completed": False,
                    "batch_id": batch_id,
                    "retire_character_count": len(retired_ids),
                    "affected_users": before["affected_users"],
                    "removed_copies": before["removed_copies"],
                    "coins_awarded": total_awarded,
                    "ledger_rows_inserted": inserted_rows,
                    "collection_rows_deleted": deleted_collection_rows,
                    **favorite_result,
                    **closed_refs,
                }
            except Exception:
                conn.rollback()
                raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Aposenta personagens e paga 1 Coin por cópia removida, com ledger idempotente.")
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT), help="JSON para dry-run (retire_ids ou lista JSON).")
    parser.add_argument("--plan", help="Plano final source.catalog-cleanup.final-plan.v1. Obrigatório com --apply.")
    parser.add_argument("--batch-id", default="catalog_cleanup_2026_09_v2")
    parser.add_argument("--approve-final-hash", default="", help="Hash SHA-256 final. Obrigatório e exato com --apply.")
    parser.add_argument("--apply", action="store_true", help="Sem esta flag, executa somente uma simulação de leitura.")
    args = parser.parse_args()

    if not args.apply:
        source = Path(args.plan or args.audit)
        retired_ids = load_retired_ids(source)
        if not retired_ids:
            print("NO_RETIRED_IDS")
            return 0
        result = dry_run(retired_ids)
        print("CATALOG_RETIREMENT_DRY_RUN", json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    if not args.plan:
        parser.error("--apply exige --plan; audit bruto/lista de IDs nunca pode ser aplicado diretamente")
    expected = load_apply_plan(Path(args.plan), args.approve_final_hash)
    result = apply_batch(
        expected["retired_ids"],
        str(args.batch_id).strip(),
        expected=expected,
    )
    print("CATALOG_RETIREMENT_APPLY", json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
