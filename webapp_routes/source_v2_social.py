from __future__ import annotations

import asyncio

from fastapi import APIRouter, Header, HTTPException, Query, WebSocket, WebSocketDisconnect

from source_v2_social import leaderboard, list_referrals, referral_stats
from utils.source_v2_auth import resolve_source_v2_identity
from utils.webapp_session import WebAppSessionError, validate_session_token


router = APIRouter(prefix="/api/v1_7b82", tags=["source-v2-social"])


@router.get("/social/referrals")
def referrals(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    identity = resolve_source_v2_identity(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        authorization=authorization,
    )
    return list_referrals(int(identity["user_id"]))


@router.get("/social/referrals/stats")
def referrals_stats(
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
    authorization: str = Header(default=""),
):
    identity = resolve_source_v2_identity(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        authorization=authorization,
    )
    return referral_stats(int(identity["user_id"]))


@router.get("/leaderboard")
def leaderboard_route(
    metric: str = Query(default="harem"),
    limit: int = Query(default=500, ge=1, le=500),
):
    try:
        return leaderboard(metric, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "invalid_metric") from exc


def _websocket_session_token(websocket: WebSocket) -> tuple[str, str]:
    raw = str(websocket.headers.get("sec-websocket-protocol") or "")
    for protocol in [part.strip() for part in raw.split(",") if part.strip()]:
        if protocol.startswith("source-token."):
            return protocol, protocol[len("source-token."):]
    return "", ""


@router.websocket("/ws/leaderboard")
async def leaderboard_ws(websocket: WebSocket):
    protocol, token = _websocket_session_token(websocket)
    if not token:
        await websocket.close(code=4401)
        return
    try:
        validate_session_token(token)
    except WebAppSessionError:
        await websocket.close(code=4401)
        return

    await websocket.accept(subprotocol=protocol)
    try:
        # Until Redis leaderboard broadcasts are wired into the Source v2 domain,
        # emit a periodic refresh event. The UI gets the same realtime contract and
        # performs a cheap cached refetch every 30 seconds.
        await websocket.send_json({"type": "leaderboard_update", "source": "initial"})
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "leaderboard_update", "source": "poll"})
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
