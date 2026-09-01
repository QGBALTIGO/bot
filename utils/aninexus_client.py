from __future__ import annotations

import asyncio
import copy
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode, urlparse

import httpx


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "sim"}


def _normalize_origin(value: str) -> str:
    origin = str(value or "").strip().rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("ANINEXUS_API_BASE_URL precisa ser uma origem HTTP(S) valida.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("ANINEXUS_API_BASE_URL nao pode conter credenciais, query ou fragmento.")
    if parsed.path not in {"", "/"}:
        raise RuntimeError("ANINEXUS_API_BASE_URL deve apontar para a raiz do AniNexus.")
    return f"{parsed.scheme}://{parsed.netloc}"


ANINEXUS_ENABLED = _env_bool("ANINEXUS_ENABLED", True)
ANINEXUS_API_BASE_URL = _normalize_origin(
    os.getenv("ANINEXUS_API_BASE_URL", "https://aninexus.com.br")
)
ANINEXUS_WEB_BASE_URL = _normalize_origin(
    os.getenv("ANINEXUS_WEB_BASE_URL", ANINEXUS_API_BASE_URL)
)
ANINEXUS_TIMEOUT_SECONDS = max(
    2.0,
    min(30.0, float(os.getenv("ANINEXUS_API_TIMEOUT_SECONDS", "9"))),
)
ANINEXUS_CACHE_MAX_ENTRIES = max(
    16,
    min(1024, int(os.getenv("ANINEXUS_CACHE_MAX_ENTRIES", "256"))),
)
ANINEXUS_USER_AGENT = os.getenv(
    "ANINEXUS_USER_AGENT",
    "SourceBaltigoBot/2.0 (+https://aninexus.com.br)",
).strip() or "SourceBaltigoBot/2.0"


@dataclass(frozen=True)
class AniNexusError(RuntimeError):
    code: str
    status_code: int = 502
    upstream_status: int | None = None
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


@dataclass
class _CacheEntry:
    expires_at: float
    touched_at: float
    payload: Any


class AniNexusClient:
    """Small, bounded and fail-safe client for the public AniNexus API."""

    _ALLOWED_EXACT_PATHS = {
        "/health",
        "/api/home",
        "/api/catalog",
        "/api/reading",
        "/api/schedule",
        "/api/media/summaries",
        "/api/studios",
        "/api/dublados",
        "/api/lists",
    }
    _ALLOWED_DYNAMIC_PREFIXES = ("/api/anime/", "/api/manga/")

    def __init__(
        self,
        *,
        base_url: str = ANINEXUS_API_BASE_URL,
        enabled: bool = ANINEXUS_ENABLED,
        timeout_seconds: float = ANINEXUS_TIMEOUT_SECONDS,
        max_cache_entries: int = ANINEXUS_CACHE_MAX_ENTRIES,
    ) -> None:
        self.base_url = _normalize_origin(base_url)
        self.enabled = bool(enabled)
        self.timeout_seconds = max(2.0, min(30.0, float(timeout_seconds)))
        self.max_cache_entries = max(16, min(1024, int(max_cache_entries)))
        self._cache: dict[str, _CacheEntry] = {}
        self._cache_lock = asyncio.Lock()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    @staticmethod
    def _safe_path(path: str) -> str:
        value = str(path or "").strip()
        if not value.startswith("/") or value.startswith("//"):
            raise AniNexusError("aninexus_invalid_path", status_code=500)
        if "?" in value or "#" in value or "\\" in value:
            raise AniNexusError("aninexus_invalid_path", status_code=500)
        exact = value in AniNexusClient._ALLOWED_EXACT_PATHS
        dynamic = any(value.startswith(prefix) for prefix in AniNexusClient._ALLOWED_DYNAMIC_PREFIXES)
        if not exact and not dynamic:
            raise AniNexusError("aninexus_path_not_allowed", status_code=500)
        return value

    @staticmethod
    def _cache_key(path: str, params: Mapping[str, Any] | None) -> str:
        normalized = [
            (str(key), str(value))
            for key, value in sorted((params or {}).items())
            if value is not None and value != ""
        ]
        return path + ("?" + urlencode(normalized) if normalized else "")

    async def _cached(self, key: str) -> Any | None:
        now = time.monotonic()
        async with self._cache_lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if now >= entry.expires_at:
                self._cache.pop(key, None)
                return None
            entry.touched_at = now
            return copy.deepcopy(entry.payload)

    async def _store(self, key: str, payload: Any, ttl_seconds: float) -> None:
        now = time.monotonic()
        async with self._cache_lock:
            self._cache[key] = _CacheEntry(
                expires_at=now + max(1.0, float(ttl_seconds)),
                touched_at=now,
                payload=copy.deepcopy(payload),
            )
            if len(self._cache) > self.max_cache_entries:
                ordered = sorted(self._cache.items(), key=lambda item: item[1].touched_at)
                for old_key, _ in ordered[: len(self._cache) - self.max_cache_entries]:
                    self._cache.pop(old_key, None)

    async def _lock_for(self, key: str) -> asyncio.Lock:
        async with self._cache_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._key_locks[key] = lock
            if len(self._key_locks) > self.max_cache_entries * 2:
                live_keys = set(self._cache)
                for old_key in list(self._key_locks):
                    candidate = self._key_locks.get(old_key)
                    if old_key not in live_keys and candidate is not None and not candidate.locked():
                        self._key_locks.pop(old_key, None)
                    if len(self._key_locks) <= self.max_cache_entries:
                        break
            return lock

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        cache_ttl: float = 30.0,
    ) -> Any:
        if not self.enabled:
            raise AniNexusError("aninexus_disabled", status_code=503)

        safe_path = self._safe_path(path)
        clean_params = {
            str(key): value
            for key, value in (params or {}).items()
            if value is not None and value != ""
        }
        key = self._cache_key(safe_path, clean_params)
        cached = await self._cached(key)
        if cached is not None:
            return cached

        key_lock = await self._lock_for(key)
        async with key_lock:
            cached = await self._cached(key)
            if cached is not None:
                return cached

            payload = await self._request(safe_path, clean_params)
            await self._store(key, payload, cache_ttl)
            return copy.deepcopy(payload)

    async def _http_client(self) -> httpx.AsyncClient:
        client = self._client
        if client is not None and not client.is_closed:
            return client

        async with self._client_lock:
            client = self._client
            if client is None or client.is_closed:
                timeout = httpx.Timeout(
                    self.timeout_seconds,
                    connect=min(5.0, self.timeout_seconds),
                    read=self.timeout_seconds,
                    write=min(5.0, self.timeout_seconds),
                    pool=min(3.0, self.timeout_seconds),
                )
                self._client = httpx.AsyncClient(
                    timeout=timeout,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                    follow_redirects=False,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": ANINEXUS_USER_AGENT,
                    },
                )
            return self._client

    async def aclose(self) -> None:
        async with self._client_lock:
            client = self._client
            self._client = None
        if client is not None and not client.is_closed:
            await client.aclose()

    async def _request(self, path: str, params: Mapping[str, Any]) -> Any:
        client = await self._http_client()
        url = f"{self.base_url}{path}"

        for attempt in range(2):
            try:
                response = await client.get(url, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 0:
                    await asyncio.sleep(0.18)
                    continue
                raise AniNexusError(
                    "aninexus_unavailable",
                    status_code=503,
                    retryable=True,
                ) from exc

            if response.status_code in {429, 502, 503, 504} and attempt == 0:
                retry_after = response.headers.get("retry-after", "")
                try:
                    delay = max(0.1, min(1.0, float(retry_after)))
                except (TypeError, ValueError):
                    delay = 0.2
                await asyncio.sleep(delay)
                continue

            if response.status_code == 404:
                raise AniNexusError(
                    "aninexus_not_found",
                    status_code=404,
                    upstream_status=404,
                )
            if response.status_code < 200 or response.status_code >= 300:
                raise AniNexusError(
                    "aninexus_upstream_error",
                    status_code=502,
                    upstream_status=response.status_code,
                    retryable=response.status_code >= 500 or response.status_code == 429,
                )

            content_type = str(response.headers.get("content-type") or "").lower()
            if "application/json" not in content_type:
                raise AniNexusError("aninexus_invalid_response", status_code=502)

            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > 5_000_000:
                        raise AniNexusError("aninexus_response_too_large", status_code=502)
                except ValueError:
                    pass
            if len(response.content) > 5_000_000:
                raise AniNexusError("aninexus_response_too_large", status_code=502)

            try:
                return response.json()
            except ValueError as exc:
                raise AniNexusError("aninexus_invalid_json", status_code=502) from exc

        raise AniNexusError("aninexus_unavailable", status_code=503, retryable=True)

    async def health(self) -> Any:
        return await self.get_json("/health", cache_ttl=10)

    async def home(self, *, season: str = "", year: int | None = None) -> Any:
        return await self.get_json(
            "/api/home",
            params={"season": season, "year": year},
            cache_ttl=45,
        )

    async def catalog(
        self,
        *,
        page: int = 1,
        per_page: int = 24,
        search: str = "",
        genre: str = "",
        format_name: str = "",
        season: str = "",
        year: int | None = None,
        status: str = "",
        sort: str = "POPULAR",
    ) -> Any:
        return await self.get_json(
            "/api/catalog",
            params={
                "page": page,
                "perPage": per_page,
                "search": search,
                "genre": genre,
                "format": format_name,
                "season": season,
                "year": year,
                "status": status,
                "sort": sort,
            },
            cache_ttl=45,
        )

    async def reading(
        self,
        *,
        page: int = 1,
        per_page: int = 24,
        search: str = "",
        genre: str = "",
        format_name: str = "",
        status: str = "",
        sort: str = "POPULAR",
    ) -> Any:
        return await self.get_json(
            "/api/reading",
            params={
                "page": page,
                "perPage": per_page,
                "search": search,
                "genre": genre,
                "format": format_name,
                "status": status,
                "sort": sort,
            },
            cache_ttl=45,
        )

    async def schedule(self, *, start: int, end: int) -> Any:
        return await self.get_json(
            "/api/schedule",
            params={"start": start, "end": end},
            cache_ttl=45,
        )

    async def anime(self, media_id: int) -> Any:
        return await self.get_json(f"/api/anime/{int(media_id)}", cache_ttl=300)

    async def manga(self, media_id: int) -> Any:
        return await self.get_json(f"/api/manga/{int(media_id)}", cache_ttl=300)


aninexus_client = AniNexusClient()
