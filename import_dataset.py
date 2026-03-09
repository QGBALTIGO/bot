import os
import json
from psycopg import connect

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado.")

INPUT = "personagens_otimizado.json"


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("Unid", [])

    with connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for anime in items:
                anime_id = int(anime["anime_id"])
                anime_name = anime["anime"]
                banner_image = anime.get("banner_image", "") or ""
                cover_image = anime.get("cover_image", "") or ""

                cur.execute("""
                    INSERT INTO animes (
                        anime_id, anime_name, banner_image, cover_image, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (anime_id)
                    DO UPDATE SET
                        anime_name = EXCLUDED.anime_name,
                        banner_image = EXCLUDED.banner_image,
                        cover_image = EXCLUDED.cover_image,
                        updated_at = NOW()
                """, (anime_id, anime_name, banner_image, cover_image))

                for c in anime.get("characters", []):
                    char_id = int(c["id"])
                    char_name = (c.get("name") or "").strip()
                    image_url = (c.get("image") or "").strip()

                    if not char_name:
                        continue

                    cur.execute("""
                        INSERT INTO characters (
                            character_id, anime_id, character_name, image_url, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (character_id)
                        DO UPDATE SET
                            anime_id = EXCLUDED.anime_id,
                            character_name = EXCLUDED.character_name,
                            image_url = EXCLUDED.image_url,
                            updated_at = NOW()
                    """, (char_id, anime_id, char_name, image_url))

        conn.commit()

    print("Importação concluída com sucesso.")


if __name__ == "__main__":
    main()
