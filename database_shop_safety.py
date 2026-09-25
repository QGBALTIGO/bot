"""One-transaction purchases and sales shared by legacy and native entrypoints."""
from __future__ import annotations

import json
from psycopg.rows import dict_row
from database_core import pool


def lock_inventories(cursor, *user_ids: int) -> None:
    """Serialize regular-card transfers, including destination rows not yet present."""
    for uid in sorted(set(int(value) for value in user_ids)):
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 7342))", (str(uid),))


def _ledger(cur, uid, kind, amount, balance, reference, metadata):
    cur.execute(
        "INSERT INTO shop_transactions (user_id,type,amount,balance_after,reference_id,metadata) "
        "VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
        (uid, kind, amount, balance, reference, json.dumps(metadata)),
    )


def sell_character_atomic(user_id: int, character_id: int) -> dict:
    uid, cid = int(user_id), int(character_id)
    if uid <= 0 or cid <= 0:
        return {"ok": False, "error": "invalid_character"}
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        lock_inventories(cur, uid)
        cur.execute("SELECT coins FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        account = cur.fetchone()
        if not account:
            return {"ok": False, "error": "user_not_found"}
        cur.execute("SELECT quantity FROM user_card_collection WHERE user_id=%s AND character_id=%s FOR UPDATE", (uid, cid))
        quantity = int((cur.fetchone() or {}).get("quantity") or 0)
        if quantity <= 0:
            return {"ok": False, "error": "no_card"}
        cur.execute(
            "SELECT 1 FROM card_trades WHERE status='pending' AND created_at >= NOW()-INTERVAL '24 hours' "
            "AND ((from_user=%s AND from_character_id=%s) OR (to_user=%s AND to_character_id=%s)) LIMIT 1",
            (uid, cid, uid, cid),
        )
        if cur.fetchone():
            return {"ok": False, "error": "card_reserved"}
        from source_features.common import inventory_guard, FeatureError
        try:
            inventory_guard(cur,uid,cid)
        except FeatureError as exc:
            return {"ok": False, "error": exc.code}
        from database_aninexus_social import _remove_one_locked
        _remove_one_locked(cur, uid, cid, quantity)
        cur.execute("UPDATE users SET coins=COALESCE(coins,0)+1,updated_at=NOW() WHERE user_id=%s RETURNING coins", (uid,))
        coins = int(cur.fetchone()["coins"])
        cur.execute(
            "INSERT INTO shop_card_sales (user_id,character_id,price,buyback_available_until) "
            "VALUES (%s,%s,1,NOW()+INTERVAL '72 hours') RETURNING id", (uid, cid),
        )
        sale_id = int(cur.fetchone()["id"])
        _ledger(cur, uid, "sell_character", 1, coins, sale_id, {"character_id": cid})
        return {"ok": True, "coins": coins, "sale_id": sale_id}


def buyback_character_atomic(user_id: int, sale_id: int) -> dict:
    uid, sale_id = int(user_id), int(sale_id)
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        lock_inventories(cur, uid)
        cur.execute("SELECT coins FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        account = cur.fetchone()
        if not account:
            return {"ok": False, "error": "user_not_found"}
        cur.execute(
            "SELECT *, (buyback_available_until > NOW()) AS available FROM shop_card_sales "
            "WHERE id=%s AND user_id=%s FOR UPDATE", (sale_id, uid),
        )
        sale = cur.fetchone()
        if not sale or not sale["available"]:
            return {"ok": False, "error": "sale_unavailable"}
        coins = int(account.get("coins") or 0)
        if coins < 3:
            return {"ok": False, "error": "no_coins"}
        from database_aninexus_social import _add_one_locked
        _add_one_locked(cur, uid, int(sale["character_id"]))
        cur.execute("UPDATE users SET coins=coins-3,updated_at=NOW() WHERE user_id=%s", (uid,))
        # Consume the right to repurchase, while preserving the historical sale row.
        cur.execute("UPDATE shop_card_sales SET buyback_available_until=NULL WHERE id=%s", (sale_id,))
        _ledger(cur, uid, "buyback_character", -3, coins-3, sale_id, {"sale_id": sale_id})
        return {"ok": True, "coins": coins-3}


def buy_dado_atomic(user_id: int) -> dict:
    uid = int(user_id)
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT coins FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        account = cur.fetchone()
        if not account:
            return {"ok": False, "error": "user_not_found"}
        from database import _refresh_dado_locked, DADO_MAX_BALANCE
        state = _refresh_dado_locked(cur, uid)
        coins, balance = int(account.get("coins") or 0), int(state["balance"])
        if balance >= DADO_MAX_BALANCE:
            return {"ok": False, "error": "dado_full", "coins": coins, "dado_balance": balance}
        if coins < 2:
            return {"ok": False, "error": "no_coins", "coins": coins, "dado_balance": balance}
        cur.execute("UPDATE users SET coins=coins-2,dado_balance=dado_balance+1,updated_at=NOW() WHERE user_id=%s", (uid,))
        _ledger(cur, uid, "aninexus_buy_dado", -2, coins-2, None, {"dado_added": 1})
        return {"ok": True, "coins": coins-2, "dado_balance": balance+1}


def purchase_termo_hint_atomic(user_id: int, game_id: int, cost: int = 12, time_limit: int = 300) -> dict:
    """One debit per daily game, with ownership, expiry and balance checked under locks."""
    uid, gid, price = int(user_id), int(game_id), int(cost)
    if uid <= 0 or gid <= 0 or price <= 0:
        return {"ok": False, "error": "invalid_game"}
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT *, (EXTRACT(EPOCH FROM NOW())-start_time <= %s) AS active_time "
                    "FROM termo_games WHERE id=%s AND user_id=%s FOR UPDATE", (int(time_limit), gid, uid))
        game = cur.fetchone()
        if not game or game.get("mode") != "daily" or game.get("status") != "playing" or not game["active_time"]:
            return {"ok": False, "error": "invalid_game"}
        cur.execute("SELECT coins FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        account = cur.fetchone()
        if not account:
            return {"ok": False, "error": "user_not_found"}
        coins = int(account.get("coins") or 0)
        cur.execute("SELECT 1 FROM shop_transactions WHERE user_id=%s AND type='termo_hint' AND reference_id=%s LIMIT 1", (uid, gid))
        if cur.fetchone():
            return {"ok": True, "charged": False, "coins": coins}
        if coins < price:
            return {"ok": False, "error": "no_coins", "coins": coins}
        cur.execute("UPDATE users SET coins=coins-%s,updated_at=NOW() WHERE user_id=%s", (price, uid))
        _ledger(cur, uid, "termo_hint", -price, coins-price, gid, {"game_id": gid})
        return {"ok": True, "charged": True, "coins": coins-price}
