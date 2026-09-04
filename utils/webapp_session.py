from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any


DEFAULT_SESSION_TTL_SECONDS = max(900, int(os.getenv("WEBAPP_SESSION_TTL_SECONDS", "43200")))
MAX_SESSION_TTL_SECONDS = max(DEFAULT_SESSION_TTL_SECONDS, int(os.getenv("WEBAPP_SESSION_MAX_TTL_SECONDS", "86400")))
MAX_FUTURE_SKEW_SECONDS = max(0, int(os.getenv("WEBAPP_SESSION_FUTURE_SKEW_SECONDS", "120")))


class WebAppSessionError(ValueError):
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    raw = str(value or "").strip()
    if not raw:
        raise WebAppSessionError("session_invalid")
    raw += "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as exc:
        raise WebAppSessionError("session_invalid") from exc


def _session_secret() -> bytes:
    # A dedicated secret is preferred. BOT_TOKEN fallback keeps current deployments
    # working and intentionally invalidates sessions after a BotFather token rotation.
    raw = str(os.getenv("WEBAPP_SESSION_SECRET") or os.getenv("BOT_TOKEN") or "").strip()
    if not raw:
        raise WebAppSessionError("session_secret_missing")
    return hmac.new(b"SourceBaltigoWebAppSession/v1", raw.encode("utf-8"), hashlib.sha256).digest()


def create_session_token(
    user_id: int,
    *,
    now: int | None = None,
    ttl_seconds: int | None = None,
) -> str:
    uid = int(user_id or 0)
    if uid <= 0:
        raise WebAppSessionError("session_user_invalid")

    issued_at = int(time.time() if now is None else now)
    ttl = DEFAULT_SESSION_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds)
    ttl = min(MAX_SESSION_TTL_SECONDS, max(60, ttl))
    payload = {
        "v": 1,
        "uid": uid,
        "iat": issued_at,
        "exp": issued_at + ttl,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = _b64url_encode(payload_bytes)
    signature = hmac.new(_session_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64url_encode(signature)}"


def validate_session_token(token: str, *, now: int | None = None) -> dict[str, Any]:
    raw = str(token or "").strip()
    if len(raw) > 4096:
        raise WebAppSessionError("session_invalid")
    try:
        encoded_payload, encoded_signature = raw.split(".", 1)
    except ValueError as exc:
        raise WebAppSessionError("session_invalid") from exc

    received_signature = _b64url_decode(encoded_signature)
    expected_signature = hmac.new(
        _session_secret(),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(received_signature, expected_signature):
        raise WebAppSessionError("session_signature_invalid")

    try:
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except Exception as exc:
        raise WebAppSessionError("session_invalid") from exc
    if not isinstance(payload, dict) or int(payload.get("v") or 0) != 1:
        raise WebAppSessionError("session_invalid")

    try:
        uid = int(payload.get("uid") or 0)
        issued_at = int(payload.get("iat") or 0)
        expires_at = int(payload.get("exp") or 0)
    except (TypeError, ValueError) as exc:
        raise WebAppSessionError("session_invalid") from exc
    if uid <= 0 or issued_at <= 0 or expires_at <= issued_at:
        raise WebAppSessionError("session_invalid")

    current = int(time.time() if now is None else now)
    if issued_at > current + MAX_FUTURE_SKEW_SECONDS:
        raise WebAppSessionError("session_future")
    if expires_at <= current:
        raise WebAppSessionError("session_expired")
    if expires_at - issued_at > MAX_SESSION_TTL_SECONDS:
        raise WebAppSessionError("session_invalid")

    return {
        "user_id": uid,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "version": 1,
    }


def bearer_token(authorization: str) -> str:
    value = str(authorization or "").strip()
    if not value:
        return ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()
