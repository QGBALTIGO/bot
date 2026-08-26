from __future__ import annotations

import os
from urllib.parse import urlparse


def _normalize(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def _is_railway_host(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host.endswith(".railway.app") or host.endswith(".up.railway.app")


def get_public_base_url() -> str:
    """Resolve one canonical public origin for every Telegram Mini App.

    Railway exposes RAILWAY_PUBLIC_DOMAIN for the current service. If BASE_URL is
    empty, or if BASE_URL itself points to an old Railway-generated host, prefer
    the current Railway domain so redeploys/branch switches don't keep sending
    Telegram users to a stale deployment. Explicit custom domains still win.
    """
    configured = _normalize(os.getenv("BASE_URL", ""))
    railway_domain = _normalize(os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))

    if railway_domain and (not configured or _is_railway_host(configured)):
        return railway_domain
    return configured or railway_domain


def require_public_base_url() -> str:
    value = get_public_base_url()
    if not value:
        raise RuntimeError(
            "URL pública não configurada. Defina BASE_URL ou disponibilize RAILWAY_PUBLIC_DOMAIN."
        )
    return value
