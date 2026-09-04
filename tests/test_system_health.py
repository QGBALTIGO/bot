from __future__ import annotations

import asyncio

from utils import system_health


def test_application_version_prefers_railway_commit(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_VERSION", "fallback-version")
    monkeypatch.setenv("GIT_COMMIT_SHA", "git-commit")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "1234567890abcdef")

    assert system_health.application_version() == "1234567890ab"


def test_application_version_falls_back_cleanly(monkeypatch) -> None:
    for name in ("SOURCE_VERSION", "GIT_COMMIT_SHA", "RAILWAY_GIT_COMMIT_SHA"):
        monkeypatch.delenv(name, raising=False)

    assert system_health.application_version() == "unknown"


def test_worker_snapshot_reports_running_and_missing_tasks() -> None:
    async def scenario() -> None:
        running = asyncio.create_task(asyncio.sleep(30))

        class App:
            bot_data = {
                "terms_channel_worker": running,
                "telegram_outbox_worker": running,
            }

        try:
            snapshot = system_health.worker_snapshot(App())
            assert snapshot["channel_verification"]["status"] == "running"
            assert snapshot["telegram_outbox"]["ok"] is True
            assert snapshot["aninexus_news"]["status"] == "missing"
        finally:
            running.cancel()
            try:
                await running
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())


def test_uptime_is_non_negative() -> None:
    assert system_health.uptime_seconds() >= 0
