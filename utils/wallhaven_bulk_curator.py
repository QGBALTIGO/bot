from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable

import httpx
from psycopg.rows import dict_row

from cards_service import build_cards_final_data, reload_cards_cache
from database import get_all_global_character_images, pool, set_global_character_image


SEARCH_URL = "https://wallhaven.cc/api/v1/search"
DETAIL_URL = "https://wallhaven.cc/api/v1/w/{wallpaper_id}"
LOCK_KEY = 7341123456821

# Retired legacy runtime curator. Kept only for historical/diagnostic use.
# It must never start implicitly because curated portraits are now versioned
# in data/wallhaven_character_overrides.json and validated before deployment.
ENABLED = os.getenv("WALLHAVEN_LEGACY_CURATOR_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
API_KEY = os.getenv("WALLHAVEN_API_KEY", "").strip()
MIN_WIDTH = max(600, int(os.getenv("WALLHAVEN_CURATOR_MIN_WIDTH", "1000")))
MIN_HEIGHT = max(900, int(os.getenv("WALLHAVEN_CURATOR_MIN_HEIGHT", "1500")))
TARGET_RATIO = float(os.getenv("WALLHAVEN_CURATOR_TARGET_RATIO", str(2 / 3)))
RATIO_TOLERANCE = max(0.01, float(os.getenv("WALLHAVEN_CURATOR_RATIO_TOLERANCE", "0.055")))
MIN_SCORE = max(0.0, float(os.getenv("WALLHAVEN_CURATOR_MIN_SCORE", "76")))
MIN_CHARACTER_MATCH = min(1.0, max(0.0, float(os.getenv("WALLHAVEN_CURATOR_CHARACTER_MATCH", "0.82"))))
MIN_SERIES_MATCH = min(1.0, max(0.0, float(os.getenv("WALLHAVEN_CURATOR_SERIES_MATCH", "0.58"))))
MIN_FAVORITES = max(0, int(os.getenv("WALLHAVEN_CURATOR_MIN_FAVORITES", "0")))
MIN_VIEWS = max(0, int(os.getenv("WALLHAVEN_CURATOR_MIN_VIEWS", "0")))
MIN_FILE_BYTES = max(0, int(os.getenv("WALLHAVEN_CURATOR_MIN_FILE_BYTES", "250000")))
MAX_FILE_BYTES = max(MIN_FILE_BYTES, int(os.getenv("WALLHAVEN_CURATOR_MAX_FILE_BYTES", "25000000")))
MAX_CHARACTER_TAGS = max(1, int(os.getenv("WALLHAVEN_CURATOR_MAX_CHARACTER_TAGS", "2")))
SEARCH_PAGES = max(1, min(4, int(os.getenv("WALLHAVEN_CURATOR_SEARCH_PAGES", "2"))))
DETAIL_CANDIDATES = max(1, min(12, int(os.getenv("WALLHAVEN_CURATOR_DETAIL_CANDIDATES", "6"))))
REQUEST_INTERVAL_SECONDS = max(0.35, float(os.getenv("WALLHAVEN_CURATOR_REQUEST_INTERVAL", "1.55")))
HTTP_TIMEOUT_SECONDS = max(5.0, float(os.getenv("WALLHAVEN_CURATOR_HTTP_TIMEOUT", "15")))
RETRY_DAYS = max(1, int(os.getenv("WALLHAVEN_CURATOR_RETRY_DAYS", "30")))
MAX_CHARACTERS_PER_RUN = max(0, int(os.getenv("WALLHAVEN_CURATOR_MAX_CHARACTERS_PER_RUN", "0")))
INITIAL_DELAY_SECONDS = max(0.0, float(os.getenv("WALLHAVEN_CURATOR_INITIAL_DELAY", "15")))
REPLACE_MANUAL = os.getenv("WALLHAVEN_CURATOR_REPLACE_MANUAL", "0").strip().lower() in {"1", "true", "yes", "on"}
REJECT_AI = os.getenv("WALLHAVEN_CURATOR_REJECT_AI", "1").strip().lower() not in {"0", "false", "no", "off"}

_GENERIC_CHARACTER_TAGS = {
    "anime girls",
    "anime girl",
    "anime boys",
    "anime boy",
    "original characters",
    "original character",
    "manga girls",
    "manga girl",
    "women",
    "woman",
    "men",
    "man",
}
_AI_TERMS = {
    "ai art",
    "ai generated",
    "ai generated art",
    "artificial intelligence",
    "stable diffusion",
    "midjourney",
}

_API_LOCK = asyncio.Lock()
_LAST_REQUEST_AT = 0.0
_SCHEMA_READY = False


@dataclass(frozen=True)
class CuratedCandidate:
    wallpaper_id: str
    image_url: str
    query: str
    width: int
    height: int
    favorites: int
    views: int
    score: float
    character_match: float
    series_match: float
    character_tags: tuple[str, ...]
    series_tags: tuple[str, ...]
    source_url: str


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _tokens(value: Any) -> set[str]:
    return {token for token in _normalize(value).split() if len(token) >= 2}


def _similarity(target: Any, candidate: Any) -> float:
    a = _normalize(target)
    b = _normalize(candidate)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 4 and (a in b or b in a):
        short = min(len(a), len(b))
        long = max(len(a), len(b))
        return min(0.97, 0.84 + (0.13 * short / long))

    at = _tokens(a)
    bt = _tokens(b)
    union = at | bt
    jaccard = (len(at & bt) / len(union)) if union else 0.0
    sequence = SequenceMatcher(None, a, b).ratio()
    return max(sequence, jaccard)


def _tag_variants(tag: dict[str, Any]) -> list[str]:
    variants: list[str] = []
    name = str(tag.get("name") or "").strip()
    alias = str(tag.get("alias") or "").strip()
    if name:
        variants.append(name)
        match = re.search(r"\(([^()]*)\)", name)
        if match and match.group(1).strip():
            variants.append(match.group(1).strip())
    if alias:
        variants.extend(part.strip() for part in alias.split(",") if part.strip())
    return variants


def _best_tag_match(target: str, tags: Iterable[dict[str, Any]], category: str) -> tuple[float, str]:
    best_score = 0.0
    best_name = ""
    wanted = category.casefold()
    for tag in tags:
        if str(tag.get("category") or "").casefold() != wanted:
            continue
        for variant in _tag_variants(tag):
            score = _similarity(target, variant)
            if score > best_score:
                best_score = score
                best_name = str(tag.get("name") or variant).strip()
    return best_score, best_name


def _specific_character_tags(tags: Iterable[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if str(tag.get("category") or "").casefold() != "characters":
            continue
        name = str(tag.get("name") or "").strip()
        normalized = _normalize(name)
        if not normalized or normalized in _GENERIC_CHARACTER_TAGS:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        names.append(name)
    return names


def _series_tags(tags: Iterable[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for tag in tags:
        if str(tag.get("category") or "").casefold() == "series":
            name = str(tag.get("name") or "").strip()
            if name:
                out.append(name)
    return out


def _contains_ai_tag(tags: Iterable[dict[str, Any]]) -> bool:
    for tag in tags:
        values = [str(tag.get("name") or ""), str(tag.get("alias") or "")]
        normalized = " ".join(_normalize(v) for v in values if v)
        if any(term in normalized for term in _AI_TERMS):
            return True
    return False


def _base_item_ok(item: dict[str, Any]) -> bool:
    if str(item.get("purity") or "").casefold() != "sfw":
        return False
    if str(item.get("category") or "").casefold() != "anime":
        return False
    width = int(item.get("dimension_x") or 0)
    height = int(item.get("dimension_y") or 0)
    if width < MIN_WIDTH or height < MIN_HEIGHT or width >= height:
        return False
    ratio = (width / height) if height else 0.0
    if abs(ratio - TARGET_RATIO) > RATIO_TOLERANCE:
        return False
    favorites = int(item.get("favorites") or 0)
    views = int(item.get("views") or 0)
    file_size = int(item.get("file_size") or 0)
    if favorites < MIN_FAVORITES or views < MIN_VIEWS:
        return False
    if file_size < MIN_FILE_BYTES or file_size > MAX_FILE_BYTES:
        return False
    if not str(item.get("path") or "").startswith("https://"):
        return False
    if str(item.get("file_type") or "").casefold() not in {"image/jpeg", "image/png", "image/webp"}:
        return False
    return True


def _score_candidate(
    item: dict[str, Any],
    tags: list[dict[str, Any]],
    character_name: str,
    anime_title: str,
    query: str,
) -> CuratedCandidate | None:
    if not _base_item_ok(item):
        return None
    if REJECT_AI and _contains_ai_tag(tags):
        return None

    character_match, _ = _best_tag_match(character_name, tags, "Characters")
    series_match, _ = _best_tag_match(anime_title, tags, "Series")

    # Character tags often include the series in parentheses, e.g. "Fern (Sousou No Frieren)".
    for tag in tags:
        if str(tag.get("category") or "").casefold() != "characters":
            continue
        for variant in _tag_variants(tag):
            series_match = max(series_match, _similarity(anime_title, variant))

    if character_match < MIN_CHARACTER_MATCH or series_match < MIN_SERIES_MATCH:
        return None

    character_tags = _specific_character_tags(tags)
    if len(character_tags) > MAX_CHARACTER_TAGS:
        return None

    width = int(item.get("dimension_x") or 0)
    height = int(item.get("dimension_y") or 0)
    ratio = width / height
    ratio_distance = abs(ratio - TARGET_RATIO)
    ratio_score = max(0.0, 1.0 - (ratio_distance / RATIO_TOLERANCE)) * 20.0

    pixels = width * height
    resolution_score = min(1.0, pixels / float(1500 * 2250)) * 10.0
    favorites = max(0, int(item.get("favorites") or 0))
    views = max(0, int(item.get("views") or 0))
    favorite_score = min(5.0, math.log1p(favorites) * 1.15)
    views_score = min(3.0, math.log1p(views) * 0.35)
    single_character_score = 7.0 if len(character_tags) <= 1 else 2.5

    score = (
        character_match * 35.0
        + series_match * 20.0
        + ratio_score
        + resolution_score
        + favorite_score
        + views_score
        + single_character_score
    )
    score = round(score, 4)
    if score < MIN_SCORE:
        return None

    return CuratedCandidate(
        wallpaper_id=str(item.get("id") or ""),
        image_url=str(item.get("path") or "").strip(),
        query=query,
        width=width,
        height=height,
        favorites=favorites,
        views=views,
        score=score,
        character_match=round(character_match, 4),
        series_match=round(series_match, 4),
        character_tags=tuple(character_tags),
        series_tags=tuple(_series_tags(tags)),
        source_url=str(item.get("source") or "").strip(),
    )


async def _api_get(url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    global _LAST_REQUEST_AT
    async with _API_LOCK:
        elapsed = time.monotonic() - _LAST_REQUEST_AT
        wait_for = REQUEST_INTERVAL_SECONDS - elapsed
        if wait_for > 0:
            await asyncio.sleep(wait_for)

        headers = {
            "Accept": "application/json",
            "User-Agent": "SourceBaltigo/1.0 (+strict-wallhaven-curator)",
        }
        request_params = dict(params or {})
        if API_KEY:
            request_params["apikey"] = API_KEY

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as client:
            response = await client.get(url, params=request_params)
            _LAST_REQUEST_AT = time.monotonic()
            if response.status_code == 429:
                raw_retry = response.headers.get("retry-after") or "5"
                try:
                    retry_after = max(2.0, min(30.0, float(raw_retry)))
                except ValueError:
                    retry_after = 5.0
                await asyncio.sleep(retry_after)
                raise RuntimeError("wallhaven_rate_limited")
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}


async def _search(query: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for page in range(1, SEARCH_PAGES + 1):
        payload = await _api_get(
            SEARCH_URL,
            params={
                "q": query,
                "categories": "010",
                "purity": "100",
                "sorting": "relevance",
                "order": "desc",
                "atleast": f"{MIN_WIDTH}x{MIN_HEIGHT}",
                "ratios": "2x3",
                "page": str(page),
            },
        )
        page_items = payload.get("data") or []
        if not isinstance(page_items, list):
            break
        for item in page_items:
            if not isinstance(item, dict) or not _base_item_ok(item):
                continue
            wid = str(item.get("id") or "").strip()
            if not wid or wid in seen:
                continue
            seen.add(wid)
            results.append(item)
        meta = payload.get("meta") or {}
        last_page = int(meta.get("last_page") or page)
        if page >= last_page:
            break

    # Before spending detail requests, prefer popular/high-resolution items from Wallhaven's relevance result.
    results.sort(
        key=lambda item: (
            int(item.get("favorites") or 0),
            int(item.get("views") or 0),
            int(item.get("dimension_x") or 0) * int(item.get("dimension_y") or 0),
        ),
        reverse=True,
    )
    return results


async def _details(wallpaper_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = await _api_get(DETAIL_URL.format(wallpaper_id=wallpaper_id))
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return {}, []
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return data, [tag for tag in tags if isinstance(tag, dict)]


async def find_best_wallhaven_candidate(character_name: str, anime_title: str) -> CuratedCandidate | None:
    queries: list[str] = []
    strict = " ".join(part for part in (character_name.strip(), anime_title.strip()) if part)
    if strict:
        queries.append(strict)
    if character_name.strip() and _normalize(character_name) != _normalize(strict):
        queries.append(character_name.strip())

    seen_queries: set[str] = set()
    for query in queries:
        nq = _normalize(query)
        if not nq or nq in seen_queries:
            continue
        seen_queries.add(nq)

        search_items = await _search(query)
        candidates: list[CuratedCandidate] = []
        for item in search_items[:DETAIL_CANDIDATES]:
            wid = str(item.get("id") or "").strip()
            if not wid:
                continue
            detail, tags = await _details(wid)
            merged = dict(item)
            merged.update(detail)
            candidate = _score_candidate(merged, tags, character_name, anime_title, query)
            if candidate is not None:
                candidates.append(candidate)

        if candidates:
            candidates.sort(key=lambda c: (c.score, c.favorites, c.views, c.width * c.height), reverse=True)
            return candidates[0]

    return None


def _ensure_schema_sync() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS wallhaven_character_curation (
                    character_id BIGINT PRIMARY KEY,
                    anime_id BIGINT NOT NULL DEFAULT 0,
                    character_name TEXT NOT NULL DEFAULT '',
                    anime_title TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    wallhaven_id TEXT NOT NULL DEFAULT '',
                    image_url TEXT NOT NULL DEFAULT '',
                    search_query TEXT NOT NULL DEFAULT '',
                    score DOUBLE PRECISION NOT NULL DEFAULT 0,
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    character_match DOUBLE PRECISION NOT NULL DEFAULT 0,
                    series_match DOUBLE PRECISION NOT NULL DEFAULT 0,
                    character_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                    series_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                    source_url TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    last_attempt_at TIMESTAMPTZ,
                    applied_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_wallhaven_curation_status ON wallhaven_character_curation(status, last_attempt_at)"
            )
            conn.commit()
    _SCHEMA_READY = True


def _curation_row_sync(character_id: int) -> dict[str, Any] | None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM wallhaven_character_curation WHERE character_id = %s",
                (int(character_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _record_sync(
    *,
    character_id: int,
    anime_id: int,
    character_name: str,
    anime_title: str,
    status: str,
    candidate: CuratedCandidate | None = None,
    error: str = "",
) -> None:
    candidate = candidate or CuratedCandidate("", "", "", 0, 0, 0, 0, 0.0, 0.0, 0.0, (), (), "")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO wallhaven_character_curation (
                    character_id, anime_id, character_name, anime_title, status,
                    wallhaven_id, image_url, search_query, score, width, height,
                    character_match, series_match, character_tags, series_tags,
                    source_url, attempts, last_error, last_attempt_at, applied_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s::jsonb, %s::jsonb,
                    %s, 1, %s, NOW(), CASE WHEN %s = 'applied' THEN NOW() ELSE NULL END, NOW()
                )
                ON CONFLICT (character_id) DO UPDATE SET
                    anime_id = EXCLUDED.anime_id,
                    character_name = EXCLUDED.character_name,
                    anime_title = EXCLUDED.anime_title,
                    status = EXCLUDED.status,
                    wallhaven_id = EXCLUDED.wallhaven_id,
                    image_url = EXCLUDED.image_url,
                    search_query = EXCLUDED.search_query,
                    score = EXCLUDED.score,
                    width = EXCLUDED.width,
                    height = EXCLUDED.height,
                    character_match = EXCLUDED.character_match,
                    series_match = EXCLUDED.series_match,
                    character_tags = EXCLUDED.character_tags,
                    series_tags = EXCLUDED.series_tags,
                    source_url = EXCLUDED.source_url,
                    attempts = wallhaven_character_curation.attempts + 1,
                    last_error = EXCLUDED.last_error,
                    last_attempt_at = NOW(),
                    applied_at = CASE WHEN EXCLUDED.status = 'applied' THEN NOW() ELSE wallhaven_character_curation.applied_at END,
                    updated_at = NOW()
                """,
                (
                    int(character_id), int(anime_id or 0), str(character_name), str(anime_title), str(status),
                    candidate.wallpaper_id, candidate.image_url, candidate.query, candidate.score, candidate.width, candidate.height,
                    candidate.character_match, candidate.series_match,
                    json.dumps(list(candidate.character_tags), ensure_ascii=False),
                    json.dumps(list(candidate.series_tags), ensure_ascii=False),
                    candidate.source_url, str(error or "")[:1000], str(status),
                ),
            )
            conn.commit()


def _should_retry(row: dict[str, Any] | None) -> bool:
    if not row:
        return True
    status = str(row.get("status") or "")
    if status == "applied":
        return False
    last_attempt = row.get("last_attempt_at")
    if last_attempt is None:
        return True
    try:
        age = time.time() - last_attempt.timestamp()
    except Exception:
        return True
    return age >= RETRY_DAYS * 86400


def _load_characters_sync() -> list[dict[str, Any]]:
    data = build_cards_final_data(force_reload=True)
    rows = [dict(value) for value in (data.get("characters_by_id") or {}).values()]
    rows.sort(key=lambda item: (_normalize(item.get("anime")), _normalize(item.get("name")), int(item.get("id") or 0)))
    return rows


def _try_global_lock_sync():
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
            locked = bool(cur.fetchone()[0])
        if locked:
            return conn
    except Exception:
        pool.putconn(conn)
        raise
    pool.putconn(conn)
    return None


def _release_global_lock_sync(conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    finally:
        pool.putconn(conn)


async def wallhaven_bulk_curator_worker() -> None:
    if not ENABLED:
        print("[wallhaven-curator] desativado", flush=True)
        return

    if INITIAL_DELAY_SECONDS:
        await asyncio.sleep(INITIAL_DELAY_SECONDS)

    await asyncio.to_thread(_ensure_schema_sync)
    lock_conn = await asyncio.to_thread(_try_global_lock_sync)
    if lock_conn is None:
        print("[wallhaven-curator] outro processo ja esta executando a curadoria", flush=True)
        return

    processed = 0
    applied = 0
    no_match = 0
    skipped_manual = 0
    errors = 0

    try:
        characters = await asyncio.to_thread(_load_characters_sync)
        global_images = await asyncio.to_thread(get_all_global_character_images)
        print(f"[wallhaven-curator] inicio characters={len(characters)} target=2:3 strict=true", flush=True)

        for char in characters:
            if MAX_CHARACTERS_PER_RUN and processed >= MAX_CHARACTERS_PER_RUN:
                break

            character_id = int(char.get("id") or 0)
            anime_id = int(char.get("anime_id") or 0)
            character_name = str(char.get("name") or "").strip()
            anime_title = str(char.get("anime") or "").strip()
            if character_id <= 0 or not character_name or not anime_title:
                continue

            row = await asyncio.to_thread(_curation_row_sync, character_id)
            current_global = str(global_images.get(character_id) or "").strip()

            if current_global:
                ours = bool(row and str(row.get("status") or "") == "applied" and str(row.get("image_url") or "").strip() == current_global)
                if ours:
                    continue
                if not REPLACE_MANUAL:
                    skipped_manual += 1
                    if not row or str(row.get("status") or "") != "skipped_manual":
                        await asyncio.to_thread(
                            _record_sync,
                            character_id=character_id,
                            anime_id=anime_id,
                            character_name=character_name,
                            anime_title=anime_title,
                            status="skipped_manual",
                        )
                    continue

            if not _should_retry(row):
                continue

            processed += 1
            try:
                candidate = await find_best_wallhaven_candidate(character_name, anime_title)
                if candidate is None:
                    no_match += 1
                    await asyncio.to_thread(
                        _record_sync,
                        character_id=character_id,
                        anime_id=anime_id,
                        character_name=character_name,
                        anime_title=anime_title,
                        status="no_match",
                    )
                    continue

                await asyncio.to_thread(
                    set_global_character_image,
                    character_id=character_id,
                    image_url=candidate.image_url,
                    updated_by=0,
                )
                global_images[character_id] = candidate.image_url
                applied += 1
                await asyncio.to_thread(
                    _record_sync,
                    character_id=character_id,
                    anime_id=anime_id,
                    character_name=character_name,
                    anime_title=anime_title,
                    status="applied",
                    candidate=candidate,
                )
                if applied % 10 == 0:
                    await asyncio.to_thread(reload_cards_cache)
                print(
                    f"[wallhaven-curator] applied id={character_id} name={character_name!r} "
                    f"anime={anime_title!r} wallhaven={candidate.wallpaper_id} "
                    f"score={candidate.score:.1f} size={candidate.width}x{candidate.height}",
                    flush=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                errors += 1
                await asyncio.to_thread(
                    _record_sync,
                    character_id=character_id,
                    anime_id=anime_id,
                    character_name=character_name,
                    anime_title=anime_title,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
                print(f"[wallhaven-curator] error id={character_id}: {type(exc).__name__}: {exc}", flush=True)

        await asyncio.to_thread(reload_cards_cache)
        print(
            f"[wallhaven-curator] fim processed={processed} applied={applied} "
            f"no_match={no_match} skipped_manual={skipped_manual} errors={errors}",
            flush=True,
        )
    finally:
        await asyncio.to_thread(_release_global_lock_sync, lock_conn)
