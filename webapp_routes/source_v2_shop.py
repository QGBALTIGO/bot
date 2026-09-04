from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from source_v2_shop import (
    buy_shop_character,
    exchange_currency,
    get_exchange_data,
    get_shop_characters,
    get_shop_hub,
)
from utils.source_v2_auth import resolve_source_v2_identity


router = APIRouter(prefix="/api/v1_7b82", tags=["source-v2-shop"])


def _user_id(init_data: str, webapp_uid: str, authorization: str) -> int:
    identity = resolve_source_v2_identity(
        x_telegram_init_data=init_data,
        x_webapp_uid=webapp_uid,
        authorization=authorization,
    )
    return int(identity["user_id"])


@router.get("/shop/hub")
def shop_hub(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    return get_shop_hub(_user_id(x_telegram_init_data, x_webapp_uid, authorization))


@router.get("/shop/exchange")
def shop_exchange(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    return get_exchange_data(_user_id(x_telegram_init_data, x_webapp_uid, authorization))


@router.post("/shop/exchange/{direction}")
def shop_exchange_action(
    direction: str,
    amount: int = Query(..., ge=1),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    user_id = _user_id(x_telegram_init_data, x_webapp_uid, authorization)
    try:
        return exchange_currency(user_id, direction, amount)
    except ValueError as exc:
        code = str(exc) or "exchange_failed"
        raise HTTPException(status_code=400, detail=code) from exc


@router.get("/shop/characters")
def shop_characters(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    return get_shop_characters(_user_id(x_telegram_init_data, x_webapp_uid, authorization))


@router.post("/shop/buy/character/{character_id}")
def shop_buy_character(
    character_id: int,
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    user_id = _user_id(x_telegram_init_data, x_webapp_uid, authorization)
    try:
        return buy_shop_character(user_id, character_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'") or "character_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "purchase_failed") from exc
