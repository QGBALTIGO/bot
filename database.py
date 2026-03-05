# ================================
# database.py — Postgres (Railway)
# (POOL + MIGRAÇÃO REAL + TROCAS ROBUSTAS + DADO/GIROS + DAILY)
# ================================

import os
import re
import time
import random
from typing import Optional, Dict, List, Any, Tuple

from psycopg.rows import dict_row
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado.")

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
    s = re.sub(r"[^a-z0-9_\.]", "", s)
    return s or "user"


def _set_local_timeouts(cur, lock_timeout_ms: int = 3000, statement_timeout_ms: int = 8000):
    try:
        cur.execute("SET LOCAL lock_timeout = %s", (f"{int(lock_timeout_ms)}ms",))
        cur.execute("SET LOCAL statement_timeout = %s", (f"{int(statement_timeout_ms)}ms",))
    except Exception:
        pass


def _run(sql: str, params: Tuple = (), fetch: str = "none"):
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
# SCHEMA / INIT
# ================================
def _ensure_tables_base():
    # USERS
    _run(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY
        );
        """
    )

    # USER_COLLECTION (garante tabela e colunas base)
    _run(
        """
        CREATE TABLE IF NOT EXISTS user_collection (
            user_id BIGINT NOT NULL,
            character_id INT NOT NULL,
            character_name TEXT NOT NULL,
            image TEXT,
            anime_title TEXT,
            custom_image TEXT,
            quantity INT DEFAULT 1,
            PRIMARY KEY (user_id, character_id)
        );
        """
    )

    # TRADES
    _run(
        """
        CREATE TABLE IF NOT EXISTS trades (
            trade_id SERIAL PRIMARY KEY,
            from_user BIGINT NOT NULL,
            to_user BIGINT NOT NULL,
            from_character_id INT NOT NULL,
            to_character_id INT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            created_at BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())::BIGINT)
        );
        """
    )

    # DICE ROLLS
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

    # TOP CACHE
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

    # SHOP SALES (se você usa)
    _run(
        """
        CREATE TABLE IF NOT EXISTS shop_sales (
            sale_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            character_id INT,
            created_at BIGINT NOT NULL
        );
        """
    )

    # ACHIEVEMENTS (se você usa)
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


def _ensure_columns_user_collection():
    """
    MUITO IMPORTANTE: garante compatibilidade com DB antigo.
    Se seu banco foi criado numa versão antiga sem quantity/custom_image, isso aqui resolve.
    """
    stmts = [
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS character_name TEXT;", ()),
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS image TEXT;", ()),
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS anime_title TEXT;", ()),
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS custom_image TEXT;", ()),
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS quantity INT DEFAULT 1;", ()),
    ]
    _run_many(stmts)

    # se existir linhas nulas antigas (coluna adicionada depois), normaliza
    _run("UPDATE user_collection SET quantity=1 WHERE quantity IS NULL;")
    # character_name é NOT NULL na tabela nova; em bancos antigos pode existir NULL
    _run("UPDATE user_collection SET character_name=COALESCE(character_name, CONCAT('#', character_id::text)) WHERE character_name IS NULL;")


def _ensure_indexes():
    idx = [
        ("CREATE INDEX IF NOT EXISTS user_collection_user_idx ON user_collection (user_id);"),
        ("CREATE INDEX IF NOT EXISTS user_collection_char_idx ON user_collection (character_id);"),
        ("CREATE INDEX IF NOT EXISTS trades_to_user_idx ON trades (to_user);"),
        ("CREATE INDEX IF NOT EXISTS trades_status_idx ON trades (status);"),
        ("CREATE INDEX IF NOT EXISTS trades_to_status_id_desc_idx ON trades (to_user, status, trade_id DESC);"),
        ("CREATE INDEX IF NOT EXISTS trades_from_user_idx ON trades (from_user);"),
        ("CREATE INDEX IF NOT EXISTS users_last_daily_idx ON users (last_daily);"),
        ("CREATE INDEX IF NOT EXISTS users_dado_slot_idx ON users (dado_slot);"),
        ("CREATE INDEX IF NOT EXISTS users_extra_slot_idx ON users (extra_slot);"),
        ("CREATE INDEX IF NOT EXISTS dice_rolls_user_idx ON dice_rolls (user_id);"),
        ("CREATE INDEX IF NOT EXISTS dice_rolls_status_idx ON dice_rolls (status);"),
        ("CREATE INDEX IF NOT EXISTS dice_rolls_user_created_desc_idx ON dice_rolls (user_id, created_at DESC);"),
    ]
    for s in idx:
        try:
            _run(s)
        except Exception:
            pass


def init_db():
    _ensure_tables_base()
    _ensure_columns_users()
    _ensure_columns_user_collection()
    _ensure_indexes()


# ================================
# USERS
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
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (user_id, nick, "Minha Coleção", int(new_user_dice or 0), -1, 0, -1, 0),
            )
            return
        except pg_errors.UniqueViolation:
            continue

    _run(
        """
        INSERT INTO users (
            user_id, nick, collection_name,
            dado_balance, dado_slot,
            extra_dado, extra_slot,
            last_daily
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (user_id, f"user_{user_id}", "Minha Coleção", int(new_user_dice or 0), -1, 0, -1, 0),
    )


def get_user_coins(user_id: int) -> int:
    r = _run("SELECT COALESCE(coins,0)::int AS c FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(r.get("c") or 0)


# ================================
# DADO / GIROS STATE
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


# ================================
# COLEÇÃO HELPERS
# ================================
def user_has_character(user_id: int, char_id: int) -> bool:
    row = _run(
        "SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s LIMIT 1",
        (int(user_id), int(char_id)),
        fetch="one",
    )
    return row is not None


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


# ================================
# TROCAS
# ================================
def create_trade(from_user: int, to_user: int, from_char: int, to_char: int) -> int:
    row = _run(
        """
        INSERT INTO trades (from_user, to_user, from_character_id, to_character_id, status, created_at)
        VALUES (%s,%s,%s,%s,'pendente',%s)
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


def _swap_trade_execute_legacy(cur, from_user: int, to_user: int, from_char: int, to_char: int):
    """
    Fallback para bancos MUITO antigos que não tinham quantity:
    cada linha é 1 unidade (ou nem existia a coluna).
    """
    # remove as linhas
    cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (from_user, from_char))
    cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (to_user, to_char))

    # recria trocadas (com nome mínimo)
    cur.execute(
        """
        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, custom_image, quantity)
        VALUES (%s,%s,%s,NULL,NULL,NULL,1)
        ON CONFLICT (user_id, character_id) DO UPDATE SET quantity = COALESCE(user_collection.quantity,1) + 1
        """,
        (from_user, to_char, f"#{to_char}"),
    )
    cur.execute(
        """
        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, custom_image, quantity)
        VALUES (%s,%s,%s,NULL,NULL,NULL,1)
        ON CONFLICT (user_id, character_id) DO UPDATE SET quantity = COALESCE(user_collection.quantity,1) + 1
        """,
        (to_user, from_char, f"#{from_char}"),
    )


def swap_trade_execute(trade_id: int, from_user: int, to_user: int, from_char: int, to_char: int) -> bool:
    """
    Troca segura (1 unidade por 1 unidade) SEM mexer em PK.
    + Retry para lock_timeout/deadlock
    + Fallback para schema antigo sem 'quantity'
    """
    trade_id = int(trade_id)
    from_user = int(from_user)
    to_user = int(to_user)
    from_char = int(from_char)
    to_char = int(to_char)

    u1, u2 = (from_user, to_user) if from_user <= to_user else (to_user, from_user)

    attempts = 3
    for attempt in range(1, attempts + 1):
        with pool.connection() as conn:
            with conn.cursor() as cur:
                try:
                    _set_local_timeouts(cur, lock_timeout_ms=4000, statement_timeout_ms=12000)

                    # lock trade
                    cur.execute("SELECT status FROM trades WHERE trade_id=%s FOR UPDATE", (trade_id,))
                    tr = cur.fetchone()
                    if not tr or tr.get("status") != "pendente":
                        conn.commit()
                        return False

                    # locks users (se não existir, não trava, mas ok)
                    cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (u1,))
                    cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (u2,))

                    try:
                        # lock linhas na coleção (precisa quantity)
                        cur.execute(
                            """
                            SELECT quantity::int AS q, character_name, image, anime_title, custom_image
                            FROM user_collection
                            WHERE user_id=%s AND character_id=%s
                            FOR UPDATE
                            """,
                            (from_user, from_char),
                        )
                        a = cur.fetchone()

                        cur.execute(
                            """
                            SELECT quantity::int AS q, character_name, image, anime_title, custom_image
                            FROM user_collection
                            WHERE user_id=%s AND character_id=%s
                            FOR UPDATE
                            """,
                            (to_user, to_char),
                        )
                        b = cur.fetchone()
                    except pg_errors.UndefinedColumn:
                        # schema antigo: sem quantity
                        _swap_trade_execute_legacy(cur, from_user, to_user, from_char, to_char)
                        cur.execute("UPDATE trades SET status='aceita' WHERE trade_id=%s", (trade_id,))
                        conn.commit()
                        return True

                    if not a or int(a.get("q") or 0) <= 0 or not b or int(b.get("q") or 0) <= 0:
                        cur.execute("UPDATE trades SET status='falhou' WHERE trade_id=%s", (trade_id,))
                        conn.commit()
                        return False

                    # debita 1
                    if int(a["q"]) <= 1:
                        cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (from_user, from_char))
                    else:
                        cur.execute("UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s", (from_user, from_char))

                    if int(b["q"]) <= 1:
                        cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (to_user, to_char))
                    else:
                        cur.execute("UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s", (to_user, to_char))

                    # credita 1 (mantém metadados que a gente já tinha em a/b)
                    # from_user recebe to_char (metadados de b)
                    cur.execute(
                        """
                        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, custom_image, quantity)
                        VALUES (%s,%s,%s,%s,%s,%s,1)
                        ON CONFLICT (user_id, character_id) DO UPDATE
                        SET quantity = user_collection.quantity + 1
                        """,
                        (
                            from_user,
                            to_char,
                            str(b.get("character_name") or f"#{to_char}"),
                            b.get("image"),
                            b.get("anime_title"),
                            b.get("custom_image"),
                        ),
                    )

                    # to_user recebe from_char (metadados de a)
                    cur.execute(
                        """
                        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, custom_image, quantity)
                        VALUES (%s,%s,%s,%s,%s,%s,1)
                        ON CONFLICT (user_id, character_id) DO UPDATE
                        SET quantity = user_collection.quantity + 1
                        """,
                        (
                            to_user,
                            from_char,
                            str(a.get("character_name") or f"#{from_char}"),
                            a.get("image"),
                            a.get("anime_title"),
                            a.get("custom_image"),
                        ),
                    )

                    cur.execute("UPDATE trades SET status='aceita' WHERE trade_id=%s", (trade_id,))
                    conn.commit()
                    return True

                except (pg_errors.DeadlockDetected, pg_errors.LockNotAvailable, pg_errors.QueryCanceled) as e:
                    # retry
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    if attempt < attempts:
                        time.sleep(0.15 * attempt)
                        continue
                    raise e
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise

    return False


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
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur, lock_timeout_ms=4000, statement_timeout_ms=12000)

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
                    cur.execute(
                        "UPDATE users SET extra_dado = COALESCE(extra_dado,0) + 1 WHERE user_id=%s",
                        (int(user_id),),
                    )
                    conn.commit()
                    return {"type": "giro", "amount": 1}

                amt = random.randint(int(coins_min), int(coins_max))
                cur.execute(
                    "UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s",
                    (int(amt), int(user_id)),
                )
                conn.commit()
                return {"type": "coins", "amount": int(amt)}

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

# ================================
# COMPAT: increment_commands_and_level
# ================================
def increment_commands_and_level(user_id: int, nick_fallback: str = "User", comandos_por_nivel: int = 20):
    """
    Compat do bot.py:
    - incrementa users.commands em +1
    - recalcula users.level usando comandos_por_nivel
    - retorna um dict com old_level, nick_safe, commands, level

    OBS: usa FOR UPDATE para concorrência (evita double increment errado).
    """
    user_id = int(user_id)
    comandos_por_nivel = max(1, int(comandos_por_nivel))

    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur)

                # garante linha do usuário (caso chamem sem ensure_user_row antes)
                cur.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))

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
                    (str(nick_fallback), user_id, comandos_por_nivel, user_id),
                )

                data = cur.fetchone()
                conn.commit()
                return data
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
