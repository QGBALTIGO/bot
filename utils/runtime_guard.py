from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict


@dataclass
class _RateEntry:
    count: int
    reset_at: float
    touched_at: float


class AsyncRateLimiter:
    """Bounded, async-safe fixed-window limiter used by Telegram handlers."""

    def __init__(self, *, max_keys: int = 4096, cleanup_interval: float = 30.0) -> None:
        self.max_keys = max(1, int(max_keys))
        self.cleanup_interval = max(0.25, float(cleanup_interval))
        self._entries: OrderedDict[str, _RateEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._last_cleanup = 0.0

    async def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        safe_key = str(key or "").strip()
        if not safe_key or int(limit) <= 0:
            return False

        now = time.monotonic()
        window = max(0.05, float(window_seconds))
        async with self._lock:
            self._cleanup(now)
            entry = self._entries.get(safe_key)

            if entry is None or now >= entry.reset_at:
                self._entries[safe_key] = _RateEntry(
                    count=1,
                    reset_at=now + window,
                    touched_at=now,
                )
                self._entries.move_to_end(safe_key)
                self._enforce_bound(protected_key=safe_key)
                return True

            entry.touched_at = now
            self._entries.move_to_end(safe_key)
            if entry.count >= int(limit):
                return False

            entry.count += 1
            return True

    async def size(self) -> int:
        now = time.monotonic()
        async with self._lock:
            self._cleanup(now, force=True)
            return len(self._entries)

    def _cleanup(self, now: float, *, force: bool = False) -> None:
        if not force and now - self._last_cleanup < self.cleanup_interval and len(self._entries) < self.max_keys:
            return
        expired = [key for key, entry in self._entries.items() if now >= entry.reset_at]
        for key in expired:
            self._entries.pop(key, None)
        self._last_cleanup = now
        self._enforce_bound()

    def _enforce_bound(self, *, protected_key: str = "") -> None:
        if len(self._entries) <= self.max_keys:
            return
        for key in list(self._entries):
            if len(self._entries) <= self.max_keys:
                break
            if key == protected_key and len(self._entries) > 1:
                continue
            self._entries.pop(key, None)


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    users: int
    last_used: float


class _ManagedLock:
    def __init__(self, manager: "AsyncKeyedLockManager", key: str, entry: _LockEntry) -> None:
        self._manager = manager
        self._key = key
        self._entry = entry
        self._released = False

    def locked(self) -> bool:
        return self._entry.lock.locked()

    def release(self) -> None:
        if self._released:
            raise RuntimeError("Lock is not acquired.")
        self._entry.lock.release()
        self._released = True
        self._manager._schedule_release(self._key, self._entry)

    async def __aenter__(self) -> "_ManagedLock":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.release()


class AsyncKeyedLockManager:
    """Per-key serialization with bounded metadata and cancellation safety."""

    def __init__(self, *, max_keys: int = 4096, idle_seconds: float = 120.0) -> None:
        self.max_keys = max(1, int(max_keys))
        self.idle_seconds = max(1.0, float(idle_seconds))
        self._locks: Dict[str, _LockEntry] = {}
        self._guard = asyncio.Lock()

    async def acquire(self, key: str) -> _ManagedLock:
        safe_key = str(key or "").strip()
        if not safe_key:
            raise ValueError("lock key cannot be empty")

        now = time.monotonic()
        async with self._guard:
            self._cleanup(now)
            entry = self._locks.get(safe_key)
            if entry is None:
                entry = _LockEntry(lock=asyncio.Lock(), users=0, last_used=now)
                self._locks[safe_key] = entry
            entry.users += 1
            entry.last_used = now

        try:
            await entry.lock.acquire()
        except BaseException:
            async with self._guard:
                current = self._locks.get(safe_key)
                if current is entry:
                    current.users = max(0, current.users - 1)
                    current.last_used = time.monotonic()
                    self._cleanup(current.last_used)
            raise

        return _ManagedLock(self, safe_key, entry)

    async def size(self) -> int:
        async with self._guard:
            self._cleanup(time.monotonic(), force=True)
            return len(self._locks)

    def _schedule_release(self, key: str, entry: _LockEntry) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            entry.users = max(0, entry.users - 1)
            entry.last_used = time.monotonic()
            return
        loop.create_task(self._mark_released(key, entry))

    async def _mark_released(self, key: str, entry: _LockEntry) -> None:
        async with self._guard:
            current = self._locks.get(key)
            if current is not entry:
                return
            current.users = max(0, current.users - 1)
            current.last_used = time.monotonic()
            self._cleanup(current.last_used)

    def _cleanup(self, now: float, *, force: bool = False) -> None:
        removable = [
            key
            for key, entry in self._locks.items()
            if entry.users <= 0
            and not entry.lock.locked()
            and (force or now - entry.last_used >= self.idle_seconds)
        ]
        for key in removable:
            self._locks.pop(key, None)

        if len(self._locks) <= self.max_keys:
            return

        candidates = sorted(
            (
                (key, entry)
                for key, entry in self._locks.items()
                if entry.users <= 0 and not entry.lock.locked()
            ),
            key=lambda item: item[1].last_used,
        )
        for key, _ in candidates:
            if len(self._locks) <= self.max_keys:
                break
            self._locks.pop(key, None)


# Backwards-compatible names used throughout the current handlers.
InMemoryRateLimiter = AsyncRateLimiter
KeyedLockManager = AsyncKeyedLockManager

rate_limiter = AsyncRateLimiter()
lock_manager = AsyncKeyedLockManager()
