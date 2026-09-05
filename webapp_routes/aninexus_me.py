from __future__ import annotations

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from database import get_dado_state, get_user_level_rank
from database_aninexus_pets import get_active_pet, get_user_eggs, get_user_pets
from level_system import get_rank_tag
from utils.aninexus_admin import is_admin, is_owner
from webapp_routes.aninexus_compat import (
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

        pets = get_user_pets(user_id)
        active_pet = get_active_pet(user_id)
        eggs = get_user_eggs(user_id)
        active_incubations = sum(
            1 for egg in eggs if str(egg.get("status") or "") == "incubating"
        )

        admin = is_admin(user_id)
        owner = is_owner(user_id)
        payload["is_sudo"] = False  # Staff/raridades só será exposto quando o backend próprio estiver pronto.
        payload["is_staff"] = admin
        payload["can_upload"] = admin
        payload["can_edit_character"] = admin
        if owner:
            payload["role"] = "owner"
            payload["role_label"] = "Fundador"
            payload["role_tag"] = "OWNER"
            payload["role_symbol"] = "◆"
        elif admin:
            payload["role"] = "admin"
            payload["role_label"] = "Administrador"
            payload["role_tag"] = "ADMIN"
            payload["role_symbol"] = "◇"

        # O frontend herdado ainda chama o segundo recurso de `zenith`
        # internamente. No AniNexus esse campo representa Dados, nunca uma
        # segunda moeda.
        payload["zenith"] = dado_balance
        payload["titles"] = {
            "current": get_rank_tag(level),
            "all": [get_rank_tag(level)],
        }
        payload["pets"] = pets
        payload["current_pet"] = active_pet
        payload["eggs"] = eggs

        stats["points"] = int(payload.get("balance") or 0)
        stats["zenith"] = dado_balance
        stats["rank"] = int(get_user_level_rank(user_id) or 0)
        stats["pass_type"] = "free"
        stats["incubation_slots"] = 1
        stats["active_incubations"] = active_incubations
        payload["stats"] = stats
        return JSONResponse(payload)

    router.add_api_route("/me", me, methods=["GET"])
    return router
