from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from utils.webapp_identity import resolve_webapp_user as _resolve_webapp_user

CollectionSnapshot = Callable[[int], Any]
CollectionCardsFromSnapshot = Callable[..., list[dict[str, Any]]]


def build_context_router(
    *,
    collection_snapshot: CollectionSnapshot,
    collection_cards_from_snapshot: CollectionCardsFromSnapshot,
) -> APIRouter:
    """Cria a rota de bootstrap da MiniApp sem duplicar regras de coleção."""

    router = APIRouter(tags=["webapp-context"])

    @router.get("/api/webapp/context")
    def api_webapp_context(
        uid: int = Query(default=0),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        from database import (
            get_profile_settings,
            get_progress_row,
            get_user_status,
            get_user_xcard_collection,
            touch_user_identity,
        )

        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            uid=uid,
            x_webapp_uid=x_webapp_uid,
        )
        user_id = int(ctx["user_id"])
        touch_user_identity(
            user_id,
            username=str(ctx.get("username") or "").strip(),
            full_name=str(ctx.get("full_name") or "").strip(),
        )

        user = get_user_status(user_id) or {}
        progress = get_progress_row(user_id) or {}
        settings = get_profile_settings(user_id) or {}
        cards_data, qty_by_char, subcategory_map = collection_snapshot(user_id)
        cards = collection_cards_from_snapshot(
            cards_data,
            qty_by_char,
            subcategory_map,
        )
        xcards = get_user_xcard_collection(user_id) or []

        display_name = (
            str(settings.get("nickname") or "").strip()
            or str(ctx.get("full_name") or "").strip()
            or (
                f"@{ctx.get('username')}"
                if str(ctx.get("username") or "").strip()
                else f"User {user_id}"
            )
        )

        return JSONResponse(
            {
                "ok": True,
                "profile": {
                    "user_id": user_id,
                    "username": str(
                        ctx.get("username") or user.get("username") or ""
                    ).strip(),
                    "full_name": str(
                        ctx.get("full_name") or user.get("full_name") or ""
                    ).strip(),
                    "display_name": display_name,
                    "nickname": str(settings.get("nickname") or "").strip(),
                    "coins": int(user.get("coins") or 0),
                    "dado_balance": int(user.get("dado_balance") or 0),
                    "level": int(progress.get("level") or 1),
                    "collection_total": len(cards),
                    "xcollection_total": len(xcards),
                    "xcollection_copies": sum(
                        int(item.get("quantity") or 0) for item in xcards
                    ),
                    "auth_mode": str(ctx.get("auth_mode") or ""),
                },
            }
        )

    return router
