import io

import pytest
from PIL import Image

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


def test_image_proxy_error_accepts_traceback_assignment():
    error = ImageProxyError("image_source_unavailable", 502)
    error.__traceback__ = None
    assert str(error) == "image_source_unavailable"
