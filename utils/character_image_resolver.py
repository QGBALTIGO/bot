from __future__ import annotations

import asyncio
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Iterable

import httpx
from psycopg.rows import dict_row

from database import pool


WALLHAVEN_API_URL = "https://wallhaven.cc/api/v1/search"
WALLHAVEN_API_KEY = os.getenv("WALLHAVEN_API_KEY", "").strip()
WALLHAVEN_ENABLED = os.getenv("WALLHAVEN_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
WALLHAVEN_TIMEOUT_SECONDS = float(os.getenv("WALLHAVEN_TIMEOUT_SECONDS", "10"))
WALLHAVEN_MIN_WIDTH = max(600, int(os.getenv("WALLHAVEN_MIN_WIDTH", "1000")))
WALLHAVEN_MIN_HEIGHT = max(900, int(os.getenv("WALLHAVEN_MIN_HEIGHT", "1500")))
CHARACTER_IMAGE_CACHE_DAYS = max(1, int(os.getenv("CHARACTER_IMAGE_CACHE_DAYS", "30")))
CHARACTER_IMAGE_NEGATIVE_CACHE_HOURS = max(1, int(os.getenv("CHARACTER_IMAGE_NEGATIVE_CACHE_HOURS", "6")))
TARGET_PORTRAIT_RATIO = 2.0 / 3.0
MAX_RATIO_DISTANCE = 0.12

_SCHEMA_READY = False
_SCHEMA_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class CharacterImage:
    url: str
    source: str
    width: int = 0
    height: int = 0
    score: float = 0.0
    cache_hit: bool = False
    override: bool = False


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _ratio(width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    return float(width) / float(height)


def _portrait_score(item: dict[str, Any], index: int = 0) -> float:
    width = int(item.get("dimension_x") or item.get("width") or 0)
    height = int(item.get("dimension_y") or item.get("height") or 0)
    if width <= 0 or height <= 0 or width >= height:
        return -1.0

    ratio = _ratio(width, height)
    distance = abs(ratio - TARGET_PORTRAIT_RATIO)
    if distance > MAX_RATIO_DISTANCE:
        return -1.0

    # Ratio 2:3 is the most important signal.
    ratio_score = max(0.0, 1.0 - (distance / MAX_RATIO_DISTANCE)) * 70.0

    # Prefer useful source resolution, but avoid letting giant images dominate.
    pixels = width * height
    target_pixels = 1200 * 1800
    resolution_score = min(1.5, pixels / float(target_pixels)) * 14.0

    favorites = max(0, int(item.get("favorites") or 0))
    favorite_score = min(8.0, math.log1p(favorites) * 1.5)

    # Wallhaven already returns relevance order. Keep a small rank bonus.
    rank_score = max(0.0, 6.0 - (float(index) * 0.3))

    return round(ratio_score + resolution_score + favorite_score + rank_score, 4)


def choose_best_wallhaven_portrait(items: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1.0

    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        if str(raw.get("purity") or "sfw").lower() != "sfw":
            continue

        url = _clean_text(raw.get("path"))
        if not url.startswith("https://"):
            continue

        score = _portrait_score(raw, index)
        if score <= best_score:
            continue

        best = dict(raw)
        best["_baltigo_score"] = score
        best_score = score

    return best


def _ensure_schema_sync() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS character_image_overrides (
                    character_id BIGINT PRIMARY KEY,
                    image_url TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS character_image_cache (
                    character_id BIGINT PRIMARY KEY,
                    image_url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    query_text TEXT NOT NULL DEFAULT '',
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    score DOUBLE PRECISION NOT NULL DEFAULT 0,
                    expires_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conn.commit()
    _SCHEMA_READY = True


async def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    async with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        await asyncio.to_thread(_ensure_schema_sync)


def _get_override_sync(character_id: int) -> dict[str, Any] | None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT image_url, source
                FROM character_image_overrides
                WHERE character_id = %s
                  AND active = TRUE
                LIMIT 1
                """,
                (int(character_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _get_cache_sync(character_id: int) -> dict[str, Any] | None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT image_url, source, width, height, score
                FROM character_image_cache
                WHERE character_id = %s
                  AND expires_at > NOW()
                LIMIT 1
                """,
                (int(character_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _save_cache_sync(
    character_id: int,
    image_url: str,
    source: str,
    query_text: str,
    width: int,
    height: int,
    score: float,
    ttl_seconds: int,
) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO character_image_cache
                    (character_id, image_url, source, query_text, width, height, score, expires_at, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'), NOW())
                ON CONFLICT (character_id) DO UPDATE SET
                    image_url = EXCLUDED.image_url,
                    source = EXCLUDED.source,
                    query_text = EXCLUDED.query_text,
                    width = EXCLUDED.width,
                    height = EXCLUDED.height,
                    score = EXCLUDED.score,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
                """,
                (
                    int(character_id),
                    str(image_url),
                    str(source),
                    str(query_text),
                    int(width),
                    int(height),
                    float(score),
                    int(ttl_seconds),
                ),
            )
            conn.commit()


async def _wallhaven_search(query: str) -> list[dict[str, Any]]:
    if not WALLHAVEN_ENABLED or not query:
        return []

    params = {
        "q": query,
        "categories": "010",  # anime only
        "purity": "100",      # SFW only
        "sorting": "relevance",
        "order": "desc",
        "atleast": f"{WALLHAVEN_MIN_WIDTH}x{WALLHAVEN_MIN_HEIGHT}",
        "ratios": "2x3",
        "page": "1",
    }
    if WALLHAVEN_API_KEY:
        params["apikey"] = WALLHAVEN_API_KEY

    headers = {
        "Accept": "application/json",
        "User-Agent": "SourceBaltigo/1.0 (+character-image-resolver)",
    }

    async with httpx.AsyncClient(
        timeout=WALLHAVEN_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = await client.get(WALLHAVEN_API_URL, params=params)
        if response.status_code == 429:
            return []
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data") if isinstance(payload, dict) else None
    return [item for item in (data or []) if isinstance(item, dict)]


async def resolve_character_portrait(
    *,
    character_id: int,
    character_name: str,
    anime_title: str,
    fallback_url: str,
) -> CharacterImage:
    """Resolve a high-quality 2:3 portrait without changing character identity.

    Priority: manual override -> PostgreSQL cache -> Wallhaven -> AniList/current fallback.
    """
    character_id = int(character_id)
    fallback_url = _clean_text(fallback_url)
    character_name = _clean_text(character_name)
    anime_title = _clean_text(anime_title)

    if character_id <= 0:
        return CharacterImage(url=fallback_url, source="fallback")

    try:
        await _ensure_schema()

        override = await asyncio.to_thread(_get_override_sync, character_id)
        if override and _clean_text(override.get("image_url")):
            return CharacterImage(
                url=_clean_text(override["image_url"]),
                source=_clean_text(override.get("source")) or "manual",
                cache_hit=True,
                override=True,
            )

        cached = await asyncio.to_thread(_get_cache_sync, character_id)
        if cached and _clean_text(cached.get("image_url")):
            return CharacterImage(
                url=_clean_text(cached["image_url"]),
                source=_clean_text(cached.get("source")) or "cache",
                width=int(cached.get("width") or 0),
                height=int(cached.get("height") or 0),
                score=float(cached.get("score") or 0),
                cache_hit=True,
            )
    except Exception as exc:
        print(f"[character-image] cache indisponivel: {type(exc).__name__}", flush=True)

    query_candidates: list[str] = []
    if character_name and anime_title:
        query_candidates.append(f"{character_name} {anime_title}")
    if character_name:
        query_candidates.append(character_name)

    seen_queries: set[str] = set()
    for query in query_candidates:
        normalized_query = query.casefold()
        if normalized_query in seen_queries:
            continue
        seen_queries.add(normalized_query)

        try:
            items = await _wallhaven_search(query)
            best = choose_best_wallhaven_portrait(items)
            if not best:
                continue

            url = _clean_text(best.get("path"))
            width = int(best.get("dimension_x") or 0)
            height = int(best.get("dimension_y") or 0)
            score = float(best.get("_baltigo_score") or 0)

            try:
                await _ensure_schema()
                await asyncio.to_thread(
                    _save_cache_sync,
                    character_id,
                    url,
                    "wallhaven",
                    query,
                    width,
                    height,
                    score,
                    CHARACTER_IMAGE_CACHE_DAYS * 86400,
                )
            except Exception as exc:
                print(f"[character-image] falha ao salvar cache: {type(exc).__name__}", flush=True)

            return CharacterImage(
                url=url,
                source="wallhaven",
                width=width,
                height=height,
                score=score,
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            print(f"[character-image] Wallhaven falhou para {character_id}: {type(exc).__name__}", flush=True)
        except Exception as exc:
            print(f"[character-image] erro inesperado Wallhaven {character_id}: {type(exc).__name__}", flush=True)

    if fallback_url:
        try:
            await _ensure_schema()
            await asyncio.to_thread(
                _save_cache_sync,
                character_id,
                fallback_url,
                "anilist",
                "",
                0,
                0,
                0.0,
                CHARACTER_IMAGE_NEGATIVE_CACHE_HOURS * 3600,
            )
        except Exception:
            pass

    return CharacterImage(url=fallback_url, source="anilist")
