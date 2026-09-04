from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

WorkerCallable = Callable[[Any], Awaitable[None]]


def _max_restart_seconds() -> int:
    try:
        value = int(os.getenv("WORKER_RESTART_MAX_SECONDS", "30"))
    except (TypeError, ValueError):
        value = 30
    return max(2, min(300, value))


def _state_store(app) -> dict[str, dict[str, Any]]:
    store = app.bot_data.get("worker_supervisor_state")
    if not isinstance(store, dict):
        store = {}
        app.bot_data["worker_supervisor_state"] = store
    return store


def _set_state(app, name: str, **values: Any) -> None:
    store = _state_store(app)
    current = dict(store.get(name) or {})
    current.update(values)
    current["updated_monotonic"] = time.monotonic()
    store[name] = current


async def supervise_worker(
    app,
    *,
    name: str,
    worker: WorkerCallable,
    restart_on_return: bool = False,
) -> None:
    """Run a worker and restart it after failures with bounded exponential backoff.

    A normal return is treated as an intentional stop unless ``restart_on_return``
    is explicitly enabled. This lets feature workers exit cleanly when disabled by
    configuration while still recovering from exceptions automatically.
    """

    restart_count = 0
    max_delay = _max_restart_seconds()

    while True:
        _set_state(
            app,
            name,
            ok=True,
            status="running",
            restart_count=restart_count,
            last_error="",
            next_restart_seconds=0,
        )

        try:
            await worker(app)
        except asyncio.CancelledError:
            _set_state(app, name, ok=True, status="cancelled")
            raise
        except Exception as exc:
            restart_count += 1
            delay = min(max_delay, max(1, 2 ** min(restart_count - 1, 8)))
            _set_state(
                app,
                name,
                ok=False,
                status="restarting",
                restart_count=restart_count,
                last_error=type(exc).__name__,
                next_restart_seconds=delay,
            )
            print(
                f"[worker-supervisor] name={name} failure={type(exc).__name__} "
                f"restart_in={delay}s count={restart_count}",
                flush=True,
            )
            await asyncio.sleep(delay)
            continue

        if not restart_on_return:
            _set_state(
                app,
                name,
                ok=True,
                status="stopped",
                restart_count=restart_count,
                last_error="",
                next_restart_seconds=0,
            )
            return

        restart_count += 1
        delay = min(max_delay, max(1, 2 ** min(restart_count - 1, 8)))
        _set_state(
            app,
            name,
            ok=False,
            status="restarting",
            restart_count=restart_count,
            last_error="worker_returned",
            next_restart_seconds=delay,
        )
        print(
            f"[worker-supervisor] name={name} returned restart_in={delay}s "
            f"count={restart_count}",
            flush=True,
        )
        await asyncio.sleep(delay)
