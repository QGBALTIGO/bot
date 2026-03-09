import os
import re
from datetime import date, timedelta
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


# =========================================================
# CORE SQL
# =========================================================

def _run(sql: str, params: Tuple[Any, ...] = (), fetch: str = "none"):
    """
    Executa SQL usando pool.

    fetch:
      - "none" -> None
      - "one"  -> dict | None
      - "all"  -> list[dict]
    """
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

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


# =========================================================
# INIT / MIGRATIONS
# =========================================================

def create_tables():
    create_users_table()
    create_media_request_tables()
    create_cards_tables()
    create_level_tables()
    create_termo_tables()


def create_users_table():
    _run("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        lang TEXT,
        coins BIGINT NOT NULL DEFAULT 0,
        terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
        terms_version TEXT,
        accepted_at TIMESTAMPTZ,
        welcome_sent BOOLEAN NOT NULL DEFAULT FALSE,
        must_join_ok BOOLEAN NOT NULL DEFAULT FALSE
    );
    """)

    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS coins BIGINT NOT NULL DEFAULT 0;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_sent BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS must_join_ok BOOLEAN NOT NULL DEFAULT FALSE;""")


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


def create_termo_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS termo_games (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        date DATE NOT NULL,
        word TEXT NOT NULL,
        category TEXT,
        source TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        guesses JSONB NOT NULL DEFAULT '[]'::jsonb,
        used_letters TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'playing',
        mode TEXT NOT NULL DEFAULT 'daily',
        start_time BIGINT NOT NULL,
        time_spent_seconds INTEGER NOT NULL DEFAULT 0,
        reward_coins INTEGER NOT NULL DEFAULT 0,
        reward_xp INTEGER NOT NULL DEFAULT 0,
        won_at_attempt INTEGER NOT NULL DEFAULT 0,
        finished_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_termo_games_user_date_mode
    ON termo_games (user_id, date, mode)
    WHERE mode = 'daily'
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_termo_games_user_status
    ON termo_games (user_id, status)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_termo_games_date
    ON termo_games (date DESC)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_termo_games_finished_at
    ON termo_games (finished_at DESC)
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS termo_stats (
        user_id BIGINT PRIMARY KEY,
        games_played INTEGER NOT NULL DEFAULT 0,
        wins INTEGER NOT NULL DEFAULT 0,
        losses INTEGER NOT NULL DEFAULT 0,
        current_streak INTEGER NOT NULL DEFAULT 0,
        best_streak INTEGER NOT NULL DEFAULT 0,
        best_score INTEGER NOT NULL DEFAULT 0,
        last_play_date DATE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_termo_stats_wins
    ON termo_stats (wins DESC, best_streak DESC, best_score ASC, user_id ASC)
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS termo_attempt_distribution (
        user_id BIGINT PRIMARY KEY,
        one_try INTEGER NOT NULL DEFAULT 0,
        two_try INTEGER NOT NULL DEFAULT 0,
        three_try INTEGER NOT NULL DEFAULT 0,
        four_try INTEGER NOT NULL DEFAULT 0,
        five_try INTEGER NOT NULL DEFAULT 0,
        six_try INTEGER NOT NULL DEFAULT 0
    )
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS termo_used_words (
        user_id BIGINT NOT NULL,
        word TEXT NOT NULL,
        used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, word)
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_termo_used_words_user
    ON termo_used_words (user_id, used_at DESC)
    """)

    # migrações seguras
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS category TEXT;""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS source TEXT;""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS guesses JSONB NOT NULL DEFAULT '[]'::jsonb;""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS used_letters TEXT NOT NULL DEFAULT '';""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'daily';""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS time_spent_seconds INTEGER NOT NULL DEFAULT 0;""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS reward_coins INTEGER NOT NULL DEFAULT 0;""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS reward_xp INTEGER NOT NULL DEFAULT 0;""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS won_at_attempt INTEGER NOT NULL DEFAULT 0;""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")
    _run("""ALTER TABLE termo_games ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")

    _run("""ALTER TABLE termo_stats ADD COLUMN IF NOT EXISTS losses INTEGER NOT NULL DEFAULT 0;""")
    _run("""ALTER TABLE termo_stats ADD COLUMN IF NOT EXISTS best_score INTEGER NOT NULL DEFAULT 0;""")
    _run("""ALTER TABLE termo_stats ADD COLUMN IF NOT EXISTS last_play_date DATE;""")
    _run("""ALTER TABLE termo_stats ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")


# =========================================================
# USERS
# =========================================================

def create_or_get_user(user_id: int):
    _run(
        "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
        (int(user_id),)
    )


def set_language(user_id: int, lang: str):
    _run(
        "UPDATE users SET lang = %s WHERE user_id = %s",
        ((lang or "").strip(), int(user_id))
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
        ((version or "").strip(), int(user_id))
    )


def has_accepted_terms(user_id: int, version: str) -> bool:
    row = _run(
        "SELECT terms_accepted, terms_version FROM users WHERE user_id = %s",
        (int(user_id),),
        fetch="one"
    )
    if not row:
        return False
    return bool(row["terms_accepted"]) and (row["terms_version"] == version)


def get_user_status(user_id: int) -> Optional[Dict[str, Any]]:
    row = _run(
        """
        SELECT lang, coins, terms_accepted, terms_version, welcome_sent, must_join_ok
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
        "coins": int(row.get("coins") or 0),
        "terms_accepted": bool(row.get("terms_accepted")),
        "terms_version": row.get("terms_version"),
        "welcome_sent": bool(row.get("welcome_sent")),
        "must_join_ok": bool(row.get("must_join_ok")),
    }


def mark_welcome_sent(user_id: int):
    _run("UPDATE users SET welcome_sent = TRUE WHERE user_id = %s", (int(user_id),))


def reset_welcome_sent(user_id: int):
    _run("UPDATE users SET welcome_sent = FALSE WHERE user_id = %s", (int(user_id),))


def set_must_join_ok(user_id: int, value: bool):
    _run(
        "UPDATE users SET must_join_ok = %s WHERE user_id = %s",
        (bool(value), int(user_id))
    )


def add_user_coins(user_id: int, amount: int):
    create_or_get_user(user_id)
    _run(
        """
        UPDATE users
        SET coins = COALESCE(coins, 0) + %s
        WHERE user_id = %s
        """,
        (int(amount), int(user_id))
    )


# =========================================================
# MEDIA REQUESTS / REPORTS
# =========================================================

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


# =========================================================
# CARDS / COLLECTION
# =========================================================

def get_user_card_quantity(user_id: int, character_id: int) -> int:
    row = _run(
        """
        SELECT quantity
        FROM user_card_collection
        WHERE user_id = %s AND character_id = %s
        """,
        (int(user_id), int(character_id)),
        fetch="one"
    )
    if not row:
        return 0
    return int(row.get("quantity") or 0)


def add_card_copy(user_id: int, character_id: int, amount: int = 1):
    amount = int(amount)
    if amount <= 0:
        return

    _run(
        """
        INSERT INTO user_card_collection (user_id, character_id, quantity, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (user_id, character_id)
        DO UPDATE SET
            quantity = user_card_collection.quantity + EXCLUDED.quantity,
            updated_at = NOW()
        """,
        (int(user_id), int(character_id), amount)
    )


def remove_card_copy(user_id: int, character_id: int, amount: int = 1):
    amount = int(amount)
    if amount <= 0:
        return

    row = _run(
        """
        SELECT quantity
        FROM user_card_collection
        WHERE user_id = %s AND character_id = %s
        """,
        (int(user_id), int(character_id)),
        fetch="one"
    )

    current = int((row or {}).get("quantity") or 0)
    new_qty = max(0, current - amount)

    if current == 0:
        return

    if new_qty == 0:
        _run(
            """
            DELETE FROM user_card_collection
            WHERE user_id = %s AND character_id = %s
            """,
            (int(user_id), int(character_id))
        )
    else:
        _run(
            """
            UPDATE user_card_collection
            SET quantity = %s,
                updated_at = NOW()
            WHERE user_id = %s AND character_id = %s
            """,
            (new_qty, int(user_id), int(character_id))
        )


def set_card_quantity(user_id: int, character_id: int, quantity: int):
    quantity = int(quantity)

    if quantity <= 0:
        _run(
            """
            DELETE FROM user_card_collection
            WHERE user_id = %s AND character_id = %s
            """,
            (int(user_id), int(character_id))
        )
        return

    _run(
        """
        INSERT INTO user_card_collection (user_id, character_id, quantity, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (user_id, character_id)
        DO UPDATE SET
            quantity = EXCLUDED.quantity,
            updated_at = NOW()
        """,
        (int(user_id), int(character_id), quantity)
    )


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


def get_user_card_collection(user_id: int) -> List[Dict[str, Any]]:
    rows = _run(
        """
        SELECT user_id, character_id, quantity, first_obtained_at, updated_at
        FROM user_card_collection
        WHERE user_id = %s
        ORDER BY quantity DESC, updated_at DESC
        """,
        (int(user_id),),
        fetch="all"
    )
    return rows or []


# =========================================================
# LEVEL / PROGRESS SYSTEM
# =========================================================

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


def get_top_level_users(limit: int = 10) -> List[Dict[str, Any]]:
    rows = _run(
        """
        SELECT user_id, xp, level, total_actions
        FROM user_progress
        ORDER BY level DESC, xp DESC, total_actions DESC, user_id ASC
        LIMIT %s
        """,
        (int(limit),),
        fetch="all"
    )
    return rows or []


# =========================================================
# TERMO
# =========================================================

def ensure_termo_stats_row(user_id: int):
    _run(
        """
        INSERT INTO termo_stats (user_id)
        VALUES (%s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),)
    )

    _run(
        """
        INSERT INTO termo_attempt_distribution (user_id)
        VALUES (%s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),)
    )


def get_termo_daily_game(user_id: int, game_date: date) -> Optional[Dict[str, Any]]:
    return _run(
        """
        SELECT *
        FROM termo_games
        WHERE user_id = %s
          AND date = %s
          AND mode = 'daily'
        LIMIT 1
        """,
        (int(user_id), game_date),
        fetch="one"
    )


def get_termo_active_game(user_id: int) -> Optional[Dict[str, Any]]:
    return _run(
        """
        SELECT *
        FROM termo_games
        WHERE user_id = %s
          AND status = 'playing'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one"
    )


def create_termo_game(
    user_id: int,
    game_date: date,
    word: str,
    category: str,
    source: str,
    start_time: int,
    mode: str = "daily",
):
    _run(
        """
        INSERT INTO termo_games
        (
            user_id,
            date,
            word,
            category,
            source,
            attempts,
            guesses,
            used_letters,
            status,
            mode,
            start_time,
            time_spent_seconds,
            reward_coins,
            reward_xp,
            won_at_attempt,
            created_at,
            updated_at
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            0,
            '[]'::jsonb,
            '',
            'playing',
            %s,
            %s,
            0,
            0,
            0,
            0,
            NOW(),
            NOW()
        )
        """,
        (
            int(user_id),
            game_date,
            (word or "").strip().lower(),
            (category or "").strip(),
            (source or "").strip(),
            (mode or "daily").strip(),
            int(start_time),
        )
    )


def update_termo_game_progress(
    user_id: int,
    attempts: int,
    guesses_json: str,
    used_letters: str,
):
    _run(
        """
        UPDATE termo_games
        SET attempts = %s,
            guesses = %s::jsonb,
            used_letters = %s,
            updated_at = NOW()
        WHERE user_id = %s
          AND status = 'playing'
        """,
        (
            int(attempts),
            guesses_json,
            (used_letters or "").strip().upper(),
            int(user_id),
        )
    )


def finish_termo_game(
    user_id: int,
    status: str,
    attempts: int,
    guesses_json: str,
    used_letters: str,
    time_spent_seconds: int = 0,
    reward_coins: int = 0,
    reward_xp: int = 0,
    won_at_attempt: int = 0,
):
    _run(
        """
        UPDATE termo_games
        SET status = %s,
            attempts = %s,
            guesses = %s::jsonb,
            used_letters = %s,
            time_spent_seconds = %s,
            reward_coins = %s,
            reward_xp = %s,
            won_at_attempt = %s,
            finished_at = NOW(),
            updated_at = NOW()
        WHERE user_id = %s
          AND status = 'playing'
        """,
        (
            (status or "").strip(),
            int(attempts),
            guesses_json,
            (used_letters or "").strip().upper(),
            int(time_spent_seconds),
            int(reward_coins),
            int(reward_xp),
            int(won_at_attempt),
            int(user_id),
        )
    )


def mark_termo_word_used(user_id: int, word: str):
    _run(
        """
        INSERT INTO termo_used_words (user_id, word)
        VALUES (%s, %s)
        ON CONFLICT (user_id, word) DO NOTHING
        """,
        (int(user_id), (word or "").strip().lower())
    )


def has_user_used_termo_word(user_id: int, word: str) -> bool:
    row = _run(
        """
        SELECT 1
        FROM termo_used_words
        WHERE user_id = %s
          AND word = %s
        LIMIT 1
        """,
        (int(user_id), (word or "").strip().lower()),
        fetch="one"
    )
    return bool(row)


def record_termo_result(user_id: int, win: bool, attempts: int):
    ensure_termo_stats_row(user_id)

    row = _run(
        """
        SELECT user_id, games_played, wins, losses, current_streak, best_streak, best_score, last_play_date
        FROM termo_stats
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    ) or {}

    today = date.today()
    yesterday = today - timedelta(days=1)

    games_played = int(row.get("games_played") or 0) + 1
    wins = int(row.get("wins") or 0)
    losses = int(row.get("losses") or 0)
    current_streak = int(row.get("current_streak") or 0)
    best_streak = int(row.get("best_streak") or 0)
    best_score = int(row.get("best_score") or 0)
    last_play_date = row.get("last_play_date")

    if win:
        wins += 1

        if last_play_date == yesterday:
            current_streak += 1
        elif last_play_date == today:
            current_streak = max(current_streak, 1)
        else:
            current_streak = 1

        if current_streak > best_streak:
            best_streak = current_streak

        attempts = int(attempts)
        if attempts > 0 and (best_score == 0 or attempts < best_score):
            best_score = attempts
    else:
        losses += 1
        current_streak = 0

    _run(
        """
        UPDATE termo_stats
        SET games_played = %s,
            wins = %s,
            losses = %s,
            current_streak = %s,
            best_streak = %s,
            best_score = %s,
            last_play_date = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (
            games_played,
            wins,
            losses,
            current_streak,
            best_streak,
            best_score,
            today,
            int(user_id),
        )
    )

    if win:
        col_map = {
            1: "one_try",
            2: "two_try",
            3: "three_try",
            4: "four_try",
            5: "five_try",
            6: "six_try",
        }
        col = col_map.get(int(attempts))
        if col:
            _run(
                f"""
                UPDATE termo_attempt_distribution
                SET {col} = {col} + 1
                WHERE user_id = %s
                """,
                (int(user_id),)
            )


def get_termo_stats(user_id: int) -> Optional[Dict[str, Any]]:
    ensure_termo_stats_row(user_id)

    return _run(
        """
        SELECT
            ts.user_id,
            ts.games_played,
            ts.wins,
            ts.losses,
            ts.current_streak,
            ts.best_streak,
            ts.best_score,
            ts.last_play_date,
            ts.updated_at,
            tad.one_try,
            tad.two_try,
            tad.three_try,
            tad.four_try,
            tad.five_try,
            tad.six_try
        FROM termo_stats ts
        LEFT JOIN termo_attempt_distribution tad
               ON tad.user_id = ts.user_id
        WHERE ts.user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )


def get_termo_global_ranking(limit: int = 10) -> List[Dict[str, Any]]:
    rows = _run(
        """
        SELECT
            user_id,
            games_played,
            wins,
            losses,
            current_streak,
            best_streak,
            best_score,
            CASE
                WHEN games_played > 0 THEN ROUND((wins::numeric / games_played::numeric) * 100, 2)
                ELSE 0
            END AS win_rate
        FROM termo_stats
        WHERE games_played > 0
        ORDER BY wins DESC, best_streak DESC, best_score ASC, user_id ASC
        LIMIT %s
        """,
        (int(limit),),
        fetch="all"
    )
    return rows or []


def get_termo_period_ranking(days: int, limit: int = 10) -> List[Dict[str, Any]]:
    rows = _run(
        """
        SELECT
            user_id,
            COUNT(*) FILTER (WHERE status = 'win') AS wins,
            COUNT(*) FILTER (WHERE status IN ('win', 'lose', 'timeout')) AS games_played,
            COALESCE(AVG(NULLIF(won_at_attempt, 0)) FILTER (WHERE status = 'win'), 0) AS avg_attempts
        FROM termo_games
        WHERE mode = 'daily'
          AND finished_at >= NOW() - (%s || ' days')::interval
        GROUP BY user_id
        HAVING COUNT(*) FILTER (WHERE status IN ('win', 'lose', 'timeout')) > 0
        ORDER BY wins DESC, avg_attempts ASC, user_id ASC
        LIMIT %s
        """,
        (str(int(days)), int(limit)),
        fetch="all"
    )
    return rows or []


def get_termo_user_rank(user_id: int) -> int:
    ensure_termo_stats_row(user_id)

    row = _run(
        """
        SELECT rank_pos
        FROM (
            SELECT
                user_id,
                RANK() OVER (
                    ORDER BY wins DESC, best_streak DESC, best_score ASC, user_id ASC
                ) AS rank_pos
            FROM termo_stats
            WHERE games_played > 0
        ) ranked
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )

    return int((row or {}).get("rank_pos") or 0)
