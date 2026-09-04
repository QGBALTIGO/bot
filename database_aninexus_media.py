from __future__ import annotations

import json
from threading import Lock
from typing import Any, Dict, List, Optional

from psycopg.rows import dict_row

from database_core import pool

_TABLE_LOCK = Lock()
_TABLE_READY = False


def ensure_media_tables() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    with _TABLE_LOCK:
        if _TABLE_READY:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_character_assets (
                        asset_id BIGSERIAL PRIMARY KEY,
                        character_id BIGINT NOT NULL,
                        source_url TEXT,
                        storage_url TEXT NOT NULL,
                        content_sha256 TEXT NOT NULL,
                        output_width INTEGER NOT NULL,
                        output_height INTEGER NOT NULL,
                        crop_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        source_kind TEXT NOT NULL DEFAULT 'upload',
                        status TEXT NOT NULL DEFAULT 'active',
                        is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                        uploaded_by BIGINT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        activated_at TIMESTAMPTZ
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_aninexus_character_assets_character
                    ON aninexus_character_assets (character_id, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_aninexus_character_assets_primary
                    ON aninexus_character_assets (character_id)
                    WHERE is_primary = TRUE AND status = 'active'
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_aninexus_character_assets_hash
                    ON aninexus_character_assets (character_id, content_sha256)
                    WHERE status = 'active'
                    """
                )
            conn.commit()
        _TABLE_READY = True


def _serialize(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    item = dict(row)
    for key in ("created_at", "activated_at"):
        value = item.get(key)
        item[key] = value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)
    metadata = item.get("crop_metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    item["crop_metadata"] = metadata if isinstance(metadata, dict) else {}
    item["asset_id"] = int(item.get("asset_id") or 0)
    item["character_id"] = int(item.get("character_id") or 0)
    item["uploaded_by"] = int(item.get("uploaded_by") or 0)
    item["is_primary"] = bool(item.get("is_primary"))
    return item


def list_character_assets(character_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    ensure_media_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM aninexus_character_assets
                WHERE character_id = %s AND status = 'active'
                ORDER BY is_primary DESC, activated_at DESC NULLS LAST, created_at DESC
                LIMIT %s
                """,
                (int(character_id), max(1, min(int(limit), 100))),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
            conn.commit()
    return [item for item in (_serialize(row) for row in rows) if item]


def get_asset(asset_id: int) -> Optional[Dict[str, Any]]:
    ensure_media_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM aninexus_character_assets WHERE asset_id = %s LIMIT 1",
                (int(asset_id),),
            )
            row = _serialize(cur.fetchone())
            conn.commit()
            return row
