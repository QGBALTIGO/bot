from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from utils.webapp_identity import resolve_webapp_user as _resolve_webapp_user
from webapp_services.profile_overview import build_menu_user_payload

CollectionSnapshot = Callable[[int], tuple[Any, Any, Any]]
CollectionCardsBuilder = Callable[[Any, Any, Any], list[dict[str, Any]]]


def build_profile_overview_router(
    *,
    collection_snapshot: CollectionSnapshot,
    collection_cards_from_snapshot: CollectionCardsBuilder,
) -> APIRouter:
    router = APIRouter(tags=["profile"])

    @router.get("/api/menu/profile")
    def api_menu_profile(
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
            build_menu_user_payload(
                int(ctx["user_id"]),
                collection_snapshot=collection_snapshot,
                collection_cards_from_snapshot=collection_cards_from_snapshot,
            )
        )

    return router
