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


def create_and_activate_asset(
    character_id: int,
    source_url: str,
    storage_url: str,
    content_sha256: str,
    output_width: int,
    output_height: int,
    crop_metadata: Dict[str, Any],
    source_kind: str,
    uploaded_by: int,
) -> Dict[str, Any]:
    ensure_media_tables()
    character_id = int(character_id)
    uploaded_by = int(uploaded_by)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (character_id,))
                cur.execute(
                    """
                    SELECT asset_id FROM aninexus_character_assets
                    WHERE character_id = %s
                      AND content_sha256 = %s
                      AND status = 'active'
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (character_id, str(content_sha256)),
                )
                existing = cur.fetchone()
                if existing:
                    asset_id = int(existing.get("asset_id") or 0)
                    cur.execute(
                        "UPDATE aninexus_character_assets SET is_primary = FALSE WHERE character_id = %s",
                        (character_id,),
                    )
                    cur.execute(
                        """
                        UPDATE aninexus_character_assets
                        SET is_primary = TRUE, activated_at = NOW()
                        WHERE asset_id = %s
                        RETURNING *
                        """,
                        (asset_id,),
                    )
                    row = cur.fetchone()
                    final_url = str((row or {}).get("storage_url") or storage_url)
                else:
                    cur.execute(
                        "UPDATE aninexus_character_assets SET is_primary = FALSE WHERE character_id = %s",
                        (character_id,),
                    )
                    cur.execute(
                        """
                        INSERT INTO aninexus_character_assets (
                            character_id, source_url, storage_url, content_sha256,
                            output_width, output_height, crop_metadata,
                            source_kind, status, is_primary, uploaded_by, activated_at
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'active',TRUE,%s,NOW())
                        RETURNING *
                        """,
                        (
                            character_id,
                            str(source_url or "").strip() or None,
                            str(storage_url).strip(),
                            str(content_sha256),
                            int(output_width),
                            int(output_height),
                            json.dumps(crop_metadata or {}, ensure_ascii=False),
                            str(source_kind or "upload"),
                            uploaded_by,
                        ),
                    )
                    row = cur.fetchone()
                    final_url = str(storage_url).strip()

                cur.execute(
                    """
                    INSERT INTO global_character_images (character_id, image_url, updated_by, updated_at)
                    VALUES (%s,%s,%s,NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET image_url = EXCLUDED.image_url,
                                  updated_by = EXCLUDED.updated_by,
                                  updated_at = NOW()
                    """,
                    (character_id, final_url, uploaded_by),
                )
                conn.commit()
                return _serialize(row) or {}
            except Exception:
                conn.rollback()
                raise


def activate_asset(asset_id: int, activated_by: int) -> Optional[Dict[str, Any]]:
    ensure_media_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT * FROM aninexus_character_assets
                    WHERE asset_id = %s AND status = 'active'
                    FOR UPDATE
                    """,
                    (int(asset_id),),
                )
                asset = dict(cur.fetchone() or {})
                if not asset:
                    conn.rollback()
                    return None
                character_id = int(asset.get("character_id") or 0)
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (character_id,))
                cur.execute(
                    "UPDATE aninexus_character_assets SET is_primary = FALSE WHERE character_id = %s",
                    (character_id,),
                )
                cur.execute(
                    """
                    UPDATE aninexus_character_assets
                    SET is_primary = TRUE, activated_at = NOW()
                    WHERE asset_id = %s
                    RETURNING *
                    """,
                    (int(asset_id),),
                )
                row = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO global_character_images (character_id, image_url, updated_by, updated_at)
                    VALUES (%s,%s,%s,NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET image_url = EXCLUDED.image_url,
                                  updated_by = EXCLUDED.updated_by,
                                  updated_at = NOW()
                    """,
                    (character_id, str(asset.get("storage_url") or ""), int(activated_by)),
                )
                conn.commit()
                return _serialize(row)
            except Exception:
                conn.rollback()
                raise
