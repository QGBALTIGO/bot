"""Transaction, validation and inventory contracts shared by all collecting features."""

from __future__ import annotations
import hashlib
import json
from contextlib import contextmanager
from typing import Callable
from uuid import UUID
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from database_core import pool
from database_shop_safety import lock_inventories, _ledger


from source_features.errors import FeatureError


@contextmanager
def transaction(*users: int):
    with (
        pool.connection() as conn,
        conn.transaction(),
        conn.cursor(row_factory=dict_row) as cur,
    ):
        cur.execute("SET LOCAL lock_timeout='5s'")
        cur.execute("SET LOCAL statement_timeout='8s'")
        lock_inventories(cur, *users)
        yield cur


def account(cur, uid: int):
    cur.execute("SELECT user_id, coins FROM users WHERE user_id=%s FOR UPDATE", (uid,))
    row = cur.fetchone()
    if not row:
        raise FeatureError(
            "account_missing", "Abra o bot e conclua seu cadastro primeiro.", 404
        )
    return row


def operation(
    cur, uid: int, request_id: str, name: str, payload: dict, execute: Callable
):
    """Replay identical requests; reject reuse for a different action or payload."""
    try:
        key = str(UUID(str(request_id)))
    except (ValueError, TypeError) as exc:
        raise FeatureError(
            "invalid_request_id", "Identificador da ação inválido.", 400
        ) from exc
    cur.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,7343))", (f"{uid}:{key}",)
    )
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    cur.execute(
        "SELECT operation,digest,result FROM source_operations WHERE user_id=%s AND request_id=%s",
        (uid, key),
    )
    prior = cur.fetchone()
    if prior:
        if prior["operation"] != name or prior["digest"] != digest:
            raise FeatureError(
                "request_conflict", "Essa confirmação pertence a outra ação."
            )
        return prior["result"]
    result = execute()
    cur.execute(
        "INSERT INTO source_operations(user_id,request_id,operation,digest,result) VALUES(%s,%s,%s,%s,%s)",
        (uid, key, name, digest, Jsonb(result)),
    )
    return result


def inventory_guard(
    cur,
    uid: int,
    cid: int,
    count: int = 1,
    *,
    preserve_last=False,
    trade_id: int | None = None,
):
    """Call under lock_inventories. Returns quantity only if the card can leave safely."""
    cur.execute(
        "SELECT quantity FROM user_card_collection WHERE user_id=%s AND character_id=%s FOR UPDATE",
        (uid, cid),
    )
    quantity = int((cur.fetchone() or {}).get("quantity") or 0)
    if count < 1 or quantity < count:
        raise FeatureError(
            "card_missing", "Você não possui essa quantidade do personagem."
        )
    cur.execute(
        "SELECT 1 FROM source_card_protection WHERE user_id=%s AND character_id=%s UNION ALL SELECT 1 FROM user_profile_settings WHERE user_id=%s AND favorite_character_id=%s LIMIT 1",
        (uid, cid, uid, cid),
    )
    if cur.fetchone():
        raise FeatureError(
            "card_protected",
            "Personagem protegido. Remova o cadeado ou altere o favorito nas configurações antes de continuar.",
        )
    cur.execute(
        "SELECT 1 FROM source_reservations WHERE user_id=%s AND character_id=%s",
        (uid, cid),
    )
    if cur.fetchone():
        raise FeatureError(
            "card_reserved",
            "Esse personagem está reservado no mercado. Encerre o anúncio primeiro.",
        )
    cur.execute(
        "SELECT 1 FROM card_trades WHERE status='pending' AND created_at>=NOW()-INTERVAL '24 hours' AND trade_id<>%s AND ((from_user=%s AND from_character_id=%s) OR (to_user=%s AND to_character_id=%s)) LIMIT 1",
        (trade_id or 0, uid, cid, uid, cid),
    )
    if cur.fetchone():
        raise FeatureError(
            "card_reserved", "Esse personagem está reservado em uma troca."
        )
    if preserve_last and quantity - count < 1:
        raise FeatureError(
            "last_copy", "A última cópia está preservada. Escolha apenas duplicatas."
        )
    return quantity


def remove_copies(cur, uid: int, cid: int, amount: int):
    cur.execute(
        "UPDATE user_card_collection SET quantity=quantity-%s,updated_at=NOW() WHERE user_id=%s AND character_id=%s AND quantity>=%s RETURNING quantity",
        (amount, uid, cid, amount),
    )
    row = cur.fetchone()
    if row is None:
        raise FeatureError(
            "card_missing", "A coleção foi alterada. Confira a seleção novamente."
        )
    if row["quantity"] == 0:
        cur.execute(
            "DELETE FROM user_card_collection WHERE user_id=%s AND character_id=%s",
            (uid, cid),
        )


def add_copies(cur, uid: int, cid: int, amount: int):
    cur.execute(
        "INSERT INTO user_card_collection(user_id,character_id,quantity) VALUES(%s,%s,%s) ON CONFLICT(user_id,character_id) DO UPDATE SET quantity=user_card_collection.quantity+EXCLUDED.quantity,updated_at=NOW()",
        (uid, cid, amount),
    )


def move_coins(
    cur, uid: int, delta: int, kind: str, reference: str, metadata: dict | None = None
):
    cur.execute(
        "UPDATE users SET coins=COALESCE(coins,0)+%s,updated_at=NOW() WHERE user_id=%s AND COALESCE(coins,0)+%s>=0 RETURNING coins",
        (delta, uid, delta),
    )
    row = cur.fetchone()
    if not row:
        raise FeatureError(
            "no_coins", "Coins insuficientes. Nenhuma alteração foi aplicada."
        )
    _ledger(
        cur,
        uid,
        kind,
        delta,
        int(row["coins"]),
        None,
        {"reference": reference, **(metadata or {})},
    )
    return int(row["coins"])


def cosmetic(cur, uid: int, key: str, label: str, kind="badge"):
    cur.execute(
        "INSERT INTO source_cosmetics(user_id,cosmetic_id,label,kind) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING cosmetic_id",
        (uid, key, label, kind),
    )
    return bool(cur.fetchone())
