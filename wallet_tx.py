from __future__ import annotations

import json
from typing import Any, Dict

from game_rules import DICE_INITIAL_BALANCE, DICE_MAX_BALANCE, dice_slot_number, recharged_dice_balance


def lock_wallet(cur, user_id: int) -> Dict[str, Any]:
    """Return a refreshed wallet row locked inside the caller's transaction."""
    user_id = int(user_id)
    current_slot = dice_slot_number()
    cur.execute(
        """
        INSERT INTO game_wallets (user_id, coins, dice, spins, dice_slot)
        VALUES (%s, 0, %s, 0, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, DICE_INITIAL_BALANCE, current_slot),
    )
    cur.execute(
        """
        SELECT user_id, coins, dice, spins, dice_slot
        FROM game_wallets
        WHERE user_id = %s
        FOR UPDATE
        """,
        (user_id,),
    )
    row = dict(cur.fetchone() or {})
    if not row:
        raise RuntimeError("wallet_missing")

    new_dice, new_slot = recharged_dice_balance(
        int(row.get("dice") or 0),
        int(row.get("dice_slot")) if row.get("dice_slot") is not None else None,
        current_slot,
    )
    if new_dice != int(row.get("dice") or 0) or new_slot != int(row.get("dice_slot") or 0):
        cur.execute(
            """
            UPDATE game_wallets
            SET dice = %s,
                dice_slot = %s,
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING user_id, coins, dice, spins, dice_slot
            """,
            (new_dice, new_slot, user_id),
        )
        row = dict(cur.fetchone() or row)
    return row


def wallet_payload(row: Dict[str, Any]) -> Dict[str, int]:
    return {
        "coins": int(row.get("coins") or 0),
        "dice": int(row.get("dice") or 0),
        "spins": int(row.get("spins") or 0),
        "dice_max": DICE_MAX_BALANCE,
    }


def insert_ledger(
    cur,
    *,
    user_id: int,
    resource: str,
    delta: int,
    reason: str,
    reference: str = "",
    metadata: Dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO game_ledger
        (user_id, resource, delta, reason, reference, metadata)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            int(user_id),
            str(resource),
            int(delta),
            str(reason),
            str(reference or "") or None,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
