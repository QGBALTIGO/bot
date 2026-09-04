from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request

from cards_service import build_cards_final_data
from database_migrations import migration_status
from source_v2_progression import claim_quest, get_user_quests, list_achievements
from utils.runtime_guard import AsyncRateLimiter
from utils.webapp_identity import (
    build_fallback_webapp_user,
    get_tg_user,
    resolve_webapp_user,
)
from utils.webapp_session import (
    WebAppSessionError,
    bearer_token,
    create_session_token,
    validate_session_token,
)
from webapp_services.source_v2_compat import (
    build_source_collection,
    build_source_gallery,
    build_source_me,
    paginate_items,
)

router = APIRouter(prefix="/api/v1_7b82", tags=["source-v2-compat"])
_secure_init_limiter = AsyncRateLimiter(max_keys=10_000, cleanup_interval=60.0)


def _identity(
    *,
    x_telegram_init_data: str,
    x_webapp_uid: str,
    authorization: str = "",
) -> dict[str, Any]:
    # Prefer fresh Telegram-signed identity whenever the MiniApp still has it.
    if str(x_telegram_init_data or "").strip():
        return resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            x_webapp_uid=x_webapp_uid,
        )

    token = bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="telegram_init_data_or_session_required")
    try:
        session = validate_session_token(token)
    except WebAppSessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc) or "session_invalid") from exc

    identity = build_fallback_webapp_user(int(session["user_id"]))
    identity["auth_mode"] = "source_session"
    return identity


def _private_identity(
    x_telegram_init_data: str,
    x_webapp_uid: str,
    authorization: str,
) -> dict[str, Any]:
    return _identity(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        authorization=authorization,
    )


@router.post("/secure_init")
async def secure_init(request: Request, payload: dict = Body(...)):
    client_key = request.client.host if request.client else "unknown"
    if not await _secure_init_limiter.allow(f"secure_init:{client_key}", 10, 60.0):
        raise HTTPException(status_code=429, detail="too_many_requests")

    init_data = str(payload.get("initData") or "").strip()
    provided_token = str(payload.get("token") or "").strip()

    if init_data:
        try:
            identity = get_tg_user(init_data)
        except HTTPException:
            identity = None
        if identity:
            return {"token": create_session_token(int(identity["user_id"]))}

    if provided_token:
        try:
            session = validate_session_token(provided_token)
        except WebAppSessionError:
            session = None
        if session:
            # Refresh expiry without changing user identity.
            return {"token": create_session_token(int(session["user_id"]))}

    raise HTTPException(status_code=403, detail="authentication_failed")


@router.get("/bot/info")
def bot_info():
    return {
        "name": "SOURCE BALTIGO",
        "username": str(os.getenv("BOT_USERNAME", "SourceBaltigo_Bot") or "SourceBaltigo_Bot").lstrip("@"),
        "id": None,
        "avatar": "",
    }


@router.get("/me")
def me(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    identity = _private_identity(x_telegram_init_data, x_webapp_uid, authorization)
    return build_source_me(int(identity["user_id"]), identity)


@router.get("/harem")
def harem(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=100),
    search: str = Query(default=""),
    rarity: str = Query(default=""),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    identity = _private_identity(x_telegram_init_data, x_webapp_uid, authorization)
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
    authorization: str = Header(default=""),
):
    identity = _private_identity(x_telegram_init_data, x_webapp_uid, authorization)
    items = build_source_gallery(int(identity["user_id"]))
    return paginate_items(items, page=page, limit=limit, search=search, rarity=rarity)


@router.get("/rarities")
def rarities():
    # Character-to-rarity migration comes later. Legacy cards stay Standard until
    # each existing Source character is mapped deliberately.
    return ["Standard"]


@router.get("/social/marriage")
def marriage(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    _private_identity(x_telegram_init_data, x_webapp_uid, authorization)
    return None


@router.get("/battle/stats")
def battle_stats(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    identity = _private_identity(x_telegram_init_data, x_webapp_uid, authorization)
    from database_core import run

    row = run(
        """
        SELECT
            COUNT(*) FILTER (WHERE winner_user_id = %s) AS wins,
            COUNT(*) FILTER (WHERE loser_user_id = %s) AS losses
        FROM duels
        WHERE winner_user_id = %s OR loser_user_id = %s
        """,
        (int(identity["user_id"]), int(identity["user_id"]), int(identity["user_id"]), int(identity["user_id"])),
        fetch="one",
    ) or {}
    wins = int(row.get("wins") or 0)
    losses = int(row.get("losses") or 0)
    total = wins + losses
    return {
        "total_battles": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) * 100, 1) if total else 0,
    }


@router.get("/achievements/list")
def achievements_list(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    identity = _private_identity(x_telegram_init_data, x_webapp_uid, authorization)
    return list_achievements(int(identity["user_id"]))


@router.get("/quests")
def quests(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    identity = _private_identity(x_telegram_init_data, x_webapp_uid, authorization)
    return get_user_quests(int(identity["user_id"]))


@router.post("/quests/claim/{quest_id}")
def quests_claim(
    quest_id: str,
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    identity = _private_identity(x_telegram_init_data, x_webapp_uid, authorization)
    try:
        return claim_quest(int(identity["user_id"]), str(quest_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'") or "quest_not_found") from exc
    except ValueError as exc:
        code = str(exc) or "quest_invalid"
        status = 409 if code == "quest_already_claimed" else 400
        raise HTTPException(status_code=status, detail=code) from exc


@router.get("/compat/status")
def compat_status():
    data = build_cards_final_data()
    schema = migration_status()
    return {
        "ok": True,
        "version": "source-v2-seal-fusion",
        "catalog_characters": len(data.get("characters_by_id") or {}),
        "schema": schema,
        "implemented": [
            "/secure_init",
            "/me",
            "/harem",
            "/gallery",
            "/rarities",
            "/social/marriage",
            "/battle/stats",
            "/achievements/list",
            "/quests",
            "/quests/claim/{quest_id}",
        ],
    }
