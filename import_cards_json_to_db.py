import os
import json
from psycopg import connect

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

POSSIBLE_PATHS = [
    os.path.join(BASE_DIR, "data", "personagens_anilists.txt"),
    os.path.join(BASE_DIR, "data", "personagens_anilist.txt"),
    os.path.join(BASE_DIR, "dados", "personagens_anilist.txt"),
    os.path.join(BASE_DIR, "data", "personagens_anilist.json"),
]


def resolve_path():
    for p in POSSIBLE_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Arquivo de personagens não encontrado.")


def load_json_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        items = raw.get("items", raw.get("characters", []))
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    if not isinstance(items, list):
        raise ValueError("Formato inválido: esperado lista de personagens.")

    return items


def normalize_items(items):
    normalized = []

    for item in items:
        if not isinstance(item, dict):
            continue

        try:
            char_id = int(item.get("id"))
        except Exception:
            continue

        name = str(item.get("name") or "").strip()
        anime = str(item.get("anime") or "").strip()
        image = str(item.get("image") or "").strip()

        if not name or not anime:
            continue

        normalized.append({
            "id": char_id,
            "name": name,
            "anime": anime,
            "image": image,
        })

    return normalized


def main():
    path = resolve_path()
    items = load_json_file(path)
    items = normalize_items(items)

    print(f"Arquivo encontrado: {path}")
    print(f"Personagens válidos: {len(items)}")

    with connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for item in items:
                cur.execute("""
                    INSERT INTO card_characters_catalog (
                        character_id,
                        character_name,
                        anime_name,
                        image_url,
                        is_deleted,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, FALSE, NOW(), NOW())
                    ON CONFLICT (character_id)
                    DO UPDATE SET
                        character_name = EXCLUDED.character_name,
                        anime_name = EXCLUDED.anime_name,
                        image_url = EXCLUDED.image_url,
                        is_deleted = FALSE,
                        updated_at = NOW();
                """, (
                    item["id"],
                    item["name"],
                    item["anime"],
                    item["image"],
                ))

        conn.commit()

    print("Importação concluída com sucesso.")


if __name__ == "__main__":
    main()
