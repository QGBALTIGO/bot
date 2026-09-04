from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from utils.system_health import public_health_snapshot

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
@router.get("/api/health")
def source_health():
    payload = public_health_snapshot()
    return JSONResponse(
        payload,
        status_code=200 if payload.get("ok") else 503,
        headers={"Cache-Control": "no-store"},
    )
