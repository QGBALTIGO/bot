from __future__ import annotations

import asyncio

from utils import worker_supervisor
from utils.system_health import worker_snapshot


class FakeApp:
    def __init__(self) -> None:
        self.bot_data = {}


def test_supervisor_restarts_after_exception(monkeypatch) -> None:
    calls = 0

    async def fake_sleep(_seconds: float) -> None:
        return None

    async def flaky(_app) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(worker_supervisor.asyncio, "sleep", fake_sleep)

    app = FakeApp()
    asyncio.run(
        worker_supervisor.supervise_worker(
            app,
            name="telegram_outbox",
            worker=flaky,
        )
    )

    assert calls == 2
    state = app.bot_data["worker_supervisor_state"]["telegram_outbox"]
    assert state["status"] == "stopped"
    assert state["restart_count"] == 1
    assert state["last_error"] == ""


def test_health_prefers_supervisor_state_over_wrapper_task() -> None:
    async def scenario() -> None:
        sleeping = asyncio.create_task(asyncio.sleep(30))
        app = FakeApp()
        app.bot_data.update(
            {
                "terms_channel_worker": sleeping,
                "telegram_outbox_worker": sleeping,
                "aninexus_news_worker": sleeping,
                "worker_supervisor_state": {
                    "telegram_outbox": {
                        "ok": False,
                        "status": "restarting",
                        "restart_count": 3,
                        "last_error": "RuntimeError",
                        "next_restart_seconds": 4,
                    }
                },
            }
        )
        try:
            snapshot = worker_snapshot(app)
            assert snapshot["telegram_outbox"]["ok"] is False
            assert snapshot["telegram_outbox"]["status"] == "restarting"
            assert snapshot["telegram_outbox"]["restart_count"] == 3
            assert snapshot["telegram_outbox"]["error"] == "RuntimeError"
            assert snapshot["telegram_outbox"]["next_restart_seconds"] == 4
        finally:
            sleeping.cancel()
            try:
                await sleeping
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())
