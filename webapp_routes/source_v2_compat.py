from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Query

from cards_service import build_cards_final_data
from utils.webapp_identity import resolve_webapp_user
from webapp_services.source_v2_compat import (
    build_source_collection,
    build_source_gallery,
    build_source_me,
    paginate_items,
)

router = APIRouter(prefix="/api/v1_7b82", tags=["source-v2-compat"])


def _identity(
    *,
    x_telegram_init_data: str,
    x_webapp_uid: str,
) -> dict[str, Any]:
    return resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
    )


@router.get("/bot/info")
def bot_info():
    return {
        "name": "SOURCE BALTIGO",
        "username": "",
        "id": None,
        "avatar": "",
    }


@router.get("/me")
def me(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    identity = _identity(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
    )
    return build_source_me(int(identity["user_id"]), identity)


@router.get("/harem")
def harem(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=100),
    search: str = Query(default=""),
    rarity: str = Query(default=""),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    identity = _identity(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
    )
    _, _, items = build_source_collection(int(identity["user_id"]))
    return paginate_items(items, page=page, limit=limit, search=search, rarity=rarity)


@router.get("/gallery")
def gallery(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=100),
    search: str = Query(default=""),
    rarity: str = Query(default=""),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    identity = _identity(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
    )
    items = build_source_gallery(int(identity["user_id"]))
    return paginate_items(items, page=page, limit=limit, search=search, rarity=rarity)


@router.get("/rarities")
def rarities():
    # O sistema de raridades do Seal será portado como domínio próprio.
    # Até a migration, todos os cards atuais pertencem ao pool estável Standard.
    return ["Standard"]


@router.get("/social/marriage")
def marriage(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    _identity(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
    )
    return None


@router.get("/battle/stats")
def battle_stats(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    _identity(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
    )
    return {
        "total_battles": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0,
    }


@router.get("/achievements/list")
def achievements_list(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    _identity(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
    )
    return []


@router.get("/compat/status")
def compat_status():
    data = build_cards_final_data()
    return {
        "ok": True,
        "version": "source-v2-seal-fusion",
        "catalog_characters": len(data.get("characters_by_id") or {}),
        "implemented": [
            "/me",
            "/harem",
            "/gallery",
            "/rarities",
            "/social/marriage",
            "/battle/stats",
            "/achievements/list",
        ],
    }
