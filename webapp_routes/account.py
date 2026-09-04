from __future__ import annotations

from fastapi import APIRouter, Body, Header

from utils.webapp_identity import resolve_webapp_user as _resolve_webapp_user

router = APIRouter(tags=["account"])


@router.post("/api/menu/delete-account")
def api_menu_delete_account(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )

    from database import delete_user_account

    delete_user_account(int(ctx["user_id"]))
    return {"ok": True}
