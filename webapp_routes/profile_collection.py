from __future__ import annotations

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse

from database_profile import set_profile_favorite
from utils.webapp_identity import resolve_webapp_user as _resolve_webapp_user
from webapp_services.profile_collection import menu_collection_characters

router = APIRouter(tags=["profile"])


@router.get("/api/menu/collection-characters")
def api_menu_collection_characters(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    return JSONResponse(
        {
            "ok": True,
            "items": menu_collection_characters(int(ctx["user_id"])),
        }
    )


@router.post("/api/menu/favorite")
def api_menu_favorite(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    user_id = int(ctx["user_id"])

    try:
        character_id = int(payload.get("character_id") or 0)
    except (TypeError, ValueError):
        character_id = 0

    if character_id <= 0:
        return JSONResponse(
            {"ok": False, "message": "Personagem inválido."},
            status_code=400,
        )

    owned_ids = {
        int(item["id"])
        for item in menu_collection_characters(user_id)
    }
    if character_id not in owned_ids:
        return JSONResponse(
            {
                "ok": False,
                "message": "Você só pode favoritar personagens da sua coleção.",
            },
            status_code=403,
        )

    set_profile_favorite(user_id, character_id)
    return {"ok": True}
