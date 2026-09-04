from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlparse

from utils.public_character_image import is_own_image_proxy_url

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
    if is_own_image_proxy_url(value):
        return value

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return value

    host = (parsed.hostname or "").strip().lower()
    if host in DIRECT_IMAGE_HOSTS:
        return value

    encoded = quote(value, safe="")
    if host == "w.wallhaven.cc":
        return f"/api/image-proxy?crop=portrait&url={encoded}"
    return f"/api/image-proxy?url={encoded}"
