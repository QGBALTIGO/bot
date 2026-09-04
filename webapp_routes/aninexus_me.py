from __future__ import annotations

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from database import get_dado_state, get_user_level_rank
from level_system import get_rank_tag
from webapp_routes.seal_compat import (
    API_PREFIX,
    _require_user,
    _unauthorized,
    _user_payload,
)


def build_aninexus_me_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-profile"])

    def me(authorization: str = Header(default="")):
        try:
            session_user = _require_user(authorization)
        except PermissionError as exc:
            return _unauthorized(str(exc))

        user_id = int(session_user.get("id") or 0)
        payload = _user_payload(session_user)
        stats = dict(payload.get("stats") or {})
        dado_state = get_dado_state(user_id) or {}
        dado_balance = int(dado_state.get("balance") or 0)
        level = int(stats.get("level") or 1)

        payload["zenith"] = dado_balance
        payload["titles"] = {
            "current": get_rank_tag(level),
            "all": [get_rank_tag(level)],
        }
        stats["points"] = int(payload.get("balance") or 0)
        stats["zenith"] = dado_balance
        stats["rank"] = int(get_user_level_rank(user_id) or 0)
        stats["pass_type"] = "free"
        payload["stats"] = stats
        return JSONResponse(payload)

    router.add_api_route("/me", me, methods=["GET"])
    return router
