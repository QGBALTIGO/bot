from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse

from cards_service import get_character_by_id, reload_cards_cache, search_characters
from database_aninexus_media import (
    activate_asset,
    create_and_activate_asset,
    get_asset,
    list_character_assets,
)
from utils.aninexus_admin import is_admin
from utils.aninexus_media import AniNexusMediaError, load_source_image, make_portrait_asset, upload_portrait_asset
from utils.web_image_url import web_image_url
from webapp_routes.aninexus_compat import API_PREFIX, _require_user, _unauthorized


def _auth_admin(authorization: str) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        user = _require_user(authorization)
    except PermissionError as exc:
        return None, _unauthorized(str(exc))
    user_id = int(user.get("id") or 0)
    if not is_admin(user_id):
        return None, JSONResponse(
            {"error": {"code": "admin_required", "message": "Acesso restrito à administração."}},
            status_code=403,
        )
    return user, None


def _character_payload(character_id: int) -> dict[str, Any] | None:
    character = dict(get_character_by_id(int(character_id)) or {})
    if not character:
        return None
    return {
        "id": int(character.get("id") or character_id),
        "name": str(character.get("name") or "").strip(),
        "anime": str(character.get("anime") or "").strip(),
        "anime_id": int(character.get("anime_id") or 0),
        "image": web_image_url(character.get("image")),
    }


def build_aninexus_admin_media_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-admin-media"])

    @router.get("/admin/media/search")
    def media_search(
        q: str = Query(..., min_length=1, max_length=120),
        limit: int = Query(default=30, ge=1, le=100),
        authorization: str = Header(default=""),
    ):
        _user, error = _auth_admin(authorization)
        if error:
            return error
        items = []
        for row in search_characters(q, limit=limit):
            payload = _character_payload(int(row.get("id") or 0))
            if payload:
                items.append(payload)
        return JSONResponse({"items": items, "total": len(items)})

    @router.get("/admin/media/{character_id}/assets")
    def media_assets(character_id: int, authorization: str = Header(default="")):
        _user, error = _auth_admin(authorization)
        if error:
            return error
        character = _character_payload(character_id)
        if not character:
            return JSONResponse(
                {"error": {"code": "character_not_found", "message": "Personagem não encontrado."}},
                status_code=404,
            )
        return JSONResponse(
            {
                "character": character,
                "assets": list_character_assets(character_id),
            }
        )

    @router.post("/admin/media/{character_id}/replace")
    async def media_replace(
        character_id: int,
        payload: dict = Body(default={}),
        authorization: str = Header(default=""),
    ):
        user, error = _auth_admin(authorization)
        if error:
            return error
        assert user is not None

        character = _character_payload(character_id)
        if not character:
            return JSONResponse(
                {"error": {"code": "character_not_found", "message": "Personagem não encontrado."}},
                status_code=404,
            )

        if not bool((payload or {}).get("rights_confirmed")):
            return JSONResponse(
                {
                    "error": {
                        "code": "rights_confirmation_required",
                        "message": "Confirme que você tem autorização para usar essa imagem.",
                    }
                },
                status_code=400,
            )

        media_url = str((payload or {}).get("media_url") or "").strip()
        media_data = str((payload or {}).get("media_data") or "").strip()
        try:
            source, _media_type, final_source_url = await load_source_image(
                media_url=media_url,
                media_data=media_data,
            )
            portrait, metadata, sha256 = make_portrait_asset(source)
            storage_url = await upload_portrait_asset(
                portrait,
                filename=f"aninexus-{int(character_id)}-{sha256[:12]}.jpg",
            )
            asset = create_and_activate_asset(
                character_id=int(character_id),
                source_url=final_source_url or media_url,
                storage_url=storage_url,
                content_sha256=sha256,
                output_width=int(metadata.get("output_width") or 0),
                output_height=int(metadata.get("output_height") or 0),
                crop_metadata=metadata,
                source_kind="url" if media_url else "file",
                uploaded_by=int(user.get("id") or 0),
            )
        except AniNexusMediaError as exc:
            messages = {
                "provide_one_image_source": "Envie uma URL ou um arquivo, nunca os dois ao mesmo tempo.",
                "invalid_image_data": "O arquivo enviado não é uma imagem válida.",
                "unsupported_image_type": "Formato de imagem não suportado.",
                "image_too_large": "A imagem é grande demais.",
                "unsupported_portrait_shape": "A imagem precisa ter enquadramento vertical compatível com o corte 2:3.",
                "invalid_image": "Não foi possível abrir essa imagem.",
                "blocked_image_host": "Essa origem de imagem não é permitida.",
                "media_storage_unavailable": "Não foi possível hospedar a imagem processada agora.",
            }
            return JSONResponse(
                {"error": {"code": str(exc), "message": messages.get(str(exc), "Não foi possível processar essa imagem.")}},
                status_code=int(exc.status_code),
            )

        reload_cards_cache()
        updated = _character_payload(character_id) or character
        updated["image"] = storage_url
        return JSONResponse({"ok": True, "character": updated, "asset": asset})

    @router.post("/admin/media/assets/{asset_id}/activate")
    def media_activate(asset_id: int, authorization: str = Header(default="")):
        user, error = _auth_admin(authorization)
        if error:
            return error
        assert user is not None
        if not get_asset(asset_id):
            return JSONResponse(
                {"error": {"code": "asset_not_found", "message": "Arte não encontrada."}},
                status_code=404,
            )
        asset = activate_asset(asset_id, int(user.get("id") or 0))
        if not asset:
            return JSONResponse(
                {"error": {"code": "asset_not_found", "message": "Arte não encontrada."}},
                status_code=404,
            )
        reload_cards_cache()
        return JSONResponse({"ok": True, "asset": asset})

    return router
