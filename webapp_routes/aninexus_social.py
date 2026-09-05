from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse

from cards_service import get_character_by_id
from database_aninexus_social import (
    claim_referral_rewards,
    create_trade_offer,
    get_economy_summary,
    get_referral_stats,
    get_trade_collection,
    is_profile_private,
    list_referrals,
    list_trade_offers,
    respond_trade_offer,
)
from database_core import run as db_run
from utils.web_image_url import web_image_url
from webapp_routes.aninexus_compat import API_PREFIX, _require_user, _unauthorized


def _auth(authorization: str) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        return _require_user(authorization), None
    except PermissionError as exc:
        return None, _unauthorized(str(exc))


def _character_payload(character_id: int, quantity: int = 1) -> dict[str, Any]:
    meta = dict(get_character_by_id(int(character_id)) or {})
    return {
        "id": str(int(character_id)),
        "name": str(meta.get("name") or f"Personagem {int(character_id)}"),
        "anime": str(meta.get("anime") or ""),
        "rarity": str(meta.get("subcategory") or meta.get("rarity") or "Personagem"),
        "img_url": web_image_url(meta.get("image")),
        "count": max(1, int(quantity or 1)),
        "owned": True,
        "zenith_price": 0,
    }


def _name_for_user(user_id: int) -> str:
    from database import get_display_name_parts

    row = dict(get_display_name_parts(int(user_id)) or {})
    nickname = str(row.get("nickname") or "").strip()
    if nickname:
        return nickname
    full_name = str(row.get("full_name") or "").strip()
    if full_name:
        return full_name
    username = str(row.get("username") or "").strip().lstrip("@")
    if username:
        return f"@{username}"
    return f"Usuário {int(user_id)}"


def _trade_payload(row: dict[str, Any]) -> dict[str, Any]:
    sender_id = int(row.get("from_user") or 0)
    receiver_id = int(row.get("to_user") or 0)
    sender_char_id = int(row.get("from_character_id") or 0)
    receiver_char_id = int(row.get("to_character_id") or 0)
    return {
        "id": str(int(row.get("trade_id") or 0)),
        "sender_id": sender_id,
        "sender_name": _name_for_user(sender_id),
        "receiver_id": receiver_id,
        "receiver_name": _name_for_user(receiver_id),
        "sender_char": _character_payload(sender_char_id),
        "receiver_char": _character_payload(receiver_char_id),
        "status": str(row.get("status") or "pending"),
    }


def _battle_stats(user_id: int) -> dict[str, Any]:
    row = db_run(
        """
        SELECT total_duels, wins, losses, friendly_wins, friendly_losses,
               wager_wins, wager_losses, surrendered, timeouts, cards_won,
               cards_lost, coins_spent, coins_refunded
        FROM duel_stats
        WHERE user_id = %s
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one",
    ) or {}
    total = max(0, int(row.get("total_duels") or 0))
    wins = max(0, int(row.get("wins") or 0))
    losses = max(0, int(row.get("losses") or 0))
    return {
        "total_battles": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) * 100, 2) if total else 0.0,
        "friendly_wins": max(0, int(row.get("friendly_wins") or 0)),
        "friendly_losses": max(0, int(row.get("friendly_losses") or 0)),
        "wager_wins": max(0, int(row.get("wager_wins") or 0)),
        "wager_losses": max(0, int(row.get("wager_losses") or 0)),
        "surrendered": max(0, int(row.get("surrendered") or 0)),
        "timeouts": max(0, int(row.get("timeouts") or 0)),
        "cards_won": max(0, int(row.get("cards_won") or 0)),
        "cards_lost": max(0, int(row.get("cards_lost") or 0)),
        "coins_spent": max(0, int(row.get("coins_spent") or 0)),
        "coins_refunded": max(0, int(row.get("coins_refunded") or 0)),
    }


def build_aninexus_social_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-social"])

    @router.get("/battle/stats")
    def battle_stats(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        return JSONResponse(_battle_stats(int(user.get("id") or 0)))

    @router.get("/social/referrals")
    def referrals(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        return JSONResponse(list_referrals(int(user.get("id") or 0)))

    @router.get("/social/referrals/stats")
    def referral_stats(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        return JSONResponse(get_referral_stats(int(user.get("id") or 0)))

    @router.post("/social/referrals/claim")
    def referral_claim(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        return JSONResponse(claim_referral_rewards(int(user.get("id") or 0)))

    @router.get("/trade/user/{target_user_id}/collection")
    def trade_user_collection(
        target_user_id: int,
        limit: int = Query(default=50, ge=1, le=100),
        authorization: str = Header(default=""),
    ):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        requester_id = int(user.get("id") or 0)
        target_user_id = int(target_user_id)
        if target_user_id != requester_id and is_profile_private(target_user_id):
            return JSONResponse(
                {"error": {"code": "private_profile", "message": "Este perfil é privado."}},
                status_code=403,
            )
        rows = get_trade_collection(target_user_id)
        items = [
            _character_payload(int(row.get("character_id") or 0), int(row.get("quantity") or 1))
            for row in rows[:limit]
            if int(row.get("character_id") or 0) > 0
        ]
        return JSONResponse({"total": len(rows), "page": 1, "items": items})

    @router.get("/trade/offers")
    def trade_offers(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        rows = list_trade_offers(int(user.get("id") or 0))
        return JSONResponse([_trade_payload(row) for row in rows])

    @router.post("/trade/offer")
    def trade_offer(
        payload: dict = Body(default={}),
        authorization: str = Header(default=""),
    ):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        try:
            receiver_id = int((payload or {}).get("receiver_id") or 0)
            sender_char_id = int((payload or {}).get("sender_char_id") or 0)
            receiver_char_id = int((payload or {}).get("receiver_char_id") or 0)
        except (TypeError, ValueError):
            receiver_id = sender_char_id = receiver_char_id = 0
        result = create_trade_offer(
            int(user.get("id") or 0), receiver_id, sender_char_id, receiver_char_id
        )
        if result.get("ok"):
            return JSONResponse(result)
        messages = {
            "invalid_user": "Usuário inválido.",
            "invalid_character": "Personagem inválido.",
            "same_character": "Escolha personagens diferentes.",
            "private_profile": "Este perfil é privado.",
            "receiver_not_found": "Usuário não encontrado.",
            "sender_card_missing": "Você não possui mais esse personagem.",
            "receiver_card_missing": "O outro usuário não possui mais esse personagem.",
            "sender_card_reserved": "Esse personagem já está reservado em outra troca.",
            "receiver_card_reserved": "O personagem escolhido já está reservado em outra troca.",
        }
        code = str(result.get("error") or "trade_failed")
        return JSONResponse(
            {"error": {"code": code, "message": messages.get(code, "Não foi possível criar a troca.")}},
            status_code=409,
        )

    @router.post("/trade/respond/{trade_id}")
    def trade_respond(
        trade_id: int,
        payload: dict = Body(default={}),
        authorization: str = Header(default=""),
    ):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        action = str((payload or {}).get("action") or "").strip().lower()
        result = respond_trade_offer(int(user.get("id") or 0), int(trade_id), action)
        if result.get("ok"):
            return JSONResponse(result)
        messages = {
            "invalid_action": "Ação inválida.",
            "trade_not_found": "Troca não encontrada.",
            "forbidden": "Apenas quem recebeu a oferta pode responder.",
            "trade_not_pending": "Esta troca já foi encerrada.",
            "trade_expired": "Esta oferta expirou.",
            "card_missing": "Um dos personagens não está mais disponível.",
        }
        code = str(result.get("error") or "trade_failed")
        return JSONResponse(
            {"error": {"code": code, "message": messages.get(code, "Não foi possível concluir a troca.")}},
            status_code=409,
        )

    @router.get("/economy")
    def economy(
        limit: int = Query(default=50, ge=1, le=100),
        authorization: str = Header(default=""),
    ):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        return JSONResponse(get_economy_summary(int(user.get("id") or 0), limit=limit))

    return router
