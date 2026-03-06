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

    # 2) migra colunas (seguro)
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;""")

    # NOVO: obrigatoriedade do canal + controle de mensagens
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_sent BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS must_join_ok BOOLEAN NOT NULL DEFAULT FALSE;""")

def create_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY
    );
    """)

    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_sent BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS must_join_ok BOOLEAN NOT NULL DEFAULT FALSE;""")

    create_media_request_tables()

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

def get_user_status(user_id: int):
    row = _run(
        "SELECT lang, terms_accepted, terms_version, welcome_sent FROM users WHERE user_id = %s",
        (user_id,),
        fetch="one"
    )
    if not row:
        return None
    lang, terms_accepted, terms_version, welcome_sent = row
    return {
        "lang": lang,
        "terms_accepted": bool(terms_accepted),
        "terms_version": terms_version,
        "welcome_sent": bool(welcome_sent),
    }

def mark_welcome_sent(user_id: int):
    _run("UPDATE users SET welcome_sent = TRUE WHERE user_id = %s", (user_id,))

def reset_welcome_sent(user_id: int):
    _run("UPDATE users SET welcome_sent = FALSE WHERE user_id = %s", (user_id,))


# =========================
# PEDIDOS / REPORTS WEBAPP
# =========================
def create_media_request_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS media_requests (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        username TEXT,
        full_name TEXT,
        media_type TEXT NOT NULL,
        anilist_id BIGINT,
        title TEXT NOT NULL,
        title_norm TEXT NOT NULL,
        cover_url TEXT,
        request_status TEXT NOT NULL DEFAULT 'pending',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_media_requests_user_created
    ON media_requests (user_id, created_at DESC)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_media_requests_media_title
    ON media_requests (media_type, title_norm)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_media_requests_media_anilist
    ON media_requests (media_type, anilist_id)
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS webapp_reports (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        username TEXT,
        full_name TEXT,
        report_type TEXT,
        message TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_webapp_reports_user_created
    ON webapp_reports (user_id, created_at DESC)
    """)


def normalize_media_title(title: str) -> str:
    import re
    t = (title or '').strip().lower()
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'[^\w\s]', '', t)
    return t.strip()


def count_user_media_requests_last_24h(user_id: int) -> int:
    row = _run(
        """
        SELECT COUNT(*)
        FROM media_requests
        WHERE user_id = %s
          AND created_at >= NOW() - INTERVAL '24 hours'
        """,
        (user_id,),
        fetch='one'
    )
    return int(row[0] or 0) if row else 0


def media_request_exists(media_type: str, title: str, anilist_id=None) -> bool:
    title_norm = normalize_media_title(title)

    if anilist_id:
        row = _run(
            """
            SELECT id FROM media_requests
            WHERE media_type = %s
              AND anilist_id = %s
              AND request_status IN ('pending', 'approved')
            LIMIT 1
            """,
            (media_type, int(anilist_id)),
            fetch='one'
        )
        if row:
            return True

    row = _run(
        """
        SELECT id FROM media_requests
        WHERE media_type = %s
          AND title_norm = %s
          AND request_status IN ('pending', 'approved')
        LIMIT 1
        """,
        (media_type, title_norm),
        fetch='one'
    )
    return bool(row)


def save_media_request(user_id: int, username: str, full_name: str, media_type: str, title: str, anilist_id=None, cover_url: str = ''):
    _run(
        """
        INSERT INTO media_requests
        (user_id, username, full_name, media_type, anilist_id, title, title_norm, cover_url, request_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """,
        (
            int(user_id),
            (username or '').strip(),
            (full_name or '').strip(),
            (media_type or '').strip(),
            int(anilist_id) if anilist_id else None,
            (title or '').strip(),
            normalize_media_title(title),
            (cover_url or '').strip(),
        )
    )


def save_webapp_report(user_id: int, username: str, full_name: str, report_type: str, message: str):
    _run(
        """
        INSERT INTO webapp_reports
        (user_id, username, full_name, report_type, message)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (int(user_id), (username or '').strip(), (full_name or '').strip(), (report_type or '').strip(), (message or '').strip())
    )
