from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class _RateEntry:
    count: int
    reset_at: float
    last_seen: float


class AsyncRateLimiter:
    """Async-safe fixed-window limiter with bounded in-memory state."""

    def __init__(self, *, max_keys: int = 50000, cleanup_interval: float = 60.0):
        self.max_keys = max(1, int(max_keys))
        self.cleanup_interval = max(1.0, float(cleanup_interval))
        self._entries: Dict[str, _RateEntry] = {}
        self._lock = asyncio.Lock()
        self._last_cleanup = 0.0

    def _cleanup_locked(self, now: float, *, reserve_slot: bool = False) -> None:
        should_cleanup = (
            now - self._last_cleanup >= self.cleanup_interval
            or len(self._entries) >= self.max_keys
        )
        if should_cleanup:
            expired = [
                key
                for key, entry in self._entries.items()
                if now >= entry.reset_at
            ]
            for key in expired:
                self._entries.pop(key, None)
            self._last_cleanup = now

        target = self.max_keys - (1 if reserve_slot else 0)
        target = max(0, target)
        if len(self._entries) <= target:
            return

        oldest = sorted(
            self._entries.items(),
            key=lambda item: item[1].last_seen,
        )
        excess = len(self._entries) - target
        for key, _ in oldest[:excess]:
            self._entries.pop(key, None)

    async def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        if limit <= 0:
            return False

        normalized_key = str(key)
        window = max(0.05, float(window_seconds))
        now = time.monotonic()

        async with self._lock:
            entry = self._entries.get(normalized_key)
            if entry is None:
                self._cleanup_locked(now, reserve_slot=True)
                self._entries[normalized_key] = _RateEntry(
                    count=1,
                    reset_at=now + window,
                    last_seen=now,
                )
                return True

            if now >= entry.reset_at:
                entry.count = 1
                entry.reset_at = now + window
                entry.last_seen = now
                self._cleanup_locked(now)
                return True

            entry.last_seen = now
            if entry.count >= int(limit):
                self._cleanup_locked(now)
                return False

            entry.count += 1
            self._cleanup_locked(now)
            return True

    async def size(self) -> int:
        async with self._lock:
            self._cleanup_locked(time.monotonic())
            return len(self._entries)


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    last_used: float


class AsyncKeyedLockManager:
    """Per-key async locks with safe cleanup of idle, unlocked entries."""

    def __init__(self, *, max_keys: int = 20000, idle_seconds: float = 300.0):
        self.max_keys = max(1, int(max_keys))
        self.idle_seconds = max(1.0, float(idle_seconds))
        self._entries: Dict[str, _LockEntry] = {}
        self._guard = asyncio.Lock()

    def _prune_locked(self, now: float, *, reserve_slot: bool = False) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if not entry.lock.locked() and now - entry.last_used >= self.idle_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)

        target = self.max_keys - (1 if reserve_slot else 0)
        target = max(0, target)
        if len(self._entries) <= target:
            return

        removable = sorted(
            (
                (key, entry)
                for key, entry in self._entries.items()
                if not entry.lock.locked()
            ),
            key=lambda item: item[1].last_used,
        )
        excess = len(self._entries) - target
        for key, _ in removable[:excess]:
            self._entries.pop(key, None)

    async def acquire(self, key: str) -> asyncio.Lock:
        normalized_key = str(key)
        now = time.monotonic()

        async with self._guard:
            entry = self._entries.get(normalized_key)
            if entry is None:
                self._prune_locked(now, reserve_slot=True)
                entry = _LockEntry(lock=asyncio.Lock(), last_used=now)
                self._entries[normalized_key] = entry
            else:
                entry.last_used = now
            lock = entry.lock

        await lock.acquire()

        async with self._guard:
            current = self._entries.get(normalized_key)
            if current is not None and current.lock is lock:
                current.last_used = time.monotonic()
        return lock

    async def size(self) -> int:
        async with self._guard:
            self._prune_locked(time.monotonic())
            return len(self._entries)


class InMemoryRateLimiter(AsyncRateLimiter):
    """Compatibility wrapper using deployment defaults."""

    def __init__(self):
        super().__init__(
            max_keys=int(os.getenv("RATE_LIMITER_MAX_KEYS", "50000")),
            cleanup_interval=float(os.getenv("RATE_LIMITER_CLEANUP_SECONDS", "60")),
        )


class KeyedLockManager(AsyncKeyedLockManager):
    """Compatibility wrapper using deployment defaults."""

    def __init__(self):
        super().__init__(
            max_keys=int(os.getenv("LOCK_MANAGER_MAX_KEYS", "20000")),
            idle_seconds=float(os.getenv("LOCK_MANAGER_IDLE_SECONDS", "300")),
        )


rate_limiter = InMemoryRateLimiter()
lock_manager = KeyedLockManager()
