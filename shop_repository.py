from __future__ import annotations

import json
import secrets
from typing import Any, Dict

from psycopg.rows import dict_row

from database import pool
from game_rules import DICE_MAX_BALANCE
from shop_rules import SELL_DUPLICATE_PRICE, ShopProduct
from wallet_tx import insert_ledger, lock_wallet, wallet_payload


class ShopRepositoryError(RuntimeError):
    pass


class InsufficientCoinsError(ShopRepositoryError):
    pass


class InsufficientCopiesError(ShopRepositoryError):
    pass


class ResourceFullError(ShopRepositoryError):
    pass


def create_shop_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shop_transactions_v2 (
                        id BIGSERIAL PRIMARY KEY,
                        transaction_token TEXT NOT NULL UNIQUE,
                        user_id BIGINT NOT NULL,
                        action TEXT NOT NULL,
                        product_code TEXT,
                        character_id BIGINT,
                        quantity INTEGER NOT NULL DEFAULT 1,
                        coins_delta BIGINT NOT NULL DEFAULT 0,
                        resource TEXT,
                        resource_delta INTEGER NOT NULL DEFAULT 0,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_shop_transactions_v2_user_created
                    ON shop_transactions_v2 (user_id, created_at DESC)
                    """
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def buy_product(user_id: int, product: ShopProduct) -> Dict[str, Any]:
    user_id = int(user_id)
    token = secrets.token_urlsafe(18)

    if product.resource not in {"dice", "spins"}:
        raise ShopRepositoryError("unsupported_product_resource")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = lock_wallet(cur, user_id)
                if int(wallet.get("coins") or 0) < int(product.coin_price):
                    raise InsufficientCoinsError("insufficient_coins")
                if product.resource == "dice" and int(wallet.get("dice") or 0) >= DICE_MAX_BALANCE:
                    raise ResourceFullError("dice_full")

                if product.resource == "dice":
                    cur.execute(
                        """
                        UPDATE game_wallets
                        SET coins = coins - %s,
                            dice = LEAST(%s, dice + %s),
                            updated_at = NOW()
                        WHERE user_id = %s AND coins >= %s
                        RETURNING user_id, coins, dice, spins, dice_slot
                        """,
                        (product.coin_price, DICE_MAX_BALANCE, product.amount, user_id, product.coin_price),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE game_wallets
                        SET coins = coins - %s,
                            spins = spins + %s,
                            updated_at = NOW()
                        WHERE user_id = %s AND coins >= %s
                        RETURNING user_id, coins, dice, spins, dice_slot
                        """,
                        (product.coin_price, product.amount, user_id, product.coin_price),
                    )
                updated = dict(cur.fetchone() or {})
                if not updated:
                    raise InsufficientCoinsError("insufficient_coins")

                credited = max(0, int(updated.get(product.resource) or 0) - int(wallet.get(product.resource) or 0))
                if credited <= 0:
                    raise ResourceFullError("resource_full")

                insert_ledger(
                    cur,
                    user_id=user_id,
                    resource="coins",
                    delta=-product.coin_price,
                    reason="shop_purchase",
                    reference=token,
                    metadata={"product_code": product.code},
                )
                insert_ledger(
                    cur,
                    user_id=user_id,
                    resource=product.resource,
                    delta=credited,
                    reason="shop_purchase_reward",
                    reference=token,
                    metadata={"product_code": product.code},
                )
                cur.execute(
                    """
                    INSERT INTO shop_transactions_v2
                    (transaction_token, user_id, action, product_code, quantity, coins_delta, resource, resource_delta)
                    VALUES (%s, %s, 'buy', %s, 1, %s, %s, %s)
                    """,
                    (token, user_id, product.code, -product.coin_price, product.resource, credited),
                )
                conn.commit()
                return {
                    "transaction_token": token,
                    "product_code": product.code,
                    "credited": credited,
                    "wallet": wallet_payload(updated),
                }
            except (InsufficientCoinsError, ResourceFullError):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def sell_duplicate_character(user_id: int, character_id: int) -> Dict[str, Any]:
    """Sell one duplicate copy while always preserving the user's last copy."""
    user_id = int(user_id)
    character_id = int(character_id)
    token = secrets.token_urlsafe(18)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = lock_wallet(cur, user_id)
                cur.execute(
                    """
                    SELECT quantity
                    FROM user_card_collection
                    WHERE user_id = %s AND character_id = %s
                    FOR UPDATE
                    """,
                    (user_id, character_id),
                )
                quantity = int((cur.fetchone() or {}).get("quantity") or 0)
                if quantity <= 1:
                    raise InsufficientCopiesError("duplicate_required")

                cur.execute(
                    """
                    UPDATE user_card_collection
                    SET quantity = quantity - 1, updated_at = NOW()
                    WHERE user_id = %s AND character_id = %s AND quantity > 1
                    RETURNING quantity
                    """,
                    (user_id, character_id),
                )
                collection = cur.fetchone()
                if not collection:
                    raise InsufficientCopiesError("duplicate_required")

                cur.execute(
                    """
                    UPDATE game_wallets
                    SET coins = coins + %s, updated_at = NOW()
                    WHERE user_id = %s
                    RETURNING user_id, coins, dice, spins, dice_slot
                    """,
                    (SELL_DUPLICATE_PRICE, user_id),
                )
                wallet = dict(cur.fetchone() or wallet)

                insert_ledger(
                    cur,
                    user_id=user_id,
                    resource="coins",
                    delta=SELL_DUPLICATE_PRICE,
                    reason="shop_sell_duplicate",
                    reference=token,
                    metadata={"character_id": character_id},
                )
                cur.execute(
                    """
                    INSERT INTO shop_transactions_v2
                    (transaction_token, user_id, action, character_id, quantity, coins_delta, metadata)
                    VALUES (%s, %s, 'sell_duplicate', %s, 1, %s, %s::jsonb)
                    """,
                    (
                        token,
                        user_id,
                        character_id,
                        SELL_DUPLICATE_PRICE,
                        json.dumps({"remaining_quantity": int(collection.get("quantity") or 1)}),
                    ),
                )
                conn.commit()
                return {
                    "transaction_token": token,
                    "character_id": character_id,
                    "remaining_quantity": int(collection.get("quantity") or 1),
                    "coins_earned": SELL_DUPLICATE_PRICE,
                    "wallet": wallet_payload(wallet),
                }
            except InsufficientCopiesError:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise
