from __future__ import annotations

import os
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


@router.get("/api/image-proxy")
async def api_image_proxy(
    url: str = Query(..., min_length=8, max_length=2000),
    crop: str = Query("", max_length=20),
):
    """Proxy público de imagens com validação SSRF e crop opcional 2:3."""

    target = str(url or "").strip()
    parsed = urlparse(target)
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
            content, _crop_meta = crop_portrait_bytes(content)
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
            "X-Image-Crop": "2:3" if applied_crop else "original",
        },
    )
