from __future__ import annotations

from pathlib import Path

import pytest

from database_migrations import (
    Migration,
    _validate_applied_checksums,
    discover_migrations,
)


def test_discover_migrations_orders_versions_and_hashes_content(tmp_path: Path) -> None:
    (tmp_path / "010_second.sql").write_text("SELECT 2;\n", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignored", encoding="utf-8")

    migrations = discover_migrations(tmp_path)

    assert [m.version for m in migrations] == ["001", "010"]
    assert [m.name for m in migrations] == ["first", "second"]
    assert all(len(m.checksum) == 64 for m in migrations)


def test_duplicate_migration_versions_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "001_other.sql").write_text("SELECT 2;", encoding="utf-8")

    with pytest.raises(RuntimeError, match="duplicate migration version"):
        discover_migrations(tmp_path)


def test_applied_migration_cannot_be_silently_edited(tmp_path: Path) -> None:
    path = tmp_path / "001_source.sql"
    path.write_text("SELECT 1;", encoding="utf-8")
    migration = discover_migrations(tmp_path)[0]

    with pytest.raises(RuntimeError, match="changed after being applied"):
        _validate_applied_checksums([migration], {"001": "different-checksum"})


def test_matching_checksum_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "001_source.sql"
    path.write_text("SELECT 1;", encoding="utf-8")
    migration = discover_migrations(tmp_path)[0]

    _validate_applied_checksums([migration], {"001": migration.checksum})
