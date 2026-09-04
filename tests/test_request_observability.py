from __future__ import annotations

import asyncio
import io
import json
from contextlib import redirect_stdout

from utils.request_observability import (
    RequestObservabilityMiddleware,
    _log_event,
    normalize_request_id,
)


def test_request_id_accepts_safe_client_value() -> None:
    assert normalize_request_id("client_1234") == "client_1234"


def test_request_id_replaces_invalid_values() -> None:
    generated = normalize_request_id("bad value with spaces")
    assert generated.startswith("req_")
    assert len(generated) == 20


def test_structured_log_contains_only_operational_fields() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        _log_event(
            request_id="req_1234567890abcdef",
            method="POST",
            path="/api/dado/roll",
            status=401,
            duration_ms=12.345,
            error="TelegramWebAppAuthError",
        )

    payload = json.loads(output.getvalue())
    assert set(payload) == {
        "event",
        "request_id",
        "method",
        "path",
        "status",
        "duration_ms",
        "error",
    }
    assert payload["path"] == "/api/dado/roll"
    assert "user_id" not in payload
    assert "headers" not in payload
    assert "query" not in payload
    assert "body" not in payload


def test_middleware_returns_request_id_header() -> None:
    async def scenario() -> None:
        messages = []

        async def app(scope, receive, send):
            assert scope["state"]["request_id"] == "client_1234"
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        middleware = RequestObservabilityMiddleware(app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"x-request-id", b"client_1234")],
            "state": {},
        }
        await middleware(scope, receive, send)

        start = next(item for item in messages if item["type"] == "http.response.start")
        headers = dict(start["headers"])
        assert headers[b"x-request-id"] == b"client_1234"

    asyncio.run(scenario())
