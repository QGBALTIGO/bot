"""Coins-only market. Inventory reservations, bid escrow and final settlement are atomic."""

from __future__ import annotations
import logging
from uuid import uuid4
from database_core import run
from database_shop_safety import lock_inventories
from source_features.common import (
    FeatureError,
    transaction,
    account,
    operation,
    inventory_guard,
    remove_copies,
    add_copies,
    move_coins,
)
from source_features.collection import character

log = logging.getLogger(__name__)


def _listing(cur, listing_id: str):
    cur.execute(
        "SELECT *, ends_at<=NOW() AS ended FROM source_market WHERE id=%s FOR UPDATE",
        (listing_id,),
    )
    row = cur.fetchone()
    if not row:
        raise FeatureError("listing_missing", "Anúncio não encontrado.", 404)
    return row


def _participants(cur, *uids):
    users = sorted({int(uid) for uid in uids if uid})
    lock_inventories(cur, *users)
    for uid in users:
        account(cur, uid)


def _release(cur, row):
    cur.execute(
        "DELETE FROM source_reservations WHERE owner_type='market' AND owner_id=%s",
        (row["id"],),
    )


def _transfer(cur, row, buyer):
    # Caller holds listing, both accounts and inventories. Unlock inside this same transaction.
    _release(cur, row)
    inventory_guard(cur, row["seller_id"], row["character_id"], row["quantity"])
    remove_copies(cur, row["seller_id"], row["character_id"], row["quantity"])
    add_copies(cur, buyer, row["character_id"], row["quantity"])
    cur.execute(
        "UPDATE source_market SET status='sold',bidder_id=%s,version=version+1 WHERE id=%s",
        (buyer, row["id"]),
    )


def create(uid: int, data: dict):
    from cards_service import get_character_by_id

    if not get_character_by_id(data["character_id"]):
        raise FeatureError(
            "invalid_character", "Personagem indisponível no catálogo.", 400
        )
    with transaction(uid) as cur:
        account(cur, uid)

        def execute():
            cur.execute(
                "SELECT COUNT(*) n FROM source_market WHERE seller_id=%s AND status='active'",
                (uid,),
            )
            if cur.fetchone()["n"] >= 10:
                raise FeatureError(
                    "listing_limit",
                    "Encerre um dos seus 10 anúncios antes de criar outro.",
                )
            cur.execute(
                "SELECT preserve_last FROM source_collecting_settings WHERE user_id=%s",
                (uid,),
            )
            preserve = (cur.fetchone() or {}).get("preserve_last", True)
            inventory_guard(
                cur, uid, data["character_id"], data["quantity"], preserve_last=preserve
            )
            key = str(uuid4())
            cur.execute(
                "INSERT INTO source_market(id,seller_id,character_id,quantity,kind,price,ends_at,hard_ends_at) VALUES(%s,%s,%s,%s,%s,%s,NOW()+make_interval(hours=>%s),NOW()+make_interval(hours=>%s)+INTERVAL '10 minutes')",
                (
                    key,
                    uid,
                    data["character_id"],
                    data["quantity"],
                    data["kind"],
                    data["price"],
                    data["hours"],
                    data["hours"],
                ),
            )
            cur.execute(
                "INSERT INTO source_reservations(user_id,character_id,owner_type,owner_id) VALUES(%s,%s,'market',%s)",
                (uid, data["character_id"], key),
            )
            return {"ok": True, "id": key}

        return operation(
            cur,
            uid,
            data["request_id"],
            "listing-create",
            {k: v for k, v in data.items() if k != "request_id"},
            execute,
        )


def listings(uid: int, mine=False, offset=0):
    rows = run(
        """SELECT m.*,COALESCE(NULLIF(p.nickname,''),'Colecionador') AS seller_name
        FROM source_market m LEFT JOIN user_profile_settings p ON p.user_id=m.seller_id
        WHERE """
        + ("m.seller_id=%s" if mine else "m.status='active'")
        + """ ORDER BY m.created_at DESC,m.id LIMIT 25 OFFSET %s""",
        ((uid, offset) if mine else (offset,)),
        fetch="all",
    )
    return {
        "items": [
            {
                "id": str(r["id"]),
                "character": character(int(r["character_id"])),
                "quantity": r["quantity"],
                "kind": r["kind"],
                "price": r["price"],
                "bid": r["bid"],
                "minimum_bid": max(r["price"], r["bid"] + 1),
                "status": r["status"],
                "ends_at": r["ends_at"].isoformat(),
                "version": r["version"],
                "is_owner": uid == r["seller_id"],
                "is_highest_bidder": uid == r["bidder_id"],
                "seller_name": r["seller_name"],
            }
            for r in rows[:24]
        ],
        "has_more": len(rows) > 24,
    }


def act(
    uid: int, key: str, action: str, request_id: str, version: int, amount: int = 0
):
    with transaction() as cur:
        row = _listing(cur, key)
        _participants(cur, uid, row["seller_id"], row["bidder_id"])

        def execute():
            if row["status"] != "active":
                raise FeatureError("listing_closed", "Este anúncio já foi encerrado.")
            if version != row["version"]:
                raise FeatureError(
                    "listing_changed",
                    "O anúncio mudou. Confira o valor atualizado e confirme novamente.",
                )
            if action == "cancel":
                if uid != row["seller_id"]:
                    raise FeatureError(
                        "forbidden", "Apenas o anunciante pode cancelar.", 403
                    )
                if row["bidder_id"]:
                    raise FeatureError(
                        "has_bids", "Um leilão com lances não pode ser cancelado."
                    )
                _release(cur, row)
                cur.execute(
                    "UPDATE source_market SET status='cancelled',version=version+1 WHERE id=%s",
                    (key,),
                )
                return {"ok": True, "status": "cancelled"}
            if row["ended"]:
                raise FeatureError(
                    "listing_ended",
                    "O prazo encerrou. Use Concluir para liberar a reserva.",
                )
            if uid == row["seller_id"]:
                raise FeatureError(
                    "own_listing",
                    "Você não pode comprar ou dar lances no próprio anúncio.",
                )
            if action == "buy":
                if row["kind"] != "fixed":
                    raise FeatureError(
                        "invalid_action",
                        "Este anúncio aceita lances, não compra direta.",
                        400,
                    )
                move_coins(cur, uid, -row["price"], "market_purchase", key)
                _transfer(cur, row, uid)
                move_coins(cur, row["seller_id"], row["price"], "market_sale", key)
                return {"ok": True, "status": "sold"}
            if action != "bid" or row["kind"] != "auction":
                raise FeatureError("invalid_action", "Ação inválida.", 400)
            if amount < max(row["price"], row["bid"] + 1):
                raise FeatureError(
                    "bid_low", "O lance deve superar o atual e atingir o valor inicial."
                )
            if row["bidder_id"] == uid:
                move_coins(cur, uid, -(amount - row["bid"]), "auction_escrow", key)
            else:
                move_coins(cur, uid, -amount, "auction_escrow", key)
                if row["bidder_id"]:
                    move_coins(cur, row["bidder_id"], row["bid"], "auction_refund", key)
            cur.execute(
                "UPDATE source_market SET bid=%s,bidder_id=%s,version=version+1,ends_at=CASE WHEN ends_at-NOW()<INTERVAL '2 minutes' THEN LEAST(hard_ends_at,NOW()+INTERVAL '2 minutes') ELSE ends_at END WHERE id=%s",
                (amount, uid, key),
            )
            return {"ok": True, "status": "active", "bid": amount, "escrowed": True}

        return operation(
            cur,
            uid,
            request_id,
            f"market-{action}",
            {"id": key, "version": version, "amount": amount},
            execute,
        )


def settle(key: str, requester: int | None = None):
    with transaction() as cur:
        row = _listing(cur, key)
        if requester is not None and requester not in (
            row["seller_id"],
            row["bidder_id"],
        ):
            raise FeatureError(
                "forbidden", "Apenas participantes podem concluir este anúncio.", 403
            )
        if row["status"] != "active":
            return {"ok": True, "status": row["status"]}
        if not row["ended"]:
            raise FeatureError("not_ended", "O prazo do anúncio ainda não terminou.")
        _participants(cur, row["seller_id"], row["bidder_id"])
        if row["kind"] == "auction" and row["bidder_id"]:
            # Escrow already debited at bidding. Never charge the winner twice.
            _transfer(cur, row, row["bidder_id"])
            move_coins(cur, row["seller_id"], row["bid"], "auction_sale", key)
            return {"ok": True, "status": "sold"}
        _release(cur, row)
        cur.execute(
            "UPDATE source_market SET status='expired',version=version+1 WHERE id=%s",
            (key,),
        )
        return {"ok": True, "status": "expired"}


def settle_due():
    rows = run(
        "SELECT id FROM source_market WHERE status='active' AND ends_at<=NOW() ORDER BY ends_at LIMIT 40",
        fetch="all",
    )
    for r in rows:
        try:
            settle(str(r["id"]))
        except Exception:
            log.exception("market settlement failed id=%s", str(r["id"]))


async def settlement_worker():
    import asyncio

    while True:
        try:
            await asyncio.to_thread(settle_due)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("market settlement batch failed")
        await asyncio.sleep(30)
