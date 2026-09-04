from __future__ import annotations

from utils import health_monitor


def test_alert_target_prefers_explicit_chat(monkeypatch) -> None:
    monkeypatch.setenv("BOT_OWNER_ID", "123")
    monkeypatch.setenv("SOURCE_ALERT_CHAT_ID", "-100999")
    assert health_monitor.alert_target() == -100999


def test_alert_target_falls_back_to_owner(monkeypatch) -> None:
    monkeypatch.delenv("SOURCE_ALERT_CHAT_ID", raising=False)
    monkeypatch.setenv("BOT_OWNER_ID", "456")
    assert health_monitor.alert_target() == 456


def test_alert_target_rejects_unsafe_free_text(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_ALERT_CHAT_ID", "not-a-chat")
    assert health_monitor.alert_target() is None


def test_evaluate_components_identifies_failed_worker() -> None:
    snapshot = health_monitor.evaluate_components(
        database={"ok": True, "status": "healthy"},
        telegram_ok=True,
        workers={
            "telegram_outbox": {"ok": True, "status": "running"},
            "aninexus_news": {"ok": False, "status": "failed"},
        },
    )
    assert snapshot["ok"] is False
    assert snapshot["failed"] == ("worker:aninexus_news",)


def test_evaluate_components_is_healthy_when_everything_runs() -> None:
    snapshot = health_monitor.evaluate_components(
        database={"ok": True, "status": "healthy"},
        telegram_ok=True,
        workers={
            "telegram_outbox": {"ok": True, "status": "running"},
            "aninexus_news": {"ok": True, "status": "running"},
        },
    )
    assert snapshot["ok"] is True
    assert snapshot["failed"] == ()
