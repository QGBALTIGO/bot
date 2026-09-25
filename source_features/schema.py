"""Versioned additive migrations, serialized across the existing bot and HTTP services."""

from pathlib import Path
from database_core import pool


def migrate() -> None:
    path = Path(__file__).resolve().parents[1] / "migrations" / "001_collecting.sql"
    with pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (73420001,))
        cur.execute(
            "CREATE TABLE IF NOT EXISTS source_feature_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        )
        cur.execute(
            "SELECT 1 FROM source_feature_migrations WHERE version=%s",
            ("001_collecting",),
        )
        if cur.fetchone():
            return
        cur.execute(path.read_text(encoding="utf-8"))
        cur.execute(
            "INSERT INTO source_feature_migrations(version) VALUES (%s)",
            ("001_collecting",),
        )
