import os
import time
import psycopg
from typing import Optional

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado nas variáveis de ambiente.")

_conn: Optional[psycopg.Connection] = None

def _get_conn() -> psycopg.Connection:
    global _conn
    if _conn is not None and not _conn.closed:
        return _conn

    last_err = None
    for _ in range(8):  # tenta por alguns segundos
        try:
            _conn = psycopg.connect(DATABASE_URL)
            return _conn
        except Exception as e:
            last_err = e
            time.sleep(1.2)

    raise last_err

def create_tables():
    conn = _get_conn()
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
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
            (user_id,)
        )
        conn.commit()

def set_language(user_id: int, lang: str):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET lang = %s WHERE user_id = %s",
            (lang, user_id)
        )
        conn.commit()

def accept_terms(user_id: int, version: str):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE users
               SET terms_accepted = TRUE,
                   terms_version = %s,
                   accepted_at = NOW()
             WHERE user_id = %s
            """,
            (version, user_id)
        )
        conn.commit()
