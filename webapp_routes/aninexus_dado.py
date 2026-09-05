from __future__ import annotations

import json
import os
import random
from html import escape

import httpx
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from cards_service import build_cards_final_data
from database import (
    cancel_dice_roll,
    create_dice_roll,
    expire_stale_dice_rolls,
    get_active_dice_roll,
    get_dado_state,
    get_next_dado_recharge_info,
    pick_dice_roll_anime,
    resolve_dice_roll,
)
from utils.web_image_url import web_image_url
from webapp_routes.aninexus_compat import API_PREFIX, _require_user, _unauthorized


def _auth(authorization: str) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        return _require_user(authorization), None
    except PermissionError as exc:
        return None, _unauthorized(str(exc))


def _options_from_active(active: dict[str, Any]) -> list[dict[str, Any]]:
    raw = active.get("options_json") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    return [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _anime_pool() -> list[dict[str, Any]]:
    data = build_cards_final_data()
    chars_by_anime = data.get("characters_by_anime") or {}
    pool: list[dict[str, Any]] = []
    for anime in data.get("animes_list") or []:
        anime_id = int((anime or {}).get("anime_id") or 0)
        if anime_id <= 0 or not (chars_by_anime.get(anime_id) or []):
            continue
        pool.append(
            {
                "id": anime_id,
                "title": str((anime or {}).get("anime") or f"Anime {anime_id}"),
                "cover": web_image_url(
                    (anime or {}).get("cover_image") or (anime or {}).get("banner_image")
                ),
            }
        )
    return pool


def _character_from_anime(anime_id: int) -> Optional[dict[str, Any]]:
    data = build_cards_final_data()
    choices = [
        dict(item)
        for item in ((data.get("characters_by_anime") or {}).get(int(anime_id)) or [])
        if int((item or {}).get("id") or 0) > 0
    ]
    if not choices:
        return None
    item = random.SystemRandom().choice(choices)
    return {
        "id": int(item.get("id") or 0),
        "name": str(item.get("name") or "Personagem"),
        "image": web_image_url(item.get("image")),
        "anime_title": str(item.get("anime") or "Anime"),
        "anime_cover": web_image_url(
            ((data.get("animes_by_id") or {}).get(int(anime_id)) or {}).get("cover_image")
        ),
        "rarity": str(item.get("subcategory") or "COMMON").upper(),
    }


def _deterministic_tier(dice_value: int, character_id: int) -> dict[str, Any]:
    seed = ((int(character_id) * 1103515245) + (int(dice_value) * 12345)) & 0xFFFFFFFF
    roll = seed % 1000
    if roll < 30:
        return {"tier": "MÍTICO", "stars": 5}
    if roll < 150:
        return {"tier": "LENDÁRIO", "stars": 4}
    if roll < 420:
        return {"tier": "ÉPICO", "stars": 3}
    if roll < 760:
        return {"tier": "RARO", "stars": 2}
    return {"tier": "COMUM", "stars": 1}



def _dado_reward_photo(character_id: int, web_image: str) -> str:
    try:
        data = build_cards_final_data()
        item = dict((data.get("characters_by_id") or {}).get(int(character_id)) or {})
        raw = str(item.get("image") or "").strip()
        if raw.startswith(("http://", "https://")):
            return raw
    except Exception:
        pass

    image = str(web_image or "").strip()
    base_url = (str(os.getenv("BASE_URL", "") or "").strip() or str(os.getenv("WEBAPP_URL", "") or "").strip()).rstrip("/")
    if image.startswith("/") and base_url:
        return f"{base_url}{image}"
    if image.startswith(("http://", "https://")):
        return image
    return str(os.getenv("DADO_BANNER_URL", "") or "").strip()


def _deliver_dado_reward(user_id: int, roll_id: int, character: dict[str, Any]) -> None:
    character_id = int(character.get("id") or 0)
    if character_id <= 0:
        return

    name = escape(str(character.get("name") or "Personagem"))
    anime_title = escape(str(character.get("anime_title") or "Anime"))
    photo = _dado_reward_photo(character_id, str(character.get("image") or ""))
    caption = (
        "🎁 <b>VOCÊ GANHOU!</b>\n\n"
        f"🧧 <code>{character_id}</code>. <b>{name}</b>\n"
        f"<i>{anime_title}</i>\n\n"
        "📦 <b>Adicionado à sua coleção!</b>"
    )

    try:
        from utils.telegram_outbox import enqueue_photo

        enqueue_photo(
            dedupe_key=f"dado:{int(user_id)}:{int(roll_id)}",
            chat_id=int(user_id),
            photo=photo,
            caption=caption,
            parse_mode="HTML",
        )
        return
    except Exception as exc:
        print(f"[dado] falha ao enfileirar entrega no chat: {type(exc).__name__}", flush=True)

    token = str(os.getenv("BOT_TOKEN", "") or "").strip()
    if not token:
        return
    try:
        with httpx.Client(timeout=8.0) as client:
            if photo:
                client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    json={
                        "chat_id": int(user_id),
                        "photo": photo,
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                )
            else:
                client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": int(user_id),
                        "text": caption,
                        "parse_mode": "HTML",
                    },
                )
    except Exception as exc:
        print(f"[dado] falha no fallback de entrega: {type(exc).__name__}", flush=True)

def build_aninexus_dado_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-dado"])

    def state(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        try:
            expire_stale_dice_rolls(refund_pending=True)
        except Exception:
            pass
        dado = get_dado_state(user_id) or {}
        recharge = get_next_dado_recharge_info(user_id) or {}
        active = get_active_dice_roll(user_id)
        active_payload = None
        if active:
            options = _options_from_active(active)
            dice_value = int(active.get("dice_value") or 0)
            if options and len(options) == dice_value:
                active_payload = {
                    "roll_id": int(active.get("roll_id") or 0),
                    "dice_value": dice_value,
                    "options": options,
                    "status": str(active.get("status") or "pending"),
                }
        return JSONResponse(
            {
                "ok": True,
                "balance": int(dado.get("balance") or 0),
                "max_balance": int(recharge.get("max_balance") or 24),
                "next_recharge_hhmm": str(recharge.get("next_recharge_hhmm") or "--:--"),
                "next_recharge_iso": recharge.get("next_recharge_iso"),
                "active_roll": active_payload,
            }
        )

    def roll(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        try:
            expire_stale_dice_rolls(refund_pending=True)
        except Exception:
            pass

        active = get_active_dice_roll(user_id)
        if active:
            options = _options_from_active(active)
            dice_value = int(active.get("dice_value") or 0)
            if options and len(options) == dice_value:
                return JSONResponse(
                    {
                        "ok": True,
                        "reused": True,
                        "roll_id": int(active.get("roll_id") or 0),
                        "dice_value": dice_value,
                        "options": options,
                        "balance": int((get_dado_state(user_id) or {}).get("balance") or 0),
                    }
                )
            try:
                cancel_dice_roll(user_id, int(active.get("roll_id") or 0), refund=True)
            except Exception:
                pass

        pool = _anime_pool()
        max_value = min(6, len(pool))
        if max_value <= 0:
            return JSONResponse({"ok": False, "error": "anime_pool_unavailable"})
        dice_value = random.SystemRandom().randint(1, max_value)
        options = random.SystemRandom().sample(pool, dice_value)
        created = create_dice_roll(user_id, dice_value, options)
        if not created.get("ok"):
            return JSONResponse(created)
        roll_row = dict(created.get("roll") or {})
        response_options = created.get("options") or options or _options_from_active(roll_row)
        return JSONResponse(
            {
                "ok": True,
                "reused": bool(created.get("reused")),
                "roll_id": int(roll_row.get("roll_id") or 0),
                "dice_value": int(roll_row.get("dice_value") or dice_value),
                "options": response_options,
                "balance": int((get_dado_state(user_id) or {}).get("balance") or 0),
            }
        )

    def pick(
        payload: dict = Body(default={}),
        authorization: str = Header(default=""),
    ):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        try:
            roll_id = int((payload or {}).get("roll_id") or 0)
            anime_id = int((payload or {}).get("anime_id") or 0)
        except (TypeError, ValueError):
            roll_id = anime_id = 0
        if roll_id <= 0 or anime_id <= 0:
            return JSONResponse({"ok": False, "error": "invalid_pick"}, status_code=400)

        picked = pick_dice_roll_anime(user_id, roll_id, anime_id)
        if not picked.get("ok"):
            return JSONResponse(picked, status_code=409)

        roll_row = dict(picked.get("roll") or {})
        already_done = bool(picked.get("already_done"))
        if already_done:
            character_id = int(roll_row.get("rewarded_character_id") or 0)
            data = build_cards_final_data()
            item = dict((data.get("characters_by_id") or {}).get(character_id) or {})
            if not item:
                return JSONResponse({"ok": False, "error": "reward_unavailable"}, status_code=409)
            character = {
                "id": character_id,
                "name": str(item.get("name") or "Personagem"),
                "image": web_image_url(item.get("image")),
                "anime_title": str(item.get("anime") or "Anime"),
                "anime_cover": "",
            }
        else:
            character = _character_from_anime(anime_id)
            if not character:
                cancel_dice_roll(user_id, roll_id, refund=True)
                return JSONResponse(
                    {"ok": False, "error": "character_not_found", "refunded": True},
                    status_code=409,
                )
            resolved = resolve_dice_roll(user_id, roll_id, int(character.get("id") or 0))
            if not resolved.get("ok"):
                cancel_dice_roll(user_id, roll_id, refund=True)
                return JSONResponse(
                    {**resolved, "refunded": True},
                    status_code=409,
                )
            roll_row = dict(resolved.get("roll") or roll_row)

        tier = _deterministic_tier(
            int(roll_row.get("dice_value") or 1),
            int(character.get("id") or 0),
        )
        if not already_done:
            _deliver_dado_reward(user_id, roll_id, character)
        return JSONResponse(
            {
                "ok": True,
                "already_done": already_done,
                "roll_id": roll_id,
                "balance": int((get_dado_state(user_id) or {}).get("balance") or 0),
                "character": {
                    **character,
                    "tier": tier["tier"],
                    "stars": tier["stars"],
                },
            }
        )

    router.add_api_route("/dado/state", state, methods=["GET"])
    router.add_api_route("/dado/roll", roll, methods=["POST"])
    router.add_api_route("/dado/pick", pick, methods=["POST"])
    return router
