from __future__ import annotations

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import HTMLResponse, JSONResponse

from premium_webapp_ui import build_memory_page as build_memory_page_html
from utils.webapp_identity import resolve_webapp_user as _resolve_webapp_user
from webapp_services.memory import (
    build_memory_best_payload,
    build_memory_finish_payload,
    normalize_memory_finish_input,
)

_VALIDATION_MESSAGES = {
    "Nivel invalido.",
    "Tempo invalido.",
    "Quantidade de jogadas invalida.",
}


def _touch_identity(user_id: int, ctx: dict) -> None:
    from database import touch_user_identity

    touch_user_identity(
        int(user_id),
        username=str(ctx.get("username") or "").strip(),
        full_name=str(ctx.get("full_name") or "").strip(),
    )


def build_memory_router(*, banner_url: str) -> APIRouter:
    router = APIRouter(tags=["memory"])

    @router.get("/memoria", response_class=HTMLResponse)
    def memory_page(
        level: str = Query(default="medium"),
        uid: int = Query(default=0),
    ):
        return HTMLResponse(
            build_memory_page_html(
                uid=int(uid or 0),
                banner_url=banner_url,
                default_level=str(level or "medium"),
            )
        )

    @router.get("/memory", response_class=HTMLResponse)
    def memory_alias(
        level: str = Query(default="medium"),
        uid: int = Query(default=0),
    ):
        return memory_page(level=level, uid=uid)

    @router.get("/api/memory/best")
    def api_memory_best(
        uid: int = Query(default=0),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        from database import get_memory_best_summary

        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            uid=uid,
            x_webapp_uid=x_webapp_uid,
        )
        user_id = int(ctx["user_id"])
        _touch_identity(user_id, ctx)

        return JSONResponse(build_memory_best_payload(get_memory_best_summary(user_id)))

    @router.post("/api/memory/finish")
    def api_memory_finish(
        payload: dict = Body(...),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        from database import save_memory_game_result

        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            uid=payload.get("uid"),
            body_uid=payload.get("uid"),
            x_webapp_uid=x_webapp_uid,
        )
        user_id = int(ctx["user_id"])
        _touch_identity(user_id, ctx)

        try:
            level, time_ms, moves = normalize_memory_finish_input(payload)
        except ValueError as exc:
            message = str(exc)
            if message not in _VALIDATION_MESSAGES:
                raise
            return JSONResponse({"ok": False, "message": message}, status_code=400)

        try:
            result = save_memory_game_result(user_id, level, time_ms, moves)
        except ValueError as exc:
            return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)

        return JSONResponse(
            build_memory_finish_payload(
                result,
                level=level,
                time_ms=time_ms,
                moves=moves,
            )
        )

    return router
