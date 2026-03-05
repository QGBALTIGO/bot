import os
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado nas variáveis de ambiente.")

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=10,
    timeout=10,
)

def _run(sql: str, params=(), fetch: str = "none"):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, params)

                if fetch == "one":
                    row = cur.fetchone()
                    conn.commit()
                    return row

                if fetch == "all":
                    rows = cur.fetchall() or []
                    conn.commit()
                    return rows

                conn.commit()
                return None

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

def create_tables():
    # 1) cria tabela base (se não existir)
    _run("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY
    );
    """)

    # 2) migra colunas (seguro, não quebra)
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;""")

def create_or_get_user(user_id: int):
    _run(
        "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
        (user_id,)
    )

def set_language(user_id: int, lang: str):
    _run(
        "UPDATE users SET lang = %s WHERE user_id = %s",
        (lang, user_id)
    )

def accept_terms(user_id: int, version: str):
    _run(
        """
        UPDATE users
           SET terms_accepted = TRUE,
               terms_version = %s,
               accepted_at = NOW()
         WHERE user_id = %s
        """,
        (version, user_id)
    )

def has_accepted_terms(user_id: int, version: str) -> bool:
    row = _run(
        "SELECT terms_accepted, terms_version FROM users WHERE user_id = %s",
        (user_id,),
        fetch="one"
    )
    if not row:
        return False
    accepted, v = row
    return bool(accepted) and (v == version)
