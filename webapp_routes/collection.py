from __future__ import annotations

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import HTMLResponse, JSONResponse

from premium_webapp_ui import build_collection_page as build_collection_page_html
from utils.webapp_identity import resolve_webapp_user as _resolve_webapp_user
from utils.collection_share import (
    CollectionShareError,
    create_collection_share_token,
    verify_collection_share_token,
)
from webapp_services.collection import (
    collection_animes_from_snapshot,
    collection_cards_from_snapshot,
    collection_detail_from_snapshot,
    collection_profile_payload,
    collection_snapshot,
)


def _touch_identity(user_id: int, ctx: dict) -> None:
    from database import touch_user_identity

    touch_user_identity(
        int(user_id),
        username=str(ctx.get("username") or "").strip(),
        full_name=str(ctx.get("full_name") or "").strip(),
    )


def _shared_owner(share: str) -> int:
    try:
        owner_id = verify_collection_share_token(share)
    except (CollectionShareError, RuntimeError):
        return 0
    from source_features.collection import settings
    return owner_id if bool(settings(owner_id).get("share_inline")) else 0


def _shared_error() -> JSONResponse:
    return JSONResponse(
        {"ok": False, "message": "Este compartilhamento expirou ou foi desativado."},
        status_code=404,
    )


def _state_payload(user_id: int, *, ctx: dict | None = None) -> dict:
    data, qty_by_char, subcategory_map = collection_snapshot(user_id)
    cards_items = collection_cards_from_snapshot(data, qty_by_char, subcategory_map)
    anime_items = collection_animes_from_snapshot(data, qty_by_char)
    profile = collection_profile_payload(user_id, ctx=ctx or {}, snapshot=(data, qty_by_char, subcategory_map))
    profile["collection_total"] = len(cards_items)
    return {
        "ok": True,
        "profile": profile,
        "stats": {
            "unique_cards": len(cards_items),
            "total_copies": sum(int(item.get("quantity") or 0) for item in cards_items),
            "completed_animes": sum(
                1 for item in anime_items
                if int(item.get("total_count") or 0) > 0 and int(item.get("missing_count") or 0) <= 0
            ),
            "active_animes": len(anime_items),
            "favorite_name": str(((profile.get("favorite") or {}).get("name") or "")).strip() or "--",
        },
    }


def build_collection_router(*, banner_url: str) -> APIRouter:
    router = APIRouter(tags=["collection"])

    @router.get("/cccolecao", response_class=HTMLResponse)
    def collection_webapp_page(uid: int = Query(default=0)):
        return HTMLResponse(
            build_collection_page_html(
                uid=int(uid or 0),
                banner_url=banner_url,
            )
        )

    @router.get("/cccolecao/shared", response_class=HTMLResponse)
    def shared_collection_webapp_page(share: str = Query(..., min_length=16)):
        if not _shared_owner(share):
            return HTMLResponse("Compartilhamento expirado ou desativado.", status_code=404)
        return HTMLResponse(
            build_collection_page_html(uid=0, banner_url=banner_url, share_token=share)
        )

    @router.post("/api/collection/share")
    def api_collection_share(
        payload: dict = Body(default={}),
        uid: int = Query(default=0),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data, uid=uid, x_webapp_uid=x_webapp_uid
        )
        user_id = int(ctx["user_id"])
        from source_features.collection import save_settings
        # Clicking Share is the explicit opt-in. The existing setting remains the revocation switch.
        save_settings(user_id, {"share_inline": True})
        token = create_collection_share_token(user_id)
        return JSONResponse({
            "ok": True,
            "path": f"/cccolecao/shared?share={token}",
            "expires_in": 7 * 24 * 3600,
        })

    @router.get("/api/collection/shared/state")
    def api_shared_collection_state(share: str = Query(..., min_length=16)):
        owner_id = _shared_owner(share)
        if not owner_id:
            return _shared_error()
        return JSONResponse(_state_payload(owner_id))

    @router.get("/api/collection/shared/cards")
    def api_shared_collection_cards(share: str = Query(..., min_length=16)):
        owner_id = _shared_owner(share)
        if not owner_id:
            return _shared_error()
        data, qty_by_char, subcategory_map = collection_snapshot(owner_id)
        return JSONResponse({"ok": True, "items": collection_cards_from_snapshot(data, qty_by_char, subcategory_map)})

    @router.get("/api/collection/shared/animes")
    def api_shared_collection_animes(share: str = Query(..., min_length=16)):
        owner_id = _shared_owner(share)
        if not owner_id:
            return _shared_error()
        data, qty_by_char, _ = collection_snapshot(owner_id)
        return JSONResponse({"ok": True, "items": collection_animes_from_snapshot(data, qty_by_char)})

    @router.get("/api/collection/shared/anime")
    def api_shared_collection_anime(
        share: str = Query(..., min_length=16),
        anime_id: int = Query(..., ge=1),
        mode: str = Query(default="owned"),
    ):
        owner_id = _shared_owner(share)
        if not owner_id:
            return _shared_error()
        data, qty_by_char, subcategory_map = collection_snapshot(owner_id)
        result = collection_detail_from_snapshot(data, qty_by_char, subcategory_map, anime_id=anime_id, mode=mode)
        if not result:
            return JSONResponse({"ok": False, "message": "Obra nao encontrada."}, status_code=404)
        return JSONResponse({"ok": True, **result})

    @router.get("/api/collection/state")
    def api_collection_state(
        uid: int = Query(default=0),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            uid=uid,
            x_webapp_uid=x_webapp_uid,
        )
        user_id = int(ctx["user_id"])

        return JSONResponse(_state_payload(user_id, ctx=ctx))

    @router.get("/api/collection/cards")
    def api_collection_cards(
        uid: int = Query(default=0),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            uid=uid,
            x_webapp_uid=x_webapp_uid,
        )
        user_id = int(ctx["user_id"])

        data, qty_by_char, subcategory_map = collection_snapshot(user_id)
        return JSONResponse({
            "ok": True,
            "items": collection_cards_from_snapshot(data, qty_by_char, subcategory_map),
        })

    @router.get("/api/collection/animes")
    def api_collection_animes(
        uid: int = Query(default=0),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            uid=uid,
            x_webapp_uid=x_webapp_uid,
        )
        user_id = int(ctx["user_id"])

        data, qty_by_char, _ = collection_snapshot(user_id)
        return JSONResponse({
            "ok": True,
            "items": collection_animes_from_snapshot(data, qty_by_char),
        })

    @router.get("/api/collection/anime")
    def api_collection_anime(
        anime_id: int = Query(..., ge=1),
        mode: str = Query(default="owned"),
        uid: int = Query(default=0),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            uid=uid,
            x_webapp_uid=x_webapp_uid,
        )
        user_id = int(ctx["user_id"])

        data, qty_by_char, subcategory_map = collection_snapshot(user_id)
        payload = collection_detail_from_snapshot(
            data,
            qty_by_char,
            subcategory_map,
            anime_id=anime_id,
            mode=mode,
        )
        if not payload:
            return JSONResponse(
                {"ok": False, "message": "Obra nao encontrada."},
                status_code=404,
            )
        return JSONResponse({"ok": True, **payload})

    return router
