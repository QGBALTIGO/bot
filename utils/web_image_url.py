from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, quote, urlparse

DIRECT_IMAGE_HOSTS = frozenset({
    "s4.anilist.co",
    "img.anili.st",
})


def web_image_url(url: Any) -> str:
    """Retorna uma URL segura/compatível para imagens exibidas pela WebApp."""

    value = str(url or "").strip()
    if not value:
        return ""

    if value.startswith(("data:", "/api/image-proxy?")):
        return value

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return value

    # Approved images may retain an absolute URL from an older Railway proxy.
    # Rebuild it against the WebApp's current proxy instead of returning a stale host.
    if parsed.scheme == "https" and parsed.path == "/api/image-proxy":
        params = parse_qs(parsed.query)
        source = str((params.get("url") or [""])[0]).strip()
        if source.startswith(("http://", "https://")):
            crop = str((params.get("crop") or [""])[0]).strip().lower()
            crop_arg = "crop=portrait&" if crop == "portrait" else ""
            return f"/api/image-proxy?{crop_arg}url={quote(source, safe='')}"

    host = (parsed.hostname or "").strip().lower()
    if host in DIRECT_IMAGE_HOSTS:
        return value

    encoded = quote(value, safe="")
    if host == "w.wallhaven.cc":
        return f"/api/image-proxy?crop=portrait&url={encoded}"
    return f"/api/image-proxy?url={encoded}"
