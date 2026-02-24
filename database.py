# database.py
import os
import time
from typing import Optional, List, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrado. No Railway, crie a variável DATABASE_URL "
        "com valor ${{Postgres.DATABASE_URL}}"
    )

db = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
db.autocommit = True  # evita esquecer commit
cursor = db.cursor()


def init_db() -> None:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id         BIGINT PRIMARY KEY,
        first_name      TEXT,
        nick            TEXT,
        collection_name TEXT DEFAULT 'Minha Coleção',
        fav_name        TEXT,
        fav_image       TEXT,
        coins           INTEGER DEFAULT 0,
        commands        INTEGER DEFAULT 0,
        level           INTEGER DEFAULT 1,
        xp              INTEGER DEFAULT 0,
        last_dado       BIGINT DEFAULT 0,
        last_pedido     BIGINT DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_collection (
        user_id        BIGINT NOT NULL,
        character_id   BIGINT NOT NULL,
        character_name TEXT NOT NULL,
        image          TEXT,
        quantity       INTEGER DEFAULT 1,
        PRIMARY KEY (user_id, character_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_spawns (
        chat_id        BIGINT PRIMARY KEY,
        character_id   BIGINT,
        character_name TEXT,
        image          TEXT,
        expires_at     BIGINT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shop_sales (
        user_id        BIGINT,
        character_id   BIGINT,
        character_name TEXT,
        image          TEXT,
        created_at     BIGINT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        trade_id            BIGSERIAL PRIMARY KEY,
        from_user           BIGINT,
        to_user             BIGINT,
        from_character_id   BIGINT,
        to_character_id     BIGINT,
        status              TEXT DEFAULT 'pendente'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_photos (
        user_id   BIGINT PRIMARY KEY,
        photo_url TEXT NOT NULL
    )
    """)


def ensure_user(user_id: int, first_name: str) -> None:
    cursor.execute("SELECT 1 FROM users WHERE user_id=%s", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO users (user_id, first_name, nick) VALUES (%s, %s, %s)",
            (user_id, first_name, first_name)
        )


def get_user(user_id: int) -> dict:
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise RuntimeError("Usuário não existe (chame ensure_user antes).")
    return row


def add_command_and_level(user_id: int, comandos_por_nivel: int) -> Tuple[int, int, bool]:
    cursor.execute("SELECT commands, level, nick FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    commands = int(row["commands"]) + 1
    old_level = int(row["level"])
    new_level = (commands // comandos_por_nivel) + 1

    cursor.execute(
        "UPDATE users SET commands=%s, level=%s WHERE user_id=%s",
        (commands, new_level, user_id)
    )
    return commands, new_level, new_level > old_level


def set_nick(user_id: int, nick: str) -> None:
    cursor.execute("UPDATE users SET nick=%s WHERE user_id=%s", (nick, user_id))


def set_favorite(user_id: int, fav_name: str, fav_image: str) -> None:
    cursor.execute(
        "UPDATE users SET fav_name=%s, fav_image=%s WHERE user_id=%s",
        (fav_name, fav_image, user_id)
    )


def clear_favorite(user_id: int) -> None:
    cursor.execute("UPDATE users SET fav_name=NULL, fav_image=NULL WHERE user_id=%s", (user_id,))


def get_admin_photo(user_id: int) -> Optional[str]:
    cursor.execute("SELECT photo_url FROM admin_photos WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["photo_url"] if row else None


def set_admin_photo(user_id: int, url: str) -> None:
    cursor.execute("""
        INSERT INTO admin_photos (user_id, photo_url)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET photo_url = EXCLUDED.photo_url
    """, (user_id, url))


def get_profile_counts(user_id: int) -> Tuple[int, int]:
    cursor.execute("SELECT coins FROM users WHERE user_id=%s", (user_id,))
    coins = int(cursor.fetchone()["coins"])

    cursor.execute("SELECT COUNT(*) AS total FROM user_collection WHERE user_id=%s", (user_id,))
    total = int(cursor.fetchone()["total"])
    return coins, total


def get_collection_name(user_id: int) -> str:
    cursor.execute("SELECT collection_name FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["collection_name"] or "Minha Coleção"


def set_collection_name(user_id: int, name: str) -> None:
    cursor.execute("UPDATE users SET collection_name=%s WHERE user_id=%s", (name, user_id))


def get_dado_state(user_id: int) -> Tuple[int, int]:
    cursor.execute("SELECT last_dado, coins FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return int(row["last_dado"]), int(row["coins"])


def set_dado_state(user_id: int, last_dado: int, coins: int) -> None:
    cursor.execute(
        "UPDATE users SET last_dado=%s, coins=%s WHERE user_id=%s",
        (last_dado, coins, user_id)
    )


def add_to_collection(user_id: int, character_id: int, name: str, image: str) -> bool:
    try:
        cursor.execute("""
            INSERT INTO user_collection (user_id, character_id, character_name, image, quantity)
            VALUES (%s, %s, %s, %s, 1)
        """, (user_id, character_id, name, image))
        return True
    except psycopg2.errors.UniqueViolation:
        # precisa limpar o erro da transação antes de continuar
        db.rollback()
        return False


def add_coin(user_id: int, amount: int = 1) -> None:
    cursor.execute("UPDATE users SET coins = coins + %s WHERE user_id=%s", (amount, user_id))


def get_last_pedido(user_id: int) -> int:
    cursor.execute("SELECT last_pedido FROM users WHERE user_id=%s", (user_id,))
    return int(cursor.fetchone()["last_pedido"])


def set_last_pedido(user_id: int, ts: int) -> None:
    cursor.execute("UPDATE users SET last_pedido=%s WHERE user_id=%s", (ts, user_id))


def collection_total(user_id: int) -> int:
    cursor.execute("SELECT COUNT(*) AS total FROM user_collection WHERE user_id=%s", (user_id,))
    return int(cursor.fetchone()["total"])


def paginated_collection(user_id: int, limit: int, offset: int) -> List[dict]:
    cursor.execute("""
        SELECT character_id, character_name, image, quantity
        FROM user_collection
        WHERE user_id=%s
        ORDER BY character_id ASC
        LIMIT %s OFFSET %s
    """, (user_id, limit, offset))
    return cursor.fetchall()
