from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from typing import Any, Dict

import httpx

from utils.image_proxy import ImageProxyError, MAX_IMAGE_BYTES, fetch_public_image
from utils.portrait_image import PortraitCropError, crop_portrait_bytes

CATBOX_UPLOAD_URL = "https://catbox.moe/user/api.php"


@dataclass(frozen=True)
class AniNexusMediaError(Exception):
    code: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.code


def decode_image_data_uri(raw: str) -> bytes:
    value = str(raw or "").strip()
    if not value.startswith("data:image/") or ";base64," not in value:
        raise AniNexusMediaError("invalid_image_data", 400)
    header, encoded = value.split(",", 1)
    media_type = header[5:].split(";", 1)[0].strip().lower()
    if media_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise AniNexusMediaError("unsupported_image_type", 415)
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AniNexusMediaError("invalid_image_data", 400) from exc
    if not content:
        raise AniNexusMediaError("invalid_image_data", 400)
    if len(content) > MAX_IMAGE_BYTES:
        raise AniNexusMediaError("image_too_large", 413)
    return content


async def load_source_image(*, media_url: str = "", media_data: str = "") -> tuple[bytes, str, str]:
    url = str(media_url or "").strip()
    data = str(media_data or "").strip()
    if bool(url) == bool(data):
        raise AniNexusMediaError("provide_one_image_source", 400)

    if data:
        return decode_image_data_uri(data), "image/jpeg", ""

    try:
        content, media_type, final_url = await fetch_public_image(url)
        return content, media_type, final_url
    except ImageProxyError as exc:
        raise AniNexusMediaError(str(exc), int(exc.status_code)) from exc


def make_portrait_asset(content: bytes) -> tuple[bytes, Dict[str, Any], str]:
    try:
        output, metadata = crop_portrait_bytes(content)
    except PortraitCropError as exc:
        raise AniNexusMediaError(str(exc), 422) from exc

    sha256 = hashlib.sha256(output).hexdigest()
    return output, dict(metadata), sha256


async def upload_portrait_asset(content: bytes, *, filename: str = "aninexus-character.jpg") -> str:
    if not content:
        raise AniNexusMediaError("empty_image", 400)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(35.0, connect=10.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                CATBOX_UPLOAD_URL,
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (filename, content, "image/jpeg")},
            )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
        raise AniNexusMediaError("media_storage_unavailable", 502) from exc

    if response.status_code != 200:
        raise AniNexusMediaError("media_storage_unavailable", 502)
    url = response.text.strip()
    if not url.startswith("https://"):
        raise AniNexusMediaError("media_storage_invalid_response", 502)
    return url
