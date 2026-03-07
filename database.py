import os
import re
from typing import Any, Dict, List, Optional, Tuple

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado.")

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=10,
    timeout=10,
)


# =========================================================
# CORE SQL
# =========================================================

def _run(sql: str, params: Tuple[Any, ...] = (), fetch: str = "none"):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
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

            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                print("SQL ERROR:", e)
                raise


# =========================================================
# INIT
# =========================================================

def create_tables():
    create_users_table()
    create_cards_tables()
    create_level_tables()
    create_friendship_tables()
    create_media_request_tables()


# =========================================================
# USERS
# =========================================================

def create_users_table():
    _run("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        nick TEXT,
        lang TEXT,
        coins BIGINT DEFAULT 0,

        terms_accepted BOOLEAN DEFAULT FALSE,
        terms_version TEXT,
        accepted_at TIMESTAMPTZ,

        welcome_sent BOOLEAN DEFAULT FALSE,
        must_join_ok BOOLEAN DEFAULT FALSE,

        fav_character_id BIGINT,
        fav_name TEXT,
        fav_image TEXT
    )
    """)


def create_or_get_user(user_id: int, nick: Optional[str] = None):
    _run(
        """
        INSERT INTO users (user_id, nick)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id), nick)
    )


def get_user_row(user_id: int) -> Optional[Dict[str, Any]]:
    return _run(
        "SELECT * FROM users WHERE user_id = %s",
        (int(user_id),),
        fetch="one"
    )


def get_user_status(user_id: int) -> Optional[Dict[str, Any]]:
    row = _run(
        """
        SELECT
            lang,
            terms_accepted,
            terms_version,
            welcome_sent,
            must_join_ok
        FROM users
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )

    if not row:
        return None

    return {
        "lang": row["lang"],
        "terms_accepted": bool(row["terms_accepted"]),
        "terms_version": row["terms_version"],
        "welcome_sent": bool(row["welcome_sent"]),
        "must_join_ok": bool(row["must_join_ok"]),
    }


def accept_terms(user_id: int, version: str):
    _run(
        """
        UPDATE users
        SET terms_accepted = TRUE,
            terms_version = %s,
            accepted_at = NOW()
        WHERE user_id = %s
        """,
        (version, int(user_id))
    )


def mark_welcome_sent(user_id: int):
    _run(
        "UPDATE users SET welcome_sent = TRUE WHERE user_id = %s",
        (int(user_id),)
    )


def reset_welcome_sent(user_id: int):
    _run(
        "UPDATE users SET welcome_sent = FALSE WHERE user_id = %s",
        (int(user_id),)
    )


# =========================================================
# FAVORITOS
# =========================================================

def set_favorite_card(user_id: int, char_id: int, name: str, image: str):
    _run(
        """
        UPDATE users
        SET fav_character_id=%s,
            fav_name=%s,
            fav_image=%s
        WHERE user_id=%s
        """,
        (char_id, name, image, user_id)
    )


def get_user_favorite_card_quantity(user_id: int) -> int:
    row = _run(
        """
        SELECT c.quantity
        FROM users u
        LEFT JOIN user_card_collection c
        ON c.user_id = u.user_id
        AND c.character_id = u.fav_character_id
        WHERE u.user_id = %s
        """,
        (user_id,),
        fetch="one"
    )

    return int((row or {}).get("quantity") or 0)


# =========================================================
# CARDS
# =========================================================

def create_cards_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS user_card_collection (
        user_id BIGINT,
        character_id BIGINT,
        quantity INTEGER DEFAULT 0,
        first_obtained_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (user_id, character_id)
    )
    """)


def get_user_card_quantity(user_id: int, char_id: int) -> int:
    row = _run(
        """
        SELECT quantity
        FROM user_card_collection
        WHERE user_id=%s AND character_id=%s
        """,
        (user_id, char_id),
        fetch="one"
    )

    return int((row or {}).get("quantity") or 0)


def get_card_total_copies(char_id: int) -> int:
    row = _run(
        """
        SELECT SUM(quantity) AS total
        FROM user_card_collection
        WHERE character_id=%s
        """,
        (char_id,),
        fetch="one"
    )

    return int((row or {}).get("total") or 0)


def get_card_owner_count(char_id: int) -> int:
    row = _run(
        """
        SELECT COUNT(*) AS total
        FROM user_card_collection
        WHERE character_id=%s AND quantity>0
        """,
        (char_id,),
        fetch="one"
    )

    return int((row or {}).get("total") or 0)


def count_collection(user_id: int) -> int:
    row = _run(
        """
        SELECT SUM(quantity) AS total
        FROM user_card_collection
        WHERE user_id=%s
        """,
        (user_id,),
        fetch="one"
    )

    return int((row or {}).get("total") or 0)


# =========================================================
# LEVEL SYSTEM
# =========================================================

def create_level_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS user_progress (
        user_id BIGINT PRIMARY KEY,
        xp BIGINT DEFAULT 0,
        level INTEGER DEFAULT 1,
        total_actions BIGINT DEFAULT 0,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """)


def ensure_progress_row(user_id: int):
    _run(
        """
        INSERT INTO user_progress (user_id)
        VALUES (%s)
        ON CONFLICT DO NOTHING
        """,
        (user_id,)
    )


def get_progress_row(user_id: int):
    ensure_progress_row(user_id)

    return _run(
        "SELECT * FROM user_progress WHERE user_id=%s",
        (user_id,),
        fetch="one"
    )


# =========================================================
# AMIZADE
# =========================================================

def create_friendship_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS friendships (
        user_id BIGINT,
        friend_id BIGINT,
        status TEXT DEFAULT 'accepted',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (user_id, friend_id)
    )
    """)


def get_friend_count(user_id: int) -> int:
    row = _run(
        """
        SELECT COUNT(*) AS total
        FROM friendships
        WHERE user_id=%s
        """,
        (user_id,),
        fetch="one"
    )

    return int((row or {}).get("total") or 0)


# =========================================================
# MEDIA REQUESTS
# =========================================================

def create_media_request_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS media_requests (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT,
        username TEXT,
        full_name TEXT,
        media_type TEXT,
        anilist_id BIGINT,
        title TEXT,
        title_norm TEXT,
        cover_url TEXT,
        request_status TEXT DEFAULT 'pending',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """)


def normalize_media_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s]", "", t)
    return t
