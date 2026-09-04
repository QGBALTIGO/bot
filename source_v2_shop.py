from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row

from source_v2_rewards import grant_character_locked


COINS_PER_PRISM = 10_000
SHOP_SIZE = 18
DEFAULT_PRICE_PRISMS = 5
DEFAULT_STOCK_LIMIT = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _rotation_timing(now: datetime | None = None) -> dict[str, Any]:
    current = (now or _utcnow()).astimezone(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    reset = start + timedelta(days=1)
    return {
        "rotation_date": start.date(),
        "rotation_date_text": start.date().isoformat(),
        "reset_at": reset.isoformat().replace("+00:00", "Z"),
    }


def _catalog_pool() -> list[dict[str, Any]]:
    from cards_service import build_cards_final_data

    chars = build_cards_final_data().get("characters_by_id") or {}
    out: list[dict[str, Any]] = []
    for raw_id, meta in chars.items():
        try:
            character_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if character_id <= 0:
            continue
        image = str((meta or {}).get("image") or "").strip()
        if not image:
            continue
        out.append(
            {
                "id": character_id,
                "name": str((meta or {}).get("name") or f"Personagem {character_id}"),
                "anime": str((meta or {}).get("anime") or "Obra desconhecida"),
                "img_url": image,
            }
        )
    out.sort(key=lambda item: int(item["id"]))
    return out


def daily_rotation_ids(now: datetime | None = None, *, pool: list[dict[str, Any]] | None = None) -> list[int]:
    timing = _rotation_timing(now)
    items = list(pool if pool is not None else _catalog_pool())
    if not items:
        return []
    seed = int.from_bytes(
        hashlib.sha256(f"source-v2-shop:{timing['rotation_date_text']}".encode("utf-8")).digest()[:8],
        "big",
    )
    rng = random.Random(seed)
    count = min(SHOP_SIZE, len(items))
    return [int(item["id"]) for item in rng.sample(items, count)]


def _ensure_wallet_locked(cur, user_id: int) -> int:
    user_id = int(user_id)
    cur.execute(
        "INSERT INTO source_v2_wallet (user_id, prisms) VALUES (%s, 0) ON CONFLICT (user_id) DO NOTHING",
        (user_id,),
    )
    cur.execute("SELECT prisms FROM source_v2_wallet WHERE user_id = %s FOR UPDATE", (user_id,))
    row = cur.fetchone()
    return int((row.get("prisms") if isinstance(row, dict) else row[0]) if row else 0)


def prism_balance(user_id: int) -> int:
    from database_core import run

    row = run(
        "SELECT prisms FROM source_v2_wallet WHERE user_id = %s",
        (int(user_id),),
        fetch="one",
    ) or {}
    return max(0, int(row.get("prisms") or 0))


def get_exchange_data(user_id: int) -> dict[str, int]:
    from database_core import run

    row = run(
        "SELECT COALESCE(coins, 0) AS coins FROM users WHERE user_id = %s",
        (int(user_id),),
        fetch="one",
    ) or {}
    return {
        "balance": max(0, int(row.get("coins") or 0)),
        "zenith": prism_balance(user_id),
        "rate": COINS_PER_PRISM,
        "minimum_shards": COINS_PER_PRISM,
        "minimum_zenith": 1,
    }


def exchange_currency(user_id: int, direction: str, amount: int) -> dict[str, Any]:
    from database_core import pool

    user_id = int(user_id)
    amount = int(amount or 0)
    direction = str(direction or "").strip().lower()
    if amount <= 0:
        raise ValueError("invalid_amount")
    if direction not in {"shards_to_zenith", "zenith_to_shards"}:
        raise ValueError("invalid_exchange_direction")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                    (user_id,),
                )
                cur.execute("SELECT COALESCE(coins, 0) AS coins FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                user = cur.fetchone() or {}
                coins = int(user.get("coins") or 0)
                prisms = _ensure_wallet_locked(cur, user_id)

                if direction == "shards_to_zenith":
                    if amount < COINS_PER_PRISM or amount % COINS_PER_PRISM != 0:
                        raise ValueError("coins_must_match_exchange_rate")
                    if coins < amount:
                        raise ValueError("insufficient_coins")
                    prism_delta = amount // COINS_PER_PRISM
                    new_coins = coins - amount
                    new_prisms = prisms + prism_delta
                    message = f"Converted {amount:,} Coins to {prism_delta:,} Prisms"
                else:
                    if prisms < amount:
                        raise ValueError("insufficient_prisms")
                    coin_delta = amount * COINS_PER_PRISM
                    new_coins = coins + coin_delta
                    new_prisms = prisms - amount
                    message = f"Converted {amount:,} Prisms to {coin_delta:,} Coins"

                cur.execute(
                    "UPDATE users SET coins = %s, updated_at = NOW() WHERE user_id = %s",
                    (new_coins, user_id),
                )
                cur.execute(
                    "UPDATE source_v2_wallet SET prisms = %s, updated_at = NOW() WHERE user_id = %s",
                    (new_prisms, user_id),
                )
                conn.commit()
                return {
                    "status": "success",
                    "message": message,
                    "balance": new_coins,
                    "zenith": new_prisms,
                    "rate": COINS_PER_PRISM,
                }
            except ValueError:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def _rarity_meta_for_ids(cur, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    cur.execute(
        """
        SELECT
            cgm.character_id,
            cgm.rarity_slug,
            gr.name AS rarity_name,
            gr.shop_price,
            gr.stock_limit
        FROM character_gacha_meta cgm
        JOIN gacha_rarities gr ON gr.slug = cgm.rarity_slug
        WHERE cgm.character_id = ANY(%s)
        """,
        (ids,),
    )
    return {int(row["character_id"]): dict(row) for row in (cur.fetchall() or [])}


def _ensure_daily_stock(cur, rotation_date, ids: list[int]) -> dict[int, dict[str, Any]]:
    rarity_meta = _rarity_meta_for_ids(cur, ids)
    for character_id in ids:
        meta = rarity_meta.get(character_id) or {}
        price = max(1, int(meta.get("shop_price") or DEFAULT_PRICE_PRISMS))
        stock_limit = max(1, int(meta.get("stock_limit") or DEFAULT_STOCK_LIMIT))
        cur.execute(
            """
            INSERT INTO source_v2_shop_stock
                (rotation_date, character_id, price_prisms, stock_limit, sold_count)
            VALUES (%s, %s, %s, %s, 0)
            ON CONFLICT (rotation_date, character_id) DO NOTHING
            """,
            (rotation_date, character_id, price, stock_limit),
        )

    cur.execute(
        """
        SELECT rotation_date, character_id, price_prisms, stock_limit, sold_count
        FROM source_v2_shop_stock
        WHERE rotation_date = %s AND character_id = ANY(%s)
        """,
        (rotation_date, ids),
    )
    rows = {int(row["character_id"]): dict(row) for row in (cur.fetchall() or [])}
    for character_id, meta in rarity_meta.items():
        if character_id in rows:
            rows[character_id]["rarity_name"] = meta.get("rarity_name")
    return rows


def get_shop_characters(user_id: int, now: datetime | None = None) -> list[dict[str, Any]]:
    from database_core import pool

    pool_chars = _catalog_pool()
    chars_by_id = {int(item["id"]): item for item in pool_chars}
    ids = daily_rotation_ids(now, pool=pool_chars)
    if not ids:
        return []
    timing = _rotation_timing(now)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                stock = _ensure_daily_stock(cur, timing["rotation_date"], ids)
                cur.execute(
                    "SELECT character_id FROM user_card_collection WHERE user_id = %s AND quantity > 0 AND character_id = ANY(%s)",
                    (int(user_id), ids),
                )
                owned = {int(row["character_id"]) for row in (cur.fetchall() or [])}
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    result: list[dict[str, Any]] = []
    for character_id in ids:
        char = chars_by_id.get(character_id)
        row = stock.get(character_id)
        if not char or not row:
            continue
        sold_count = max(0, int(row.get("sold_count") or 0))
        stock_limit = max(1, int(row.get("stock_limit") or DEFAULT_STOCK_LIMIT))
        price = max(1, int(row.get("price_prisms") or DEFAULT_PRICE_PRISMS))
        remaining = max(0, stock_limit - sold_count)
        result.append(
            {
                "id": str(character_id),
                "name": char["name"],
                "anime": char["anime"],
                "img_url": char["img_url"],
                "rarity": str(row.get("rarity_name") or "Standard"),
                "owned": character_id in owned,
                "base_zenith_price": price,
                "zenith_price": price,
                "staff_discount": 0,
                "stock_limit": stock_limit,
                "sold_count": sold_count,
                "stock_remaining": remaining,
                "sold_out": remaining <= 0,
            }
        )
    return result


def get_shop_hub(user_id: int, now: datetime | None = None) -> dict[str, Any]:
    exchange = get_exchange_data(user_id)
    timing = _rotation_timing(now)
    return {
        "balance": exchange["balance"],
        "zenith": exchange["zenith"],
        "pass_type": "free",
        "characters_rarity": "Various",
        "rotation_date": timing["rotation_date_text"],
        "reset_at": timing["reset_at"],
        "exchange_rate": COINS_PER_PRISM,
    }


def buy_shop_character(user_id: int, character_id: int, now: datetime | None = None) -> dict[str, Any]:
    from database_core import pool

    user_id = int(user_id)
    character_id = int(character_id)
    pool_chars = _catalog_pool()
    chars_by_id = {int(item["id"]): item for item in pool_chars}
    rotation_ids = daily_rotation_ids(now, pool=pool_chars)
    if character_id not in rotation_ids:
        raise KeyError("character_rotated_out")
    char = chars_by_id.get(character_id)
    if not char:
        raise KeyError("character_not_found")
    timing = _rotation_timing(now)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                _ensure_daily_stock(cur, timing["rotation_date"], rotation_ids)
                cur.execute(
                    """
                    SELECT price_prisms, stock_limit, sold_count
                    FROM source_v2_shop_stock
                    WHERE rotation_date = %s AND character_id = %s
                    FOR UPDATE
                    """,
                    (timing["rotation_date"], character_id),
                )
                stock = cur.fetchone()
                if not stock:
                    raise KeyError("character_rotated_out")
                if int(stock.get("sold_count") or 0) >= int(stock.get("stock_limit") or 0):
                    raise ValueError("character_sold_out")

                cur.execute(
                    "SELECT quantity FROM user_card_collection WHERE user_id = %s AND character_id = %s FOR UPDATE",
                    (user_id, character_id),
                )
                owned = cur.fetchone()
                if owned and int(owned.get("quantity") or 0) > 0:
                    raise ValueError("character_already_owned")

                prisms = _ensure_wallet_locked(cur, user_id)
                price = max(1, int(stock.get("price_prisms") or DEFAULT_PRICE_PRISMS))
                if prisms < price:
                    raise ValueError("insufficient_prisms")

                cur.execute(
                    "UPDATE source_v2_wallet SET prisms = prisms - %s, updated_at = NOW() WHERE user_id = %s",
                    (price, user_id),
                )
                cur.execute(
                    """
                    UPDATE source_v2_shop_stock
                    SET sold_count = sold_count + 1, updated_at = NOW()
                    WHERE rotation_date = %s AND character_id = %s AND sold_count < stock_limit
                    RETURNING sold_count
                    """,
                    (timing["rotation_date"], character_id),
                )
                if not cur.fetchone():
                    raise ValueError("character_sold_out")

                quantity_after = grant_character_locked(cur, user_id, character_id)
                conn.commit()
                return {
                    "status": "success",
                    "char_name": char["name"],
                    "character_id": str(character_id),
                    "price": price,
                    "base_price": price,
                    "staff_discount": 0,
                    "quantity_after": quantity_after,
                }
            except (ValueError, KeyError):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise
