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
        host = (urlparse(url).hostname or "").strip().lower()
    except Exception:
        return False
    return host.endswith(".railway.app") or host.endswith(".up.railway.app")


def get_public_base_url() -> str:
    """Resolve the canonical public origin used by Telegram Mini Apps.

    A custom BASE_URL remains authoritative. For Railway-generated hosts, the
    domain injected by the *currently running service* wins so an old BASE_URL
    cannot keep Telegram buttons pointed at a detached Railway domain.
    """
    configured = _normalize(os.getenv("BASE_URL", ""))
    railway_domain = _normalize(os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))

    if railway_domain and (not configured or _is_railway_host(configured)):
        return railway_domain
    return configured or railway_domain


def public_url_diagnostics() -> dict[str, str | bool]:
    configured = _normalize(os.getenv("BASE_URL", ""))
    railway_domain = _normalize(os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
    resolved = get_public_base_url()
    return {
        "configured": configured,
        "railway": railway_domain,
        "resolved": resolved,
        "configured_is_railway": _is_railway_host(configured) if configured else False,
    }


def require_public_base_url() -> str:
    value = get_public_base_url()
    if not value:
        raise RuntimeError(
            "URL pública não configurada. Defina BASE_URL ou disponibilize RAILWAY_PUBLIC_DOMAIN."
        )
    return value
