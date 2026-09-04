from __future__ import annotations

from typing import Any, Dict, Optional


def record_primary_character_art(
    character_id: int,
    image_url: str,
    *,
    source_type: str = "manual",
    source_url: str | None = None,
    source_credit: str | None = None,
    source_license: str | None = None,
    variant: str = "default",
    width: int | None = None,
    height: int | None = None,
    sha256: str | None = None,
    perceptual_hash: str | None = None,
    updated_by: int = 0,
) -> Dict[str, Any]:
    """Set a character's active art while keeping ownership tied to character_id.

    `global_character_images` remains the compatibility pointer used by the current
    Source code. `character_art_assets` stores history/provenance for the v2 UI.
    """

    character_id = int(character_id)
    if character_id <= 0:
        raise ValueError("character_id must be positive")
    image_url = str(image_url or "").strip()
    if not image_url.startswith("https://"):
        raise ValueError("image_url must use https")

    source_type = str(source_type or "manual").strip() or "manual"
    variant = str(variant or "default").strip() or "default"
    updated_by = int(updated_by or 0)
    aspect_ratio: Optional[float] = None
    if width and height and int(width) > 0 and int(height) > 0:
        aspect_ratio = float(width) / float(height)

    from database_core import pool

    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT image_url FROM global_character_images WHERE character_id = %s",
                    (character_id,),
                )
                row = cur.fetchone()
                previous_image_url = str(row[0]) if row and row[0] else None

                # Preserve a previous override as historical art before switching.
                if previous_image_url and previous_image_url != image_url:
                    cur.execute(
                        """
                        INSERT INTO character_art_assets (
                            character_id, source_type, image_url, variant, status,
                            is_primary, created_by, source_credit, source_license
                        )
                        VALUES (%s, 'legacy_override', %s, 'legacy', 'archived', FALSE, %s, %s, %s)
                        ON CONFLICT (character_id, image_url) DO UPDATE SET
                            is_primary = FALSE,
                            status = CASE
                                WHEN character_art_assets.status = 'rejected' THEN 'rejected'
                                ELSE 'archived'
                            END,
                            updated_at = NOW()
                        """,
                        (
                            character_id,
                            previous_image_url,
                            updated_by,
                            source_credit,
                            source_license,
                        ),
                    )

                cur.execute(
                    """
                    UPDATE character_art_assets
                    SET is_primary = FALSE, updated_at = NOW()
                    WHERE character_id = %s AND is_primary = TRUE
                    """,
                    (character_id,),
                )

                cur.execute(
                    """
                    INSERT INTO character_art_assets (
                        character_id, source_type, source_url, image_url,
                        width, height, aspect_ratio, sha256, perceptual_hash,
                        variant, status, is_primary, source_credit, source_license,
                        reviewed_by, reviewed_at, created_by
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, 'approved', TRUE, %s, %s,
                        %s, NOW(), %s
                    )
                    ON CONFLICT (character_id, image_url) DO UPDATE SET
                        source_type = EXCLUDED.source_type,
                        source_url = COALESCE(EXCLUDED.source_url, character_art_assets.source_url),
                        width = COALESCE(EXCLUDED.width, character_art_assets.width),
                        height = COALESCE(EXCLUDED.height, character_art_assets.height),
                        aspect_ratio = COALESCE(EXCLUDED.aspect_ratio, character_art_assets.aspect_ratio),
                        sha256 = COALESCE(EXCLUDED.sha256, character_art_assets.sha256),
                        perceptual_hash = COALESCE(EXCLUDED.perceptual_hash, character_art_assets.perceptual_hash),
                        variant = EXCLUDED.variant,
                        status = 'approved',
                        is_primary = TRUE,
                        source_credit = COALESCE(EXCLUDED.source_credit, character_art_assets.source_credit),
                        source_license = COALESCE(EXCLUDED.source_license, character_art_assets.source_license),
                        reviewed_by = EXCLUDED.reviewed_by,
                        reviewed_at = NOW(),
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        character_id,
                        source_type,
                        source_url,
                        image_url,
                        int(width) if width else None,
                        int(height) if height else None,
                        aspect_ratio,
                        sha256,
                        perceptual_hash,
                        variant,
                        source_credit,
                        source_license,
                        updated_by,
                        updated_by,
                    ),
                )
                asset_row = cur.fetchone()
                asset_id = int(asset_row[0]) if asset_row else 0

                cur.execute(
                    """
                    INSERT INTO global_character_images (character_id, image_url, updated_by, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (character_id) DO UPDATE SET
                        image_url = EXCLUDED.image_url,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = NOW()
                    """,
                    (character_id, image_url, updated_by),
                )
                conn.commit()
                return {
                    "asset_id": asset_id,
                    "character_id": character_id,
                    "image_url": image_url,
                    "previous_image_url": previous_image_url,
                }
            except Exception:
                conn.rollback()
                raise


def list_character_art_assets(character_id: int, *, include_rejected: bool = False) -> list[Dict[str, Any]]:
    character_id = int(character_id)
    from database_core import run

    where = "character_id = %s"
    params: tuple[Any, ...] = (character_id,)
    if not include_rejected:
        where += " AND status <> 'rejected'"

    return run(
        f"""
        SELECT
            id, character_id, source_type, source_url, image_url, storage_url,
            telegram_file_id, width, height, aspect_ratio, sha256, perceptual_hash,
            variant, status, is_primary, source_credit, source_license,
            reviewed_by, reviewed_at, created_by, created_at, updated_at
        FROM character_art_assets
        WHERE {where}
        ORDER BY is_primary DESC, created_at DESC, id DESC
        """,
        params,
        fetch="all",
    ) or []
