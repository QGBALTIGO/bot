import asyncio
import time
import weakref
from dataclasses import dataclass
from typing import Dict


@dataclass
class _RateEntry:
    count: int
    reset_at: float


class InMemoryRateLimiter:
    """Async-safe fixed-window rate limiter with stale-entry cleanup."""

    def __init__(self, prune_threshold: int = 1024):
        self._entries: Dict[str, _RateEntry] = {}
        self._lock = asyncio.Lock()
        self._prune_threshold = max(128, int(prune_threshold))
        self._operations = 0

    async def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        if limit <= 0 or window_seconds <= 0:
            return False

        key = str(key or "").strip()
        if not key:
            return False

        now = time.monotonic()
        async with self._lock:
            self._operations += 1
            self._maybe_prune(now)

            entry = self._entries.get(key)
            if entry is None or now >= entry.reset_at:
                self._entries[key] = _RateEntry(
                    count=1,
                    reset_at=now + window_seconds,
                )
                return True

            if entry.count >= limit:
                return False

            entry.count += 1
            return True

    def _maybe_prune(self, now: float) -> None:
        if (
            len(self._entries) < self._prune_threshold
            and self._operations % 256 != 0
        ):
            return

        expired = [
            key
            for key, entry in self._entries.items()
            if now >= entry.reset_at
        ]
        for key in expired:
            self._entries.pop(key, None)


class KeyedLockManager:
    """Provides per-key locks without retaining inactive keys forever."""

    def __init__(self):
        # Active owners/waiters keep strong references to their lock. Once no
        # coroutine uses a key anymore, the weak mapping can discard it safely.
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._guard = asyncio.Lock()

    async def acquire(self, key: str) -> asyncio.Lock:
        key = str(key or "").strip()
        if not key:
            raise ValueError("lock key cannot be empty")

        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock

        await lock.acquire()
        return lock


rate_limiter = InMemoryRateLimiter()
lock_manager = KeyedLockManager()
