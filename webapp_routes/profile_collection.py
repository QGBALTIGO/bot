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

    # Removing a favorite is explicit; an omitted or invalid ID is not a delete.
    if "character_id" in payload and payload["character_id"] is None:
        set_profile_favorite(user_id, None)
        return {"ok": True, "favorite": None}
    try:
        character_id = int(payload.get("character_id") or 0)
    except (TypeError, ValueError):
        character_id = 0
    if character_id <= 0:
        return JSONResponse({"ok": False, "message": "Personagem inválido."}, status_code=400)
    from database_core import run
    from cards_service import get_character_by_id
    from utils.web_image_url import web_image_url

    owned = run(
        "SELECT 1 FROM user_card_collection WHERE user_id=%s AND character_id=%s AND quantity>0 LIMIT 1",
        (user_id, character_id), fetch="one",
    )
    character = get_character_by_id(character_id) if owned else None
    if not character:
        return JSONResponse(
            {"ok": False, "message": "Você só pode favoritar personagens da sua coleção."},
            status_code=403,
        )
    set_profile_favorite(user_id, character_id)
    return {"ok": True, "favorite": {
        "id": character_id, "name": str(character.get("name") or ""),
        "anime": str(character.get("anime") or ""), "image": web_image_url(character.get("image")),
    }}
