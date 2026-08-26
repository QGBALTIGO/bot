from __future__ import annotations

import os
from urllib.parse import quote, urlparse


def _normalize_origin(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw.rstrip("/")


def _is_railway_generated(origin: str) -> bool:
    try:
        host = (urlparse(origin).hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return host.endswith(".railway.app") or host.endswith(".up.railway.app")


def public_origin() -> str:
    configured = _normalize_origin(os.getenv("BASE_URL", ""))
    railway = _normalize_origin(os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))

    # A custom domain remains authoritative. When BASE_URL is just an old
    # Railway-generated hostname, prefer the domain injected by the service
    # that is actually running this process.
    if railway and (not configured or _is_railway_generated(configured)):
        return railway
    return configured or railway


def is_wallhaven_asset(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
        host = (parsed.hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return parsed.scheme == "https" and host == "w.wallhaven.cc"


def character_portrait_url(source_url: str) -> str:
    source = str(source_url or "").strip()
    if not source or not is_wallhaven_asset(source):
        return source

    origin = public_origin()
    if not origin:
        return source

    return f"{origin}/api/image-proxy?crop=portrait&url={quote(source, safe='')}"


def is_own_image_proxy_url(url: str) -> bool:
    value = str(url or "").strip()
    if not value:
        return False
    origin = public_origin()
    if not origin:
        return False

    try:
        parsed = urlparse(value)
        expected = urlparse(origin)
    except Exception:
        return False

    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname == expected.hostname
        and (parsed.port or (443 if parsed.scheme == "https" else 80))
        == (expected.port or (443 if expected.scheme == "https" else 80))
        and parsed.path == "/api/image-proxy"
    )
