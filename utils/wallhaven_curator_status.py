from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row

from database import pool
from utils.wallhaven_bulk_curator import (
    ENABLED,
    MAX_CHARACTER_TAGS,
    MIN_CHARACTER_MATCH,
    MIN_HEIGHT,
    MIN_SCORE,
    MIN_SERIES_MATCH,
    MIN_WIDTH,
    RATIO_TOLERANCE,
    TARGET_RATIO,
)


router = APIRouter()


@router.get("/api/system/wallhaven-curator-status")
def wallhaven_curator_status():
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT to_regclass('public.wallhaven_character_curation') AS table_name")
                row = cur.fetchone() or {}
                if not row.get("table_name"):
                    return JSONResponse({
                        "ok": True,
                        "ready": False,
                        "counts": {},
                        "config": _config_payload(),
                    })

                cur.execute(
                    """
                    SELECT status, COUNT(*)::BIGINT AS total
                    FROM wallhaven_character_curation
                    GROUP BY status
                    ORDER BY status
                    """
                )
                counts = {
                    str(item.get("status") or "unknown"): int(item.get("total") or 0)
                    for item in (cur.fetchall() or [])
                }
                cur.execute(
                    """
                    SELECT MAX(updated_at) AS last_update,
                           COUNT(*) FILTER (WHERE image_url LIKE 'https://w.wallhaven.cc/%')::BIGINT AS wallhaven_urls
                    FROM wallhaven_character_curation
                    """
                )
                meta = cur.fetchone() or {}

        return JSONResponse({
            "ok": True,
            "ready": True,
            "counts": counts,
            "wallhaven_urls": int(meta.get("wallhaven_urls") or 0),
            "last_update": meta.get("last_update").isoformat() if meta.get("last_update") else None,
            "config": _config_payload(),
        })
    except Exception as exc:
        return JSONResponse({
            "ok": False,
            "ready": False,
            "error": type(exc).__name__,
            "config": _config_payload(),
        }, status_code=500)


def _config_payload() -> dict:
    return {
        "enabled": bool(ENABLED),
        "target_ratio": round(float(TARGET_RATIO), 4),
        "ratio_tolerance": round(float(RATIO_TOLERANCE), 4),
        "min_width": int(MIN_WIDTH),
        "min_height": int(MIN_HEIGHT),
        "min_score": float(MIN_SCORE),
        "character_match": float(MIN_CHARACTER_MATCH),
        "series_match": float(MIN_SERIES_MATCH),
        "max_character_tags": int(MAX_CHARACTER_TAGS),
        "purity": "sfw",
        "category": "anime",
    }
