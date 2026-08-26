from __future__ import annotations

import json
import secrets
from typing import Any, Dict

from psycopg.rows import dict_row

from database import pool
from game_rules import DICE_INITIAL_BALANCE, DICE_MAX_BALANCE, dice_slot_number, recharged_dice_balance
from shop_rules import SELL_DUPLICATE_PRICE, ShopProduct


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


def _lock_wallet(cur, user_id: int) -> Dict[str, Any]:
    current_slot = dice_slot_number()
    cur.execute(
        """
        INSERT INTO game_wallets (user_id, coins, dice, spins, dice_slot)
        VALUES (%s, 0, %s, 0, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id), DICE_INITIAL_BALANCE, current_slot),
    )
    cur.execute(
        """
        SELECT user_id, coins, dice, spins, dice_slot
        FROM game_wallets
        WHERE user_id = %s
        FOR UPDATE
        """,
        (int(user_id),),
    )
    row = dict(cur.fetchone() or {})
    if not row:
        raise ShopRepositoryError("wallet_missing")

    new_dice, new_slot = recharged_dice_balance(
        int(row.get("dice") or 0),
        int(row.get("dice_slot")) if row.get("dice_slot") is not None else None,
        current_slot,
    )
    if new_dice != int(row.get("dice") or 0) or new_slot != int(row.get("dice_slot") or 0):
        cur.execute(
            """
            UPDATE game_wallets
            SET dice = %s, dice_slot = %s, updated_at = NOW()
            WHERE user_id = %s
            RETURNING user_id, coins, dice, spins, dice_slot
            """,
            (new_dice, new_slot, int(user_id)),
        )
        row = dict(cur.fetchone() or row)
    return row


def _wallet_payload(row: Dict[str, Any]) -> Dict[str, int]:
    return {
        "coins": int(row.get("coins") or 0),
        "dice": int(row.get("dice") or 0),
        "spins": int(row.get("spins") or 0),
        "dice_max": DICE_MAX_BALANCE,
    }


def buy_product(user_id: int, product: ShopProduct) -> Dict[str, Any]:
    user_id = int(user_id)
    token = secrets.token_urlsafe(18)

    if product.resource not in {"dice", "spins"}:
        raise ShopRepositoryError("unsupported_product_resource")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = _lock_wallet(cur, user_id)
                current_coins = int(wallet.get("coins") or 0)
                if current_coins < int(product.coin_price):
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
                        WHERE user_id = %s
                          AND coins >= %s
                        RETURNING user_id, coins, dice, spins, dice_slot
                        """,
                        (
                            int(product.coin_price),
                            DICE_MAX_BALANCE,
                            int(product.amount),
                            user_id,
                            int(product.coin_price),
                        ),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE game_wallets
                        SET coins = coins - %s,
                            spins = spins + %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                          AND coins >= %s
                        RETURNING user_id, coins, dice, spins, dice_slot
                        """,
                        (
                            int(product.coin_price),
                            int(product.amount),
                            user_id,
                            int(product.coin_price),
                        ),
                    )
                updated = dict(cur.fetchone() or {})
                if not updated:
                    raise InsufficientCoinsError("insufficient_coins")

                before_resource = int(wallet.get(product.resource) or 0)
                after_resource = int(updated.get(product.resource) or 0)
                credited = max(0, after_resource - before_resource)
                if credited <= 0:
                    raise ResourceFullError("resource_full")

                cur.execute(
                    """
                    INSERT INTO game_ledger
                    (user_id, resource, delta, reason, reference, metadata)
                    VALUES (%s, 'coins', %s, 'shop_purchase', %s, %s::jsonb)
                    """,
                    (
                        user_id,
                        -int(product.coin_price),
                        token,
                        json.dumps({"product_code": product.code}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO game_ledger
                    (user_id, resource, delta, reason, reference, metadata)
                    VALUES (%s, %s, %s, 'shop_purchase_reward', %s, %s::jsonb)
                    """,
                    (
                        user_id,
                        product.resource,
                        credited,
                        token,
                        json.dumps({"product_code": product.code}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO shop_transactions_v2
                    (transaction_token, user_id, action, product_code, quantity, coins_delta, resource, resource_delta)
                    VALUES (%s, %s, 'buy', %s, 1, %s, %s, %s)
                    """,
                    (
                        token,
                        user_id,
                        product.code,
                        -int(product.coin_price),
                        product.resource,
                        credited,
                    ),
                )
                conn.commit()
                return {
                    "transaction_token": token,
                    "product_code": product.code,
                    "credited": credited,
                    "wallet": _wallet_payload(updated),
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
                wallet = _lock_wallet(cur, user_id)
                cur.execute(
                    """
                    SELECT quantity
                    FROM user_card_collection
                    WHERE user_id = %s AND character_id = %s
                    FOR UPDATE
                    """,
                    (user_id, character_id),
                )
                ownership = cur.fetchone()
                quantity = int((ownership or {}).get("quantity") or 0)
                if quantity <= 1:
                    raise InsufficientCopiesError("duplicate_required")

                cur.execute(
                    """
                    UPDATE user_card_collection
                    SET quantity = quantity - 1,
                        updated_at = NOW()
                    WHERE user_id = %s
                      AND character_id = %s
                      AND quantity > 1
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
                    SET coins = coins + %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    RETURNING user_id, coins, dice, spins, dice_slot
                    """,
                    (SELL_DUPLICATE_PRICE, user_id),
                )
                wallet = dict(cur.fetchone() or wallet)

                cur.execute(
                    """
                    INSERT INTO game_ledger
                    (user_id, resource, delta, reason, reference, metadata)
                    VALUES (%s, 'coins', %s, 'shop_sell_duplicate', %s, %s::jsonb)
                    """,
                    (
                        user_id,
                        SELL_DUPLICATE_PRICE,
                        token,
                        json.dumps({"character_id": character_id}),
                    ),
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
                    "wallet": _wallet_payload(wallet),
                }
            except InsufficientCopiesError:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise
