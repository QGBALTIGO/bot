from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from memory_rules import normalize_level
from memory_service import MemoryProofInvalid, MemorySessionInvalid, MemoryTooFast, finish_memory_session, memory_stats, start_memory_session
from memory_webapp import _page
from utils.api_response import api_error, api_ok
from utils.runtime_guard import rate_limiter


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def register_memory_routes(app) -> None:
    @app.get("/memory", response_class=HTMLResponse)
    async def memory_page(level: str = "medium"):
        return HTMLResponse(_page(level))

    @app.get("/api/v2/memory/stats")
    async def stats_api(request: Request):
        user_id = _uid(request)
        return api_ok(stats=memory_stats(user_id))

    @app.post("/api/v2/memory/start")
    async def start_api(request: Request):
        user_id = _uid(request)
        if not await rate_limiter.allow(f"memory:start:{user_id}", limit=6, window_seconds=60):
            return api_error("Muitas partidas iniciadas em sequência.", code="rate_limited", status_code=429)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        return api_ok(session=start_memory_session(user_id, normalize_level(str(payload.get("level") or "medium"))))

    @app.post("/api/v2/memory/finish")
    async def finish_api(request: Request):
        user_id = _uid(request)
        if not await rate_limiter.allow(f"memory:finish:{user_id}", limit=10, window_seconds=60):
            return api_error("Muitas tentativas em sequência.", code="rate_limited", status_code=429)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        try:
            result = finish_memory_session(user_id, str(payload.get("session_token") or ""), int(payload.get("moves") or 0), payload.get("proof"))
        except MemoryTooFast:
            return api_error("A conclusão foi rápida demais para ser validada.", code="implausible_time", status_code=409)
        except MemoryProofInvalid:
            return api_error("A sequência de pares não corresponde a esta partida.", code="invalid_proof", status_code=400)
        except MemorySessionInvalid:
            return api_error("Essa partida expirou ou já foi concluída.", code="invalid_session", status_code=409)
        return api_ok(result=result)
