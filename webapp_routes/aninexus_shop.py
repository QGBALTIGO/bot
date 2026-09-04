from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row

from database import (
    buy_daily_xcard_shop_offer,
    get_daily_xcard_shop_refresh_info,
    get_dado_state,
    get_or_create_daily_xcard_shop_offers,
    get_progress_row,
    get_user_daily_xcard_shop_purchase_map,
    get_user_status,
)
from database_core import pool
from utils.web_image_url import web_image_url
from webapp_routes.aninexus_compat import API_PREFIX, _require_user, _unauthorized
from xcards_service import get_xcard_by_id

DADO_PRICE = 2
DADO_MAX = 24


def _auth(authorization: str) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        return _require_user(authorization), None
    except PermissionError as exc:
        return None, _unauthorized(str(exc))


def _error(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status_code)


def _buy_dado_atomic(user_id: int) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT coins, dado_balance
                    FROM users
                    WHERE user_id=%s
                    FOR UPDATE
                    """,
                    (int(user_id),),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return {"ok": False, "error": "user_not_found"}

                coins = int(row.get("coins") or 0)
                dado = int(row.get("dado_balance") or 0)
                if dado >= DADO_MAX:
                    conn.rollback()
                    return {"ok": False, "error": "dado_full", "coins": coins, "dado_balance": dado}
                if coins < DADO_PRICE:
                    conn.rollback()
                    return {"ok": False, "error": "no_coins", "coins": coins, "dado_balance": dado}

                new_coins = coins - DADO_PRICE
                new_dado = min(DADO_MAX, dado + 1)
                cur.execute(
                    """
                    UPDATE users
                    SET coins=%s, dado_balance=%s, updated_at=NOW()
                    WHERE user_id=%s
                    """,
                    (new_coins, new_dado, int(user_id)),
                )
                cur.execute(
                    """
                    INSERT INTO shop_transactions
                    (user_id, type, amount, balance_after, metadata, created_at)
                    VALUES (%s, 'aninexus_buy_dado', %s, %s, %s::jsonb, NOW())
                    """,
                    (
                        int(user_id),
                        -DADO_PRICE,
                        new_coins,
                        json.dumps({"dado_added": 1}, ensure_ascii=False),
                    ),
                )
                conn.commit()
                return {"ok": True, "coins": new_coins, "dado_balance": new_dado}
            except Exception:
                conn.rollback()
                raise


def _offer_payload(offer: dict[str, Any], bought: bool) -> dict[str, Any]:
    card = get_xcard_by_id(int(offer.get("card_id") or 0)) or {}
    return {
        "slot_code": str(offer.get("slot_code") or ""),
        "group": str(offer.get("slot_group") or "normal"),
        "display_order": int(offer.get("display_order") or 0),
        "card_id": int(offer.get("card_id") or 0),
        "character_id": int(offer.get("character_id") or 0),
        "name": str(card.get("name") or "XCard"),
        "title": str(card.get("title") or "Source"),
        "card_no": str(card.get("card_no") or ""),
        "rarity": str(card.get("rarity") or "").upper(),
        "bp": str(card.get("bp") or ""),
        "image": web_image_url(card.get("image")),
        "price": int(offer.get("price") or 0),
        "level_required": int(offer.get("level_required") or 1),
        "bought": bool(bought),
    }


def build_aninexus_shop_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-shop"])

    def state(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)

        status = get_user_status(user_id) or {}
        dado_state = get_dado_state(user_id) or {}
        progress = get_progress_row(user_id) or {}
        offers = get_or_create_daily_xcard_shop_offers()
        bought = get_user_daily_xcard_shop_purchase_map(user_id)
        refresh = get_daily_xcard_shop_refresh_info()

        return JSONResponse(
            {
                "coins": int(status.get("coins") or 0),
                "dado_balance": int(dado_state.get("balance") or 0),
                "dado_max": int(dado_state.get("max_balance") or DADO_MAX),
                "dado_price": DADO_PRICE,
                "level": int(progress.get("level") or 1),
                "next_refresh_iso": refresh.get("next_refresh_iso"),
                "countdown_label": str(refresh.get("countdown_label") or ""),
                "offers": [
                    _offer_payload(item, str(item.get("slot_code") or "") in bought)
                    for item in offers
                ],
            }
        )

    def buy_dado(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        result = _buy_dado_atomic(int(session_user.get("id") or 0))
        if result.get("ok"):
            return JSONResponse(result)
        code = str(result.get("error") or "purchase_failed")
        messages = {
            "dado_full": "Seu saldo de Dados já está cheio.",
            "no_coins": f"Você precisa de {DADO_PRICE} Coins para comprar 1 Dado.",
            "user_not_found": "Usuário não encontrado.",
        }
        return _error(code, messages.get(code, "Não foi possível concluir a compra."), 409)

    def buy_xcard(slot_code: str, authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        result = buy_daily_xcard_shop_offer(
            int(session_user.get("id") or 0),
            str(slot_code or "").strip().lower(),
        )
        if result.get("ok"):
            return JSONResponse(result)
        code = str(result.get("error") or "purchase_failed")
        messages = {
            "invalid_slot": "Oferta inválida.",
            "offer_not_found": "Essa oferta não está mais disponível.",
            "already_bought": "Você já comprou essa oferta hoje.",
            "level_locked": f"Seu nível ainda não libera esta oferta. Nível necessário: {int(result.get('required_level') or 1)}.",
            "no_coins": f"Coins insuficientes. Preço: {int(result.get('price') or 0)}.",
        }
        return _error(code, messages.get(code, "Não foi possível concluir a compra."), 409)

    router.add_api_route("/source-shop", state, methods=["GET"])
    router.add_api_route("/source-shop/buy-dado", buy_dado, methods=["POST"])
    router.add_api_route("/source-shop/buy-xcard/{slot_code}", buy_xcard, methods=["POST"])
    return router
