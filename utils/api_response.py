from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def api_response(payload: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(payload), status_code=int(status_code))


def api_ok(**payload: Any) -> JSONResponse:
    return api_response({"ok": True, **payload})


def api_error(message: str, *, code: str = "request_failed", status_code: int = 400, **extra: Any) -> JSONResponse:
    return api_response({"ok": False, "code": str(code), "message": str(message), **extra}, status_code=status_code)
