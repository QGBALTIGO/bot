from __future__ import annotations

from psycopg.errors import UndefinedTable
from psycopg.rows import dict_row

from database import (
    delete_global_character_image,
    get_all_global_character_images,
    pool,
)


def cleanup_legacy_wallhaven_global_images() -> int:
    """Remove only DB image overrides created by the retired Wallhaven worker.

    A row is removed only when the current global image URL is byte-for-byte
    equal to the URL that the legacy curator recorded as `applied`. Manual DB
    overrides with a different URL are never touched.
    """
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT character_id, image_url
                    FROM wallhaven_character_curation
                    WHERE status = 'applied'
                      AND image_url <> ''
                    """
                )
                legacy_rows = [dict(row) for row in (cur.fetchall() or [])]
    except UndefinedTable:
        return 0

    if not legacy_rows:
        return 0

    current = get_all_global_character_images()
    removed_ids: list[int] = []

    for row in legacy_rows:
        character_id = int(row.get("character_id") or 0)
        legacy_url = str(row.get("image_url") or "").strip()
        current_url = str(current.get(character_id) or "").strip()
        if character_id <= 0 or not legacy_url:
            continue
        if not current_url or current_url != legacy_url:
            continue

        delete_global_character_image(character_id)
        removed_ids.append(character_id)

    if removed_ids:
        try:
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE wallhaven_character_curation
                        SET status = 'legacy_removed',
                            updated_at = NOW()
                        WHERE character_id = ANY(%s)
                          AND status = 'applied'
                        """,
                        (removed_ids,),
                    )
                conn.commit()
        except UndefinedTable:
            pass

        try:
            from cards_service import reload_cards_cache

            reload_cards_cache()
        except Exception:
            pass

    print(
        f"[wallhaven-legacy-cleanup] legacy_rows={len(legacy_rows)} removed={len(removed_ids)}",
        flush=True,
    )
    return len(removed_ids)
