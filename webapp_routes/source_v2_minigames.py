from __future__ import annotations

from fastapi import APIRouter, Body, Header, HTTPException

from source_v2_minigames import get_minigame_state, start_minigame, submit_minigame
from utils.source_v2_auth import resolve_source_v2_identity


router = APIRouter(prefix="/api/v1_7b82", tags=["source-v2-minigames"])


def _user_id(init_data: str, webapp_uid: str, authorization: str) -> int:
    identity = resolve_source_v2_identity(
        x_telegram_init_data=init_data,
        x_webapp_uid=webapp_uid,
        authorization=authorization,
    )
    return int(identity["user_id"])


@router.get("/minigames/state")
def minigames_state(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    return get_minigame_state(_user_id(x_telegram_init_data, x_webapp_uid, authorization))


@router.post("/minigames/start/{game_type}")
def minigames_start(
    game_type: str,
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    user_id = _user_id(x_telegram_init_data, x_webapp_uid, authorization)
    try:
        session = start_minigame(user_id, game_type)
    except ValueError as exc:
        code = str(exc) or "minigame_start_failed"
        status = 400 if code in {"invalid_game_type", "not_enough_energy"} else 409
        raise HTTPException(status_code=status, detail=code) from exc
    return {"status": "success", "session": session}


@router.post("/minigames/submit")
def minigames_submit(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    user_id = _user_id(x_telegram_init_data, x_webapp_uid, authorization)
    game_type = str(payload.get("game_type") or "")
    try:
        score = int(payload.get("score") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid_score") from exc

    try:
        rewards = submit_minigame(user_id, game_type, score)
    except ValueError as exc:
        code = str(exc) or "minigame_submit_failed"
        status = 403 if code in {"no_active_session", "session_expired", "suspicious_activity"} else 400
        raise HTTPException(status_code=status, detail=code) from exc
    return {"status": "success", "rewards": rewards}
