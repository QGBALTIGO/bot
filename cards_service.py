def set_global_character_image(character_id: int, image_url: str, updated_by: int) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO character_image_overrides (character_id, image_url, updated_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (character_id)
                DO UPDATE SET
                    image_url = EXCLUDED.image_url,
                    updated_by = EXCLUDED.updated_by
                """,
                (int(character_id), str(image_url).strip(), int(updated_by)),
            )
        conn.commit()


def get_global_character_image(character_id: int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT image_url
                FROM character_image_overrides
                WHERE character_id = %s
                LIMIT 1
                """,
                (int(character_id),),
            )
            row = cur.fetchone()

            if not row:
                return None

            if isinstance(row, dict):
                return row.get("image_url")

            try:
                return row["image_url"]
            except Exception:
                return row[0]


def delete_global_character_image(character_id: int) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM character_image_overrides
                WHERE character_id = %s
                """,
                (int(character_id),),
            )
        conn.commit()
