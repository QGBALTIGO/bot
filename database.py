import os
import re
from typing import Any, Dict, List, Optional, Tuple

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado nas variáveis de ambiente.")

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=10,
    timeout=10,
)


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
                print("SQL ERROR:", e, flush=True)
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
        coins BIGINT NOT NULL DEFAULT 0,
        terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
        terms_version TEXT,
        accepted_at TIMESTAMPTZ,
        welcome_sent BOOLEAN NOT NULL DEFAULT FALSE,
        must_join_ok BOOLEAN NOT NULL DEFAULT FALSE,
        fav_name TEXT,
        fav_image TEXT,
        fav_character_id BIGINT
    )
    """)

    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS nick TEXT""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS coins BIGINT DEFAULT 0""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version TEXT""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_sent BOOLEAN NOT NULL DEFAULT FALSE""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS must_join_ok BOOLEAN NOT NULL DEFAULT FALSE""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_name TEXT""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_image TEXT""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_character_id BIGINT""")


def create_or_get_user(user_id: int, nick: Optional[str] = None):
    _run(
        """
        INSERT INTO users (user_id, nick)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id), (nick or "").strip() or None)
    )


def get_user_row(user_id: int) -> Optional[Dict[str, Any]]:
    return _run(
        """
        SELECT
            user_id,
            nick,
            lang,
            coins,
            terms_accepted,
            terms_version,
            accepted_at,
            welcome_sent,
            must_join_ok,
            fav_name,
            fav_image,
            fav_character_id
        FROM users
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )


def get_user_status(user_id: int) -> Optional[Dict[str, Any]]:
    row = _run(
        """
        SELECT lang, terms_accepted, terms_version, welcome_sent, must_join_ok
        FROM users
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )
    if not row:
        return None

    return {
        "lang": row.get("lang"),
        "terms_accepted": bool(row.get("terms_accepted")),
        "terms_version": row.get("terms_version"),
        "welcome_sent": bool(row.get("welcome_sent")),
        "must_join_ok": bool(row.get("must_join_ok")),
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
        ((version or "").strip(), int(user_id))
    )


def set_favorite_card(user_id: int, character_id: int, fav_name: str, fav_image: str):
    _run(
        """
        UPDATE users
        SET fav_character_id = %s,
            fav_name = %s,
            fav_image = %s
        WHERE user_id = %s
        """,
        (
            int(character_id),
            (fav_name or "").strip(),
            (fav_image or "").strip(),
            int(user_id),
        )
    )


def clear_favorite_card(user_id: int):
    _run(
        """
        UPDATE users
        SET fav_character_id = NULL,
            fav_name = NULL,
            fav_image = NULL
        WHERE user_id = %s
        """,
        (int(user_id),)
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
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one"
    )
    return int((row or {}).get("quantity") or 0)


# =========================================================
# CARDS
# =========================================================

def create_cards_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS user_card_collection (
        user_id BIGINT NOT NULL,
        character_id BIGINT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 0,
        first_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, character_id)
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_card_collection_character
    ON user_card_collection (character_id)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_card_collection_user
    ON user_card_collection (user_id)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_collection_user_char
    ON user_card_collection (user_id, character_id)
    """)


def get_user_card_quantity(user_id: int, character_id: int) -> int:
    row = _run(
        """
        SELECT quantity
        FROM user_card_collection
        WHERE user_id = %s
          AND character_id = %s
        """,
        (int(user_id), int(character_id)),
        fetch="one"
    )
    return int((row or {}).get("quantity") or 0)


def get_card_total_copies(character_id: int) -> int:
    row = _run(
        """
        SELECT COALESCE(SUM(quantity), 0) AS total
        FROM user_card_collection
        WHERE character_id = %s
        """,
        (int(character_id),),
        fetch="one"
    )
    return int((row or {}).get("total") or 0)


def get_card_owner_count(character_id: int) -> int:
    row = _run(
        """
        SELECT COUNT(*) AS total
        FROM user_card_collection
        WHERE character_id = %s
          AND quantity > 0
        """,
        (int(character_id),),
        fetch="one"
    )
    return int((row or {}).get("total") or 0)


def count_collection(user_id: int) -> int:
    row = _run(
        """
        SELECT COALESCE(SUM(quantity), 0) AS total
        FROM user_card_collection
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )
    return int((row or {}).get("total") or 0)


# =========================================================
# LEVEL
# =========================================================

def create_level_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS user_progress (
        user_id BIGINT PRIMARY KEY,
        xp BIGINT NOT NULL DEFAULT 0,
        level INTEGER NOT NULL DEFAULT 1,
        total_actions BIGINT NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_progress_level_xp
    ON user_progress (level DESC, xp DESC)
    """)


def ensure_progress_row(user_id: int):
    _run(
        """
        INSERT INTO user_progress (user_id)
        VALUES (%s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),)
    )


def get_progress_row(user_id: int) -> Optional[Dict[str, Any]]:
    ensure_progress_row(user_id)

    return _run(
        """
        SELECT user_id, xp, level, total_actions, updated_at
        FROM user_progress
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )


def level_xp_required(level: int) -> int:
    level = max(1, int(level))
    return 80 * (level - 1) * (level - 1) + 120 * (level - 1)


def xp_to_level(xp: int) -> int:
    xp = max(0, int(xp))
    level = 1

    while True:
        next_level = level + 1
        if xp < level_xp_required(next_level):
            return level
        level = next_level


def get_level_progress_values(xp: int) -> Dict[str, int]:
    xp = max(0, int(xp))
    level = xp_to_level(xp)

    current_floor = level_xp_required(level)
    next_floor = level_xp_required(level + 1)

    current_in_level = xp - current_floor
    needed_in_level = next_floor - current_floor
    remaining = max(next_floor - xp, 0)

    return {
        "level": level,
        "xp_total": xp,
        "xp_current": current_in_level,
        "xp_needed": needed_in_level,
        "xp_remaining": remaining,
        "xp_next_total": next_floor,
    }


def add_progress_xp(user_id: int, amount: int = 3) -> Dict[str, Any]:
    ensure_progress_row(user_id)

    row = get_progress_row(user_id)
    old_xp = int((row or {}).get("xp") or 0)
    old_level = int((row or {}).get("level") or 1)
    old_actions = int((row or {}).get("total_actions") or 0)

    new_xp = old_xp + max(0, int(amount))
    new_level = xp_to_level(new_xp)
    new_actions = old_actions + 1

    _run(
        """
        UPDATE user_progress
        SET xp = %s,
            level = %s,
            total_actions = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (new_xp, new_level, new_actions, int(user_id))
    )

    return {
        "old_level": old_level,
        "new_level": new_level,
        "xp": new_xp,
        "total_actions": new_actions,
    }


def get_user_level_rank(user_id: int) -> int:
    ensure_progress_row(user_id)

    row = _run(
        """
        SELECT rank_pos
        FROM (
            SELECT
                user_id,
                RANK() OVER (ORDER BY level DESC, xp DESC, total_actions DESC, user_id ASC) AS rank_pos
            FROM user_progress
        ) ranked
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )

    return int((row or {}).get("rank_pos") or 0)


# =========================================================
# FRIENDSHIPS
# =========================================================

def create_friendship_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS friendships (
        user_id BIGINT NOT NULL,
        friend_id BIGINT NOT NULL,
        status TEXT NOT NULL DEFAULT 'accepted',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, friend_id)
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_friendships_user
    ON friendships (user_id)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_friendships_friend
    ON friendships (friend_id)
    """)


def get_friend_count(user_id: int) -> int:
    row = _run(
        """
        SELECT COUNT(*) AS total
        FROM friendships
        WHERE user_id = %s
          AND status = 'accepted'
        """,
        (int(user_id),),
        fetch="one"
    )
    return int((row or {}).get("total") or 0)


# =========================================================
# MEDIA REQUESTS / REPORTS
# =========================================================

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
    t = (title or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s]", "", t)
    return t.strip()


def count_user_media_requests_last_24h(user_id: int) -> int:
    row = _run(
        """
        SELECT COUNT(*) AS total
        FROM media_requests
        WHERE user_id = %s
          AND created_at >= NOW() - INTERVAL '24 hours'
        """,
        (int(user_id),),
        fetch="one"
    )
    return int((row or {}).get("total") or 0)


def media_request_exists(media_type: str, title: str, anilist_id=None) -> bool:
    media_type = (media_type or "").strip()
    title_norm = normalize_media_title(title)

    if anilist_id:
        row = _run(
            """
            SELECT id
            FROM media_requests
            WHERE media_type = %s
              AND anilist_id = %s
              AND request_status IN ('pending', 'approved')
            LIMIT 1
            """,
            (media_type, int(anilist_id)),
            fetch="one"
        )
        if row:
            return True

    row = _run(
        """
        SELECT id
        FROM media_requests
        WHERE media_type = %s
          AND title_norm = %s
          AND request_status IN ('pending', 'approved')
        LIMIT 1
        """,
        (media_type, title_norm),
        fetch="one"
    )
    return bool(row)


def save_media_request(
    user_id: int,
    username: str,
    full_name: str,
    media_type: str,
    title: str,
    anilist_id=None,
    cover_url: str = "",
):
    _run(
        """
        INSERT INTO media_requests
        (user_id, username, full_name, media_type, anilist_id, title, title_norm, cover_url, request_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """,
        (
            int(user_id),
            (username or "").strip(),
            (full_name or "").strip(),
            (media_type or "").strip(),
            int(anilist_id) if anilist_id else None,
            (title or "").strip(),
            normalize_media_title(title),
            (cover_url or "").strip(),
        )
    )


def save_webapp_report(
    user_id: int,
    username: str,
    full_name: str,
    report_type: str,
    message: str,
):
    _run(
        """
        INSERT INTO webapp_reports
        (user_id, username, full_name, report_type, message)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            int(user_id),
            (username or "").strip(),
            (full_name or "").strip(),
            (report_type or "").strip(),
            (message or "").strip(),
        )
    )
