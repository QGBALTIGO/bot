from __future__ import annotations

from dataclasses import dataclass


SELL_DUPLICATE_PRICE = 1


@dataclass(frozen=True)
class ShopProduct:
    code: str
    label: str
    description: str
    resource: str
    amount: int
    coin_price: int


SHOP_PRODUCTS: tuple[ShopProduct, ...] = (
    ShopProduct(
        code="dice_1",
        label="+1 dado",
        description="Adiciona um dado, respeitando o limite máximo da carteira.",
        resource="dice",
        amount=1,
        coin_price=4,
    ),
    ShopProduct(
        code="spin_1",
        label="+1 giro",
        description="Adiciona um giro para a roleta do Game Center.",
        resource="spins",
        amount=1,
        coin_price=6,
    ),
)


def get_product(code: str) -> ShopProduct | None:
    code = str(code or "").strip().lower()
    for product in SHOP_PRODUCTS:
        if product.code == code:
            return product
    return None
