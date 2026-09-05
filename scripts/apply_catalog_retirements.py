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


def load_owned_rows(cur, retired_ids: list[int]) -> list[dict[str, Any]]:
    if not retired_ids:
        return []
    cur.execute(
        """
        SELECT user_id, character_id, quantity
        FROM user_card_collection
        WHERE quantity > 0
          AND character_id = ANY(%s)
        ORDER BY user_id, character_id
        """,
        (retired_ids,),
    )
    return [dict(row) for row in (cur.fetchall() or [])]


def dry_run(retired_ids: list[int]) -> dict[str, Any]:
    from database_core import pool

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = load_owned_rows(cur, retired_ids)
            summary = summarize_rows(rows)
            summary["retire_character_count"] = len(retired_ids)
            summary["apply"] = False
            return summary


def apply_batch(retired_ids: list[int], batch_id: str) -> dict[str, Any]:
    from database_core import pool

    digest = audit_hash(retired_ids)
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

                owned_rows = load_owned_rows(cur, retired_ids)
                before = summarize_rows(owned_rows)
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
                        """,
                        (amount, user_id),
                    )
                    total_awarded += amount

                # Aposenta de verdade da coleção somente depois que a compensação
                # daquele usuário/personagem foi registrada na mesma transação.
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

                # Se o personagem aposentado era favorito, limpa a referência para
                # não deixar perfil apontando para uma carta que deixou o catálogo.
                cur.execute(
                    """
                    UPDATE user_profile_settings
                    SET favorite_character_id = NULL,
                        updated_at = NOW()
                    WHERE favorite_character_id = ANY(%s)
                    """,
                    (retired_ids,),
                )
                cleared_favorites = int(cur.rowcount or 0)

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
                    "favorites_cleared": cleared_favorites,
                }
            except Exception:
                conn.rollback()
                raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Aposenta personagens e paga 1 Coin por cópia removida, com ledger idempotente.")
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT), help="JSON com retire_ids ou uma lista JSON de IDs.")
    parser.add_argument("--batch-id", default="catalog_cleanup_2026_09_v1")
    parser.add_argument("--apply", action="store_true", help="Sem esta flag, executa somente uma simulação de leitura.")
    args = parser.parse_args()

    retired_ids = load_retired_ids(Path(args.audit))
    if not retired_ids:
        print("NO_RETIRED_IDS")
        return 0

    if not args.apply:
        result = dry_run(retired_ids)
        print("CATALOG_RETIREMENT_DRY_RUN", json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    result = apply_batch(retired_ids, str(args.batch_id).strip())
    print("CATALOG_RETIREMENT_APPLY", json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
