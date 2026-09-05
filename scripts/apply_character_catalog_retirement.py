from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database_core import pool  # noqa: E402

DEFAULT_PLAN = ROOT / "data" / "character_catalog_plan.json"


def load_plan(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("catalog plan must be a JSON object")
    return raw


def retired_ids_from_plan(plan: dict[str, Any]) -> list[int]:
    ids: set[int] = set()
    for raw in plan.get("retired_character_ids") or []:
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid > 0:
            ids.add(cid)
    if not ids:
        for row in plan.get("retired_characters") or []:
            if not isinstance(row, dict):
                continue
            try:
                cid = int(row.get("id") or 0)
            except Exception:
                continue
            if cid > 0:
                ids.add(cid)
    return sorted(ids)


def ensure_migration_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS character_catalog_retirement_compensations (
            batch_key TEXT NOT NULL,
            user_id BIGINT NOT NULL,
            character_id BIGINT NOT NULL,
            quantity_removed INTEGER NOT NULL CHECK (quantity_removed > 0),
            coins_awarded INTEGER NOT NULL CHECK (coins_awarded >= 0),
            processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (batch_key, user_id, character_id)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_character_retirement_comp_user
        ON character_catalog_retirement_compensations (user_id, processed_at DESC)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_character_retirement_comp_character
        ON character_catalog_retirement_compensations (character_id, processed_at DESC)
        """
    )


def table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS name", (f"public.{table_name}",))
    row = cur.fetchone() or {}
    return bool(row.get("name"))


def preview(cur, retired_ids: list[int], coins_per_copy: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
            COUNT(*)::BIGINT AS owner_rows,
            COUNT(DISTINCT user_id)::BIGINT AS affected_users,
            COALESCE(SUM(quantity), 0)::BIGINT AS copies,
            COUNT(DISTINCT character_id)::BIGINT AS owned_retired_characters
        FROM user_card_collection
        WHERE character_id = ANY(%s)
          AND quantity > 0
        """,
        (retired_ids,),
    )
    row = cur.fetchone() or {}
    copies = int(row.get("copies") or 0)
    return {
        "affected_users": int(row.get("affected_users") or 0),
        "owner_rows": int(row.get("owner_rows") or 0),
        "copies_to_remove": copies,
        "owned_retired_characters": int(row.get("owned_retired_characters") or 0),
        "coins_to_award": copies * int(coins_per_copy),
    }


def apply_batch(
    *,
    batch_key: str,
    retired_ids: list[int],
    coins_per_copy: int,
) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                # Only one retirement migration may mutate collections at a time.
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('source_character_catalog_retirement'))")
                ensure_migration_table(cur)
                before = preview(cur, retired_ids, coins_per_copy)

                cur.execute(
                    """
                    SELECT user_id, character_id, quantity
                    FROM user_card_collection
                    WHERE character_id = ANY(%s)
                      AND quantity > 0
                    ORDER BY user_id, character_id
                    FOR UPDATE
                    """,
                    (retired_ids,),
                )
                owned_rows = cur.fetchall() or []

                inserted: list[dict[str, Any]] = []
                for row in owned_rows:
                    user_id = int(row.get("user_id") or 0)
                    character_id = int(row.get("character_id") or 0)
                    quantity = int(row.get("quantity") or 0)
                    if user_id <= 0 or character_id <= 0 or quantity <= 0:
                        continue
                    coins = quantity * int(coins_per_copy)
                    cur.execute(
                        """
                        INSERT INTO character_catalog_retirement_compensations (
                            batch_key, user_id, character_id, quantity_removed, coins_awarded
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (batch_key, user_id, character_id) DO NOTHING
                        RETURNING user_id, character_id, quantity_removed, coins_awarded
                        """,
                        (batch_key, user_id, character_id, quantity, coins),
                    )
                    created = cur.fetchone()
                    if created:
                        inserted.append(dict(created))

                coins_by_user: dict[int, int] = {}
                for row in inserted:
                    uid = int(row["user_id"])
                    coins_by_user[uid] = coins_by_user.get(uid, 0) + int(row["coins_awarded"])

                for user_id, coins in coins_by_user.items():
                    # Users referenced by the collection should already exist, but this makes
                    # the migration resilient to old/orphan rows.
                    cur.execute(
                        """
                        INSERT INTO users (user_id, coins, created_at, updated_at)
                        VALUES (%s, %s, NOW(), NOW())
                        ON CONFLICT (user_id)
                        DO UPDATE SET
                            coins = COALESCE(users.coins, 0) + EXCLUDED.coins,
                            updated_at = NOW()
                        """,
                        (user_id, coins),
                    )

                # Delete only rows compensated in THIS transaction/batch. If the command is
                # accidentally run again, ON CONFLICT creates no new compensation and no
                # second coin credit is possible.
                for row in inserted:
                    cur.execute(
                        """
                        DELETE FROM user_card_collection
                        WHERE user_id = %s
                          AND character_id = %s
                        """,
                        (int(row["user_id"]), int(row["character_id"])),
                    )

                # A removed character cannot remain selected as a favourite.
                if table_exists(cur, "user_collection_profile"):
                    cur.execute(
                        """
                        UPDATE user_collection_profile
                        SET favorite_character_id = NULL,
                            updated_at = NOW()
                        WHERE favorite_character_id = ANY(%s)
                        """,
                        (retired_ids,),
                    )
                    favourites_cleared = int(cur.rowcount or 0)
                else:
                    favourites_cleared = 0

                # Prevent an already-retired card from still being claimable via an active
                # group spawn. Historical capture rows remain untouched for audit/history.
                active_spawns_removed = 0
                if table_exists(cur, "active_group_spawns"):
                    cur.execute(
                        "DELETE FROM active_group_spawns WHERE character_id = ANY(%s)",
                        (retired_ids,),
                    )
                    active_spawns_removed = int(cur.rowcount or 0)

                # Daily shop tables have changed names across versions. Clean any known live
                # offer table only when it exists, without coupling this migration to one schema.
                shop_offer_rows_removed = 0
                for table_name in ("shop_daily_offers", "shop_card_offers", "daily_shop_offers"):
                    if not table_exists(cur, table_name):
                        continue
                    cur.execute(
                        f"DELETE FROM {table_name} WHERE character_id = ANY(%s)",
                        (retired_ids,),
                    )
                    shop_offer_rows_removed += int(cur.rowcount or 0)

                conn.commit()
                copies_removed = sum(int(x["quantity_removed"]) for x in inserted)
                coins_awarded = sum(int(x["coins_awarded"]) for x in inserted)
                return {
                    "batch_key": batch_key,
                    "retired_character_ids": len(retired_ids),
                    "before": before,
                    "compensation_rows_created": len(inserted),
                    "users_compensated": len(coins_by_user),
                    "copies_removed": copies_removed,
                    "coins_awarded": coins_awarded,
                    "favourites_cleared": favourites_cleared,
                    "active_spawns_removed": active_spawns_removed,
                    "shop_offer_rows_removed": shop_offer_rows_removed,
                }
            except Exception:
                conn.rollback()
                raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refund and remove owned copies of characters retired by a catalog curation plan."
    )
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--batch-key", default="")
    parser.add_argument("--coins-per-copy", type=int, default=1)
    parser.add_argument("--apply", action="store_true", help="Actually mutate DB. Default is preview only.")
    args = parser.parse_args()

    if args.coins_per_copy < 0 or args.coins_per_copy > 100:
        raise SystemExit("--coins-per-copy must be between 0 and 100")

    plan_path = Path(args.plan)
    plan = load_plan(plan_path)
    retired_ids = retired_ids_from_plan(plan)
    if not retired_ids:
        print(json.dumps({"ok": True, "message": "No retired character IDs in plan."}))
        return 0

    generated = int(plan.get("generated_at_epoch") or 0)
    batch_key = str(args.batch_key or f"catalog-v{int(plan.get('version') or 1)}-{generated}").strip()
    if not batch_key:
        raise SystemExit("batch key is empty")

    if not args.apply:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_migration_table(cur)
                result = preview(cur, retired_ids, args.coins_per_copy)
                conn.rollback()
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "preview",
                    "batch_key": batch_key,
                    "retired_character_ids": len(retired_ids),
                    **result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    result = apply_batch(
        batch_key=batch_key,
        retired_ids=retired_ids,
        coins_per_copy=int(args.coins_per_copy),
    )
    print(json.dumps({"ok": True, "mode": "applied", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
