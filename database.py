
# ================================
# database.py — Postgres (Railway)
# (POOL + TRANSACOES SEGURAS + MIGRACAO + DADO + GIROS SLOT + CACHE + DAILY + CONQUISTAS + RANKINGS + STATS)
# ================================

import os
import re
import time
from typing import Optional, Dict, List, Any, Tuple

import psycopg
from psycopg.rows import dict_row
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado.")

# Pool (fundamental para concorrência: evita 1 conexão global compartilhada entre tasks)
POOL_MIN = int(os.getenv("PGPOOL_MIN", "1"))
POOL_MAX = int(os.getenv("PGPOOL_MAX", "10"))
POOL_TIMEOUT = float(os.getenv("PGPOOL_TIMEOUT", "10"))

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=POOL_MIN,
    max_size=POOL_MAX,
    timeout=POOL_TIMEOUT,
    kwargs={"row_factory": dict_row, "autocommit": False},
)

# ================================
# HELPERS
# ================================
def _sanitize_nick(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^a-z0-9_\.]", "", s)  # permite: a-z 0-9 _ .
    return s or "user"


def _run(sql: str, params: Tuple = (), fetch: str = "none"):
    """Executa 1 comando SQL com conexão do pool.

    fetch:
      - "none" -> None
      - "one"  -> dict | None
      - "all"  -> list[dict]
    """
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


def _run_many(statements: List[Tuple[str, Tuple]]):
    """Executa vários comandos em sequência (mesma conexão). Use para DDL/migração."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                for sql, params in statements:
                    cur.execute(sql, params)
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


# ================================
# MIGRAÇÃO / INIT
# ================================
def _ensure_columns_users():
    stmts = [
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS nick TEXT;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS collection_name TEXT;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_name TEXT;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_image TEXT;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS private_profile BOOLEAN DEFAULT FALSE;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_photo TEXT;", ()),

        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS coins INT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS commands INT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS level INT DEFAULT 1;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS xp INT DEFAULT 0;", ()),

        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_dado BIGINT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_pedido BIGINT DEFAULT 0;", ()),

        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily BIGINT DEFAULT 0;", ()),

        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_balance INT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_slot BIGINT DEFAULT -1;", ()),

        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_dado INT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_slot BIGINT DEFAULT -1;", ()),
    ]
    _run_many(stmts)


def _dedupe_nicks_before_unique_index():
    dups = _run(
        """
        SELECT LOWER(nick) AS n, COUNT(*)::int AS c
        FROM users
        WHERE nick IS NOT NULL
        GROUP BY LOWER(nick)
        HAVING COUNT(*) > 1
        """,
        fetch="all",
    ) or []

    for r in dups:
        base = _sanitize_nick(r.get("n") or "user")
        ids = _run(
            """
            SELECT user_id
            FROM users
            WHERE LOWER(nick)=LOWER(%s)
            ORDER BY user_id ASC
            """,
            (base,),
            fetch="all",
        ) or []
        ids = [int(x["user_id"]) for x in ids]
        if len(ids) <= 1:
            continue
        for uid in ids[1:]:
            _run("UPDATE users SET nick=%s WHERE user_id=%s", (f"{base}_{uid}", int(uid)))


def _ensure_achievements_table():
    _run(
        """
        CREATE TABLE IF NOT EXISTS user_achievements (
            user_id BIGINT NOT NULL,
            achievement_key TEXT NOT NULL,
            unlocked_at BIGINT NOT NULL,
            PRIMARY KEY (user_id, achievement_key)
        );
        """
    )
    _run("CREATE INDEX IF NOT EXISTS user_achievements_user_idx ON user_achievements (user_id);")


def \1
    try:
        create_engine_tables()
    except Exception as e:
        print('⚠️ create_engine_tables falhou (ok continuar):', e)
:
    try:
        _dedupe_nicks_before_unique_index()
    except Exception as e:
        print("⚠️ Dedupe nicks falhou (ok continuar):", e)

    try:
        _run(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS users_nick_unique
            ON users (LOWER(nick))
            WHERE nick IS NOT NULL;
            """
        )
    except Exception as e:
        print("⚠️ users_nick_unique falhou (ok continuar):", e)

    indexes = [
        ("user_collection_user_idx", "CREATE INDEX IF NOT EXISTS user_collection_user_idx ON user_collection (user_id);"),
        ("user_collection_char_idx", "CREATE INDEX IF NOT EXISTS user_collection_char_idx ON user_collection (character_id);"),
        ("trades_to_user_idx", "CREATE INDEX IF NOT EXISTS trades_to_user_idx ON trades (to_user);"),
        ("trades_status_idx", "CREATE INDEX IF NOT EXISTS trades_status_idx ON trades (status);"),
        ("dice_rolls_user_idx", "CREATE INDEX IF NOT EXISTS dice_rolls_user_idx ON dice_rolls (user_id);"),
        ("dice_rolls_status_idx", "CREATE INDEX IF NOT EXISTS dice_rolls_status_idx ON dice_rolls (status);"),
        ("top_cache_rank_idx", "CREATE INDEX IF NOT EXISTS top_cache_rank_idx ON top_anime_cache (rank);"),
        ("shop_sales_user_idx", "CREATE INDEX IF NOT EXISTS shop_sales_user_idx ON shop_sales (user_id);"),
    ]
    for name, sql in indexes:
        try:
            _run(sql)
        except Exception as e:
            print(f"⚠️ index {name} falhou (ok continuar):", e)


def init_db():
    # tabelas principais (idêntico ao seu, só que com pool)
    _run(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            nick TEXT,
            collection_name TEXT DEFAULT 'Minha Coleção',
            fav_name TEXT,
            fav_image TEXT,
            private_profile BOOLEAN DEFAULT FALSE,
            admin_photo TEXT,
            coins INT DEFAULT 0,
            commands INT DEFAULT 0,
            level INT DEFAULT 1,
            xp INT DEFAULT 0,
            last_dado BIGINT DEFAULT 0,
            last_pedido BIGINT DEFAULT 0,
            last_daily BIGINT DEFAULT 0,
            dado_balance INT DEFAULT 0,
            dado_slot BIGINT DEFAULT -1,
            extra_dado INT DEFAULT 0,
            extra_slot BIGINT DEFAULT -1
        );
        """
    )

    _run(
        """
        CREATE TABLE IF NOT EXISTS user_collection (
            user_id BIGINT NOT NULL,
            character_id INT NOT NULL,
            character_name TEXT NOT NULL,
            image TEXT,
            custom_image TEXT,
            anime_title TEXT,
            quantity INT DEFAULT 1,
            PRIMARY KEY (user_id, character_id)
        );
        """
    )

    _run(
        """
        CREATE TABLE IF NOT EXISTS trades (
            trade_id SERIAL PRIMARY KEY,
            from_user BIGINT NOT NULL,
            to_user BIGINT NOT NULL,
            from_character_id INT NOT NULL,
            to_character_id INT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            created_at BIGINT NOT NULL DEFAULT 0
        );
        """
    )

    _run(
        """
        CREATE TABLE IF NOT EXISTS shop_sales (
            sale_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            character_id INT,
            created_at BIGINT
        );
        """
    )

    _run(
        """
        CREATE TABLE IF NOT EXISTS character_images (
            character_id INT PRIMARY KEY,
            image_url TEXT NOT NULL,
            updated_at BIGINT NOT NULL,
            updated_by BIGINT
        );
        """
    )

    _run(
        """
        CREATE TABLE IF NOT EXISTS banned_characters (
            character_id INT PRIMARY KEY,
            reason TEXT,
            created_at BIGINT NOT NULL,
            created_by BIGINT
        );
        """
    )

    _run(
        """
        CREATE TABLE IF NOT EXISTS top_anime_cache (
            anime_id INT PRIMARY KEY,
            title TEXT NOT NULL,
            rank INT NOT NULL,
            updated_at BIGINT NOT NULL
        );
        """
    )

    _run(
        """
        CREATE TABLE IF NOT EXISTS dice_rolls (
            roll_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            dice_value INT NOT NULL,
            options_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at BIGINT NOT NULL
        );
        """
    )

    _ensure_columns_users()
    _ensure_achievements_table()
    _try_create_indexes()


# ================================
# USERS / PERFIL
# ================================
def ensure_user_row(user_id: int, default_name: str, new_user_dice: int = 0):
    user_id = int(user_id)
    exists = _run("SELECT 1 FROM users WHERE user_id=%s", (user_id,), fetch="one")
    if exists:
        return

    base = _sanitize_nick(default_name)
    candidates = [base, f"{base}_{user_id}", f"user_{user_id}"]

    for nick in candidates:
        try:
            _run(
                """
                INSERT INTO users (
                    user_id, nick, collection_name,
                    dado_balance, dado_slot,
                    extra_dado, extra_slot,
                    last_daily
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, nick, "Minha Coleção", int(new_user_dice or 0), -1, 0, -1, 0),
                fetch="none",
            )
            return
        except pg_errors.UniqueViolation:
            # nick já existe -> tenta outro
            continue

    _run(
        """
        INSERT INTO users (
            user_id, nick, collection_name,
            dado_balance, dado_slot,
            extra_dado, extra_slot,
            last_daily
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, f"user_{user_id}", "Minha Coleção", int(new_user_dice or 0), -1, 0, -1, 0),
    )


def get_user_row(user_id: int):
    return _run("SELECT * FROM users WHERE user_id=%s", (int(user_id),), fetch="one")


def get_user_by_nick(nick: str):
    return _run("SELECT * FROM users WHERE LOWER(nick)=LOWER(%s) LIMIT 1", (str(nick),), fetch="one")


def set_private_profile(user_id: int, is_private: bool):
    _run("UPDATE users SET private_profile=%s WHERE user_id=%s", (bool(is_private), int(user_id)))


def set_admin_photo(user_id: int, url: str):
    _run("UPDATE users SET admin_photo=%s WHERE user_id=%s", (str(url), int(user_id)))


def get_admin_photo_db(user_id: int) -> Optional[str]:
    row = _run("SELECT admin_photo FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return row.get("admin_photo")


def set_last_pedido(user_id: int, ts: int):
    _run("UPDATE users SET last_pedido=%s WHERE user_id=%s", (int(ts), int(user_id)))

def set_collection_name(user_id: int, name: str):
    _run("UPDATE users SET collection_name=%s WHERE user_id=%s", (str(name), int(user_id)))


def get_collection_name(user_id: int) -> str:
    row = _run("SELECT COALESCE(collection_name,'Minha Coleção') AS n FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return str(row.get("n") or "Minha Coleção")


# ================================
# COINS (ATÔMICO)
# ================================
def add_coin(user_id: int, amount: int):
    _run("UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s", (int(amount), int(user_id)))


def get_user_coins(user_id: int) -> int:
    row = _run("SELECT COALESCE(coins,0)::int AS c FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("c") or 0)


def try_spend_coins(user_id: int, amount: int) -> bool:
    row = _run(
        """
        UPDATE users
        SET coins = COALESCE(coins,0) - %s
        WHERE user_id=%s AND COALESCE(coins,0) >= %s
        RETURNING coins
        """,
        (int(amount), int(user_id), int(amount)),
        fetch="one",
    )
    return row is not None


def spend_coins_and_add_giro(user_id: int, price: int, giros: int = 1) -> bool:
    """Transação única: evita gastar coins e falhar antes de creditar o giro."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    UPDATE users
                    SET coins = COALESCE(coins,0) - %s
                    WHERE user_id=%s AND COALESCE(coins,0) >= %s
                    RETURNING user_id
                    """,
                    (int(price), int(user_id), int(price)),
                )
                ok = cur.fetchone() is not None
                if not ok:
                    conn.commit()
                    return False

                cur.execute(
                    "UPDATE users SET extra_dado = COALESCE(extra_dado,0) + %s WHERE user_id=%s",
                    (int(giros), int(user_id)),
                )
                conn.commit()
                return True
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


# ================================
# COLEÇÃO
# ================================
def count_collection(user_id: int) -> int:
    row = _run("SELECT COALESCE(SUM(quantity),0)::int AS n FROM user_collection WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("n") or 0)


def get_collection_page(user_id: int, limit: int, offset: int):
    return _run(
        """
        SELECT character_id, character_name, image, custom_image, anime_title, quantity
        FROM user_collection
        WHERE user_id=%s
        ORDER BY character_id ASC
        LIMIT %s OFFSET %s
        """,
        (int(user_id), int(limit), int(offset)),
        fetch="all",
    ) or []


def list_collection_cards(user_id: int, limit: int = 200):
    return _run(
        """
        SELECT character_id, character_name, image, custom_image, anime_title, quantity
        FROM user_collection
        WHERE user_id=%s
        ORDER BY quantity DESC, character_id ASC
        LIMIT %s
        """,
        (int(user_id), int(limit)),
        fetch="all",
    ) or []


def user_has_character(user_id: int, char_id: int) -> bool:
    row = _run(
        "SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s",
        (int(user_id), int(char_id)),
        fetch="one",
    )
    return row is not None


def add_character_to_collection(user_id: int, char_id: int, name: str, image: str, anime_title: Optional[str] = None):
    _run(
        """
        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
        VALUES (%s, %s, %s, %s, %s, 1)
        ON CONFLICT (user_id, character_id) DO UPDATE
        SET quantity = user_collection.quantity + 1,
            character_name = COALESCE(EXCLUDED.character_name, user_collection.character_name),
            image = COALESCE(EXCLUDED.image, user_collection.image),
            anime_title = COALESCE(EXCLUDED.anime_title, user_collection.anime_title)
        """,
        (int(user_id), int(char_id), str(name), str(image), anime_title),
    )


def get_collection_character_full(user_id: int, char_id: int):
    return _run(
        """
        SELECT character_id, character_name, image, custom_image, anime_title, quantity
        FROM user_collection
        WHERE user_id=%s AND character_id=%s
        LIMIT 1
        """,
        (int(user_id), int(char_id)),
        fetch="one",
    )


def get_collection_character(user_id: int, char_id: int):
    return _run(
        """
        SELECT character_id, character_name, image
        FROM user_collection
        WHERE user_id=%s AND character_id=%s
        LIMIT 1
        """,
        (int(user_id), int(char_id)),
        fetch="one",
    )


def remove_one_from_collection(user_id: int, char_id: int) -> bool:
    row = _run(
        "SELECT quantity::int AS q FROM user_collection WHERE user_id=%s AND character_id=%s",
        (int(user_id), int(char_id)),
        fetch="one",
    )
    if not row:
        return False

    q = int(row.get("q") or 0)
    if q <= 1:
        _run("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))
    else:
        _run("UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))
    return True


def set_favorite_from_collection(user_id: int, char_name: str, image: str):
    _run("UPDATE users SET fav_name=%s, fav_image=%s WHERE user_id=%s", (str(char_name), str(image), int(user_id)))


def clear_favorite(user_id: int):
    _run("UPDATE users SET fav_name=NULL, fav_image=NULL WHERE user_id=%s", (int(user_id),))


# ================================
# GIROS (extra_dado) + SLOT
# ================================
def get_extra_state(user_id: int) -> dict:
    row = _run(
        "SELECT COALESCE(extra_dado,0)::int AS x, COALESCE(extra_slot,-1)::bigint AS s FROM users WHERE user_id=%s",
        (int(user_id),),
        fetch="one",
    ) or {}
    return {"x": int(row.get("x") or 0), "s": int(row.get("s") or -1)}


def set_extra_state(user_id: int, extra: int, slot: int):
    _run("UPDATE users SET extra_dado=%s, extra_slot=%s WHERE user_id=%s", (int(extra), int(slot), int(user_id)))


def consume_extra_dado(user_id: int) -> bool:
    row = _run(
        """
        UPDATE users
        SET extra_dado = COALESCE(extra_dado,0) - 1
        WHERE user_id=%s AND COALESCE(extra_dado,0) > 0
        RETURNING extra_dado
        """,
        (int(user_id),),
        fetch="one",
    )
    return row is not None


def add_extra_dado(user_id: int, amount: int):
    _run("UPDATE users SET extra_dado = COALESCE(extra_dado,0) + %s WHERE user_id=%s", (int(amount), int(user_id)))


def get_extra_dado(user_id: int) -> int:
    st = get_extra_state(user_id)
    return int(st.get("x") or 0)


# ================================
# DADO (saldo/slot)
# ================================
def get_dado_state(user_id: int) -> Optional[Dict[str, int]]:
    row = _run(
        "SELECT COALESCE(dado_balance,0)::int AS b, COALESCE(dado_slot,-1)::bigint AS s FROM users WHERE user_id=%s",
        (int(user_id),),
        fetch="one",
    )
    if not row:
        return None
    return {"b": int(row.get("b") or 0), "s": int(row.get("s") or -1)}


def set_dado_state(user_id: int, balance: int, slot: int):
    _run("UPDATE users SET dado_balance=%s, dado_slot=%s WHERE user_id=%s", (int(balance), int(slot), int(user_id)))


def inc_dado_balance(user_id: int, amount: int, max_balance: int = 18):
    row = _run("SELECT COALESCE(dado_balance,0)::int AS b FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    b = int(row.get("b") or 0)
    b2 = min(int(max_balance), b + int(amount))
    _run("UPDATE users SET dado_balance=%s WHERE user_id=%s", (int(b2), int(user_id)))


# ================================
# ROLLS (idempotência)
# ================================
def create_dice_roll(user_id: int, dice_value: int, options_json: str, status: str, created_at: int) -> int:
    row = _run(
        """
        INSERT INTO dice_rolls (user_id, dice_value, options_json, status, created_at)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING roll_id
        """,
        (int(user_id), int(dice_value), str(options_json), str(status), int(created_at)),
        fetch="one",
    ) or {}
    return int(row.get("roll_id") or 0)


def get_dice_roll(roll_id: int):
    return _run("SELECT * FROM dice_rolls WHERE roll_id=%s", (int(roll_id),), fetch="one")


def set_dice_roll_status(roll_id: int, status: str):
    _run("UPDATE dice_rolls SET status=%s WHERE roll_id=%s", (str(status), int(roll_id)))


def try_set_dice_roll_status(roll_id: int, expected: str, new_status: str) -> bool:
    row = _run(
        """
        UPDATE dice_rolls
        SET status=%s
        WHERE roll_id=%s AND status=%s
        RETURNING roll_id
        """,
        (str(new_status), int(roll_id), str(expected)),
        fetch="one",
    )
    return row is not None


# ================================
# TROCAS (lock de linha + transação)
# ================================
def create_trade(from_user: int, to_user: int, from_char: int, to_char: int) -> int:
    row = _run(
        """
        INSERT INTO trades (from_user, to_user, from_character_id, to_character_id, status, created_at)
        VALUES (%s, %s, %s, %s, 'pendente', %s)
        RETURNING trade_id
        """,
        (int(from_user), int(to_user), int(from_char), int(to_char), int(time.time())),
        fetch="one",
    ) or {}
    return int(row.get("trade_id") or 0)


def get_trade_by_id(trade_id: int):
    return _run("SELECT * FROM trades WHERE trade_id=%s", (int(trade_id),), fetch="one")


def get_latest_pending_trade_for_to_user(to_user: int):
    row = _run(
        """
        SELECT trade_id, from_user, from_character_id, to_character_id
        FROM trades
        WHERE to_user=%s AND status='pendente'
        ORDER BY trade_id DESC
        LIMIT 1
        """,
        (int(to_user),),
        fetch="one",
    )
    if not row:
        return None
    return (int(row["trade_id"]), int(row["from_user"]), int(row["from_character_id"]), int(row["to_character_id"]))


def mark_trade_status(trade_id: int, status: str):
    _run("UPDATE trades SET status=%s WHERE trade_id=%s", (str(status), int(trade_id)))


def list_pending_trades_for_user(user_id: int, limit: int = 10):
    return _run(
        """
        SELECT trade_id, from_user, from_character_id, to_character_id, status, created_at
        FROM trades
        WHERE to_user=%s AND status='pendente'
        ORDER BY trade_id DESC
        LIMIT %s
        """,
        (int(user_id), int(limit)),
        fetch="all",
    ) or []


def swap_trade_execute(trade_id: int, from_user: int, to_user: int, from_char: int, to_char: int) -> bool:
    """Troca segura: lock em trade + locks em duas linhas da coleção."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT status FROM trades WHERE trade_id=%s FOR UPDATE", (int(trade_id),))
                tr = cur.fetchone()
                if not tr or tr.get("status") != "pendente":
                    conn.commit()
                    return False

                cur.execute(
                    "SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s FOR UPDATE",
                    (int(from_user), int(from_char)),
                )
                a_ok = cur.fetchone() is not None

                cur.execute(
                    "SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s FOR UPDATE",
                    (int(to_user), int(to_char)),
                )
                b_ok = cur.fetchone() is not None

                if not a_ok or not b_ok:
                    cur.execute("UPDATE trades SET status='falhou' WHERE trade_id=%s", (int(trade_id),))
                    conn.commit()
                    return False

                cur.execute(
                    "UPDATE user_collection SET user_id=%s WHERE user_id=%s AND character_id=%s",
                    (int(to_user), int(from_user), int(from_char)),
                )
                cur.execute(
                    "UPDATE user_collection SET user_id=%s WHERE user_id=%s AND character_id=%s",
                    (int(from_user), int(to_user), int(to_char)),
                )
                cur.execute("UPDATE trades SET status='aceita' WHERE trade_id=%s", (int(trade_id),))
                conn.commit()
                return True
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


# ================================
# DAILY (idempotente)
# ================================
def claim_daily_reward(
    user_id: int,
    day_start_ts: int,
    coins_min: int = 1,
    coins_max: int = 3,
    giro_chance: float = 0.20,
):
    import random
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    UPDATE users
                    SET last_daily=%s
                    WHERE user_id=%s AND COALESCE(last_daily,0) < %s
                    RETURNING user_id
                    """,
                    (int(day_start_ts), int(user_id), int(day_start_ts)),
                )
                ok = cur.fetchone() is not None
                if not ok:
                    conn.commit()
                    return None

                if random.random() < float(giro_chance):
                    cur.execute("UPDATE users SET extra_dado = COALESCE(extra_dado,0) + 1 WHERE user_id=%s", (int(user_id),))
                    conn.commit()
                    return {"type": "giro", "amount": 1}

                amt = random.randint(int(coins_min), int(coins_max))
                cur.execute("UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s", (int(amt), int(user_id)))
                conn.commit()
                return {"type": "coins", "amount": int(amt)}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


# ================================
# IMAGENS GLOBAIS + BAN
# ================================
def set_global_character_image(char_id: int, url: str, updated_by: Optional[int] = None):
    _run(
        """
        INSERT INTO character_images (character_id, image_url, updated_at, updated_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (character_id) DO UPDATE
        SET image_url=EXCLUDED.image_url, updated_at=EXCLUDED.updated_at, updated_by=EXCLUDED.updated_by
        """,
        (int(char_id), str(url), int(time.time()), int(updated_by) if updated_by else None),
    )


def get_global_character_image(char_id: int) -> Optional[str]:
    row = _run("SELECT image_url FROM character_images WHERE character_id=%s", (int(char_id),), fetch="one") or {}
    return row.get("image_url")


def delete_global_character_image(char_id: int):
    _run("DELETE FROM character_images WHERE character_id=%s", (int(char_id),))


def ban_character(char_id: int, reason: Optional[str] = None, created_by: Optional[int] = None):
    _run(
        """
        INSERT INTO banned_characters (character_id, reason, created_at, created_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (character_id) DO UPDATE
        SET reason=EXCLUDED.reason, created_at=EXCLUDED.created_at, created_by=EXCLUDED.created_by
        """,
        (int(char_id), str(reason) if reason else None, int(time.time()), int(created_by) if created_by else None),
    )


def unban_character(char_id: int):
    _run("DELETE FROM banned_characters WHERE character_id=%s", (int(char_id),))


def is_banned_character(char_id: int) -> bool:
    row = _run("SELECT 1 FROM banned_characters WHERE character_id=%s", (int(char_id),), fetch="one")
    return row is not None


# ================================
# TOP CACHE
# ================================
def top_cache_last_updated() -> int:
    row = _run("SELECT COALESCE(MAX(updated_at),0)::int AS t FROM top_anime_cache", fetch="one") or {}
    return int(row.get("t") or 0)


def replace_top_anime_cache(items: List[Dict[str, Any]], updated_at: int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM top_anime_cache")
                for it in items:
                    cur.execute(
                        "INSERT INTO top_anime_cache (anime_id, title, rank, updated_at) VALUES (%s,%s,%s,%s)",
                        (int(it["anime_id"]), str(it["title"]), int(it["rank"]), int(updated_at)),
                    )
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def get_top_anime_list(limit: int = 50):
    return _run(
        "SELECT anime_id, title, rank, updated_at FROM top_anime_cache ORDER BY rank ASC LIMIT %s",
        (int(limit),),
        fetch="all",
    ) or []


def increment_commands_and_level(user_id: int, nick_fallback: str, comandos_por_nivel: int):
    """Incrementa commands e atualiza level de forma transacional e concorrente (FOR UPDATE).
    Retorna dict com old_level, level, commands, nick_safe, ou None.
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    WITH old AS (
                        SELECT
                            COALESCE(commands, 0) AS old_commands,
                            COALESCE(level, 1)    AS old_level,
                            COALESCE(nick, %s)    AS nick_safe
                        FROM users
                        WHERE user_id = %s
                        FOR UPDATE
                    ),
                    upd AS (
                        UPDATE users
                        SET
                            commands = (SELECT old_commands FROM old) + 1,
                            level = GREATEST(
                                (SELECT old_level FROM old),
                                (((SELECT old_commands FROM old) + 1) / %s) + 1
                            )
                        WHERE user_id = %s
                        RETURNING commands, level
                    )
                    SELECT
                        (SELECT old_level FROM old)    AS old_level,
                        (SELECT nick_safe FROM old)    AS nick_safe,
                        (SELECT commands FROM upd)     AS commands,
                        (SELECT level FROM upd)        AS level
                    ;
                    """,
                    (str(nick_fallback), int(user_id), int(comandos_por_nivel), int(user_id)),
                )
                data = cur.fetchone()
                conn.commit()
                return data
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return None

def try_set_nick(user_id: int, nick: str) -> bool:
    """Tenta setar nick. Retorna False se violar unique."""
    try:
        _run("UPDATE users SET nick=%s WHERE user_id=%s", (str(nick), int(user_id)))
        return True
    except pg_errors.UniqueViolation:
        return False
    except Exception:
        return False

def get_collection_quantities(user_id: int, char_ids: List[int]) -> Dict[int, int]:
    if not char_ids:
        return {}
    placeholders = ",".join(["%s"] * len(char_ids))
    sql = f"""
        SELECT character_id, quantity
        FROM user_collection
        WHERE user_id=%s AND character_id IN ({placeholders})
    """
    rows = _run(sql, (int(user_id), *[int(x) for x in char_ids]), fetch="all") or []
    out: Dict[int, int] = {}
    for r in rows:
        out[int(r["character_id"])] = int(r.get("quantity") or 0)
    return out

# ================================
# RANKINGS / STATS / CONQUISTAS
# ================================
# Mantive a interface do seu arquivo original — por brevidade e compatibilidade.
# Estas funções são as mesmas do seu "novo database.txt" (não alteram textos do bot).
# Para não estourar tamanho aqui, eu carrego o restante do seu arquivo original e anexo no final.

# ================================
# RANKINGS
# ================================
def get_top_by_level(limit: int = 10):
    return _run(
        """
        SELECT user_id,
               COALESCE(nick, 'User') AS nick,
               COALESCE(level, 1) AS level,
               COALESCE(commands, 0) AS commands,
               COALESCE(coins, 0) AS coins
        FROM users
        ORDER BY COALESCE(level,1) DESC,
                 COALESCE(commands,0) DESC,
                 COALESCE(coins,0) DESC,
                 user_id ASC
        LIMIT %s
        """,
        (int(limit),),
        fetch="all",
    ) or []


def get_top_by_coins(limit: int = 10):
    return _run(
        """
        SELECT user_id,
               COALESCE(nick, 'User') AS nick,
               COALESCE(coins, 0) AS coins,
               COALESCE(level, 1) AS level
        FROM users
        ORDER BY COALESCE(coins,0) DESC,
                 COALESCE(level,1) DESC,
                 user_id ASC
        LIMIT %s
        """,
        (int(limit),),
        fetch="all",
    ) or []


def get_top_by_collection(limit: int = 10):
    return _run(
        """
        WITH c AS (
            SELECT user_id, COUNT(*)::int AS total
            FROM user_collection
            GROUP BY user_id
        )
        SELECT u.user_id,
               COALESCE(u.nick, 'User') AS nick,
               COALESCE(c.total, 0) AS total
        FROM users u
        LEFT JOIN c ON c.user_id = u.user_id
        ORDER BY COALESCE(c.total,0) DESC,
                 u.user_id ASC
        LIMIT %s
        """,
        (int(limit),),
        fetch="all",
    ) or []


# ================================
# STATS / CONQUISTAS
# ================================
def get_collection_unique_count(user_id: int) -> int:
    row = _run("SELECT COUNT(*)::int AS c FROM user_collection WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("c") or 0)


def get_collection_total_quantity(user_id: int) -> int:
    row = _run("SELECT COALESCE(SUM(quantity),0)::int AS s FROM user_collection WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("s") or 0)


def get_dice_roll_counts(user_id: int) -> dict:
    r = _run(
        """
        SELECT
          COUNT(*)::int AS total,
          COALESCE(SUM((status='resolved')::int),0)::int AS resolved,
          COALESCE(SUM((status='expired')::int),0)::int AS expired,
          COALESCE(SUM((status='pending')::int),0)::int AS pending
        FROM dice_rolls
        WHERE user_id=%s
        """,
        (int(user_id),),
        fetch="one",
    ) or {}
    return {
        "total": int(r.get("total") or 0),
        "resolved": int(r.get("resolved") or 0),
        "expired": int(r.get("expired") or 0),
        "pending": int(r.get("pending") or 0),
    }


def get_trade_counts(user_id: int) -> dict:
    r = _run(
        """
        SELECT
          COUNT(*)::int AS total,
          COALESCE(SUM((status='pendente')::int),0)::int AS pendente,
          COALESCE(SUM((status='aceita')::int),0)::int AS aceita,
          COALESCE(SUM((status='recusada')::int),0)::int AS recusada,
          COALESCE(SUM((status='falhou')::int),0)::int AS falhou
        FROM trades
        WHERE from_user=%s OR to_user=%s
        """,
        (int(user_id), int(user_id)),
        fetch="one",
    ) or {}
    return {
        "total": int(r.get("total") or 0),
        "pendente": int(r.get("pendente") or 0),
        "aceita": int(r.get("aceita") or 0),
        "recusada": int(r.get("recusada") or 0),
        "falhou": int(r.get("falhou") or 0),
    }


def get_user_stats(user_id: int) -> dict:
    u = _run(
        """
        SELECT
          user_id,
          COALESCE(nick,'User') AS nick,
          COALESCE(coins,0) AS coins,
          COALESCE(level,1) AS level,
          COALESCE(commands,0) AS commands,
          COALESCE(extra_dado,0) AS extra_dado,
          COALESCE(extra_slot,-1) AS extra_slot,
          COALESCE(dado_balance,0) AS dado_balance,
          COALESCE(dado_slot,-1) AS dado_slot
        FROM users
        WHERE user_id=%s
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one",
    ) or {}

    return {
        "user_id": int(u.get("user_id") or user_id),
        "nick": u.get("nick") or "User",
        "coins": int(u.get("coins") or 0),
        "level": int(u.get("level") or 1),
        "commands": int(u.get("commands") or 0),
        "extra_dado": int(u.get("extra_dado") or 0),
        "extra_slot": int(u.get("extra_slot") or -1),
        "dado_balance": int(u.get("dado_balance") or 0),
        "dado_slot": int(u.get("dado_slot") or -1),
        "collection_unique": int(get_collection_unique_count(user_id)),
        "collection_total_qty": int(get_collection_total_quantity(user_id)),
        "dice": get_dice_roll_counts(user_id),
        "trades": get_trade_counts(user_id),
    }


def list_user_achievement_keys(user_id: int) -> set[str]:
    rows = _run(
        "SELECT achievement_key FROM user_achievements WHERE user_id=%s",
        (int(user_id),),
        fetch="all",
    ) or []
    return {str(r["achievement_key"]) for r in rows if r.get("achievement_key")}


def count_user_achievements(user_id: int) -> int:
    row = _run("SELECT COUNT(*)::int AS c FROM user_achievements WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("c") or 0)


def grant_achievements_and_reward(user_id: int, new_keys: list[str], reward_extra_dado_per: int = 1) -> int:
    if not new_keys:
        return 0

    now = int(time.time())
    new_keys = [str(k) for k in new_keys if k]

    cur = db.cursor()
    try:
        cur.execute("BEGIN")

        inserted = 0
        for k in new_keys:
            cur.execute(
                """
                INSERT INTO user_achievements (user_id, achievement_key, unlocked_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, achievement_key) DO NOTHING
                """,
                (int(user_id), k, now),
            )
            inserted += int(cur.rowcount or 0)

        if inserted > 0 and reward_extra_dado_per > 0:
            cur.execute(
                """
                UPDATE users
                SET extra_dado = COALESCE(extra_dado,0) + %s
                WHERE user_id=%s
                """,
                (int(inserted * reward_extra_dado_per), int(user_id)),
            )

        cur.execute("COMMIT")
        db.commit()
        return inserted

    except Exception:
        try:
            cur.execute("ROLLBACK")
        except Exception:
            pass
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass


# ================================
# MINIAPP: listar cards
# ================================
def list_collection_cards(user_id: int, limit: int = 200):
    rows = _run(
        """
        SELECT character_id, character_name, image, COALESCE(anime_title,'') AS anime_title
        FROM user_collection
        WHERE user_id=%s
        ORDER BY character_id DESC
        LIMIT %s
        """,
        (int(user_id), int(limit)),
        fetch="all",
    ) or []

    return [
        {
            "character_id": int(r["character_id"]),
            "name": r["character_name"],
            "image": r.get("image"),
            "anime_title": r.get("anime_title") or "",
        }
        for r in rows
    ]


# ==================================================
# BALTIGO ENGINE — MARKET / EVENTS / SECURITY / STATS
# ==================================================
def _now_ts() -> int:
    return int(time.time())

def create_engine_tables():
    _run(
        """
        CREATE TABLE IF NOT EXISTS market_listings (
            listing_id SERIAL PRIMARY KEY,
            seller_id BIGINT NOT NULL,
            character_id INT NOT NULL,
            character_name TEXT NOT NULL,
            image TEXT,
            anime_title TEXT,
            price INT NOT NULL,
            created_at BIGINT NOT NULL
        );
        """
    )
    _run("CREATE INDEX IF NOT EXISTS market_listings_price_idx ON market_listings (price);")
    _run("CREATE INDEX IF NOT EXISTS market_listings_seller_idx ON market_listings (seller_id);")

    _run(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id SERIAL PRIMARY KEY,
            event_name TEXT NOT NULL,
            start_time BIGINT NOT NULL,
            end_time BIGINT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by BIGINT,
            created_at BIGINT NOT NULL
        );
        """
    )
    _run("CREATE INDEX IF NOT EXISTS events_active_idx ON events (active);")

    _run(
        """
        CREATE TABLE IF NOT EXISTS security_flags (
            user_id BIGINT PRIMARY KEY,
            risk_score INT NOT NULL DEFAULT 0,
            updated_at BIGINT NOT NULL DEFAULT 0,
            reason TEXT
        );
        """
    )

def get_global_stats() -> dict:
    users = _run("SELECT COUNT(*)::int AS c FROM users", fetch="one") or {}
    coins = _run("SELECT COALESCE(SUM(coins),0)::bigint AS s FROM users", fetch="one") or {}
    chars = _run("SELECT COALESCE(SUM(quantity),0)::bigint AS s FROM user_collection", fetch="one") or {}
    market = _run("SELECT COUNT(*)::int AS c FROM market_listings", fetch="one") or {}
    return {
        "users": int(users.get("c") or 0),
        "coins": int(coins.get("s") or 0),
        "chars": int(chars.get("s") or 0),
        "market": int(market.get("c") or 0),
    }

def get_active_event():
    return _run(
        """
        SELECT event_id, event_name, start_time, end_time
        FROM events
        WHERE active=TRUE AND start_time <= %s AND end_time >= %s
        ORDER BY event_id DESC
        LIMIT 1
        """,
        (_now_ts(), _now_ts()),
        fetch="one",
    )

def start_event(event_name: str, duration_hours: int, created_by: int = 0):
    now = _now_ts()
    end = now + int(duration_hours) * 3600
    _run(
        """
        INSERT INTO events (event_name, start_time, end_time, active, created_by, created_at)
        VALUES (%s, %s, %s, TRUE, %s, %s)
        """,
        (str(event_name), int(now), int(end), int(created_by or 0), int(now)),
    )

def stop_all_events():
    _run("UPDATE events SET active=FALSE WHERE active=TRUE")

def market_create_listing(user_id: int, character_id: int, price: int) -> tuple[bool, str]:
    user_id = int(user_id); character_id = int(character_id); price = int(price)
    if price <= 0:
        return False, "preço inválido"
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT character_id, character_name, COALESCE(custom_image,image) AS img, anime_title, quantity
                    FROM user_collection
                    WHERE user_id=%s AND character_id=%s
                    FOR UPDATE
                    """,
                    (user_id, character_id),
                )
                it = cur.fetchone()
                if not it:
                    conn.rollback()
                    return False, "você não tem esse personagem"
                qty = int(it.get("quantity") or 0)
                if qty <= 0:
                    conn.rollback()
                    return False, "quantidade inválida"
                if qty == 1:
                    cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (user_id, character_id))
                else:
                    cur.execute("UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s", (user_id, character_id))

                cur.execute(
                    """
                    INSERT INTO market_listings (seller_id, character_id, character_name, image, anime_title, price, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING listing_id
                    """,
                    (user_id, character_id, str(it.get("character_name") or "Personagem"), str(it.get("img") or ""), str(it.get("anime_title") or ""), price, _now_ts()),
                )
                lid = cur.fetchone()["listing_id"]
                conn.commit()
                return True, f"listing criado (ID {lid})"
            except Exception as e:
                try: conn.rollback()
                except Exception: pass
                return False, f"erro: {e}"

def market_list(page: int = 1, per_page: int = 10):
    page = max(1, int(page)); per_page = max(1, min(20, int(per_page)))
    off = (page-1)*per_page
    rows = _run(
        """
        SELECT listing_id, seller_id, character_id, character_name, image, anime_title, price, created_at
        FROM market_listings
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        (per_page, off),
        fetch="all",
    ) or []
    return rows

def market_buy(buyer_id: int, listing_id: int) -> tuple[bool, str]:
    buyer_id = int(buyer_id); listing_id = int(listing_id)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT listing_id, seller_id, character_id, character_name, image, anime_title, price
                    FROM market_listings
                    WHERE listing_id=%s
                    FOR UPDATE
                    """,
                    (listing_id,),
                )
                lst = cur.fetchone()
                if not lst:
                    conn.rollback()
                    return False, "listing não existe"
                seller_id = int(lst["seller_id"]); price = int(lst["price"])
                if seller_id == buyer_id:
                    conn.rollback()
                    return False, "você não pode comprar sua própria venda"

                cur.execute(
                    """
                    UPDATE users
                    SET coins = COALESCE(coins,0) - %s
                    WHERE user_id=%s AND COALESCE(coins,0) >= %s
                    RETURNING user_id
                    """,
                    (price, buyer_id, price),
                )
                if cur.fetchone() is None:
                    conn.rollback()
                    return False, "coins insuficientes"

                cur.execute("UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s", (price, seller_id))

                cur.execute(
                    """
                    INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
                    VALUES (%s, %s, %s, %s, %s, 1)
                    ON CONFLICT (user_id, character_id) DO UPDATE
                    SET quantity = user_collection.quantity + 1,
                        character_name = COALESCE(EXCLUDED.character_name, user_collection.character_name),
                        image = COALESCE(EXCLUDED.image, user_collection.image),
                        anime_title = COALESCE(EXCLUDED.anime_title, user_collection.anime_title)
                    """,
                    (buyer_id, int(lst["character_id"]), str(lst["character_name"]), str(lst.get("image") or ""), str(lst.get("anime_title") or "")),
                )

                cur.execute("DELETE FROM market_listings WHERE listing_id=%s", (listing_id,))
                conn.commit()
                return True, "compra concluída"
            except Exception as e:
                try: conn.rollback()
                except Exception: pass
                return False, f"erro: {e}"
