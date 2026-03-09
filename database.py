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
# INIT
# =========================================================

def create_tables():
    create_users_table()
    create_level_tables()
    create_cards_tables()
    create_media_request_tables()
    create_termo_tables()


# =========================================================
# USERS
# =========================================================

def create_users_table():
    _run("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        lang TEXT,
        coins BIGINT DEFAULT 0,
        terms_accepted BOOLEAN DEFAULT FALSE,
        terms_version TEXT,
        accepted_at TIMESTAMPTZ,
        welcome_sent BOOLEAN DEFAULT FALSE,
        must_join_ok BOOLEAN DEFAULT FALSE
    )
    """)


# =========================================================
# LEVEL
# =========================================================

def create_level_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS user_progress (
        user_id BIGINT PRIMARY KEY,
        xp BIGINT DEFAULT 0,
        level INT DEFAULT 1,
        total_actions BIGINT DEFAULT 0,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """)


def add_progress_xp(user_id: int, amount: int = 3):

    _run("""
    INSERT INTO user_progress (user_id, xp)
    VALUES (%s,%s)
    ON CONFLICT (user_id)
    DO UPDATE SET xp = user_progress.xp + EXCLUDED.xp
    """,(user_id,amount))


# =========================================================
# CARDS
# =========================================================

def create_cards_tables():

    _run("""
    CREATE TABLE IF NOT EXISTS user_card_collection (
        user_id BIGINT,
        character_id BIGINT,
        quantity INT DEFAULT 0,
        PRIMARY KEY (user_id, character_id)
    )
    """)


# =========================================================
# MEDIA REQUESTS
# =========================================================

def create_media_request_tables():

    _run("""
    CREATE TABLE IF NOT EXISTS media_requests (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT,
        media_type TEXT,
        title TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """)


# =========================================================
# TERMO
# =========================================================

def create_termo_tables():

    _run("""
    CREATE TABLE IF NOT EXISTS termo_games (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT,
        date DATE,
        word TEXT,
        attempts INT DEFAULT 0,
        guesses JSONB DEFAULT '[]',
        status TEXT,
        start_time BIGINT,
        mode TEXT DEFAULT 'daily'
    )
    """)

    _run("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_termo_daily
    ON termo_games (user_id,date,mode)
    WHERE mode='daily'
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS termo_stats (
        user_id BIGINT PRIMARY KEY,
        games_played INT DEFAULT 0,
        wins INT DEFAULT 0,
        losses INT DEFAULT 0,
        current_streak INT DEFAULT 0,
        best_streak INT DEFAULT 0,
        best_score INT DEFAULT 0,
        last_play_date DATE
    )
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS termo_attempt_distribution (
        user_id BIGINT PRIMARY KEY,
        one_try INT DEFAULT 0,
        two_try INT DEFAULT 0,
        three_try INT DEFAULT 0,
        four_try INT DEFAULT 0,
        five_try INT DEFAULT 0,
        six_try INT DEFAULT 0
    )
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS termo_used_words (
        user_id BIGINT,
        word TEXT,
        PRIMARY KEY (user_id,word)
    )
    """)


# =========================================================
# TERMO GAME
# =========================================================

def create_termo_game(user_id:int, game_date:date, word:str, start_time:int, mode:str="daily"):

    _run("""
    INSERT INTO termo_games
    (user_id,date,word,start_time,status,mode)
    VALUES (%s,%s,%s,%s,'playing',%s)
    """,(user_id,game_date,word,start_time,mode))


def get_termo_active_game(user_id:int):

    return _run("""
    SELECT *
    FROM termo_games
    WHERE user_id=%s
    AND status='playing'
    ORDER BY id DESC
    LIMIT 1
    """,(user_id,),fetch="one")


def finish_termo_game(user_id:int,status:str,attempts:int):

    _run("""
    UPDATE termo_games
    SET status=%s,attempts=%s
    WHERE user_id=%s
    AND status='playing'
    """,(status,attempts,user_id))


# =========================================================
# TERMO STATS
# =========================================================

def record_termo_result(user_id:int, win:bool, attempts:int):

    stats=_run(
        "SELECT * FROM termo_stats WHERE user_id=%s",
        (user_id,),
        "one"
    )

    today=date.today()

    if not stats:

        _run("""
        INSERT INTO termo_stats
        (user_id,games_played,wins,losses,current_streak,best_streak,last_play_date)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,(user_id,1,1 if win else 0,0 if win else 1,1 if win else 0,1 if win else 0,today))

        return

    games=stats["games_played"]+1
    wins=stats["wins"]+(1 if win else 0)
    losses=stats["losses"]+(0 if win else 1)

    streak=stats["current_streak"]

    if win:
        if stats["last_play_date"]==today-timedelta(days=1):
            streak+=1
        else:
            streak=1
    else:
        streak=0

    best=max(streak,stats["best_streak"])

    _run("""
    UPDATE termo_stats
    SET
    games_played=%s,
    wins=%s,
    losses=%s,
    current_streak=%s,
    best_streak=%s,
    last_play_date=%s
    WHERE user_id=%s
    """,(games,wins,losses,streak,best,today,user_id))


# =========================================================
# RANKING
# =========================================================

def get_termo_global_ranking(limit:int=10):

    return _run("""
    SELECT user_id,wins,best_streak
    FROM termo_stats
    ORDER BY wins DESC,best_streak DESC
    LIMIT %s
    """,(limit,),fetch="all")
