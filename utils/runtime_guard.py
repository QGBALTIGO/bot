import asyncio
import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class _RateEntry:
    count: int
    reset_at: float


class InMemoryRateLimiter:
    """Simple, async-safe fixed-window rate limiter for bot handlers."""

    def __init__(self):
        self._entries: Dict[str, _RateEntry] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        if limit <= 0:
            return False

        now = time.monotonic()
        async with self._lock:
            entry = self._entries.get(key)

            if entry is None or now >= entry.reset_at:
                self._entries[key] = _RateEntry(count=1, reset_at=now + window_seconds)
                self._prune(now)
                return True

            if entry.count >= limit:
                self._prune(now)
                return False

            entry.count += 1
            self._prune(now)
            return True

    def _prune(self, now: float) -> None:
        if len(self._entries) < 2048:
            return

        expired = [k for k, v in self._entries.items() if now >= v.reset_at]
        for k in expired:
            self._entries.pop(k, None)


class KeyedLockManager:
    """Provides per-key locks to serialize critical sections by resource."""

    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def acquire(self, key: str):
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
        await lock.acquire()
        return lock


rate_limiter = InMemoryRateLimiter()
lock_manager = KeyedLockManager()
