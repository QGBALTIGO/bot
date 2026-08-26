from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourceBaltigo").strip()


def _is_channel_member(result: dict[str, Any]) -> bool:
    status = str(result.get("status") or "").strip().lower()
    if status in {"creator", "administrator", "member"}:
        return True
    return status == "restricted" and bool(result.get("is_member", False))


async def _get_chat_member(user_id: int) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
    payload = {
        "chat_id": REQUIRED_CHANNEL,
        "user_id": int(user_id),
    }
    timeout = httpx.Timeout(10.0, connect=5.0)
    last_error: Exception | None = None

    # Railway can expose proxy variables in the environment. The bot client itself
    # works without relying on those proxies, so this request should do the same.
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        for attempt in range(2):
            try:
                response = await client.post(url, json=payload)
                data = response.json()

                # A transient Telegram/server failure deserves one quick retry.
                if response.status_code >= 500 and attempt == 0:
                    await asyncio.sleep(0.25)
                    continue

                return data if isinstance(data, dict) else {}
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue

    if last_error is not None:
        raise last_error
    return {}


async def api_channel_check(payload: dict = Body(...)):
    try:
        user_id = int((payload or {}).get("uid") or 0)
    except (TypeError, ValueError):
        user_id = 0

    if user_id <= 0:
        return JSONResponse(
            {"ok": False, "message": "UID inválido."},
            status_code=400,
        )

    if not REQUIRED_CHANNEL:
        return {"ok": True}

    if not BOT_TOKEN:
        print("[terms-membership] BOT_TOKEN ausente", flush=True)
        return JSONResponse(
            {"ok": False, "message": "Não foi possível verificar sua inscrição agora."},
            status_code=500,
        )

    try:
        data = await _get_chat_member(user_id)
    except Exception as exc:
        print(
            f"[terms-membership] falha de rede user_id={user_id}: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return JSONResponse(
            {"ok": False, "message": "Não foi possível consultar o Telegram agora. Tente novamente em instantes."},
            status_code=502,
        )

    if not data.get("ok"):
        description = str(data.get("description") or "erro desconhecido").strip()
        error_code = data.get("error_code")
        print(
            f"[terms-membership] Telegram recusou getChatMember "
            f"user_id={user_id} channel={REQUIRED_CHANNEL!r} "
            f"error_code={error_code!r} description={description!r}",
            flush=True,
        )
        return JSONResponse(
            {"ok": False, "message": "Não foi possível verificar sua inscrição agora. Tente novamente em instantes."},
            status_code=502,
        )

    result = data.get("result") or {}
    return {"ok": _is_channel_member(result)}


def install_terms_membership_route(app: FastAPI) -> None:
    """Replace only the legacy Terms membership endpoint.

    webapp.py is intentionally left untouched: the Terms page keeps calling the
    same /api/channel/check URL, while this installs the corrected implementation
    before Uvicorn starts serving requests.
    """
    kept_routes = []
    removed = 0

    for route in app.router.routes:
        is_target = (
            isinstance(route, APIRoute)
            and route.path == "/api/channel/check"
            and "POST" in (route.methods or set())
        )
        if is_target:
            removed += 1
            continue
        kept_routes.append(route)

    app.router.routes = kept_routes
    app.add_api_route(
        "/api/channel/check",
        api_channel_check,
        methods=["POST"],
        name="api_channel_check",
    )
    print(
        f"[terms-membership] rota /api/channel/check instalada; antigas removidas={removed}",
        flush=True,
    )
