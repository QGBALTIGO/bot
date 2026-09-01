from __future__ import annotations

import asyncio

from utils.runtime_guard import AsyncKeyedLockManager, AsyncRateLimiter


def test_rate_limiter_enforces_window() -> None:
    async def scenario() -> None:
        limiter = AsyncRateLimiter(max_keys=100, cleanup_interval=60)
        assert await limiter.allow(key="user:1", limit=2, window_seconds=10)
        assert await limiter.allow(key="user:1", limit=2, window_seconds=10)
        assert not await limiter.allow(key="user:1", limit=2, window_seconds=10)

    asyncio.run(scenario())


def test_rate_limiter_bounds_key_count() -> None:
    async def scenario() -> None:
        limiter = AsyncRateLimiter(max_keys=2, cleanup_interval=60)
        assert await limiter.allow(key="a", limit=1, window_seconds=10)
        assert await limiter.allow(key="b", limit=1, window_seconds=10)
        assert await limiter.allow(key="c", limit=1, window_seconds=10)
        assert await limiter.size() <= 2

    asyncio.run(scenario())


def test_keyed_lock_serializes_same_key() -> None:
    async def scenario() -> None:
        manager = AsyncKeyedLockManager(max_keys=100, idle_seconds=30)
        inside = 0
        peak_inside = 0

        async def worker() -> None:
            nonlocal inside, peak_inside
            lock = await manager.acquire("same-key")
            try:
                inside += 1
                peak_inside = max(peak_inside, inside)
                await asyncio.sleep(0.01)
                inside -= 1
            finally:
                lock.release()

        await asyncio.gather(*(worker() for _ in range(8)))
        assert peak_inside == 1

    asyncio.run(scenario())


def test_keyed_lock_allows_different_keys_in_parallel() -> None:
    async def scenario() -> None:
        manager = AsyncKeyedLockManager(max_keys=100, idle_seconds=30)
        both_inside = asyncio.Event()
        entered = 0

        async def worker(key: str) -> None:
            nonlocal entered
            lock = await manager.acquire(key)
            try:
                entered += 1
                if entered == 2:
                    both_inside.set()
                await asyncio.wait_for(both_inside.wait(), timeout=1)
            finally:
                lock.release()

        await asyncio.gather(worker("a"), worker("b"))
        assert entered == 2

    asyncio.run(scenario())
