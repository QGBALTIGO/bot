from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from termo_game_service import (
    TermoDuplicateGuess,
    TermoHintAlreadyUsed,
    TermoInsufficientCoins,
    TermoInvalidGuess,
    TermoInvalidState,
    buy_hint,
    get_active_or_today,
    start_daily_game,
    start_train_game,
    submit_guess,
)
from termo_rules import HINT_COST_COINS
from termo_service import get_termo_dashboard
from termo_webapp import _page
from utils.api_response import api_error, api_ok
from utils.runtime_guard import rate_limiter


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def register_termo_routes(app) -> None:
    @app.get("/termo", response_class=HTMLResponse)
    async def termo_page(): return HTMLResponse(_page())

    @app.get("/api/v2/termo/state")
    async def state_api(request: Request):
        uid=_uid(request); return api_ok(game=get_active_or_today(uid),dashboard=get_termo_dashboard(uid))

    @app.post("/api/v2/termo/start")
    async def start_api(request: Request):
        uid=_uid(request)
        if not await rate_limiter.allow(f"termo:start:{uid}",limit=5,window_seconds=60): return api_error("Muitas tentativas em sequência.",code="rate_limited",status_code=429)
        return api_ok(game=start_daily_game(uid))

    @app.post("/api/v2/termo/train")
    async def train_api(request: Request):
        uid=_uid(request)
        if not await rate_limiter.allow(f"termo:train:{uid}",limit=8,window_seconds=60): return api_error("Muitos treinos iniciados.",code="rate_limited",status_code=429)
        return api_ok(game=start_train_game(uid))

    @app.post("/api/v2/termo/guess")
    async def guess_api(request: Request):
        uid=_uid(request)
        if not await rate_limiter.allow(f"termo:guess:{uid}",limit=10,window_seconds=15): return api_error("Aguarde antes de tentar novamente.",code="rate_limited",status_code=429)
        try: payload=await request.json()
        except Exception: payload={}
        try: game=submit_guess(uid,str(payload.get("session_token") or ""),str(payload.get("guess") or ""))
        except TermoInvalidGuess: return api_error("Essa palavra não está na lista do jogo.",code="invalid_word",status_code=400)
        except TermoDuplicateGuess: return api_error("Você já tentou essa palavra.",code="duplicate_guess",status_code=409)
        except TermoInvalidState: return api_error("Essa partida terminou ou expirou.",code="invalid_state",status_code=409)
        return api_ok(game=game)

    @app.post("/api/v2/termo/hint")
    async def hint_api(request: Request):
        uid=_uid(request)
        if not await rate_limiter.allow(f"termo:hint:{uid}",limit=4,window_seconds=60): return api_error("Aguarde antes de tentar novamente.",code="rate_limited",status_code=429)
        try: payload=await request.json()
        except Exception: payload={}
        try: result=buy_hint(uid,str(payload.get("session_token") or ""))
        except TermoHintAlreadyUsed: return api_error("A dica desta partida já foi usada.",code="hint_used",status_code=409)
        except TermoInsufficientCoins: return api_error(f"Você precisa de {HINT_COST_COINS} coins para a dica.",code="insufficient_coins",status_code=409)
        except TermoInvalidState: return api_error("Essa partida não está mais ativa.",code="invalid_state",status_code=409)
        return api_ok(**result)
