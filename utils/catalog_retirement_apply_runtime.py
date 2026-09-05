from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from psycopg.rows import dict_row

from utils.catalog_impact_manifest import candidate_ids_hash
from utils.catalog_retirement_plan import load_final_retirement_plan

COINS_PER_REMOVED_COPY = 1


def _table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS reg", (f"public.{table}",))
    return bool((cur.fetchone() or {}).get("reg"))


def _runtime_deleted_ids() -> set[int]:
    import os
    from pathlib import Path

    path = Path(str(os.getenv("CARDS_OVERRIDES_PATH") or "").strip())
    if not path.exists():
        raise RuntimeError("CARDS_OVERRIDES_PATH ativo não existe")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("override runtime inválido")
    out: set[int] = set()
    for value in raw.get("deleted_characters") or []:
        try:
            cid = int(value)
        except Exception:
            continue
        if cid > 0:
            out.add(cid)
    return out


def _summarize_owned_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    users = {int(row.get("user_id") or 0) for row in rows if int(row.get("user_id") or 0) > 0}
    copies = sum(max(0, int(row.get("quantity") or 0)) for row in rows)
    return {
        "affected_users": len(users),
        "removed_copies": copies,
        "owner_character_links": len(rows),
    }


def _ensure_migration_tables(cur) -> None:
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_retired_characters (
            character_id BIGINT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            retired_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE OR REPLACE FUNCTION block_retired_character_collection_write()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF COALESCE(NEW.quantity, 0) > 0
               AND EXISTS (
                    SELECT 1 FROM catalog_retired_characters r
                    WHERE r.character_id = NEW.character_id
               ) THEN
                RAISE EXCEPTION 'character_id % is retired and cannot enter user_card_collection', NEW.character_id
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'trg_block_retired_character_collection_write'
                  AND tgrelid = 'user_card_collection'::regclass
                  AND NOT tgisinternal
            ) THEN
                CREATE TRIGGER trg_block_retired_character_collection_write
                BEFORE INSERT OR UPDATE ON user_card_collection
                FOR EACH ROW
                EXECUTE FUNCTION block_retired_character_collection_write();
            END IF;
        END;
        $$
        """
    )


def _lock_tables(cur) -> list[str]:
    required = ["user_card_collection", "users", "shop_transactions"]
    optional = [
        "card_trades",
        "capture_spawns",
        "active_group_spawns",
        "shop_card_sales",
        "user_profile_settings",
        "user_collection_profile",
    ]
    missing_required = [name for name in required if not _table_exists(cur, name)]
    if missing_required:
        raise RuntimeError(f"tabelas críticas ausentes: {missing_required}")
    existing = required + [name for name in optional if _table_exists(cur, name)]
    cur.execute("LOCK TABLE " + ", ".join(existing) + " IN SHARE ROW EXCLUSIVE MODE")
    return existing


def _load_owned_rows_for_update(cur, retired_ids: list[int]) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT user_id, character_id, quantity
        FROM user_card_collection
        WHERE quantity > 0
          AND character_id = ANY(%s)
        ORDER BY user_id, character_id
        FOR UPDATE
        """,
        (retired_ids,),
    )
    return [dict(row) for row in (cur.fetchall() or [])]


def _assert_no_new_high_impact(cur, retired_ids: list[int], owner_threshold: int, copy_threshold: int) -> None:
    cur.execute(
        """
        SELECT character_id,
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
    rows = [dict(row) for row in (cur.fetchall() or [])]
    if rows:
        preview = [
            {
                "character_id": int(row.get("character_id") or 0),
                "owners": int(row.get("owners") or 0),
                "copies": int(row.get("copies") or 0),
            }
            for row in rows[:20]
        ]
        raise RuntimeError(f"uso real mudou; nova trava de coleção acionada: {preview}")


def _register_db_guard(cur, retired_ids: list[int], batch_id: str) -> None:
    cur.execute(
        """
        INSERT INTO catalog_retired_characters (character_id, batch_id, retired_at)
        SELECT item, %s, NOW()
        FROM unnest(%s::bigint[]) AS item
        ON CONFLICT (character_id) DO UPDATE
        SET batch_id = EXCLUDED.batch_id,
            retired_at = EXCLUDED.retired_at
        """,
        (batch_id, retired_ids),
    )


def _close_optional_refs(cur, retired_ids: list[int], tables: set[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    if "card_trades" in tables:
        cur.execute(
            """
            UPDATE card_trades SET status = 'cancelled'
            WHERE status = 'pending'
              AND (from_character_id = ANY(%s) OR to_character_id = ANY(%s))
            """,
            (retired_ids, retired_ids),
        )
        result["pending_trades_cancelled"] = int(cur.rowcount or 0)

    if "capture_spawns" in tables:
        cur.execute(
            """
            UPDATE capture_spawns
            SET status = 'escaped', updated_at = NOW(), expires_at = LEAST(expires_at, NOW())
            WHERE character_id = ANY(%s) AND status = 'active'
            """,
            (retired_ids,),
        )
        result["active_spawns_expired"] = int(cur.rowcount or 0)
        cur.execute(
            """
            UPDATE capture_spawns
            SET status = 'captured_offer_expired', purchase_expires_at = NOW(), updated_at = NOW()
            WHERE character_id = ANY(%s) AND status = 'captured_offer_open'
            """,
            (retired_ids,),
        )
        result["purchase_offers_expired"] = int(cur.rowcount or 0)

    if "active_group_spawns" in tables:
        cur.execute("DELETE FROM active_group_spawns WHERE character_id = ANY(%s)", (retired_ids,))
        result["legacy_spawns_removed"] = int(cur.rowcount or 0)

    if "shop_card_sales" in tables:
        cur.execute("DELETE FROM shop_card_sales WHERE character_id = ANY(%s)", (retired_ids,))
        result["buyback_sales_invalidated"] = int(cur.rowcount or 0)
    return result


def _clear_optional_favorites(cur, retired_ids: list[int], tables: set[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    if "user_profile_settings" in tables:
        cur.execute(
            """
            UPDATE user_profile_settings
            SET favorite_character_id = NULL, updated_at = NOW()
            WHERE favorite_character_id = ANY(%s)
            """,
            (retired_ids,),
        )
        result["profile_favorites_cleared"] = int(cur.rowcount or 0)
    if "user_collection_profile" in tables:
        cur.execute(
            """
            UPDATE user_collection_profile
            SET favorite_character_id = NULL, updated_at = NOW()
            WHERE favorite_character_id = ANY(%s)
            """,
            (retired_ids,),
        )
        result["collection_favorites_cleared"] = int(cur.rowcount or 0)
    return result


def _record_shop_transaction(cur, user_id: int, amount: int, balance_after: int, batch_id: str) -> None:
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


def apply_final_retirements() -> dict[str, Any]:
    plan = load_final_retirement_plan()
    retired_ids = list(plan["retired_ids"])
    batch_id = str(plan.get("batch_id") or "").strip()
    final_hash = str(plan.get("actual_final_retire_ids_sha256") or "").strip().lower()
    compensation = plan.get("compensation") or {}
    expected_users = int(compensation.get("affected_users") or 0)
    expected_copies = int(compensation.get("removed_copies") or 0)
    owner_threshold = int(plan.get("owner_review_threshold") or 10)
    copy_threshold = int(plan.get("copy_review_threshold") or 20)

    if not batch_id or len(retired_ids) != int(plan.get("final_retire_count") or 0):
        raise RuntimeError("plano final incompleto")
    if candidate_ids_hash(retired_ids) != final_hash:
        raise RuntimeError("hash final do plano não confere")
    if expected_copies != int(compensation.get("coins_required") or -1):
        raise RuntimeError("Coins esperados não correspondem às cópias")

    runtime_deleted = _runtime_deleted_ids()
    missing_disabled = sorted(set(retired_ids) - runtime_deleted)
    if missing_disabled:
        raise RuntimeError(
            f"catálogo ainda não desativou todos os RETIRE finais: {len(missing_disabled)} ausentes"
        )

    from database_core import pool

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                _ensure_migration_tables(cur)
                cur.execute(
                    "SELECT batch_id, audit_hash, status FROM catalog_retirement_batches WHERE batch_id = %s FOR UPDATE",
                    (batch_id,),
                )
                existing_batch = cur.fetchone()
                if existing_batch and str(existing_batch.get("audit_hash") or "") != final_hash:
                    raise RuntimeError("batch_id já existe com hash diferente")
                if existing_batch and str(existing_batch.get("status") or "") == "completed":
                    conn.rollback()
                    return {
                        "ok": True,
                        "already_completed": True,
                        "batch_id": batch_id,
                        "retire_character_count": len(retired_ids),
                        "final_retire_ids_sha256": final_hash,
                    }
                if not existing_batch:
                    cur.execute(
                        """
                        INSERT INTO catalog_retirement_batches
                            (batch_id, audit_hash, retire_character_count, status, started_at)
                        VALUES (%s, %s, %s, 'running', NOW())
                        """,
                        (batch_id, final_hash, len(retired_ids)),
                    )

                existing_tables = set(_lock_tables(cur))
                _assert_no_new_high_impact(cur, retired_ids, owner_threshold, copy_threshold)
                owned_rows = _load_owned_rows_for_update(cur, retired_ids)
                current = _summarize_owned_rows(owned_rows)
                if current["affected_users"] != expected_users:
                    raise RuntimeError(
                        f"affected_users mudou: {current['affected_users']} != {expected_users}"
                    )
                if current["removed_copies"] != expected_copies:
                    raise RuntimeError(
                        f"removed_copies mudou: {current['removed_copies']} != {expected_copies}"
                    )

                _register_db_guard(cur, retired_ids, batch_id)
                refs = _close_optional_refs(cur, retired_ids, existing_tables)

                awards_by_user: dict[int, int] = defaultdict(int)
                ledger_rows = 0
                for row in owned_rows:
                    user_id = int(row.get("user_id") or 0)
                    character_id = int(row.get("character_id") or 0)
                    quantity = max(0, int(row.get("quantity") or 0))
                    if user_id <= 0 or character_id <= 0 or quantity <= 0:
                        continue
                    coins = quantity * COINS_PER_REMOVED_COPY
                    cur.execute(
                        """
                        INSERT INTO catalog_retirement_compensations
                            (batch_id, user_id, character_id, quantity, coins_awarded, created_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (batch_id, user_id, character_id) DO NOTHING
                        RETURNING coins_awarded
                        """,
                        (batch_id, user_id, character_id, quantity, coins),
                    )
                    inserted = cur.fetchone()
                    if inserted:
                        ledger_rows += 1
                        awards_by_user[user_id] += int(inserted.get("coins_awarded") or 0)

                total_awarded = 0
                for user_id, amount in awards_by_user.items():
                    if amount <= 0:
                        continue
                    cur.execute(
                        """
                        UPDATE users
                        SET coins = COALESCE(coins, 0) + %s, updated_at = NOW()
                        WHERE user_id = %s
                        RETURNING coins
                        """,
                        (amount, user_id),
                    )
                    updated = cur.fetchone()
                    if not updated:
                        raise RuntimeError(f"user_id {user_id} da coleção não existe em users")
                    _record_shop_transaction(cur, user_id, amount, int(updated.get("coins") or 0), batch_id)
                    total_awarded += amount

                if total_awarded != expected_copies:
                    raise RuntimeError(f"Coins calculados divergiram: {total_awarded} != {expected_copies}")

                cur.execute(
                    """
                    DELETE FROM user_card_collection uc
                    WHERE uc.character_id = ANY(%s)
                      AND EXISTS (
                          SELECT 1 FROM catalog_retirement_compensations c
                          WHERE c.batch_id = %s
                            AND c.user_id = uc.user_id
                            AND c.character_id = uc.character_id
                      )
                    """,
                    (retired_ids, batch_id),
                )
                collection_rows_deleted = int(cur.rowcount or 0)
                if collection_rows_deleted != len(owned_rows):
                    raise RuntimeError(
                        f"linhas removidas divergiram do snapshot travado: {collection_rows_deleted} != {len(owned_rows)}"
                    )

                favorites = _clear_optional_favorites(cur, retired_ids, existing_tables)
                cur.execute(
                    "SELECT COUNT(*)::BIGINT AS total FROM user_card_collection WHERE quantity > 0 AND character_id = ANY(%s)",
                    (retired_ids,),
                )
                remaining = int((cur.fetchone() or {}).get("total") or 0)
                if remaining != 0:
                    raise RuntimeError(f"ainda restam {remaining} linhas aposentadas na coleção")

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
                    "final_retire_ids_sha256": final_hash,
                    "affected_users": expected_users,
                    "removed_copies": expected_copies,
                    "coins_awarded": total_awarded,
                    "ledger_rows": ledger_rows,
                    "collection_rows_deleted": collection_rows_deleted,
                    **refs,
                    **favorites,
                }
            except Exception:
                conn.rollback()
                raise


def run_and_log_apply() -> dict[str, Any]:
    result = apply_final_retirements()
    print(
        "CATALOG_RETIREMENT_APPLY_RESULT "
        + json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        flush=True,
    )
    return result
