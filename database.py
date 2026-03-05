import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado nas variáveis de ambiente.")

conn = psycopg.connect(DATABASE_URL)

def create_tables():
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            lang TEXT,
            terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
            terms_version TEXT,
            accepted_at TIMESTAMPTZ
        );
        """)
        conn.commit()

def create_or_get_user(user_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
            (user_id,)
        )
        conn.commit()

def get_user_lang(user_id: int):
    with conn.cursor() as cur:
        cur.execute("SELECT lang FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return (row[0] if row else None)

def set_language(user_id: int, lang: str):
    with conn.cursor
