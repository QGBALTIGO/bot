from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
_REQUEST_ID_HEADER = b"x-request-id"


def normalize_request_id(value: str | None) -> str:
    candidate = str(value or "").strip()
    if candidate and _REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return f"req_{uuid.uuid4().hex[:16]}"


def _request_header(scope: dict[str, Any], name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if bytes(key).lower() == name:
            try:
                return bytes(value).decode("utf-8", errors="ignore")
            except Exception:
                return ""
    return ""


def _log_event(
    *,
    request_id: str,
    method: str,
    path: str,
    status: int,
    duration_ms: float,
    error: str = "",
) -> None:
    payload: dict[str, Any] = {
        "event": "http_request",
        "request_id": request_id,
        "method": method,
        "path": path,
        "status": int(status),
        "duration_ms": round(float(duration_ms), 2),
    }
    if error:
        payload["error"] = error
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


class RequestObservabilityMiddleware:
    """Add request correlation without logging private Telegram request data.

    The middleware intentionally logs only method, route path, status, duration and
    a request ID. Query strings, headers, request bodies, Telegram initData, IPs and
    user identifiers are never included.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = normalize_request_id(
            _request_header(scope, _REQUEST_ID_HEADER)
        )
        method = str(scope.get("method") or "UNKNOWN").upper()
        path = str(scope.get("path") or "/")
        started = time.perf_counter()
        status_code = 500

        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["request_id"] = request_id

        async def send_with_request_id(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 500)
                headers = list(message.get("headers") or [])
                if not any(bytes(key).lower() == _REQUEST_ID_HEADER for key, _ in headers):
                    headers.append((_REQUEST_ID_HEADER, request_id.encode("ascii")))
                message = dict(message)
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            _log_event(
                request_id=request_id,
                method=method,
                path=path,
                status=500,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=type(exc).__name__,
            )
            raise

        if path != "/health" or status_code >= 400:
            _log_event(
                request_id=request_id,
                method=method,
                path=path,
                status=status_code,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
