from __future__ import annotations

import hashlib
import io
import os
from collections import OrderedDict
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from PIL import Image, ImageOps

from utils.image_proxy import fetch_public_image
from utils.portrait_image import PortraitCropError, crop_portrait_bytes
from utils.public_character_image import is_own_image_proxy_url


_FILE_ID_CACHE_SIZE = max(16, int(os.getenv("TELEGRAM_PHOTO_FILE_CACHE_SIZE", "512")))
_FILE_ID_CACHE: OrderedDict[str, str] = OrderedDict()

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def _source_url(image_url: str) -> tuple[str, bool]:
    """Avoid a slow self-request when the stored URL points at our image proxy."""
    value = str(image_url or "").strip()
    if not is_own_image_proxy_url(value):
        return value, False

    params = parse_qs(urlparse(value).query)
    source = str((params.get("url") or [""])[0]).strip()
    if not source.startswith(("http://", "https://")):
        return value, False
    return source, str((params.get("crop") or [""])[0]).strip().lower() == "portrait"


def _request_headers(url: str) -> dict[str, str]:
    headers = dict(_BROWSER_HEADERS)
    hostname = (urlparse(str(url or "")).hostname or "").lower()
    if hostname.endswith("donmai.us"):
        headers["Referer"] = "https://danbooru.donmai.us/"
    elif hostname.endswith("zerochan.net"):
        headers["Referer"] = "https://www.zerochan.net/"
    elif hostname.endswith("wallhaven.cc"):
        headers["Referer"] = "https://wallhaven.cc/"
    return headers


def _jpeg_bytes(content: bytes, *, portrait_crop: bool) -> bytes:
    if portrait_crop:
        try:
            cropped, _metadata = crop_portrait_bytes(content)
            return cropped
        except PortraitCropError:
            # Older overrides may not satisfy the new portrait-shape rules.
            # Preserve them instead of making the /card command fail.
            pass

    with Image.open(io.BytesIO(content)) as source:
        if getattr(source, "is_animated", False):
            source.seek(0)
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
        return output.getvalue()


def _cache_get(image_url: str) -> str | None:
    file_id = _FILE_ID_CACHE.pop(image_url, None)
    if file_id:
        _FILE_ID_CACHE[image_url] = file_id
    return file_id


def _cache_put(image_url: str, file_id: str) -> None:
    if not image_url or not file_id:
        return
    _FILE_ID_CACHE.pop(image_url, None)
    _FILE_ID_CACHE[image_url] = file_id
    while len(_FILE_ID_CACHE) > _FILE_ID_CACHE_SIZE:
        _FILE_ID_CACHE.popitem(last=False)


async def reply_photo_from_url(message: Any, image_url: str, **kwargs: Any) -> Any:
    """Send a remote image reliably by uploading bytes, then reuse Telegram's file_id."""
    value = str(image_url or "").strip()
    if not value:
        raise ValueError("empty_image_url")

    cached_file_id = _cache_get(value)
    if cached_file_id:
        try:
            return await message.reply_photo(photo=cached_file_id, **kwargs)
        except Exception:
            _FILE_ID_CACHE.pop(value, None)

    source_url, portrait_crop = _source_url(value)
    content, _media_type, _final_url = await fetch_public_image(
        source_url,
        headers=_request_headers(source_url),
        timeout=httpx.Timeout(45.0, connect=10.0),
    )
    prepared = _jpeg_bytes(content, portrait_crop=portrait_crop)
    stream = io.BytesIO(prepared)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    stream.name = f"card-{digest}.jpg"

    sent = await message.reply_photo(photo=stream, **kwargs)
    photos = list(getattr(sent, "photo", None) or [])
    if photos:
        _cache_put(value, str(photos[-1].file_id))
    return sent

