from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from utils.telegram_webapp_auth import TelegramWebAppAuthError, validate_telegram_init_data
from utils.web_image_url import web_image_url
from webapp_services.collection import (
    collection_cards_from_snapshot,
    collection_snapshot,
)
from webapp_services.profile_overview import build_menu_user_payload

API_PREFIX = "/api/v1_7b82"
SESSION_TTL_SECONDS = max(300, int(os.getenv("SEAL_SESSION_TTL_SECONDS", "21600")))


def _bot_token() -> str:
    token = str(os.getenv("BOT_TOKEN", "") or "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN não configurado")
    return token


def _session_key() -> bytes:
    explicit = str(os.getenv("SEAL_SESSION_SECRET", "") or "").strip()
    material = explicit or f"seal-source-session:{_bot_token()}"
    return hashlib.sha256(material.encode("utf-8")).digest()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + ("=" * (-len(raw) % 4)))


def _issue_session(user: dict[str, Any]) -> str:
    now = int(time.time())
    payload = {
        "v": 1,
        "iat": now,
        "exp": now + SESSION_TTL_SECONDS,
        "user": {
            "id": int(user.get("id") or 0),
            "first_name": str(user.get("first_name") or ""),
            "last_name": str(user.get("last_name") or ""),
            "username": str(user.get("username") or ""),
            "photo_url": str(user.get("photo_url") or ""),
        },
    }
    body = _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = _b64e(hmac.new(_session_key(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def _read_session(token: str) -> dict[str, Any]:
    raw = str(token or "").strip()
    if not raw or "." not in raw:
        raise ValueError("session_missing")
    body, signature = raw.rsplit(".", 1)
    expected = hmac.new(_session_key(), body.encode("ascii"), hashlib.sha256).digest()
    try:
        received = _b64d(signature)
    except Exception as exc:
        raise ValueError("session_invalid") from exc
    if not hmac.compare_digest(expected, received):
        raise ValueError("session_invalid")
    try:
        payload = json.loads(_b64d(body).decode("utf-8"))
    except Exception as exc:
        raise ValueError("session_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("session_invalid")
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("session_expired")
    user = payload.get("user")
    if not isinstance(user, dict) or int(user.get("id") or 0) <= 0:
        raise ValueError("session_invalid")
    return payload


def _bearer_token(authorization: str) -> str:
    raw = str(authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        return ""
    return raw.split(" ", 1)[1].strip()


def _require_user(authorization: str) -> dict[str, Any]:
    token = _bearer_token(authorization)
    try:
        payload = _read_session(token)
    except ValueError as exc:
        code = str(exc)
        raise PermissionError(code) from exc
    return dict(payload.get("user") or {})


def _unauthorized(code: str = "unauthorized") -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": "Session expired. Please reopen the app.",
            }
        },
        status_code=401,
    )


def _character_payload(meta: dict[str, Any], quantity: int = 0) -> dict[str, Any]:
    cid = int(meta.get("id") or meta.get("character_id") or 0)
    rarity = str(
        meta.get("rarity")
        or meta.get("subcategory")
        or meta.get("category")
        or "COMMON"
    ).strip()
    image = web_image_url(meta.get("image") or meta.get("img_url"))
    return {
        "id": str(cid),
        "name": str(meta.get("name") or f"Character {cid}"),
        "anime": str(meta.get("anime") or "Unknown"),
        "rarity": rarity,
        "img_url": image,
        "zenith_price": int(meta.get("zenith_price") or 0),
        "base_zenith_price": int(meta.get("base_zenith_price") or 0),
        "staff_discount": 0,
        "owned": int(quantity or 0) > 0,
        "count": max(0, int(quantity or 0)),
    }


def _user_payload(session_user: dict[str, Any]) -> dict[str, Any]:
    uid = int(session_user.get("id") or 0)
    overview = build_menu_user_payload(
        uid,
        collection_snapshot=collection_snapshot,
        collection_cards_from_snapshot=collection_cards_from_snapshot,
    )
    profile = dict(overview.get("profile") or {})
    data, qty_by_char, _subcategory_map = collection_snapshot(uid)
    characters_by_id = data.get("characters_by_id") or {}

    unique_count = len([qty for qty in qty_by_char.values() if int(qty or 0) > 0])
    total_copies = sum(max(0, int(qty or 0)) for qty in qty_by_char.values())
    total_available = len(characters_by_id)
    collection_percent = (
        round((unique_count / total_available) * 100, 1)
        if total_available > 0
        else 0.0
    )

    progress = {}
    try:
        from database import get_progress_row

        progress = get_progress_row(uid) or {}
    except Exception:
        progress = {}

    level = int(profile.get("level") or progress.get("level") or 1)
    xp_total = int(progress.get("xp") or progress.get("total_xp") or 0)
    xp_current = int(progress.get("xp_current") or progress.get("current_xp") or xp_total)
    xp_needed = int(progress.get("xp_needed") or progress.get("next_level_xp") or 1000)
    if xp_needed <= 0:
        xp_needed = 1000

    first_name = str(session_user.get("first_name") or "").strip()
    last_name = str(session_user.get("last_name") or "").strip()
    username = str(session_user.get("username") or profile.get("username") or "").strip()
    avatar = str(session_user.get("photo_url") or "").strip()

    return {
        "id": uid,
        "first_name": first_name or str(profile.get("display_name") or "Operator"),
        "last_name": last_name or None,
        "username": username,
        "avatar": avatar,
        "is_sudo": False,
        "role": None,
        "role_label": None,
        "role_tag": None,
        "role_symbol": None,
        "is_staff": False,
        "can_upload": False,
        "can_edit_character": False,
        "upload_reward": None,
        "role_perks": {},
        "role_benefits": [],
        "balance": int(profile.get("coins") or 0),
        "zenith": 0,
        "stats": {
            "level": level,
            "xp": xp_total,
            "xp_current": xp_current,
            "xp_needed": xp_needed,
            "streak": int(progress.get("streak") or 0),
            "points": int(profile.get("coins") or 0),
            "zenith": 0,
            "badges": [],
            "total_characters": total_copies,
            "unique_characters": unique_count,
            "total_available_characters": total_available,
            "collection_percent": collection_percent,
            "rank": 0,
            "percentile": 0,
            "pass_type": "free",
            "incubation_slots": 1,
            "active_incubations": 0,
        },
        "achievements": [],
        "titles": {"current": "OPERATOR", "all": ["OPERATOR"]},
        "characters": [],
        "current_pet": None,
        "eggs": [],
        "pets": [],
    }


def build_seal_compat_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["seal-compat"])

    @router.post("/secure_init")
    async def secure_init(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        init_data = str((body or {}).get("initData") or "").strip()
        if not init_data:
            return _unauthorized("init_data_missing")
        try:
            validated = validate_telegram_init_data(init_data, _bot_token())
        except TelegramWebAppAuthError as exc:
            return _unauthorized(str(exc))

        user = dict(validated.get("user") or {})
        user_id = int(validated.get("user_id") or 0)
        try:
            from database import create_or_get_user, touch_user_identity

            create_or_get_user(user_id)
            touch_user_identity(
                user_id,
                username=str(user.get("username") or "").strip(),
                full_name=" ".join(
                    part
                    for part in [
                        str(user.get("first_name") or "").strip(),
                        str(user.get("last_name") or "").strip(),
                    ]
                    if part
                ),
            )
        except Exception:
            pass

        return {"token": _issue_session(user)}

    @router.get("/me")
    def me(authorization: str = Header(default="")):
        try:
            session_user = _require_user(authorization)
        except PermissionError as exc:
            return _unauthorized(str(exc))
        return JSONResponse(_user_payload(session_user))

    @router.get("/harem")
    def harem(
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=24, ge=1, le=100),
        search: str = Query(default=""),
        rarity: str = Query(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            session_user = _require_user(authorization)
        except PermissionError as exc:
            return _unauthorized(str(exc))

        uid = int(session_user.get("id") or 0)
        data, qty_by_char, subcategory_map = collection_snapshot(uid)
        chars_by_id = data.get("characters_by_id") or {}
        needle = str(search or "").strip().lower()
        rarity_needle = str(rarity or "").strip().lower()
        items: list[dict[str, Any]] = []

        for cid, quantity in qty_by_char.items():
            if int(quantity or 0) <= 0:
                continue
            meta = dict(chars_by_id.get(int(cid)) or {})
            if not meta:
                continue
            meta.setdefault("id", int(cid))
            meta.setdefault("subcategory", str(subcategory_map.get(int(cid)) or ""))
            payload = _character_payload(meta, int(quantity))
            if needle and needle not in payload["name"].lower() and needle not in payload["anime"].lower():
                continue
            if rarity_needle and rarity_needle not in payload["rarity"].lower():
                continue
            items.append(payload)

        items.sort(key=lambda item: (str(item["anime"]).lower(), str(item["name"]).lower()))
        total = len(items)
        start = (page - 1) * limit
        return {"items": items[start:start + limit], "total": total}

    @router.get("/rarities")
    def rarities(authorization: str = Header(default="")):
        try:
            _require_user(authorization)
        except PermissionError as exc:
            return _unauthorized(str(exc))
        data = collection_snapshot(0)[0]
        labels: set[str] = set()
        subcategories = data.get("subcategories") or {}
        for label in subcategories.keys():
            clean = str(label or "").strip()
            if clean:
                labels.add(clean)
        for meta in (data.get("characters_by_id") or {}).values():
            clean = str((meta or {}).get("rarity") or "").strip()
            if clean:
                labels.add(clean)
        return JSONResponse(sorted(labels, key=str.lower))

    @router.get("/social/marriage")
    def marriage(authorization: str = Header(default="")):
        try:
            _require_user(authorization)
        except PermissionError as exc:
            return _unauthorized(str(exc))
        return JSONResponse(None)

    @router.get("/battle/stats")
    def battle_stats(authorization: str = Header(default="")):
        try:
            _require_user(authorization)
        except PermissionError as exc:
            return _unauthorized(str(exc))
        return JSONResponse(None)

    return router
