import json
import os
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from zoneinfo import ZoneInfo

from datetime import date, datetime, timedelta, time as dt_time


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado nas variáveis de ambiente.")

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=10,
    timeout=10,
)

SP_TZ = ZoneInfo("America/Sao_Paulo")

def _sp_now() -> datetime:
    return datetime.now(SP_TZ)


def _sp_today() -> date:
    return _sp_now().date()

DADO_INITIAL_BALANCE = 4
DADO_MAX_BALANCE = 24
DADO_ROLL_TTL_MINUTES = int(os.getenv("DADO_ROLL_TTL_MINUTES", "15"))

# horários fixos do sistema
DADO_RECHARGE_HOURS = (1, 4, 7, 10, 13, 16, 19, 22)


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
# DADO HELPERS (São Paulo / horários fixos)
# =========================================================

def _now_sp() -> datetime:
    return datetime.now(SP_TZ)


def _slot_parts_from_dt(dt: datetime) -> Tuple[date, int]:
    """
    Retorna (data_base, idx_slot_creditado).

    idx:
      0 -> 01:00
      1 -> 04:00
      2 -> 07:00
      3 -> 10:00
      4 -> 13:00
      5 -> 16:00
      6 -> 19:00
      7 -> 22:00

    Antes de 01:00, considera o último slot do dia anterior (22:00).
    """
    dt = dt.astimezone(SP_TZ)
    h = dt.hour

    if h < 1:
        return (dt.date() - timedelta(days=1), 7)

    idx = min((h - 1) // 3, 7)
    return (dt.date(), idx)


def _slot_number_from_dt(dt: Optional[datetime] = None) -> int:
    if dt is None:
        dt = _now_sp()
    base_date, idx = _slot_parts_from_dt(dt)
    return base_date.toordinal() * 8 + idx


def _slot_datetime_from_number(slot_number: int) -> datetime:
    day_ord = int(slot_number) // 8
    idx = int(slot_number) % 8
    d = date.fromordinal(day_ord)
    hour = DADO_RECHARGE_HOURS[idx]
    return datetime(d.year, d.month, d.day, hour, 0, 0, tzinfo=SP_TZ)


def _next_recharge_dt_from_dt(dt: Optional[datetime] = None) -> datetime:
    if dt is None:
        dt = _now_sp()
    dt = dt.astimezone(SP_TZ)

    for hour in DADO_RECHARGE_HOURS:
        candidate = datetime(dt.year, dt.month, dt.day, hour, 0, 0, tzinfo=SP_TZ)
        if dt < candidate:
            return candidate

    tomorrow = dt.date() + timedelta(days=1)
    return datetime(
        tomorrow.year,
        tomorrow.month,
        tomorrow.day,
        DADO_RECHARGE_HOURS[0],
        0,
        0,
        tzinfo=SP_TZ,
    )


def _get_recharge_info() -> Dict[str, Any]:
    now = _now_sp()
    next_dt = _next_recharge_dt_from_dt(now)
    return {
        "now_iso": now.isoformat(),
        "next_recharge_iso": next_dt.isoformat(),
        "next_recharge_hhmm": next_dt.strftime("%H:%M"),
        "timezone": "America/Sao_Paulo",
        "max_balance": DADO_MAX_BALANCE,
    }


def _clean_roll_options(options: List[Dict[str, Any]], expected_len: Optional[int] = None) -> List[Dict[str, Any]]:
    clean_options: List[Dict[str, Any]] = []
    seen_ids = set()

    if not isinstance(options, list):
        raise ValueError("options inválidas")

    for item in options:
        if not isinstance(item, dict):
            raise ValueError("option inválida")

        anime_id = int(item.get("id") or 0)
        if anime_id <= 0:
            raise ValueError("anime_id inválido nas options")
        if anime_id in seen_ids:
            raise ValueError("options contém anime duplicado")
        seen_ids.add(anime_id)

        clean_options.append({
            "id": anime_id,
            "title": str(item.get("title") or "").strip(),
            "cover": str(item.get("cover") or "").strip(),
        })

    if expected_len is not None and len(clean_options) != int(expected_len):
        raise ValueError("options deve ter exatamente a quantidade do valor do dado")

    return clean_options


def _coerce_roll_options(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            items = parsed if isinstance(parsed, list) else []
        except Exception:
            items = []
    else:
        items = []

    clean: List[Dict[str, Any]] = []
    seen = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        anime_id = int(item.get("id") or 0)
        if anime_id <= 0 or anime_id in seen:
            continue
        seen.add(anime_id)

        clean.append({
            "id": anime_id,
            "title": str(item.get("title") or "").strip(),
            "cover": str(item.get("cover") or "").strip(),
        })

    return clean


def _is_valid_roll_options(options: Any, dice_value: int) -> bool:
    if not isinstance(options, list):
        return False
    if dice_value < 1 or dice_value > 6:
        return False
    if len(options) != dice_value:
        return False

    seen = set()
    for item in options:
        if not isinstance(item, dict):
            return False
        anime_id = int(item.get("id") or 0)
        if anime_id <= 0 or anime_id in seen:
            return False
        seen.add(anime_id)
    return True


def _roll_expired(row: Dict[str, Any]) -> bool:
    expires_at = row.get("expires_at")
    if not expires_at:
        return False

    try:
        now = datetime.now(expires_at.tzinfo) if getattr(expires_at, "tzinfo", None) else datetime.utcnow()
        return expires_at <= now
    except Exception:
        return False


# =========================================================
# INIT / MIGRATIONS
# =========================================================

def create_tables():
    create_users_table()
    create_media_request_tables()
    create_cards_tables()
    create_collection_tables()
    create_level_tables()
    create_termo_tables()
    create_dado_tables()
    create_profile_settings_table()
    create_shop_tables()
    create_daily_tables()
    create_weekly_ranking_tables()
    create_trades_table()
    create_message_tables()
    create_card_contrib_tables()


def create_users_table():
    _run("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        lang TEXT,
        username TEXT,
        full_name TEXT,
        coins BIGINT NOT NULL DEFAULT 0,
        terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
        terms_version TEXT,
        accepted_at TIMESTAMPTZ,
        welcome_sent BOOLEAN NOT NULL DEFAULT FALSE,
        must_join_ok BOOLEAN NOT NULL DEFAULT FALSE,
        dado_balance INTEGER NOT NULL DEFAULT 4,
        dado_slot BIGINT NOT NULL DEFAULT -1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)

    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS coins BIGINT NOT NULL DEFAULT 0;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version TEXT;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_sent BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS must_join_ok BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_balance INTEGER NOT NULL DEFAULT 4;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_slot BIGINT NOT NULL DEFAULT -1;""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")
    _run("""ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")

    _run("""
    CREATE INDEX IF NOT EXISTS idx_users_dado_balance
    ON users (dado_balance DESC)
    """)


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


def create_collection_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS user_collection_profile (
        user_id BIGINT PRIMARY KEY,
        favorite_character_id BIGINT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""ALTER TABLE user_collection_profile ADD COLUMN IF NOT EXISTS favorite_character_id BIGINT;""")
    _run("""ALTER TABLE user_collection_profile ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")
    _run("""ALTER TABLE user_collection_profile ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")


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

def set_global_character_image(character_id: int, image_url: str, updated_by: int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO character_image_overrides (character_id, image_url, updated_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (character_id)
                DO UPDATE SET
                    image_url = EXCLUDED.image_url,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                """,
                (character_id, image_url, updated_by),
            )
        conn.commit()

def get_character_image_override(character_id: int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT image_url
                FROM character_image_overrides
                WHERE character_id = %s
                """,
                (character_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return row[0]
            
def create_dado_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS dice_rolls (
        roll_id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        dice_value INTEGER NOT NULL,
        options_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        selected_anime_id BIGINT,
        rewarded_character_id BIGINT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())::BIGINT),
        picked_at TIMESTAMPTZ,
        resolved_at TIMESTAMPTZ,
        expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '15 minutes')
    )
    """)

    _run("""ALTER TABLE dice_rolls ADD COLUMN IF NOT EXISTS selected_anime_id BIGINT;""")
    _run("""ALTER TABLE dice_rolls ADD COLUMN IF NOT EXISTS rewarded_character_id BIGINT;""")
    _run("""ALTER TABLE dice_rolls ADD COLUMN IF NOT EXISTS picked_at TIMESTAMPTZ;""")
    _run("""ALTER TABLE dice_rolls ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;""")
    _run("""ALTER TABLE dice_rolls ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '15 minutes');""")

    _run("""
    DO $$
    DECLARE
        col_type TEXT;
    BEGIN
        SELECT data_type
          INTO col_type
          FROM information_schema.columns
         WHERE table_name = 'dice_rolls'
           AND column_name = 'created_at';

        IF col_type IS NOT NULL AND col_type <> 'bigint' THEN
            ALTER TABLE dice_rolls
            ALTER COLUMN created_at TYPE BIGINT
            USING CASE
                WHEN created_at IS NULL THEN NULL
                ELSE EXTRACT(EPOCH FROM created_at)::BIGINT
            END;
        END IF;
    END
    $$;
    """)

    _run("""
    ALTER TABLE dice_rolls
    ALTER COLUMN created_at SET DEFAULT (EXTRACT(EPOCH FROM NOW())::BIGINT)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_dice_rolls_user_created
    ON dice_rolls (user_id, created_at DESC)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_dice_rolls_status
    ON dice_rolls (status)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_dice_rolls_user_status
    ON dice_rolls (user_id, status)
    """)

    _run("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_dice_rolls_one_active_per_user
    ON dice_rolls (user_id)
    WHERE status IN ('pending', 'picked')
    """)


def create_profile_settings_table():
    _run("""
    CREATE TABLE IF NOT EXISTS user_profile_settings (
        user_id BIGINT PRIMARY KEY,
        nickname TEXT UNIQUE,
        favorite_character_id BIGINT,
        country_code TEXT NOT NULL DEFAULT 'BR',
        language TEXT NOT NULL DEFAULT 'pt',
        private_profile BOOLEAN NOT NULL DEFAULT FALSE,
        notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        dado_full_notified BOOLEAN NOT NULL DEFAULT FALSE,
        dado_full_notified_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS nickname TEXT;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS favorite_character_id BIGINT;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS country_code TEXT NOT NULL DEFAULT 'BR';""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'pt';""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS private_profile BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS dado_full_notified BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS dado_full_notified_at TIMESTAMPTZ;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")

    _run("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_user_profile_settings_nickname
    ON user_profile_settings (nickname)
    WHERE nickname IS NOT NULL
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_profile_settings_notifications
    ON user_profile_settings (notifications_enabled, dado_full_notified)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_profile_settings_nickname_lower
    ON user_profile_settings (LOWER(nickname))
    WHERE nickname IS NOT NULL
    """)


# =========================================================
# USERS
# =========================================================

def create_or_get_user(user_id: int):
    initial_slot = _slot_number_from_dt(_now_sp())
    _run(
        """
        INSERT INTO users (user_id, dado_balance, dado_slot, created_at, updated_at)
        VALUES (%s, %s, %s, NOW(), NOW())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id), DADO_INITIAL_BALANCE, initial_slot)
    )


def touch_user_identity(user_id: int, username: str = "", full_name: str = ""):
    create_or_get_user(user_id)
    _run(
        """
        UPDATE users
        SET username = %s,
            full_name = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (
            (username or "").strip(),
            (full_name or "").strip(),
            int(user_id),
        )
    )


def set_language(user_id: int, lang: str):
    create_or_get_user(user_id)
    _run(
        """
        UPDATE users
        SET lang = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        ((lang or "").strip(), int(user_id))
    )


def accept_terms(user_id: int, version: str):
    create_or_get_user(user_id)
    _run(
        """
        UPDATE users
           SET terms_accepted = TRUE,
               terms_version = %s,
               accepted_at = NOW(),
               updated_at = NOW()
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
        SELECT
            lang,
            username,
            full_name,
            coins,
            terms_accepted,
            terms_version,
            welcome_sent,
            must_join_ok,
            dado_balance,
            dado_slot
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
        "username": row.get("username"),
        "full_name": row.get("full_name"),
        "coins": int(row.get("coins") or 0),
        "terms_accepted": bool(row.get("terms_accepted")),
        "terms_version": row.get("terms_version"),
        "welcome_sent": bool(row.get("welcome_sent")),
        "must_join_ok": bool(row.get("must_join_ok")),
        "dado_balance": int(row.get("dado_balance") or 0),
        "dado_slot": int(row.get("dado_slot") or -1),
    }


def mark_welcome_sent(user_id: int):
    create_or_get_user(user_id)
    _run(
        "UPDATE users SET welcome_sent = TRUE, updated_at = NOW() WHERE user_id = %s",
        (int(user_id),)
    )


def reset_welcome_sent(user_id: int):
    create_or_get_user(user_id)
    _run(
        "UPDATE users SET welcome_sent = FALSE, updated_at = NOW() WHERE user_id = %s",
        (int(user_id),)
    )


def set_must_join_ok(user_id: int, value: bool):
    create_or_get_user(user_id)
    _run(
        """
        UPDATE users
        SET must_join_ok = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (bool(value), int(user_id))
    )


def add_user_coins(user_id: int, amount: int):
    create_or_get_user(user_id)
    _run(
        """
        UPDATE users
        SET coins = COALESCE(coins, 0) + %s,
            updated_at = NOW()
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

def ensure_collection_profile_row(user_id: int):
    _run(
        """
        INSERT INTO user_collection_profile (user_id, created_at, updated_at)
        VALUES (%s, NOW(), NOW())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),)
    )


def get_collection_profile(user_id: int) -> Optional[Dict[str, Any]]:
    ensure_collection_profile_row(user_id)
    row = _run(
        """
        SELECT user_id, favorite_character_id, created_at, updated_at
        FROM user_collection_profile
        WHERE user_id = %s
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one"
    )
    return row or None


def set_favorite_character_id(user_id: int, character_id: Optional[int]):
    ensure_collection_profile_row(user_id)
    _run(
        """
        UPDATE user_collection_profile
        SET favorite_character_id = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (int(character_id) if character_id else None, int(user_id))
    )


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
          AND quantity > 0
        ORDER BY quantity DESC, updated_at DESC, character_id ASC
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
        SELECT
            up.user_id,
            up.xp,
            up.level,
            up.total_actions,
            u.username,
            u.full_name,
            ups.nickname
        FROM user_progress up
        LEFT JOIN users u
               ON u.user_id = up.user_id
        LEFT JOIN user_profile_settings ups
               ON ups.user_id = up.user_id
        ORDER BY up.level DESC, up.xp DESC, up.total_actions DESC, up.user_id ASC
        LIMIT %s
        """,
        (int(limit),),
        fetch="all"
    )
    return rows or []


# =========================================================
# DADO / ROLLS (ANTIFALHA)
# =========================================================

def _refresh_dado_locked(cur, user_id: int) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT user_id, dado_balance, dado_slot
        FROM users
        WHERE user_id = %s
        FOR UPDATE
        """,
        (int(user_id),)
    )
    row = cur.fetchone()

    if not row:
        current_slot = _slot_number_from_dt(_now_sp())
        cur.execute(
            """
            INSERT INTO users (user_id, dado_balance, dado_slot, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            RETURNING user_id, dado_balance, dado_slot
            """,
            (int(user_id), DADO_INITIAL_BALANCE, current_slot)
        )
        row = cur.fetchone()

    balance = int(row.get("dado_balance") or 0)
    last_slot = int(row.get("dado_slot") or -1)
    current_slot = _slot_number_from_dt(_now_sp())

    if last_slot < 0:
        cur.execute(
            """
            UPDATE users
            SET dado_slot = %s,
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING user_id, dado_balance, dado_slot
            """,
            (current_slot, int(user_id))
        )
        row = cur.fetchone()
        balance = int(row.get("dado_balance") or 0)
        last_slot = int(row.get("dado_slot") or current_slot)
    elif current_slot > last_slot:
        gained = current_slot - last_slot
        new_balance = min(DADO_MAX_BALANCE, balance + gained)
        cur.execute(
            """
            UPDATE users
            SET dado_balance = %s,
                dado_slot = %s,
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING user_id, dado_balance, dado_slot
            """,
            (new_balance, current_slot, int(user_id))
        )
        row = cur.fetchone()
        balance = int(row.get("dado_balance") or 0)
        last_slot = int(row.get("dado_slot") or current_slot)

    info = _get_recharge_info()

    return {
        "user_id": int(user_id),
        "balance": balance,
        "slot": last_slot,
        "max_balance": DADO_MAX_BALANCE,
        "timezone": info["timezone"],
        "next_recharge_iso": info["next_recharge_iso"],
        "next_recharge_hhmm": info["next_recharge_hhmm"],
    }


def refresh_dado_balance(user_id: int) -> Dict[str, Any]:
    create_or_get_user(user_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                state = _refresh_dado_locked(cur, user_id)
                conn.commit()
                return state
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def get_dado_state(user_id: int) -> Dict[str, Any]:
    return refresh_dado_balance(user_id)


def get_dado_balance(user_id: int) -> int:
    state = refresh_dado_balance(user_id)
    return int(state.get("balance") or 0)


def set_dado_balance(user_id: int, balance: int):
    create_or_get_user(user_id)
    balance = max(0, min(DADO_MAX_BALANCE, int(balance)))

    _run(
        """
        UPDATE users
        SET dado_balance = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (balance, int(user_id))
    )


def add_dado_balance(user_id: int, amount: int):
    amount = int(amount)
    if amount <= 0:
        return
    create_or_get_user(user_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                state = _refresh_dado_locked(cur, user_id)
                new_balance = min(DADO_MAX_BALANCE, int(state["balance"]) + amount)
                cur.execute(
                    """
                    UPDATE users
                    SET dado_balance = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (new_balance, int(user_id))
                )
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def _reset_dado_full_notification_in_tx(cur, user_id: int):
    cur.execute(
        """
        UPDATE user_profile_settings
        SET dado_full_notified = FALSE,
            dado_full_notified_at = NULL,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (int(user_id),)
    )


def consume_dado(user_id: int, amount: int = 1) -> bool:
    amount = int(amount)
    if amount <= 0:
        return True

    create_or_get_user(user_id)
    ensure_profile_settings_row(user_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                state = _refresh_dado_locked(cur, user_id)
                balance = int(state["balance"])

                if balance < amount:
                    conn.rollback()
                    return False

                cur.execute(
                    """
                    UPDATE users
                    SET dado_balance = dado_balance - %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                      AND dado_balance >= %s
                    """,
                    (amount, int(user_id), amount)
                )
                if cur.rowcount != 1:
                    conn.rollback()
                    return False

                _reset_dado_full_notification_in_tx(cur, user_id)

                conn.commit()
                return True
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def refund_dado(user_id: int, amount: int = 1):
    amount = int(amount)
    if amount <= 0:
        return
    add_dado_balance(user_id, amount)


def get_next_dado_recharge_info(user_id: int) -> Dict[str, Any]:
    state = refresh_dado_balance(user_id)
    return {
        "balance": int(state["balance"]),
        "next_recharge_iso": state["next_recharge_iso"],
        "next_recharge_hhmm": state["next_recharge_hhmm"],
        "timezone": state["timezone"],
        "max_balance": state["max_balance"],
    }


def get_active_dice_roll(user_id: int) -> Optional[Dict[str, Any]]:
    row = _run(
        """
        SELECT
            roll_id,
            user_id,
            dice_value,
            options_json,
            selected_anime_id,
            rewarded_character_id,
            status,
            created_at,
            picked_at,
            resolved_at,
            expires_at
        FROM dice_rolls
        WHERE user_id = %s
          AND status IN ('pending', 'picked')
        ORDER BY roll_id DESC
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one"
    )

    if not row:
        return None

    row["options_json"] = _coerce_roll_options(row.get("options_json"))
    return row


def get_dice_roll(roll_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if user_id is None:
        row = _run(
            """
            SELECT *
            FROM dice_rolls
            WHERE roll_id = %s
            LIMIT 1
            """,
            (int(roll_id),),
            fetch="one"
        )
    else:
        row = _run(
            """
            SELECT *
            FROM dice_rolls
            WHERE roll_id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (int(roll_id), int(user_id)),
            fetch="one"
        )

    if row:
        row["options_json"] = _coerce_roll_options(row.get("options_json"))
    return row


def expire_stale_dice_rolls(refund_pending: bool = True) -> int:
    expired_count = 0

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT roll_id, user_id, status
                    FROM dice_rolls
                    WHERE status IN ('pending', 'picked')
                      AND expires_at <= NOW()
                    FOR UPDATE
                    """
                )
                rows = cur.fetchall() or []

                for row in rows:
                    roll_id = int(row["roll_id"])
                    user_id = int(row["user_id"])
                    status = str(row["status"])

                    cur.execute(
                        """
                        UPDATE dice_rolls
                        SET status = 'expired'
                        WHERE roll_id = %s
                          AND status IN ('pending', 'picked')
                        """,
                        (roll_id,)
                    )

                    if refund_pending and status == "pending":
                        state = _refresh_dado_locked(cur, user_id)
                        new_balance = min(DADO_MAX_BALANCE, int(state["balance"]) + 1)
                        cur.execute(
                            """
                            UPDATE users
                            SET dado_balance = %s,
                                updated_at = NOW()
                            WHERE user_id = %s
                            """,
                            (new_balance, user_id)
                        )

                    expired_count += 1

                conn.commit()
                return expired_count
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def create_dice_roll(user_id: int, dice_value: int, options: List[Dict[str, Any]]) -> Dict[str, Any]:
    dice_value = int(dice_value)
    if dice_value < 1 or dice_value > 6:
        raise ValueError("dice_value deve ser entre 1 e 6")

    clean_options = _clean_roll_options(options, expected_len=dice_value)
    create_or_get_user(user_id)
    ensure_profile_settings_row(user_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                _refresh_dado_locked(cur, user_id)

                cur.execute(
                    """
                    SELECT roll_id, status, expires_at, options_json, dice_value
                    FROM dice_rolls
                    WHERE user_id = %s
                      AND status IN ('pending', 'picked')
                    ORDER BY roll_id DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (int(user_id),)
                )
                active = cur.fetchone()

                if active:
                    active["options_json"] = _coerce_roll_options(active.get("options_json"))
                    active_dice = int(active.get("dice_value") or 0)

                    if _roll_expired(active):
                        old_status = str(active.get("status") or "")
                        cur.execute(
                            """
                            UPDATE dice_rolls
                            SET status = 'expired'
                            WHERE roll_id = %s
                              AND status IN ('pending', 'picked')
                            """,
                            (int(active["roll_id"]),)
                        )

                        if old_status == "pending":
                            state = _refresh_dado_locked(cur, user_id)
                            new_balance = min(DADO_MAX_BALANCE, int(state["balance"]) + 1)
                            cur.execute(
                                """
                                UPDATE users
                                SET dado_balance = %s,
                                    updated_at = NOW()
                                WHERE user_id = %s
                                """,
                                (new_balance, int(user_id))
                            )

                    elif _is_valid_roll_options(active["options_json"], active_dice):
                        cur.execute(
                            "SELECT * FROM dice_rolls WHERE roll_id = %s",
                            (int(active["roll_id"]),)
                        )
                        existing = cur.fetchone()
                        if existing:
                            existing["options_json"] = _coerce_roll_options(existing.get("options_json"))
                        conn.commit()
                        return {
                            "ok": True,
                            "reused": True,
                            "roll": existing,
                            "options": active["options_json"],
                        }

                    else:
                        cur.execute(
                            """
                            UPDATE dice_rolls
                            SET status = 'cancelled'
                            WHERE roll_id = %s
                              AND status IN ('pending', 'picked')
                            """,
                            (int(active["roll_id"]),)
                        )

                        if str(active.get("status") or "") == "pending":
                            state = _refresh_dado_locked(cur, user_id)
                            new_balance = min(DADO_MAX_BALANCE, int(state["balance"]) + 1)
                            cur.execute(
                                """
                                UPDATE users
                                SET dado_balance = %s,
                                    updated_at = NOW()
                                WHERE user_id = %s
                                """,
                                (new_balance, int(user_id))
                            )

                state = _refresh_dado_locked(cur, user_id)
                balance = int(state["balance"])

                if balance <= 0:
                    conn.rollback()
                    return {
                        "ok": False,
                        "error": "no_balance",
                        "balance": balance,
                    }

                cur.execute(
                    """
                    UPDATE users
                    SET dado_balance = dado_balance - 1,
                        updated_at = NOW()
                    WHERE user_id = %s
                      AND dado_balance > 0
                    RETURNING dado_balance
                    """,
                    (int(user_id),)
                )
                consumed = cur.fetchone()
                if not consumed:
                    conn.rollback()
                    return {
                        "ok": False,
                        "error": "consume_failed",
                        "balance": 0,
                    }

                _reset_dado_full_notification_in_tx(cur, user_id)

                created_ts = int(time.time())

                cur.execute(
                    """
                    INSERT INTO dice_rolls
                    (
                        user_id,
                        dice_value,
                        options_json,
                        status,
                        created_at,
                        expires_at
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s::jsonb,
                        'pending',
                        %s,
                        NOW() + (%s || ' minutes')::interval
                    )
                    RETURNING *
                    """,
                    (
                        int(user_id),
                        dice_value,
                        json.dumps(clean_options, ensure_ascii=False),
                        created_ts,
                        str(int(DADO_ROLL_TTL_MINUTES)),
                    )
                )
                created = cur.fetchone()
                if created:
                    created["options_json"] = _coerce_roll_options(created.get("options_json"))

                conn.commit()
                return {
                    "ok": True,
                    "reused": False,
                    "roll": created,
                    "options": clean_options,
                }

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def pick_dice_roll_anime(user_id: int, roll_id: int, anime_id: int) -> Dict[str, Any]:
    user_id = int(user_id)
    roll_id = int(roll_id)
    anime_id = int(anime_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT *
                    FROM dice_rolls
                    WHERE roll_id = %s
                      AND user_id = %s
                    FOR UPDATE
                    """,
                    (roll_id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return {"ok": False, "error": "roll_not_found"}

                row["options_json"] = _coerce_roll_options(row.get("options_json"))

                status = str(row.get("status") or "")
                if status == "resolved":
                    conn.commit()
                    return {"ok": True, "already_done": True, "roll": row}

                if status != "pending":
                    conn.rollback()
                    return {"ok": False, "error": "invalid_status", "status": status}

                if _roll_expired(row):
                    cur.execute(
                        """
                        UPDATE dice_rolls
                        SET status = 'expired'
                        WHERE roll_id = %s
                        """,
                        (roll_id,)
                    )

                    state = _refresh_dado_locked(cur, user_id)
                    new_balance = min(DADO_MAX_BALANCE, int(state["balance"]) + 1)
                    cur.execute(
                        """
                        UPDATE users
                        SET dado_balance = %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (new_balance, user_id)
                    )

                    conn.commit()
                    return {"ok": False, "error": "expired"}

                options = row.get("options_json") or []
                allowed_ids = {
                    int(item["id"])
                    for item in options
                    if isinstance(item, dict) and int(item.get("id") or 0) > 0
                }

                if not allowed_ids:
                    cur.execute(
                        """
                        UPDATE dice_rolls
                        SET status = 'cancelled'
                        WHERE roll_id = %s
                          AND user_id = %s
                          AND status = 'pending'
                        """,
                        (roll_id, user_id)
                    )

                    state = _refresh_dado_locked(cur, user_id)
                    new_balance = min(DADO_MAX_BALANCE, int(state["balance"]) + 1)
                    cur.execute(
                        """
                        UPDATE users
                        SET dado_balance = %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (new_balance, user_id)
                    )

                    conn.commit()
                    return {"ok": False, "error": "roll_invalid"}

                if anime_id not in allowed_ids:
                    conn.rollback()
                    return {
                        "ok": False,
                        "error": "anime_not_in_roll",
                        "allowed_ids": sorted(list(allowed_ids)),
                    }

                cur.execute(
                    """
                    UPDATE dice_rolls
                    SET selected_anime_id = %s,
                        status = 'picked',
                        picked_at = NOW()
                    WHERE roll_id = %s
                      AND user_id = %s
                      AND status = 'pending'
                    RETURNING *
                    """,
                    (anime_id, roll_id, user_id)
                )
                updated = cur.fetchone()
                if not updated:
                    conn.rollback()
                    return {"ok": False, "error": "pick_failed"}

                updated["options_json"] = _coerce_roll_options(updated.get("options_json"))

                conn.commit()
                return {"ok": True, "roll": updated}

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def resolve_dice_roll(user_id: int, roll_id: int, character_id: int) -> Dict[str, Any]:
    user_id = int(user_id)
    roll_id = int(roll_id)
    character_id = int(character_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT *
                    FROM dice_rolls
                    WHERE roll_id = %s
                      AND user_id = %s
                    FOR UPDATE
                    """,
                    (roll_id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return {"ok": False, "error": "roll_not_found"}

                status = str(row.get("status") or "")
                if status == "resolved":
                    conn.commit()
                    return {"ok": True, "already_done": True, "roll": row}

                if status != "picked":
                    conn.rollback()
                    return {"ok": False, "error": "invalid_status", "status": status}

                selected_anime_id = row.get("selected_anime_id")
                if not selected_anime_id:
                    conn.rollback()
                    return {"ok": False, "error": "no_selected_anime"}

                cur.execute(
                    """
                    INSERT INTO user_card_collection (user_id, character_id, quantity, updated_at)
                    VALUES (%s, %s, 1, NOW())
                    ON CONFLICT (user_id, character_id)
                    DO UPDATE SET
                        quantity = user_card_collection.quantity + 1,
                        updated_at = NOW()
                    """,
                    (user_id, character_id)
                )

                cur.execute(
                    """
                    UPDATE dice_rolls
                    SET rewarded_character_id = %s,
                        status = 'resolved',
                        resolved_at = NOW()
                    WHERE roll_id = %s
                      AND user_id = %s
                      AND status = 'picked'
                    RETURNING *
                    """,
                    (character_id, roll_id, user_id)
                )
                updated = cur.fetchone()
                if not updated:
                    conn.rollback()
                    return {"ok": False, "error": "resolve_failed"}

                conn.commit()
                return {"ok": True, "roll": updated}

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def cancel_dice_roll(user_id: int, roll_id: int, refund: bool = False) -> bool:
    user_id = int(user_id)
    roll_id = int(roll_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT *
                    FROM dice_rolls
                    WHERE roll_id = %s
                      AND user_id = %s
                    FOR UPDATE
                    """,
                    (roll_id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return False

                status = str(row.get("status") or "")
                if status not in ("pending", "picked"):
                    conn.rollback()
                    return False

                cur.execute(
                    """
                    UPDATE dice_rolls
                    SET status = 'cancelled'
                    WHERE roll_id = %s
                      AND user_id = %s
                    """,
                    (roll_id, user_id)
                )

                if refund and status == "pending":
                    state = _refresh_dado_locked(cur, user_id)
                    new_balance = min(DADO_MAX_BALANCE, int(state["balance"]) + 1)
                    cur.execute(
                        """
                        UPDATE users
                        SET dado_balance = %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (new_balance, user_id)
                    )

                conn.commit()
                return True
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def get_user_dice_roll_history(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    rows = _run(
        """
        SELECT *
        FROM dice_rolls
        WHERE user_id = %s
        ORDER BY roll_id DESC
        LIMIT %s
        """,
        (int(user_id), int(limit)),
        fetch="all"
    )

    for row in rows or []:
        row["options_json"] = _coerce_roll_options(row.get("options_json"))

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
    game_id: int,
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
        WHERE id = %s
        """,
        (
            int(attempts),
            guesses_json,
            (used_letters or "").strip().upper(),
            int(game_id),
        )
    )

def finish_termo_game(
    game_id: int,
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
        WHERE id = %s
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
            int(game_id),
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

    today = _sp_today()
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
            ts.user_id,
            u.username,
            u.full_name,
            ts.games_played,
            ts.wins,
            ts.losses,
            ts.current_streak,
            ts.best_streak,
            ts.best_score,
            CASE
                WHEN ts.games_played > 0 THEN ROUND((ts.wins::numeric / ts.games_played::numeric) * 100, 2)
                ELSE 0
            END AS win_rate
        FROM termo_stats ts
        LEFT JOIN users u
               ON u.user_id = ts.user_id
        WHERE ts.games_played > 0
        ORDER BY ts.wins DESC, ts.best_streak DESC, ts.best_score ASC, ts.user_id ASC
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
            tg.user_id,
            u.username,
            u.full_name,
            COUNT(*) FILTER (WHERE tg.status = 'win') AS wins,
            COUNT(*) FILTER (WHERE tg.status IN ('win', 'lose', 'timeout')) AS games_played,
            COALESCE(AVG(NULLIF(tg.won_at_attempt, 0)) FILTER (WHERE tg.status = 'win'), 0) AS avg_attempts
        FROM termo_games tg
        LEFT JOIN users u
               ON u.user_id = tg.user_id
        WHERE tg.mode = 'daily'
          AND tg.finished_at >= NOW() - (%s || ' days')::interval
        GROUP BY tg.user_id, u.username, u.full_name
        HAVING COUNT(*) FILTER (WHERE tg.status IN ('win', 'lose', 'timeout')) > 0
        ORDER BY wins DESC, avg_attempts ASC, tg.user_id ASC
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


# =========================================================
# ADMIN — DADO
# =========================================================

def admin_give_dado_to_user(user_id: int, amount: int) -> Dict[str, Any]:
    user_id = int(user_id)
    amount = int(amount)

    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}

    create_or_get_user(user_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                state = _refresh_dado_locked(cur, user_id)
                old_balance = int(state["balance"])
                new_balance = min(DADO_MAX_BALANCE, old_balance + amount)

                cur.execute(
                    """
                    UPDATE users
                    SET dado_balance = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (new_balance, user_id)
                )

                conn.commit()
                return {
                    "ok": True,
                    "user_id": user_id,
                    "old_balance": old_balance,
                    "new_balance": new_balance,
                    "added": amount,
                    "applied": new_balance - old_balance,
                }
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def admin_give_dado_to_all(amount: int) -> Dict[str, Any]:
    amount = int(amount)

    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT user_id
                    FROM users
                    ORDER BY user_id
                    FOR UPDATE
                    """
                )
                users = cur.fetchall() or []

                total_users = 0
                total_applied = 0

                for row in users:
                    uid = int(row["user_id"])
                    state = _refresh_dado_locked(cur, uid)
                    old_balance = int(state["balance"])
                    new_balance = min(DADO_MAX_BALANCE, old_balance + amount)
                    applied = new_balance - old_balance

                    cur.execute(
                        """
                        UPDATE users
                        SET dado_balance = %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (new_balance, uid)
                    )

                    total_users += 1
                    total_applied += applied

                conn.commit()
                return {
                    "ok": True,
                    "total_users": total_users,
                    "added": amount,
                    "total_applied": total_applied,
                }
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


# =========================================================
# MENU / PROFILE SETTINGS
# =========================================================

def ensure_profile_settings_row(user_id: int):
    _run(
        """
        INSERT INTO user_profile_settings (user_id, created_at, updated_at)
        VALUES (%s, NOW(), NOW())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),)
    )


def get_profile_settings(user_id: int):
    ensure_profile_settings_row(user_id)
    row = _run(
        """
        SELECT
            user_id,
            nickname,
            favorite_character_id,
            country_code,
            language,
            private_profile,
            notifications_enabled,
            dado_full_notified,
            dado_full_notified_at,
            created_at,
            updated_at
        FROM user_profile_settings
        WHERE user_id = %s
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one"
    )
    return row or None


def get_profile_settings_by_nickname(nickname: str):
    row = _run(
        """
        SELECT
            user_id,
            nickname,
            favorite_character_id,
            country_code,
            language,
            private_profile,
            notifications_enabled,
            dado_full_notified,
            dado_full_notified_at,
            created_at,
            updated_at
        FROM user_profile_settings
        WHERE LOWER(nickname) = LOWER(%s)
        LIMIT 1
        """,
        ((nickname or "").strip(),),
        fetch="one"
    )
    return row or None


def nickname_exists(nickname: str) -> bool:
    row = _run(
        """
        SELECT 1
        FROM user_profile_settings
        WHERE LOWER(nickname) = LOWER(%s)
        LIMIT 1
        """,
        ((nickname or "").strip(),),
        fetch="one"
    )
    return bool(row)


def set_profile_nickname(user_id: int, nickname: str) -> dict:
    ensure_profile_settings_row(user_id)

    current = get_profile_settings(user_id) or {}
    if current.get("nickname"):
        return {"ok": False, "error": "nickname_locked"}

    if nickname_exists(nickname):
        return {"ok": False, "error": "nickname_taken"}

    _run(
        """
        UPDATE user_profile_settings
        SET nickname = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        ((nickname or "").strip(), int(user_id))
    )
    return {"ok": True}


def set_profile_favorite(user_id: int, character_id: int):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET favorite_character_id = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (int(character_id), int(user_id))
    )


def set_profile_country(user_id: int, country_code: str):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET country_code = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        ((country_code or "BR").strip().upper(), int(user_id))
    )


def set_profile_language(user_id: int, language: str):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET language = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        ((language or "pt").strip().lower(), int(user_id))
    )


def set_profile_private(user_id: int, value: bool):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET private_profile = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (bool(value), int(user_id))
    )


def set_profile_notifications(user_id: int, value: bool):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET notifications_enabled = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (bool(value), int(user_id))
    )


def delete_user_account(user_id: int):
    user_id = int(user_id)

    _run("DELETE FROM user_card_collection WHERE user_id = %s", (user_id,))
    _run("DELETE FROM user_progress WHERE user_id = %s", (user_id,))
    _run("DELETE FROM termo_games WHERE user_id = %s", (user_id,))
    _run("DELETE FROM termo_stats WHERE user_id = %s", (user_id,))
    _run("DELETE FROM termo_attempt_distribution WHERE user_id = %s", (user_id,))
    _run("DELETE FROM termo_used_words WHERE user_id = %s", (user_id,))
    _run("DELETE FROM dice_rolls WHERE user_id = %s", (user_id,))
    _run("DELETE FROM media_requests WHERE user_id = %s", (user_id,))
    _run("DELETE FROM webapp_reports WHERE user_id = %s", (user_id,))
    _run("DELETE FROM user_collection_profile WHERE user_id = %s", (user_id,))
    _run("DELETE FROM user_profile_settings WHERE user_id = %s", (user_id,))
    _run("DELETE FROM users WHERE user_id = %s", (user_id,))


# =========================================================
# DADO NOTIFICATIONS
# =========================================================

def get_users_with_dado_notifications_enabled() -> List[int]:
    rows = _run(
        """
        SELECT ups.user_id
        FROM user_profile_settings ups
        INNER JOIN users u
                ON u.user_id = ups.user_id
        WHERE ups.notifications_enabled = TRUE
        ORDER BY ups.user_id ASC
        """,
        fetch="all"
    ) or []

    return [int(r["user_id"]) for r in rows]


def has_dado_full_notified(user_id: int) -> bool:
    ensure_profile_settings_row(user_id)

    row = _run(
        """
        SELECT dado_full_notified
        FROM user_profile_settings
        WHERE user_id = %s
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one"
    ) or {}

    return bool(row.get("dado_full_notified"))


def set_dado_full_notified(user_id: int, value: bool):
    ensure_profile_settings_row(user_id)

    _run(
        """
        UPDATE user_profile_settings
        SET dado_full_notified = %s,
            dado_full_notified_at = CASE WHEN %s THEN NOW() ELSE NULL END,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (bool(value), bool(value), int(user_id))
    )

# =========================================================
# SHOP / ECONOMY
# =========================================================

def create_shop_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS shop_transactions (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        type TEXT NOT NULL,
        amount INTEGER NOT NULL,
        balance_after INTEGER,
        reference_id BIGINT,
        metadata JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_shop_transactions_user
    ON shop_transactions (user_id, created_at DESC)
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS shop_card_sales (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        character_id BIGINT NOT NULL,
        price INTEGER NOT NULL DEFAULT 1,
        sold_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        buyback_available_until TIMESTAMPTZ
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_shop_card_sales_user
    ON shop_card_sales (user_id, sold_at DESC)
    """)

def record_coin_transaction(user_id: int, tx_type: str, amount: int, metadata=None):
    row = _run(
        "SELECT coins FROM users WHERE user_id = %s",
        (int(user_id),),
        fetch="one"
    )

    balance = int((row or {}).get("coins") or 0)

    _run(
        """
        INSERT INTO shop_transactions
        (user_id, type, amount, balance_after, metadata)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (
            int(user_id),
            tx_type,
            int(amount),
            balance,
            json.dumps(metadata or {})
        )
    )

def sell_character(user_id: int, character_id: int):
    qty = get_user_card_quantity(user_id, character_id)

    if qty <= 0:
        return {"ok": False, "error": "no_card"}

    remove_card_copy(user_id, character_id, 1)

    add_user_coins(user_id, 1)

    record_coin_transaction(
        user_id,
        "sell_character",
        1,
        {"character_id": character_id}
    )

    _run(
        """
        INSERT INTO shop_card_sales
        (user_id, character_id, price, buyback_available_until)
        VALUES (%s,%s,1,NOW() + INTERVAL '72 hours')
        """,
        (user_id, character_id)
    )

    return {"ok": True}

def buyback_character(user_id: int, sale_id: int):
    sale = _run(
        """
        SELECT *
        FROM shop_card_sales
        WHERE id = %s
          AND user_id = %s
        """,
        (sale_id, user_id),
        fetch="one"
    )

    if not sale:
        return {"ok": False}

    price = 3

    row = _run(
        "SELECT coins FROM users WHERE user_id = %s",
        (user_id,),
        fetch="one"
    )

    coins = int((row or {}).get("coins") or 0)

    if coins < price:
        return {"ok": False, "error": "no_coins"}

    add_user_coins(user_id, -price)

    add_card_copy(user_id, sale["character_id"], 1)

    record_coin_transaction(
        user_id,
        "buyback_character",
        -price,
        {"sale_id": sale_id}
    )

    return {"ok": True}

def buy_dado(user_id: int):
    price = 2

    row = _run(
        "SELECT coins FROM users WHERE user_id = %s",
        (user_id,),
        fetch="one"
    )

    coins = int((row or {}).get("coins") or 0)

    if coins < price:
        return {"ok": False}

    add_user_coins(user_id, -price)

    add_dado_balance(user_id, 1)

    record_coin_transaction(
        user_id,
        "buy_dado",
        -price
    )

    return {"ok": True}

def buy_nickname_change(user_id: int):
    price = 3

    row = _run(
        "SELECT coins FROM users WHERE user_id = %s",
        (user_id,),
        fetch="one"
    )

    coins = int((row or {}).get("coins") or 0)

    if coins < price:
        return {"ok": False}

    add_user_coins(user_id, -price)

    record_coin_transaction(
        user_id,
        "buy_nickname",
        -price
    )

    return {"ok": True}

def get_user_shop_history(user_id: int, limit: int = 20):
    rows = _run(
        """
        SELECT *
        FROM shop_transactions
        WHERE user_id = %s
        ORDER BY id DESC
        LIMIT %s
        """,
        (user_id, limit),
        fetch="all"
    )

    return rows or []

# =========================================================
# COINS SYSTEM (COMPATIBILITY HELPERS)
# =========================================================

def add_coin(user_id: int, amount: int = 1):
    """
    Adiciona moedas ao usuário.
    Wrapper compatível com sistemas externos.
    """
    amount = int(amount)

    if amount <= 0:
        return

    add_user_coins(user_id, amount)


def remove_coin(user_id: int, amount: int = 1) -> bool:
    """
    Remove moedas do usuário se possível.
    Retorna True se conseguiu remover.
    """

    amount = int(amount)

    if amount <= 0:
        return True

    row = _run(
        """
        SELECT coins
        FROM users
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )

    if not row:
        return False

    current = int(row.get("coins") or 0)

    if current < amount:
        return False

    _run(
        """
        UPDATE users
        SET coins = coins - %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (amount, int(user_id))
    )

    return True


def get_user_coins(user_id: int) -> int:
    """
    Retorna quantidade de moedas do usuário
    """

    row = _run(
        """
        SELECT coins
        FROM users
        WHERE user_id = %s
        """,
        (int(user_id),),
        fetch="one"
    )

    if not row:
        return 0

    return int(row.get("coins") or 0)

import random
from datetime import datetime
from zoneinfo import ZoneInfo

SP_TZ = ZoneInfo("America/Sao_Paulo")


# =========================================================
# DAILY REWARD
# =========================================================

def create_daily_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS daily_rewards (
        user_id BIGINT NOT NULL,
        day_start_ts BIGINT NOT NULL,
        reward_type TEXT NOT NULL,
        reward_amount BIGINT NOT NULL DEFAULT 0,
        claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, day_start_ts)
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_daily_rewards_user_claimed
    ON daily_rewards (user_id, claimed_at DESC)
    """)


def _daily_day_start_ts_sp() -> int:
    """
    Timestamp do começo do dia no fuso de São Paulo.
    """
    now = datetime.now(tz=SP_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp())


def ensure_daily_support():
    create_daily_tables()


def has_claimed_daily(user_id: int, day_start_ts: int) -> bool:
    row = _run(
        """
        SELECT 1
        FROM daily_rewards
        WHERE user_id = %s
          AND day_start_ts = %s
        LIMIT 1
        """,
        (int(user_id), int(day_start_ts)),
        fetch="one"
    )
    return bool(row)


def get_extra_dado(user_id: int) -> int:
    """
    Compatibilidade com sistema antigo.
    Se você ainda não tiver giros extras separados no banco,
    retorna 0 por enquanto.
    """
    return 0


def add_extra_dado(user_id: int, amount: int = 1):
    """
    Compatibilidade com sistema antigo.
    Aqui você pode plugar depois no seu sistema real de giros extras.
    Por enquanto não quebra nada.
    """
    amount = int(amount)
    if amount <= 0:
        return
    # implementar depois se quiser saldo separado de giros extras
    return


def claim_daily_reward(
    user_id: int,
    day_start_ts: int,
    coins_min: int,
    coins_max: int,
    giro_chance: float,
):
    """
    Resgata o daily uma vez por dia no horário de São Paulo.

    Retorna:
      None -> já resgatou hoje
      {"type": "giro", "amount": 1}
      {"type": "coins", "amount": X}
    """

    user_id = int(user_id)
    day_start_ts = int(day_start_ts)
    coins_min = int(coins_min)
    coins_max = int(coins_max)
    giro_chance = float(giro_chance)

    ensure_daily_support()
    create_or_get_user(user_id)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT 1
                    FROM daily_rewards
                    WHERE user_id = %s
                      AND day_start_ts = %s
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (user_id, day_start_ts)
                )
                already = cur.fetchone()

                if already:
                    conn.rollback()
                    return None

                roll = random.random()

                if roll < giro_chance:
                    reward_type = "giro"
                    reward_amount = 1

                    # compatível com sistema antigo
                    add_extra_dado(user_id, 1)
                else:
                    reward_type = "coins"
                    reward_amount = random.randint(coins_min, coins_max)

                    cur.execute(
                        """
                        UPDATE users
                        SET coins = COALESCE(coins, 0) + %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (reward_amount, user_id)
                    )

                cur.execute(
                    """
                    INSERT INTO daily_rewards
                    (user_id, day_start_ts, reward_type, reward_amount, claimed_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    """,
                    (user_id, day_start_ts, reward_type, reward_amount)
                )

                conn.commit()

                return {
                    "type": reward_type,
                    "amount": reward_amount,
                }

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

# =========================================================
# WEEKLY COMPOSITE RANKING
# =========================================================

def create_weekly_ranking_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS weekly_ranking_posts (
        week_key DATE PRIMARY KEY,
        posted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_weekly_ranking_posts_posted_at
    ON weekly_ranking_posts (posted_at DESC)
    """)


def get_display_name_parts(user_id: int) -> Optional[Dict[str, Any]]:
    return _run(
        """
        SELECT
            u.user_id,
            u.username,
            u.full_name,
            ups.nickname
        FROM users u
        LEFT JOIN user_profile_settings ups
               ON ups.user_id = u.user_id
        WHERE u.user_id = %s
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one"
    )


def get_all_coin_ranking_rows() -> List[Dict[str, Any]]:
    rows = _run(
        """
        SELECT
            u.user_id,
            u.username,
            u.full_name,
            ups.nickname,
            COALESCE(u.coins, 0) AS coins
        FROM users u
        LEFT JOIN user_profile_settings ups
               ON ups.user_id = u.user_id
        WHERE COALESCE(u.coins, 0) > 0
        ORDER BY COALESCE(u.coins, 0) DESC, u.user_id ASC
        """,
        fetch="all"
    )
    return rows or []


def get_all_level_ranking_rows() -> List[Dict[str, Any]]:
    rows = _run(
        """
        SELECT
            up.user_id,
            u.username,
            u.full_name,
            ups.nickname,
            COALESCE(up.level, 1) AS level,
            COALESCE(up.xp, 0) AS xp,
            COALESCE(up.total_actions, 0) AS total_actions
        FROM user_progress up
        LEFT JOIN users u
               ON u.user_id = up.user_id
        LEFT JOIN user_profile_settings ups
               ON ups.user_id = up.user_id
        WHERE COALESCE(up.xp, 0) > 0 OR COALESCE(up.level, 1) > 1
        ORDER BY COALESCE(up.level, 1) DESC,
                 COALESCE(up.xp, 0) DESC,
                 COALESCE(up.total_actions, 0) DESC,
                 up.user_id ASC
        """,
        fetch="all"
    )
    return rows or []


def get_all_collection_ranking_rows() -> List[Dict[str, Any]]:
    rows = _run(
        """
        SELECT
            c.user_id,
            u.username,
            u.full_name,
            ups.nickname,
            COALESCE(SUM(c.quantity), 0) AS total_cards
        FROM user_card_collection c
        LEFT JOIN users u
               ON u.user_id = c.user_id
        LEFT JOIN user_profile_settings ups
               ON ups.user_id = c.user_id
        WHERE c.quantity > 0
        GROUP BY c.user_id, u.username, u.full_name, ups.nickname
        HAVING COALESCE(SUM(c.quantity), 0) > 0
        ORDER BY total_cards DESC, c.user_id ASC
        """,
        fetch="all"
    )
    return rows or []


def get_all_termo_ranking_rows() -> List[Dict[str, Any]]:
    rows = _run(
        """
        SELECT
            ts.user_id,
            u.username,
            u.full_name,
            ups.nickname,
            COALESCE(ts.wins, 0) AS wins,
            COALESCE(ts.best_streak, 0) AS best_streak,
            COALESCE(ts.best_score, 0) AS best_score
        FROM termo_stats ts
        LEFT JOIN users u
               ON u.user_id = ts.user_id
        LEFT JOIN user_profile_settings ups
               ON ups.user_id = ts.user_id
        WHERE COALESCE(ts.games_played, 0) > 0
        ORDER BY COALESCE(ts.wins, 0) DESC,
                 COALESCE(ts.best_streak, 0) DESC,
                 COALESCE(ts.best_score, 0) ASC,
                 ts.user_id ASC
        """,
        fetch="all"
    )
    return rows or []


def has_weekly_ranking_post_for_week(week_key: date) -> bool:
    row = _run(
        """
        SELECT 1
        FROM weekly_ranking_posts
        WHERE week_key = %s
        LIMIT 1
        """,
        (week_key,),
        fetch="one"
    )
    return bool(row)


def save_weekly_ranking_post(week_key: date, payload: Dict[str, Any]) -> bool:
    """
    Retorna True se salvou agora.
    Retorna False se essa semana já foi postada.
    """
    row = _run(
        """
        INSERT INTO weekly_ranking_posts (week_key, payload_json)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (week_key) DO NOTHING
        RETURNING week_key
        """,
        (week_key, json.dumps(payload, ensure_ascii=False)),
        fetch="one"
    )
    return bool(row)

# =========================================================
# CARD TRADES
# =========================================================

def create_trades_table():
    _run("""
    CREATE TABLE IF NOT EXISTS card_trades (
        trade_id SERIAL PRIMARY KEY,
        from_user BIGINT NOT NULL,
        to_user BIGINT NOT NULL,
        from_character_id INT NOT NULL,
        to_character_id INT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)


def create_trade(from_user, to_user, from_char, to_char):

    row = _run("""
        INSERT INTO card_trades
        (from_user, to_user, from_character_id, to_character_id)
        VALUES (%s,%s,%s,%s)
        RETURNING trade_id
    """,(from_user,to_user,from_char,to_char),"one")

    return row["trade_id"]


def get_trade(trade_id):

    return _run("""
        SELECT *
        FROM card_trades
        WHERE trade_id=%s
    """,(trade_id,),"one")


def set_trade_status(trade_id,status):

    _run("""
        UPDATE card_trades
        SET status=%s
        WHERE trade_id=%s
    """,(status,trade_id))


def swap_characters_atomic(trade_id: int) -> bool:
    trade = get_trade(trade_id)
    if not trade:
        return False

    if str(trade.get("status")) != "pending":
        return False

    from_user = int(trade["from_user"])
    to_user = int(trade["to_user"])
    from_char = int(trade["from_character_id"])
    to_char = int(trade["to_character_id"])

    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("BEGIN")

                cur.execute(
                    """
                    SELECT quantity
                    FROM user_card_collection
                    WHERE user_id = %s AND character_id = %s
                    FOR UPDATE
                    """,
                    (from_user, from_char)
                )
                row_a = cur.fetchone()

                cur.execute(
                    """
                    SELECT quantity
                    FROM user_card_collection
                    WHERE user_id = %s AND character_id = %s
                    FOR UPDATE
                    """,
                    (to_user, to_char)
                )
                row_b = cur.fetchone()

                def _qty(row):
                    if not row:
                        return 0
                    if isinstance(row, dict):
                        value = row.get("quantity", 0)
                    else:
                        value = row[0] if len(row) > 0 else 0
                    return int(value or 0)

                qty_a = _qty(row_a)
                qty_b = _qty(row_b)

                if qty_a <= 0 or qty_b <= 0:
                    cur.execute(
                        """
                        UPDATE card_trades
                        SET status = 'failed'
                        WHERE trade_id = %s
                        """,
                        (trade_id,)
                    )
                    conn.commit()
                    return False

                if qty_a == 1:
                    cur.execute(
                        """
                        DELETE FROM user_card_collection
                        WHERE user_id = %s AND character_id = %s
                        """,
                        (from_user, from_char)
                    )
                else:
                    cur.execute(
                        """
                        UPDATE user_card_collection
                        SET quantity = quantity - 1,
                            updated_at = NOW()
                        WHERE user_id = %s AND character_id = %s
                        """,
                        (from_user, from_char)
                    )

                if qty_b == 1:
                    cur.execute(
                        """
                        DELETE FROM user_card_collection
                        WHERE user_id = %s AND character_id = %s
                        """,
                        (to_user, to_char)
                    )
                else:
                    cur.execute(
                        """
                        UPDATE user_card_collection
                        SET quantity = quantity - 1,
                            updated_at = NOW()
                        WHERE user_id = %s AND character_id = %s
                        """,
                        (to_user, to_char)
                    )

                cur.execute(
                    """
                    INSERT INTO user_card_collection (
                        user_id,
                        character_id,
                        quantity,
                        first_obtained_at,
                        updated_at
                    )
                    VALUES (%s, %s, 1, NOW(), NOW())
                    ON CONFLICT (user_id, character_id)
                    DO UPDATE SET
                        quantity = user_card_collection.quantity + 1,
                        updated_at = NOW()
                    """,
                    (from_user, to_char)
                )

                cur.execute(
                    """
                    INSERT INTO user_card_collection (
                        user_id,
                        character_id,
                        quantity,
                        first_obtained_at,
                        updated_at
                    )
                    VALUES (%s, %s, 1, NOW(), NOW())
                    ON CONFLICT (user_id, character_id)
                    DO UPDATE SET
                        quantity = user_card_collection.quantity + 1,
                        updated_at = NOW()
                    """,
                    (to_user, from_char)
                )

                cur.execute(
                    """
                    UPDATE card_trades
                    SET status = 'completed'
                    WHERE trade_id = %s
                    """,
                    (trade_id,)
                )

                conn.commit()
                return True

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

# =========================================================
# ADMIN RESET SYSTEM
# =========================================================

def delete_all_users():

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute("TRUNCATE TABLE user_card_collection CASCADE")
            cur.execute("TRUNCATE TABLE user_progress CASCADE")
            cur.execute("TRUNCATE TABLE termo_games CASCADE")
            cur.execute("TRUNCATE TABLE termo_stats CASCADE")
            cur.execute("TRUNCATE TABLE termo_attempt_distribution CASCADE")
            cur.execute("TRUNCATE TABLE termo_used_words CASCADE")
            cur.execute("TRUNCATE TABLE dice_rolls CASCADE")
            cur.execute("TRUNCATE TABLE media_requests CASCADE")
            cur.execute("TRUNCATE TABLE webapp_reports CASCADE")
            cur.execute("TRUNCATE TABLE user_collection_profile CASCADE")
            cur.execute("TRUNCATE TABLE user_profile_settings CASCADE")
            cur.execute("TRUNCATE TABLE users CASCADE")

        conn.commit()

# =========================================================
# ADMIN BROADCAST
# =========================================================

def get_all_started_user_ids() -> List[int]:
    rows = _run(
        """
        SELECT user_id
        FROM users
        ORDER BY user_id ASC
        """,
        fetch="all"
    ) or []

    return [int(r["user_id"]) for r in rows if r.get("user_id") is not None]

def get_all_user_ids() -> List[int]:
    rows = _run(
        """
        SELECT user_id
        FROM users
        ORDER BY user_id ASC
        """,
        fetch="all"
    ) or []

    return [int(row["user_id"]) for row in rows if row.get("user_id") is not None]

# =========================================================
# USER MESSAGES SYSTEM
# =========================================================

def create_message_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS user_message_settings (
        user_id BIGINT PRIMARY KEY,
        allow_messages BOOLEAN NOT NULL DEFAULT TRUE,
        allow_anonymous BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS user_message_blocks (
        user_id BIGINT NOT NULL,
        blocked_user_id BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, blocked_user_id)
    )
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS user_messages (
        message_id BIGSERIAL PRIMARY KEY,
        from_user_id BIGINT NOT NULL,
        to_user_id BIGINT NOT NULL,
        from_nickname TEXT,
        to_nickname TEXT,
        message_text TEXT NOT NULL,
        is_anonymous BOOLEAN NOT NULL DEFAULT FALSE,
        coin_cost INTEGER NOT NULL DEFAULT 0,
        refund_done BOOLEAN NOT NULL DEFAULT FALSE,
        status TEXT NOT NULL DEFAULT 'pending',
        fail_reason TEXT,
        reported BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        delivered_at TIMESTAMPTZ
    )
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS user_message_reports (
        report_id BIGSERIAL PRIMARY KEY,
        message_id BIGINT NOT NULL,
        reporter_user_id BIGINT NOT NULL,
        reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_messages_from_created
    ON user_messages (from_user_id, created_at DESC)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_messages_to_created
    ON user_messages (to_user_id, created_at DESC)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_messages_status
    ON user_messages (status, created_at DESC)
    """)


def ensure_message_settings_row(user_id: int):
    _run(
        """
        INSERT INTO user_message_settings (user_id, created_at, updated_at)
        VALUES (%s, NOW(), NOW())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),)
    )


def get_message_settings(user_id: int) -> Dict[str, Any]:
    ensure_message_settings_row(user_id)
    return _run(
        """
        SELECT user_id, allow_messages, allow_anonymous, created_at, updated_at
        FROM user_message_settings
        WHERE user_id = %s
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one"
    ) or {
        "user_id": int(user_id),
        "allow_messages": True,
        "allow_anonymous": True,
    }


def set_message_allow_messages(user_id: int, value: bool):
    ensure_message_settings_row(user_id)
    _run(
        """
        UPDATE user_message_settings
        SET allow_messages = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (bool(value), int(user_id))
    )


def set_message_allow_anonymous(user_id: int, value: bool):
    ensure_message_settings_row(user_id)
    _run(
        """
        UPDATE user_message_settings
        SET allow_anonymous = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (bool(value), int(user_id))
    )


def is_message_blocked(user_id: int, blocked_user_id: int) -> bool:
    row = _run(
        """
        SELECT 1
        FROM user_message_blocks
        WHERE user_id = %s
          AND blocked_user_id = %s
        LIMIT 1
        """,
        (int(user_id), int(blocked_user_id)),
        fetch="one"
    )
    return bool(row)


def block_user_messages(user_id: int, blocked_user_id: int):
    _run(
        """
        INSERT INTO user_message_blocks (user_id, blocked_user_id, created_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id, blocked_user_id) DO NOTHING
        """,
        (int(user_id), int(blocked_user_id))
    )


def unblock_user_messages(user_id: int, blocked_user_id: int):
    _run(
        """
        DELETE FROM user_message_blocks
        WHERE user_id = %s
          AND blocked_user_id = %s
        """,
        (int(user_id), int(blocked_user_id))
    )


def get_last_sent_message_at(user_id: int, is_anonymous: Optional[bool] = None) -> Optional[datetime]:
    if is_anonymous is None:
        row = _run(
            """
            SELECT created_at
            FROM user_messages
            WHERE from_user_id = %s
              AND status IN ('pending', 'delivered')
            ORDER BY message_id DESC
            LIMIT 1
            """,
            (int(user_id),),
            fetch="one"
        )
    else:
        row = _run(
            """
            SELECT created_at
            FROM user_messages
            WHERE from_user_id = %s
              AND is_anonymous = %s
              AND status IN ('pending', 'delivered')
            ORDER BY message_id DESC
            LIMIT 1
            """,
            (int(user_id), bool(is_anonymous)),
            fetch="one"
        )

    return (row or {}).get("created_at")


def get_message_cooldown_remaining(user_id: int, cooldown_seconds: int, is_anonymous: Optional[bool] = None) -> int:
    last_dt = get_last_sent_message_at(user_id, is_anonymous=is_anonymous)
    if not last_dt:
        return 0

    now = _sp_now()
    if getattr(last_dt, "tzinfo", None) is None:
        elapsed = (datetime.utcnow() - last_dt).total_seconds()
    else:
        elapsed = (now.astimezone(last_dt.tzinfo) - last_dt).total_seconds()

    return int(max(0, int(cooldown_seconds) - elapsed))


def enqueue_user_message(
    from_user_id: int,
    target_nickname: str,
    message_text: str,
    is_anonymous: bool,
    anon_cost: int,
    normal_cooldown_seconds: int,
    anonymous_cooldown_seconds: int,
) -> Dict[str, Any]:
    from_user_id = int(from_user_id)
    target_nickname = (target_nickname or "").strip()
    message_text = (message_text or "").strip()
    is_anonymous = bool(is_anonymous)
    anon_cost = int(anon_cost)

    if not target_nickname:
        return {"ok": False, "error": "target_nickname_required"}

    if not message_text:
        return {"ok": False, "error": "empty_message"}

    if len(message_text) > 500:
        return {"ok": False, "error": "message_too_long"}

    create_or_get_user(from_user_id)
    ensure_profile_settings_row(from_user_id)
    ensure_message_settings_row(from_user_id)

    sender_profile = get_profile_settings(from_user_id) or {}
    sender_nickname = (sender_profile.get("nickname") or "").strip()
    if not sender_nickname:
        return {"ok": False, "error": "sender_no_nickname"}

    target_profile = get_profile_settings_by_nickname(target_nickname)
    if not target_profile:
        return {"ok": False, "error": "target_not_found"}

    to_user_id = int(target_profile["user_id"])
    to_nickname = (target_profile.get("nickname") or "").strip()

    if from_user_id == to_user_id:
        return {"ok": False, "error": "cannot_message_self"}

    ensure_message_settings_row(to_user_id)
    target_settings = get_message_settings(to_user_id)

    if not bool(target_settings.get("allow_messages", True)):
        return {"ok": False, "error": "target_messages_disabled"}

    if is_anonymous and not bool(target_settings.get("allow_anonymous", True)):
        return {"ok": False, "error": "target_anonymous_disabled"}

    if is_message_blocked(to_user_id, from_user_id):
        return {"ok": False, "error": "blocked_by_target"}

    if is_message_blocked(from_user_id, to_user_id):
        return {"ok": False, "error": "you_blocked_target"}

    cooldown_seconds = int(anonymous_cooldown_seconds if is_anonymous else normal_cooldown_seconds)
    remaining = get_message_cooldown_remaining(
        from_user_id,
        cooldown_seconds,
        is_anonymous=is_anonymous,
    )
    if remaining > 0:
        return {"ok": False, "error": "cooldown_active", "remaining_seconds": remaining}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                # trava o usuário antes de cobrar
                cur.execute(
                    """
                    SELECT user_id, coins
                    FROM users
                    WHERE user_id = %s
                    FOR UPDATE
                    """,
                    (from_user_id,)
                )
                sender_row = cur.fetchone()

                if not sender_row:
                    conn.rollback()
                    return {"ok": False, "error": "sender_not_found"}

                sender_coins = int(sender_row.get("coins") or 0)

                if is_anonymous and sender_coins < anon_cost:
                    conn.rollback()
                    return {"ok": False, "error": "insufficient_coins"}

                if is_anonymous:
                    cur.execute(
                        """
                        UPDATE users
                        SET coins = coins - %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (anon_cost, from_user_id)
                    )

                cur.execute(
                    """
                    INSERT INTO user_messages
                    (
                        from_user_id,
                        to_user_id,
                        from_nickname,
                        to_nickname,
                        message_text,
                        is_anonymous,
                        coin_cost,
                        refund_done,
                        status,
                        created_at
                    )
                    VALUES
                    (
                        %s, %s, %s, %s, %s, %s, %s, FALSE, 'pending', NOW()
                    )
                    RETURNING *
                    """,
                    (
                        from_user_id,
                        to_user_id,
                        sender_nickname,
                        to_nickname,
                        message_text,
                        is_anonymous,
                        anon_cost if is_anonymous else 0,
                    )
                )
                row = cur.fetchone()

                conn.commit()

                return {
                    "ok": True,
                    "message": row,
                    "to_user_id": to_user_id,
                    "to_nickname": to_nickname,
                    "from_nickname": sender_nickname,
                }

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def mark_user_message_delivered(message_id: int):
    _run(
        """
        UPDATE user_messages
        SET status = 'delivered',
            delivered_at = NOW()
        WHERE message_id = %s
        """,
        (int(message_id),)
    )


def fail_user_message(message_id: int, reason: str = ""):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT message_id, from_user_id, coin_cost, refund_done, status, is_anonymous
                    FROM user_messages
                    WHERE message_id = %s
                    FOR UPDATE
                    """,
                    (int(message_id),)
                )
                row = cur.fetchone()

                if not row:
                    conn.rollback()
                    return

                status = str(row.get("status") or "")
                if status == "failed":
                    conn.rollback()
                    return

                do_refund = (
                    bool(row.get("is_anonymous"))
                    and int(row.get("coin_cost") or 0) > 0
                    and not bool(row.get("refund_done"))
                )

                if do_refund:
                    cur.execute(
                        """
                        UPDATE users
                        SET coins = COALESCE(coins, 0) + %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (int(row["coin_cost"]), int(row["from_user_id"]))
                    )

                cur.execute(
                    """
                    UPDATE user_messages
                    SET status = 'failed',
                        fail_reason = %s,
                        refund_done = %s
                    WHERE message_id = %s
                    """,
                    ((reason or "").strip()[:300], bool(do_refund), int(message_id))
                )

                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def get_received_message_by_id(user_id: int, message_id: int) -> Optional[Dict[str, Any]]:
    return _run(
        """
        SELECT *
        FROM user_messages
        WHERE message_id = %s
          AND to_user_id = %s
        LIMIT 1
        """,
        (int(message_id), int(user_id)),
        fetch="one"
    )


def report_user_message(reporter_user_id: int, message_id: int, reason: str = "") -> Dict[str, Any]:
    msg = get_received_message_by_id(reporter_user_id, message_id)
    if not msg:
        return {"ok": False, "error": "message_not_found"}

    _run(
        """
        INSERT INTO user_message_reports (message_id, reporter_user_id, reason, created_at)
        VALUES (%s, %s, %s, NOW())
        """,
        (int(message_id), int(reporter_user_id), (reason or "").strip()[:500])
    )

    _run(
        """
        UPDATE user_messages
        SET reported = TRUE
        WHERE message_id = %s
        """,
        (int(message_id),)
    )

    return {"ok": True}

# =========================================================
# CARD CONTRIBUTIONS
# =========================================================

def create_card_contrib_tables():

    _run("""
    CREATE TABLE IF NOT EXISTS card_image_suggestions (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        username TEXT,
        full_name TEXT,

        character_id BIGINT NOT NULL,
        character_name TEXT,
        anime_id BIGINT,
        anime_title TEXT,

        old_image_url TEXT,
        suggested_image_url TEXT,

        telegram_file_id TEXT,
        telegram_file_unique_id TEXT,

        note TEXT,

        status TEXT NOT NULL DEFAULT 'pending',

        reviewed_by BIGINT,
        reviewed_at TIMESTAMPTZ,
        review_note TEXT,

        channel_message_id BIGINT,

        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS card_work_requests (
        id BIGSERIAL PRIMARY KEY,

        user_id BIGINT NOT NULL,
        username TEXT,
        full_name TEXT,

        media_type TEXT,
        anilist_id BIGINT,

        title TEXT,
        title_norm TEXT,

        cover_url TEXT,

        status TEXT NOT NULL DEFAULT 'pending',

        reviewed_by BIGINT,
        reviewed_at TIMESTAMPTZ,

        channel_message_id BIGINT,

        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

def create_card_image_suggestion(data):

    return _run(
        """
        INSERT INTO card_image_suggestions
        (
            user_id,
            username,
            full_name,

            character_id,
            character_name,
            anime_id,
            anime_title,

            old_image_url,
            suggested_image_url,

            telegram_file_id,
            telegram_file_unique_id,

            note
        )
        VALUES
        (
            %(user_id)s,
            %(username)s,
            %(full_name)s,

            %(character_id)s,
            %(character_name)s,
            %(anime_id)s,
            %(anime_title)s,

            %(old_image_url)s,
            %(suggested_image_url)s,

            %(telegram_file_id)s,
            %(telegram_file_unique_id)s,

            %(note)s
        )
        RETURNING *
        """,
        data,
        fetch="one",
    )

def approve_card_image_suggestion(suggestion_id, admin_id):

    row = _run(
        """
        SELECT *
        FROM card_image_suggestions
        WHERE id = %s
        LIMIT 1
        """,
        (suggestion_id,),
        fetch="one"
    )

    if not row:
        return None

    character_id = row["character_id"]
    new_image = row["suggested_image_url"]

    override_set_character_image(character_id, new_image)

    _run(
        """
        UPDATE card_image_suggestions
        SET status='approved',
            reviewed_by=%s,
            reviewed_at=NOW()
        WHERE id=%s
        """,
        (admin_id, suggestion_id)
    )

    add_user_coins(row["user_id"], int(os.getenv("CARD_IMAGE_APPROVED_REWARD", "1")))

    return row
