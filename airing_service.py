from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ecosystem_repository import library_state

ANILIST_URL = "https://graphql.anilist.co"
_CACHE_TTL = 900.0
_cache: dict[int, tuple[float, list[dict[str, Any]]]] = {}
_locks: dict[int, asyncio.Lock] = {}


def _lock(user_id: int) -> asyncio.Lock:
    lock = _locks.get(int(user_id))
    if lock is None:
        lock = asyncio.Lock()
        _locks[int(user_id)] = lock
    return lock


def _followed_anime_ids(user_id: int) -> tuple[list[int], dict[int, dict[str, Any]]]:
    items = [
        item for item in library_state(int(user_id))
        if str(item.get("media_type")) == "anime"
        and (bool(item.get("is_favorite")) or str(item.get("status")) in {"planned", "watching"})
    ]
    items = items[:50]
    by_id = {int(item["media_id"]): item for item in items if int(item.get("media_id") or 0) > 0}
    return list(by_id), by_id


async def get_airing_agenda(user_id: int, *, force: bool = False) -> list[dict[str, Any]]:
    uid = int(user_id)
    cached = _cache.get(uid)
    if cached and not force and time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1]

    async with _lock(uid):
        cached = _cache.get(uid)
        if cached and not force and time.monotonic() - cached[0] < _CACHE_TTL:
            return cached[1]
        ids, followed = _followed_anime_ids(uid)
        if not ids:
            _cache[uid] = (time.monotonic(), [])
            return []

        query = """
        query ($ids: [Int]) {
          Page(page: 1, perPage: 50) {
            media(id_in: $ids, type: ANIME) {
              id
              title { romaji english }
              coverImage { large }
              siteUrl
              nextAiringEpisode { airingAt episode timeUntilAiring }
            }
          }
        }
        """
        try:
            async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "SourceBaltigo/2.0"}) as client:
                response = await client.post(ANILIST_URL, json={"query": query, "variables": {"ids": ids}})
                response.raise_for_status()
                payload = response.json()
        except Exception:
            # Agenda is enrichment. A remote outage must not break the Hub.
            return cached[1] if cached else []

        results: list[dict[str, Any]] = []
        for media in (((payload.get("data") or {}).get("Page") or {}).get("media") or []):
            airing = media.get("nextAiringEpisode") or {}
            airing_at = int(airing.get("airingAt") or 0)
            if airing_at <= 0:
                continue
            media_id = int(media.get("id") or 0)
            local = followed.get(media_id) or {}
            title_data = media.get("title") or {}
            results.append({
                "media_id": media_id,
                "title": str(local.get("title") or title_data.get("english") or title_data.get("romaji") or "Anime"),
                "cover_url": str(local.get("cover_url") or (media.get("coverImage") or {}).get("large") or ""),
                "episode": int(airing.get("episode") or 0),
                "airing_at": datetime.fromtimestamp(airing_at, tz=timezone.utc).isoformat(),
                "seconds_until": max(0, int(airing.get("timeUntilAiring") or 0)),
                "site_url": str(media.get("siteUrl") or ""),
            })
        results.sort(key=lambda item: item["airing_at"])
        _cache[uid] = (time.monotonic(), results)
        return results
