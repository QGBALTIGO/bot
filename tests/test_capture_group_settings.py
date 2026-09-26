from __future__ import annotations

import pytest

import source_features.capture_groups as groups


def test_capture_group_defaults(monkeypatch) -> None:
    calls = []
    def fake_run(sql, params=(), fetch=None):
        calls.append((sql, params, fetch))
        if fetch == "one":
            return None
        return None
    monkeypatch.setattr(groups, "run", fake_run)
    state = groups.capture_group_settings(-100, 90)
    assert state == {"enabled": True, "message_threshold": 90}
    assert any("CREATE TABLE IF NOT EXISTS source_capture_group_settings" in sql for sql, _, _ in calls)


def test_capture_group_saved_values(monkeypatch) -> None:
    def fake_run(sql, params=(), fetch=None):
        if fetch == "one":
            return {"enabled": False, "message_threshold": 120}
        return None
    monkeypatch.setattr(groups, "run", fake_run)
    assert groups.capture_group_settings(-100) == {"enabled": False, "message_threshold": 120}


@pytest.mark.parametrize("value", [0, 19, 501, 1000])
def test_capture_group_rejects_unsafe_threshold(monkeypatch, value) -> None:
    monkeypatch.setattr(groups, "ensure_capture_group_settings", lambda: None)
    monkeypatch.setattr(groups, "capture_group_settings", lambda chat_id: {"enabled": True, "message_threshold": 75})
    with pytest.raises(ValueError):
        groups.save_capture_group_settings(-100, 1, message_threshold=value)
