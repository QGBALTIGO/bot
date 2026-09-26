from __future__ import annotations

import hashlib
import hmac
import os
import time


class CollectionShareError(ValueError):
    pass


def _secret(explicit: str = "") -> bytes:
    value = (explicit or os.getenv("SOURCE_COLLECTION_SHARE_SECRET") or os.getenv("BOT_TOKEN") or "").strip()
    if not value:
        raise RuntimeError("SOURCE_COLLECTION_SHARE_SECRET (or BOT_TOKEN) is required")
    return value.encode("utf-8")


def create_collection_share_token(user_id: int, *, ttl_seconds: int = 7 * 24 * 3600, now: int | None = None, secret: str = "") -> str:
    uid = int(user_id)
    if uid <= 0:
        raise CollectionShareError("invalid_user")
    issued = int(time.time() if now is None else now)
    expires = issued + max(300, min(int(ttl_seconds), 30 * 24 * 3600))
    payload = f"{uid}.{expires}"
    signature = hmac.new(_secret(secret), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_collection_share_token(token: str, *, now: int | None = None, secret: str = "") -> int:
    raw = str(token or "").strip()
    parts = raw.split(".")
    if len(parts) != 3:
        raise CollectionShareError("invalid_token")
    uid_raw, expires_raw, signature = parts
    if not uid_raw.isdecimal() or not expires_raw.isdecimal():
        raise CollectionShareError("invalid_token")
    uid, expires = int(uid_raw), int(expires_raw)
    if uid <= 0:
        raise CollectionShareError("invalid_token")
    payload = f"{uid}.{expires}"
    expected = hmac.new(_secret(secret), payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise CollectionShareError("invalid_signature")
    current = int(time.time() if now is None else now)
    if expires < current:
        raise CollectionShareError("expired")
    return uid
