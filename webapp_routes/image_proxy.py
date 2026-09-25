from __future__ import annotations

import os
import asyncio
import time
from collections import OrderedDict
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from utils.image_proxy import ImageProxyError, fetch_compatible_public_image
from utils.portrait_image import PortraitCropError, crop_portrait_bytes

router = APIRouter(tags=["images"])

IMAGE_PROXY_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


async def _load_image_proxy(
    url: str = Query(..., min_length=8, max_length=2000),
    crop: str = Query("", max_length=20),
):
    """Proxy público de imagens com validação SSRF e crop opcional 2:3."""

    crop_mode = str(crop or "").strip().lower()
    if crop_mode not in {"", "portrait"}:
        raise HTTPException(status_code=400, detail="invalid_crop_mode")
    target = str(url or "").strip()
    try:
        parsed = urlparse(target)
    except ValueError as exc:
        raise HTTPException(400, "invalid_image_url") from exc
    hostname = (parsed.hostname or "").strip().lower()

    headers = {
        "User-Agent": IMAGE_PROXY_USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    if hostname.endswith("donmai.us"):
        headers["User-Agent"] = f"SourceBaltigo-Curation - {os.getenv('ZEROCHAN_USER', 'kaykys468')}"
        headers["Referer"] = "https://danbooru.donmai.us/"
    elif hostname.endswith("zerochan.net"):
        headers["User-Agent"] = f"SourceBaltigo-Curation - {os.getenv('ZEROCHAN_USER', 'kaykys468')}"
        headers["Referer"] = "https://www.zerochan.net/"

    try:
        content, media_type, _ = await fetch_compatible_public_image(
            target,
            headers=headers,
            timeout=httpx.Timeout(20.0, connect=10.0),
        )
    except ImageProxyError as exc:
        print(
            f"[image-proxy] rejected host={hostname or '-'} code={exc.code}",
            flush=True,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except Exception as exc:
        print(
            f"[image-proxy] fetch-failed host={hostname or '-'} error={type(exc).__name__}",
            flush=True,
        )
        raise HTTPException(status_code=502, detail="image_fetch_failed") from exc

    crop_mode = str(crop or "").strip().lower()
    if crop_mode not in {"", "portrait"}:
        raise HTTPException(status_code=400, detail="invalid_crop_mode")

    applied_crop = False
    if crop_mode == "portrait":
        try:
            content, _crop_meta = await asyncio.to_thread(crop_portrait_bytes, content)
            media_type = "image/jpeg"
            applied_crop = True
        except PortraitCropError as exc:
            print(
                f"[image-proxy] portrait-crop-failed host={hostname or '-'} code={exc}",
                flush=True,
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=604800, stale-while-revalidate=86400",
            "Access-Control-Allow-Origin": "*",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "X-Image-Crop": "2:3" if applied_crop else "original",
        },
    )


# Public bytes only: no user/session data. Max 16 MiB per process; no failures cached.
_IMAGE_CACHE = OrderedDict()
_IMAGE_CACHE_BYTES = 0
_IMAGE_INFLIGHT = {}
_IMAGE_LIMIT = 16 * 1024 * 1024


@router.get("/api/image-proxy")
async def api_image_proxy(url: str = Query(..., min_length=8, max_length=2000), crop: str = Query("", max_length=20)):
    global _IMAGE_CACHE_BYTES
    mode = str(crop or "").strip().lower()
    if mode not in {"", "portrait"}:
        raise HTTPException(400, "invalid_crop_mode")
    key = (str(url or "").strip(), mode)
    cached = _IMAGE_CACHE.get(key)
    if cached:
        expiry, content, headers = cached
        if expiry > time.monotonic():
            _IMAGE_CACHE.move_to_end(key)
            return Response(content=content, headers=headers)
        _IMAGE_CACHE.pop(key)
        _IMAGE_CACHE_BYTES -= len(content)
    task_key = (asyncio.get_running_loop(), key)
    task = _IMAGE_INFLIGHT.get(task_key)
    if task is None:
        if len(_IMAGE_INFLIGHT) >= 12:
            raise HTTPException(503, "image_proxy_busy", headers={"Retry-After": "2"})
        async def load():
            global _IMAGE_CACHE_BYTES
            try:
                async with asyncio.timeout(25):
                    response = await _load_image_proxy(key[0], mode)
                content, headers = response.body, dict(response.headers)
                if len(content) <= _IMAGE_LIMIT // 2:
                    old = _IMAGE_CACHE.pop(key, None)
                    if old:
                        _IMAGE_CACHE_BYTES -= len(old[1])
                    while _IMAGE_CACHE and (_IMAGE_CACHE_BYTES + len(content) > _IMAGE_LIMIT or len(_IMAGE_CACHE) >= 64):
                        _, evicted = _IMAGE_CACHE.popitem(last=False)
                        _IMAGE_CACHE_BYTES -= len(evicted[1])
                    _IMAGE_CACHE[key] = (time.monotonic()+120, content, headers)
                    _IMAGE_CACHE_BYTES += len(content)
                return content, headers
            except TimeoutError as exc:
                raise HTTPException(504, "image_fetch_timeout") from exc
            finally:
                _IMAGE_INFLIGHT.pop(task_key, None)
        task = asyncio.create_task(load())
        # Consume errors even if the original browser request was cancelled.
        task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        _IMAGE_INFLIGHT[task_key] = task
    content, headers = await asyncio.shield(task)
    return Response(content=content, headers=headers)
