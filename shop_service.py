from __future__ import annotations

from typing import Any, Dict

from collection_service import get_collection_state
from game_repository import get_wallet
from shop_repository import (
    InsufficientCoinsError,
    InsufficientCopiesError,
    ResourceFullError,
    buy_product,
    sell_duplicate_character,
)
from shop_rules import SELL_DUPLICATE_PRICE, SHOP_PRODUCTS, get_product


class ShopServiceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


def get_shop_state(user_id: int) -> Dict[str, Any]:
    collection = get_collection_state(int(user_id))
    sellable = []
    for item in collection.get("items") or []:
        quantity = int(item.get("quantity") or 0)
        if quantity <= 1:
            continue
        sellable.append(
            {
                "id": int(item.get("id") or 0),
                "name": str(item.get("name") or "Personagem"),
                "anime": str(item.get("anime") or ""),
                "image": str(item.get("image") or ""),
                "quantity": quantity,
                "sellable_copies": quantity - 1,
                "coin_value": SELL_DUPLICATE_PRICE,
            }
        )

    return {
        "wallet": get_wallet(int(user_id)),
        "products": [
            {
                "code": p.code,
                "label": p.label,
                "description": p.description,
                "resource": p.resource,
                "amount": p.amount,
                "coin_price": p.coin_price,
            }
            for p in SHOP_PRODUCTS
        ],
        "sellable": sellable,
        "rules": {
            "last_copy_protected": True,
            "duplicate_sell_price": SELL_DUPLICATE_PRICE,
            "nickname_changes_are_not_sold": True,
        },
    }


def purchase(user_id: int, product_code: str) -> Dict[str, Any]:
    product = get_product(product_code)
    if not product:
        raise ShopServiceError("product_not_found", "Esse produto não existe na loja atual.")
    try:
        return buy_product(int(user_id), product)
    except InsufficientCoinsError as exc:
        raise ShopServiceError("insufficient_coins", "Você não tem coins suficientes.") from exc
    except ResourceFullError as exc:
        raise ShopServiceError("resource_full", "Esse recurso já está no limite permitido.") from exc


def sell_duplicate(user_id: int, character_id: Any) -> Dict[str, Any]:
    try:
        character_id = int(character_id or 0)
    except (TypeError, ValueError) as exc:
        raise ShopServiceError("invalid_character", "Personagem inválido.") from exc
    if character_id <= 0:
        raise ShopServiceError("invalid_character", "Personagem inválido.")
    try:
        return sell_duplicate_character(int(user_id), character_id)
    except InsufficientCopiesError as exc:
        raise ShopServiceError(
            "duplicate_required",
            "A loja protege sua última cópia. Você precisa ter pelo menos 2 para vender 1.",
        ) from exc
