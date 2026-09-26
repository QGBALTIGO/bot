from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from database_aninexus_games import (
    get_game_energy,
    start_game_session,
    submit_game_session,
)
from webapp_routes.aninexus_compat import API_PREFIX, _require_user, _unauthorized
from source_features.termo_web import termo_guess, termo_start, termo_state


def _error(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
    )


def _auth(authorization: str) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        return _require_user(authorization), None
    except PermissionError as exc:
        return None, _unauthorized(str(exc))


def build_aninexus_games_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-games"])

    def state(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        return JSONResponse(get_game_energy(int(session_user.get("id") or 0)))

    def start(game_type: str, authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        result = start_game_session(int(session_user.get("id") or 0), game_type)
        if result.get("ok"):
            return JSONResponse(
                {
                    "status": "success",
                    "session": result.get("session") or {},
                    "reused": bool(result.get("reused")),
                }
            )

        code = str(result.get("error") or "game_start_failed")
        messages = {
            "invalid_game": "Jogo inválido.",
            "not_enough_energy": "Você está sem energia. Aguarde a próxima recarga.",
            "game_data_unavailable": "Não foi possível preparar esta partida agora.",
        }
        return _error(code, messages.get(code, "Não foi possível iniciar a partida."))

    def submit(
        payload: dict = Body(default={}),
        authorization: str = Header(default=""),
    ):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None

        game_type = str((payload or {}).get("game_type") or "").strip().lower()
        session_id = str((payload or {}).get("session_id") or "").strip()
        try:
            score = max(0, min(8, int((payload or {}).get("score") or 0)))
        except (TypeError, ValueError):
            score = 0

        result = submit_game_session(
            int(session_user.get("id") or 0),
            game_type,
            session_id,
            score,
        )
        if result.get("ok"):
            return JSONResponse(
                {
                    "status": "success",
                    "already_done": bool(result.get("already_done")),
                    "rewards": result.get("rewards") or {},
                }
            )

        code = str(result.get("error") or "game_submit_failed")
        messages = {
            "invalid_session": "Sessão inválida. Inicie uma nova partida.",
            "session_not_found": "Essa partida não existe mais.",
            "session_not_active": "Essa partida já foi encerrada.",
            "session_expired": "A partida expirou. Inicie uma nova.",
            "suspicious_activity": "A partida foi concluída rápido demais para ser validada.",
            "insufficient_score": "Você precisa encontrar pelo menos 4 pares para receber XP.",
            "character_unavailable": "Não foi possível selecionar o personagem da recompensa.",
            "invalid_prize": "A recompensa desta partida ficou inválida.",
        }
        return _error(code, messages.get(code, "Não foi possível validar a recompensa."))

    def termo_state_route(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        return JSONResponse(termo_state(int(session_user.get("id") or 0)))

    def termo_start_route(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        return JSONResponse(termo_start(int(session_user.get("id") or 0)))

    def termo_guess_route(payload: dict = Body(default={}), authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        result = termo_guess(int(session_user.get("id") or 0), str((payload or {}).get("guess") or ""))
        if result.get("ok"):
            return JSONResponse(result)
        messages = {
            "invalid_word": "Palavra inválida para o Termo Anime.",
            "not_started": "Inicie a partida antes de enviar uma palavra.",
            "already_guessed": "Essa palavra já foi usada nesta partida.",
        }
        code = str(result.get("error") or "termo_failed")
        return _error(code, messages.get(code, "Não foi possível registrar a tentativa."), 409)

    router.add_api_route("/termo/state", termo_state_route, methods=["GET"])
    router.add_api_route("/termo/start", termo_start_route, methods=["POST"])
    router.add_api_route("/termo/guess", termo_guess_route, methods=["POST"])
    router.add_api_route("/minigames/state", state, methods=["GET"])
    router.add_api_route("/minigames/start/{game_type}", start, methods=["POST"])
    router.add_api_route("/minigames/submit", submit, methods=["POST"])
    return router
