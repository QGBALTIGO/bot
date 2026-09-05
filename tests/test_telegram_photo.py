import io

import pytest
from PIL import Image

from utils import image_proxy
from utils import telegram_photo
from utils.image_proxy import ImageProxyError


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (600, 900), "navy").save(output, format="JPEG")
    return output.getvalue()


class _Photo:
    file_id = "telegram-file-id"


class _Sent:
    photo = [_Photo()]


class _Message:
    def __init__(self):
        self.photos = []

    async def reply_photo(self, *, photo, **kwargs):
        self.photos.append(photo)
        return _Sent()


@pytest.mark.asyncio
async def test_remote_photo_is_uploaded_once_then_reuses_telegram_file_id(monkeypatch):
    calls = 0

    async def fake_fetch(url, **kwargs):
        nonlocal calls
        calls += 1
        return _jpeg(), "image/jpeg", url

    monkeypatch.setattr(telegram_photo, "fetch_public_image", fake_fetch)
    telegram_photo._FILE_ID_CACHE.clear()
    message = _Message()
    url = "https://images.example/card.jpg"

    await telegram_photo.reply_photo_from_url(message, url, caption="card")
    await telegram_photo.reply_photo_from_url(message, url, caption="card")

    assert calls == 1
    assert isinstance(message.photos[0], io.BytesIO)
    assert message.photos[1] == "telegram-file-id"


@pytest.mark.asyncio
async def test_urlopen_fallback_recovers_a_source_rejected_by_httpx(monkeypatch):
    async def rejected_fetch(url, **kwargs):
        raise ImageProxyError("image_source_unavailable", 502)

    async def compatible_fetch(url, **kwargs):
        try:
            return await rejected_fetch(url, **kwargs)
        except ImageProxyError:
            return _jpeg(), "image/jpeg", url

    monkeypatch.setattr(telegram_photo, "fetch_compatible_public_image", compatible_fetch)
    telegram_photo._FILE_ID_CACHE.clear()
    message = _Message()

    await telegram_photo.reply_photo_from_url(
        message,
        "https://cdn.donmai.us/approved.jpg",
        caption="card",
    )

    assert isinstance(message.photos[0], io.BytesIO)


def test_image_proxy_error_accepts_traceback_assignment():
    error = ImageProxyError("image_source_unavailable", 502)
    error.__traceback__ = None
    assert str(error) == "image_source_unavailable"


def test_stale_public_proxy_is_unwrapped_and_keeps_portrait_crop():
    stored = (
        "https://old-bot.up.railway.app/api/image-proxy?crop=portrait&"
        "url=https%3A%2F%2Fcdn.example%2Fapproved.jpg"
    )
    assert telegram_photo._source_url(stored) == (
        "https://cdn.example/approved.jpg",
        True,
    )


@pytest.mark.asyncio
async def test_compatible_fetch_uses_urlopen_after_safe_httpx_rejection(monkeypatch):
    async def rejected_fetch(url, **kwargs):
        raise ImageProxyError("image_source_unavailable", 502)

    monkeypatch.setattr(image_proxy, "fetch_public_image", rejected_fetch)
    monkeypatch.setattr(
        image_proxy,
        "_urlopen_public_image",
        lambda url, headers: (_jpeg(), "image/jpeg", url),
    )

    content, media_type, final_url = await image_proxy.fetch_compatible_public_image(
        "https://cdn.donmai.us/approved.jpg"
    )

    assert content == _jpeg()
    assert media_type == "image/jpeg"
    assert final_url.endswith("approved.jpg")
