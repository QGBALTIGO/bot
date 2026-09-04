from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from utils.channel_verification_bridge import wait_for_verification, worker_health

ResolveWebAppUser = Callable[..., dict[str, Any]]
RequireInternalSecret = Callable[[str], None]


def build_channel_router(
    *,
    resolve_webapp_user: ResolveWebAppUser,
    require_internal_api_secret: RequireInternalSecret,
    required_channel: str,
) -> APIRouter:
    """Cria as rotas de verificação com dependências explícitas.

    A autenticação ainda é fornecida pelo legado durante a migração. Isso evita
    copiar regras de identidade e permite extrair o helper em uma etapa separada.
    """

    router = APIRouter(tags=["channel"])

    @router.get("/api/channel/selftest")
    def api_channel_selftest(
        x_internal_api_secret: str = Header(default=""),
    ):
        require_internal_api_secret(x_internal_api_secret)
        health = worker_health()
        return JSONResponse(health, status_code=200 if health.get("ok") else 503)

    @router.post("/api/channel/check")
    def api_channel_check(
        payload: dict = Body(...),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        ctx = resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            x_webapp_uid=x_webapp_uid,
            body_uid=(payload or {}).get("uid"),
        )
        user_id = int(ctx["user_id"])

        if not required_channel:
            return {"ok": True}

        try:
            result = wait_for_verification(user_id, timeout_seconds=8.0)
        except Exception as exc:
            print(
                f"[terms-membership] bridge failed type={type(exc).__name__}",
                flush=True,
            )
            return JSONResponse(
                {"ok": False, "message": "Não foi possível iniciar a verificação agora."},
                status_code=502,
            )

        if result.get("ok"):
            return {"ok": True}

        status = str(result.get("status") or "")
        if status == "not_member":
            return JSONResponse(
                {"ok": False, "message": "Você ainda não está no canal obrigatório."},
                status_code=403,
            )

        return JSONResponse(
            {"ok": False, "message": str(result.get("message") or "Falha na verificação.")},
            status_code=503 if status == "timeout" else 502,
        )

    return router
