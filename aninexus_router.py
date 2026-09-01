from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from utils.aninexus_client import (
    ANINEXUS_API_BASE_URL,
    ANINEXUS_ENABLED,
    ANINEXUS_WEB_BASE_URL,
    AniNexusError,
    aninexus_client,
)

router = APIRouter(prefix="/api/aninexus", tags=["AniNexus"])


def _raise_upstream(exc: AniNexusError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "retryable": bool(exc.retryable),
        },
    ) from exc


def _cache(response: Response, seconds: int) -> None:
    response.headers["Cache-Control"] = (
        f"public, max-age={max(0, int(seconds))}, "
        "stale-while-revalidate=180, stale-if-error=600"
    )
    response.headers["X-AniNexus-Source"] = "aninexus.com.br"


@router.get("/status")
async def aninexus_status(response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    payload: dict[str, Any] = {
        "ok": False,
        "enabled": ANINEXUS_ENABLED,
        "api_origin": ANINEXUS_API_BASE_URL,
        "web_origin": ANINEXUS_WEB_BASE_URL,
        "checked_at": int(time.time()),
    }
    if not ANINEXUS_ENABLED:
        payload["status"] = "disabled"
        return payload
    try:
        health = await aninexus_client.health()
    except AniNexusError as exc:
        payload.update({"status": "unavailable", "code": exc.code})
        return payload
    health_payload = health if isinstance(health, dict) else {}
    payload.update({"ok": bool(health_payload.get("ok", True)), "status": "online"})
    return payload


@router.get("/home")
async def aninexus_home(
    response: Response,
    season: str = Query(default="", max_length=16),
    year: int | None = Query(default=None, ge=1960, le=2100),
) -> Any:
    try:
        data = await aninexus_client.home(season=season.upper(), year=year)
    except AniNexusError as exc:
        _raise_upstream(exc)
    _cache(response, 30)
    return data


@router.get("/catalog")
async def aninexus_catalog(
    response: Response,
    page: int = Query(default=1, ge=1, le=500),
    per_page: int = Query(default=24, ge=1, le=60),
    search: str = Query(default="", max_length=120),
    genre: str = Query(default="", max_length=80),
    format_name: str = Query(default="", alias="format", max_length=40),
    season: str = Query(default="", max_length=16),
    year: int | None = Query(default=None, ge=1960, le=2100),
    status: str = Query(default="", max_length=40),
    sort: str = Query(default="POPULAR", max_length=24),
) -> Any:
    allowed_sorts = {"POPULAR", "SCORE", "TRENDING", "NEW", "TITLE", "FAVOURITES", "MATCH"}
    safe_sort = sort.upper() if sort.upper() in allowed_sorts else "POPULAR"
    try:
        data = await aninexus_client.catalog(
            page=page,
            per_page=per_page,
            search=search.strip(),
            genre=genre.strip(),
            format_name=format_name.strip().upper(),
            season=season.strip().upper(),
            year=year,
            status=status.strip().upper(),
            sort=safe_sort,
        )
    except AniNexusError as exc:
        _raise_upstream(exc)
    _cache(response, 30)
    return data


@router.get("/reading")
async def aninexus_reading(
    response: Response,
    page: int = Query(default=1, ge=1, le=500),
    per_page: int = Query(default=24, ge=1, le=60),
    search: str = Query(default="", max_length=120),
    genre: str = Query(default="", max_length=80),
    format_name: str = Query(default="", alias="format", max_length=40),
    status: str = Query(default="", max_length=40),
    sort: str = Query(default="POPULAR", max_length=24),
) -> Any:
    allowed_sorts = {"POPULAR", "SCORE", "TRENDING", "NEW", "TITLE", "FAVOURITES", "MATCH"}
    safe_sort = sort.upper() if sort.upper() in allowed_sorts else "POPULAR"
    try:
        data = await aninexus_client.reading(
            page=page,
            per_page=per_page,
            search=search.strip(),
            genre=genre.strip(),
            format_name=format_name.strip().upper(),
            status=status.strip().upper(),
            sort=safe_sort,
        )
    except AniNexusError as exc:
        _raise_upstream(exc)
    _cache(response, 30)
    return data


@router.get("/schedule")
async def aninexus_schedule(
    response: Response,
    start: int = Query(..., ge=0),
    end: int = Query(..., ge=1),
) -> Any:
    if end <= start or end - start > 10 * 86400:
        raise HTTPException(status_code=400, detail={"code": "invalid_range"})
    try:
        data = await aninexus_client.schedule(start=start, end=end)
    except AniNexusError as exc:
        _raise_upstream(exc)
    _cache(response, 30)
    return data


@router.get("/anime/{media_id}")
async def aninexus_anime(
    media_id: int,
    response: Response,
) -> Any:
    if media_id <= 0:
        raise HTTPException(status_code=400, detail={"code": "invalid_id"})
    try:
        data = await aninexus_client.anime(media_id)
    except AniNexusError as exc:
        _raise_upstream(exc)
    _cache(response, 180)
    return data


@router.get("/manga/{media_id}")
async def aninexus_manga(
    media_id: int,
    response: Response,
) -> Any:
    if media_id <= 0:
        raise HTTPException(status_code=400, detail={"code": "invalid_id"})
    try:
        data = await aninexus_client.manga(media_id)
    except AniNexusError as exc:
        _raise_upstream(exc)
    _cache(response, 180)
    return data
