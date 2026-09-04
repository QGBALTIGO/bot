from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from database_aninexus_pets import (
    buy_pet,
    care_for_active_pet,
    fuse_eggs,
    get_pet_catalog_for_user,
    hatch_egg,
    incubate_egg,
    purify_egg,
    sell_egg,
    set_active_pet,
)
from webapp_routes.aninexus_compat import API_PREFIX, _require_user, _unauthorized


def _auth(authorization: str) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        return _require_user(authorization), None
    except PermissionError as exc:
        return None, _unauthorized(str(exc))


def _failed(result: dict[str, Any]) -> JSONResponse:
    code = str(result.get("error") or "action_failed")
    messages = {
        "pet_not_found": "Companheiro não encontrado.",
        "already_owned": "Você já possui esse companheiro.",
        "level_required": f"É necessário chegar ao nível {int(result.get('required_level') or 1)}.",
        "insufficient_coins": "Coins insuficientes.",
        "pet_not_owned": "Você não possui esse companheiro.",
        "no_active_pet": "Nenhum companheiro ativo.",
        "cooldown": "Essa ação ainda está em recarga.",
        "egg_not_found": "Ovo não encontrado.",
        "invalid_status": "Esse ovo não pode ser incubado agora.",
        "no_slot": "Seu slot de incubação já está ocupado.",
        "not_incubating": "Esse ovo ainda não está incubando.",
        "not_ready": f"Esse ovo ainda precisa de {int(result.get('remaining_mins') or 1)} minuto(s).",
        "catalog_empty": "Não há personagens disponíveis para essa recompensa.",
        "egg_unavailable": "Esse ovo não pode ser vendido agora.",
        "egg_not_corrupted": "Esse ovo não precisa ser purificado.",
        "invalid_tier": "Esse tipo de ovo não pode ser fundido.",
        "not_enough_eggs": "Você precisa de 3 ovos frescos do mesmo tipo.",
    }
    return JSONResponse(
        {"error": {"code": code, "message": messages.get(code, "Não foi possível concluir a ação.")}},
        status_code=409,
    )


def build_aninexus_pets_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-pets"])

    @router.get("/shop/pets")
    def pet_shop(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        return JSONResponse(get_pet_catalog_for_user(int(user.get("id") or 0)))

    @router.post("/shop/buy/pet/{pet_ref}")
    def pet_buy(pet_ref: str, authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = buy_pet(int(user.get("id") or 0), pet_ref)
        return JSONResponse(result) if result.get("ok") else _failed(result)

    @router.post("/pets/set_active/{pet_ref}")
    def pet_activate(pet_ref: str, authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = set_active_pet(int(user.get("id") or 0), pet_ref)
        return JSONResponse(result) if result.get("ok") else _failed(result)

    @router.post("/pets/feed")
    def pet_feed(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = care_for_active_pet(int(user.get("id") or 0), "feed")
        return JSONResponse(result) if result.get("ok") else _failed(result)

    @router.post("/pets/train")
    def pet_train(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = care_for_active_pet(int(user.get("id") or 0), "train")
        return JSONResponse(result) if result.get("ok") else _failed(result)

    @router.post("/eggs/incubate/{egg_id}")
    def egg_incubate(egg_id: int, authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = incubate_egg(int(user.get("id") or 0), int(egg_id))
        return JSONResponse(result) if result.get("ok") else _failed(result)

    @router.post("/eggs/hatch/{egg_id}")
    def egg_hatch(egg_id: int, authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = hatch_egg(int(user.get("id") or 0), int(egg_id))
        return JSONResponse(result) if result.get("ok") else _failed(result)

    @router.post("/eggs/sell/{egg_id}")
    def egg_sell(egg_id: int, authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = sell_egg(int(user.get("id") or 0), int(egg_id))
        return JSONResponse(result) if result.get("ok") else _failed(result)

    @router.post("/eggs/purify/{egg_id}")
    def egg_purify(egg_id: int, authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = purify_egg(int(user.get("id") or 0), int(egg_id))
        return JSONResponse(result) if result.get("ok") else _failed(result)

    @router.post("/eggs/fuse/{tier}")
    def egg_fuse(tier: str, authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = fuse_eggs(int(user.get("id") or 0), tier)
        return JSONResponse(result) if result.get("ok") else _failed(result)

    return router
