from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database.py"
PROFILE = ROOT / "database_profile.py"

PROFILE_FUNCTIONS = (
    "create_profile_settings_table",
    "ensure_profile_settings_row",
    "get_profile_settings",
    "get_profile_settings_by_nickname",
    "nickname_exists",
    "set_profile_nickname",
    "set_profile_favorite",
    "set_profile_country",
    "set_profile_language",
    "set_profile_private",
    "set_profile_notifications",
)


def test_profile_persistence_lives_outside_database_monolith() -> None:
    legacy = DATABASE.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")

    assert "from database_profile import (" in legacy
    for name in PROFILE_FUNCTIONS:
        assert f"def {name}(" not in legacy
        assert f"def {name}(" in profile
        assert name in legacy


def test_profile_module_uses_shared_sql_core() -> None:
    profile = PROFILE.read_text(encoding="utf-8")

    assert "from database_core import run as _run" in profile
    assert "ConnectionPool(" not in profile
    assert "pool.connection()" not in profile


def test_profile_schema_contract_is_preserved() -> None:
    profile = PROFILE.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS user_profile_settings" in profile
    assert "nickname TEXT UNIQUE" in profile
    assert "favorite_character_id BIGINT" in profile
    assert "country_code TEXT NOT NULL DEFAULT 'BR'" in profile
    assert "language TEXT NOT NULL DEFAULT 'pt'" in profile
    assert "private_profile BOOLEAN NOT NULL DEFAULT FALSE" in profile
    assert "notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE" in profile
    assert "dado_full_notified BOOLEAN NOT NULL DEFAULT FALSE" in profile
    assert "uq_user_profile_settings_nickname" in profile
    assert "idx_user_profile_settings_nickname_lower" in profile


def test_profile_nickname_rules_are_preserved() -> None:
    profile = PROFILE.read_text(encoding="utf-8")

    assert 'return {"ok": False, "error": "nickname_locked"}' in profile
    assert 'return {"ok": False, "error": "nickname_taken"}' in profile
    assert "WHERE LOWER(nickname) = LOWER(%s)" in profile


def test_cross_domain_account_deletion_stays_outside_profile_module() -> None:
    legacy = DATABASE.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")

    assert "def delete_user_account(" in legacy
    assert "def delete_user_account(" not in profile
