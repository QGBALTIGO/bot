from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from telegram import Bot
from telegram.error import BadRequest, NetworkError, RetryAfter, TelegramError, TimedOut


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourceBaltigo").strip()


def _is_channel_member(member: Any) -> bool:
    status = str(getattr(member, "status", "") or "").strip().lower()
    if status in {"creator", "administrator", "member"}:
        return True
    return status == "restricted" and bool(getattr(member, "is_member", False))


def _configuration_message(exc: BaseException) -> str | None:
    text = str(exc or "").strip().lower()
    markers = (
        "chat not found",
        "member list is inaccessible",
        "not enough rights",
        "need administrator rights",
        "bot is not a member",
    )
    if any(marker in text for marker in markers):
        return (
            "O bot não consegue consultar os membros do canal. "
            "Adicione o bot como administrador do canal obrigatório e tente novamente."
        )
    return None


async def _get_chat_member(user_id: int) -> Any:
    last_error: BaseException | None = None

    for attempt in range(2):
        try:
            async with Bot(token=BOT_TOKEN) as bot:
                return await bot.get_chat_member(
                    chat_id=REQUIRED_CHANNEL,
                    user_id=int(user_id),
                )
        except RetryAfter as exc:
            last_error = exc
            if attempt == 0:
                raw = getattr(exc, "retry_after", 1)
                try:
                    seconds = float(raw.total_seconds()) if hasattr(raw, "total_seconds") else float(raw)
                except (TypeError, ValueError):
                    seconds = 1.0
                await asyncio.sleep(max(0.25, min(seconds, 2.0)))
                continue
            raise
        except (TimedOut, NetworkError) as exc:
            last_error = exc
            if attempt == 0:
                await asyncio.sleep(0.35)
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Telegram não retornou o estado do membro.")


async def api_channel_selftest():
    if not BOT_TOKEN:
        return JSONResponse({"ok": False, "stage": "config", "error": "BOT_TOKEN ausente"}, status_code=500)
    if not REQUIRED_CHANNEL:
        return {"ok": True, "stage": "disabled", "channel_required": False}

    try:
        async with Bot(token=BOT_TOKEN) as bot:
            me = await bot.get_me()
            member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=me.id)
            status = str(getattr(member, "status", "") or "").strip().lower()
            return {
                "ok": status in {"administrator", "creator"},
                "stage": "telegram",
                "channel": REQUIRED_CHANNEL,
                "bot_username": getattr(me, "username", None),
                "bot_status": status,
                "can_reliably_check_other_members": status in {"administrator", "creator"},
            }
    except BadRequest as exc:
        return JSONResponse(
            {
                "ok": False,
                "stage": "telegram",
                "channel": REQUIRED_CHANNEL,
                "error": str(exc),
                "message": _configuration_message(exc) or "Telegram recusou o self-test.",
            },
            status_code=503,
        )
    except TelegramError as exc:
        return JSONResponse(
            {
                "ok": False,
                "stage": "telegram",
                "channel": REQUIRED_CHANNEL,
                "error": f"{type(exc).__name__}: {exc}",
            },
            status_code=502,
        )


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
            {"ok": False, "message": "BOT_TOKEN não configurado no serviço do WebApp."},
            status_code=500,
        )

    try:
        member = await _get_chat_member(user_id)
    except BadRequest as exc:
        config_message = _configuration_message(exc)
        print(
            f"[terms-membership] Telegram BadRequest user_id={user_id} "
            f"channel={REQUIRED_CHANNEL!r}: {exc}",
            flush=True,
        )
        return JSONResponse(
            {
                "ok": False,
                "message": config_message or "O Telegram recusou a verificação da inscrição.",
            },
            status_code=503,
        )
    except TelegramError as exc:
        print(
            f"[terms-membership] TelegramError user_id={user_id} "
            f"channel={REQUIRED_CHANNEL!r}: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return JSONResponse(
            {"ok": False, "message": "Não foi possível consultar o Telegram agora. Tente novamente."},
            status_code=502,
        )
    except Exception as exc:
        print(
            f"[terms-membership] erro inesperado user_id={user_id}: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return JSONResponse(
            {"ok": False, "message": "Falha interna ao verificar a inscrição."},
            status_code=500,
        )

    return {"ok": _is_channel_member(member)}


def install_terms_membership_route(app: FastAPI) -> None:
    """Replace only the legacy Terms membership endpoint."""
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
    app.add_api_route(
        "/api/channel/selftest",
        api_channel_selftest,
        methods=["GET"],
        name="api_channel_selftest",
    )
    print(
        f"[terms-membership] rota /api/channel/check instalada; antigas removidas={removed}",
        flush=True,
    )
