from __future__ import annotations

import re

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from database_profile import (
    set_profile_language,
    set_profile_nickname,
    set_profile_notifications,
    set_profile_private,
)
from utils.webapp_identity import resolve_webapp_user as _resolve_webapp_user

router = APIRouter(tags=["profile"])


def valid_menu_nickname(nickname: str) -> bool:
    nickname = (nickname or "").strip()
    return bool(re.match(r"^[A-Z][A-Za-z0-9_]{3,16}$", nickname))


@router.post("/api/menu/nickname")
def api_menu_nickname(
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
    nickname = str(payload.get("nickname") or "").strip()

    if not valid_menu_nickname(nickname):
        return JSONResponse(
            {
                "ok": False,
                "message": "Nickname inválido. Use 4-17 caracteres, começando com letra maiúscula.",
            },
            status_code=400,
        )

    result = set_profile_nickname(user_id, nickname)
    if not result.get("ok"):
        error = result.get("error")
        if error == "nickname_locked":
            return JSONResponse(
                {"ok": False, "message": "Você já definiu seu nickname."},
                status_code=400,
            )
        if error == "nickname_taken":
            return JSONResponse(
                {"ok": False, "message": "Esse nickname já está em uso."},
                status_code=409,
            )
        return JSONResponse(
            {"ok": False, "message": "Não foi possível salvar o nickname."},
            status_code=400,
        )

    return {"ok": True}


@router.post("/api/menu/language")
def api_menu_language(
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
    language = str(payload.get("language") or "pt").strip().lower()

    if language not in {"pt", "en", "es"}:
        return JSONResponse(
            {"ok": False, "message": "Idioma inválido."},
            status_code=400,
        )

    set_profile_language(user_id, language)
    return {"ok": True}


@router.post("/api/menu/privacy")
def api_menu_privacy(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    value = payload.get("value")
    if not isinstance(value, bool):
        return JSONResponse(
            {"ok": False, "message": "Valor de privacidade inválido."},
            status_code=400,
        )

    set_profile_private(int(ctx["user_id"]), value)
    return {"ok": True}


@router.post("/api/menu/notifications")
def api_menu_notifications(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    value = payload.get("value")
    if not isinstance(value, bool):
        return JSONResponse(
            {"ok": False, "message": "Valor de notificação inválido."},
            status_code=400,
        )

    set_profile_notifications(int(ctx["user_id"]), value)
    return {"ok": True}
