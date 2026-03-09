import os
import json
from psycopg import connect

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "data", "personagens_anilist.txt")  # ajuste o nome se for outro


def main():
    if not os.path.exists(JSON_PATH):
        raise FileNotFoundError(f"Arquivo não encontrado: {JSON_PATH}")

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("O JSON precisa ser uma lista de personagens.")

    with connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for item in data:
                character_id = int(item["id"])
                character_name = str(item.get("name", "")).strip()
                anime_name = str(item.get("anime", "")).strip()
                image_url = str(item.get("image", "")).strip()

                if not character_name or not anime_name:
                    continue

                cur.execute("""
                    INSERT INTO card_characters (
                        character_id,
                        character_name,
                        anime_name,
                        image_url
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (character_id) DO UPDATE SET
                        character_name = EXCLUDED.character_name,
                        anime_name = EXCLUDED.anime_name,
                        image_url = EXCLUDED.image_url,
                        updated_at = NOW()
                """, (
                    character_id,
                    character_name,
                    anime_name,
                    image_url
                ))

        conn.commit()

    print("Importação concluída com sucesso.")


if __name__ == "__main__":
    main()
