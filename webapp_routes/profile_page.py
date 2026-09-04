from __future__ import annotations

import os

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from premium_webapp_ui import build_menu_page as build_menu_page_html


def build_profile_page_router(*, default_banner_url: str) -> APIRouter:
    router = APIRouter(tags=["profile"])
    menu_banner_url = os.getenv("MENU_BANNER_URL", default_banner_url).strip()

    @router.get("/menu", response_class=HTMLResponse)
    def menu_page(uid: int = Query(...)):
        return HTMLResponse(
            build_menu_page_html(
                uid=int(uid),
                menu_banner_url=menu_banner_url,
            )
        )

    return router
