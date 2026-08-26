from __future__ import annotations

import os


def _normalize(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def get_public_base_url() -> str:
    """Resolve the public Mini App origin.

    Keep BASE_URL authoritative for compatibility with the production bot's
    previously working Telegram WebApp setup. Railway's generated public domain
    is only a fallback when BASE_URL is not configured at all.
    """
    configured = _normalize(os.getenv("BASE_URL", ""))
    if configured:
        return configured
    return _normalize(os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))


def require_public_base_url() -> str:
    value = get_public_base_url()
    if not value:
        raise RuntimeError(
            "URL pública não configurada. Defina BASE_URL ou disponibilize RAILWAY_PUBLIC_DOMAIN."
        )
    return value
