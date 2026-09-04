from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATION_NAME_RE = re.compile(r"^(?P<version>\d{3,})_(?P<name>[a-z0-9][a-z0-9_-]*)\.sql$")
# Constant application-level lock id. PostgreSQL advisory locks are session scoped.
_MIGRATION_LOCK_ID = 2026090401


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    sql: str
    checksum: str


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    if not directory.exists():
        return []

    migrations: list[Migration] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_NAME_RE.match(path.name)
        if not match:
            continue
        version = match.group("version")
        if version in seen:
            raise RuntimeError(f"duplicate migration version: {version}")
        seen.add(version)
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                sql=sql,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            )
        )
    return migrations


def _create_history_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _load_applied(cur) -> dict[str, str]:
    cur.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
    return {str(row[0]): str(row[1]) for row in (cur.fetchall() or [])}


def _validate_applied_checksums(migrations: Iterable[Migration], applied: dict[str, str]) -> None:
    for migration in migrations:
        old_checksum = applied.get(migration.version)
        if old_checksum is not None and old_checksum != migration.checksum:
            raise RuntimeError(
                f"migration {migration.version}_{migration.name} changed after being applied; "
                "create a new migration instead"
            )


def apply_migrations(directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending SQL migrations once, safely across bot/webapp processes."""

    migrations = discover_migrations(directory)
    if not migrations:
        return []

    from database_core import pool

    applied_now: list[str] = []
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_ID,))
            try:
                _create_history_table(cur)
                conn.commit()
                applied = _load_applied(cur)
                _validate_applied_checksums(migrations, applied)

                for migration in migrations:
                    if migration.version in applied:
                        continue
                    try:
                        # prepare=False forces the simple-query protocol, which safely accepts
                        # migration files containing multiple SQL statements.
                        cur.execute(migration.sql, prepare=False)
                        cur.execute(
                            """
                            INSERT INTO schema_migrations (version, name, checksum)
                            VALUES (%s, %s, %s)
                            """,
                            (migration.version, migration.name, migration.checksum),
                        )
                        conn.commit()
                        applied_now.append(migration.version)
                    except Exception:
                        conn.rollback()
                        raise
            finally:
                try:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_ID,))
                    conn.commit()
                except Exception:
                    conn.rollback()

    return applied_now
