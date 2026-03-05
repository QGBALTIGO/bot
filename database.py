# ================================
# database.py — Postgres (Railway)
# Pool + transações seguras + migrações (coleção/loja/dado/giros/daily/trocas)
# Compatível com imports do bot.py enviado pelo Kayky
# ================================

import os
import re
import time
import json
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
    s = re.sub(r"[^a-z0-9_\.]", "", s)  # permite: a-z 0-9 _ .
    return s or "user"


def _set_local_timeouts(cur, lock_timeout_ms: int = 3000, statement_timeout_ms: int = 12000):
    """Evita ficar preso em lock/consulta."""
    try:
        cur.execute("SET LOCAL lock_timeout = %s", (f"{int(lock_timeout_ms)}ms",))
        cur.execute("SET LOCAL statement_timeout = %s", (f"{int(statement_timeout_ms)}ms",))
    except Exception:
        pass


def _run(sql: str, params: Tuple = (), fetch: str = "none"):
    """
    Executa 1 comando SQL com conexão do pool.

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


def _ensure_columns_user_collection():
    stmts = [
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS character_name TEXT;", ()),
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS image TEXT;", ()),
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS anime_title TEXT;", ()),
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS custom_image TEXT;", ()),
        ("ALTER TABLE user_collection ADD COLUMN IF NOT EXISTS quantity INT DEFAULT 1;", ()),
    ]
    _run_many(stmts)


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


def _try_create_indexes():
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
        ("collection_user_qty_idx", "CREATE INDEX IF NOT EXISTS collection_user_qty_idx ON user_collection (user_id, quantity DESC);"),

        ("trades_to_user_idx", "CREATE INDEX IF NOT EXISTS trades_to_user_idx ON trades (to_user);"),
        ("trades_status_idx", "CREATE INDEX IF NOT EXISTS trades_status_idx ON trades (status);"),
        ("trades_to_status_id_desc_idx",
         "CREATE INDEX IF NOT EXISTS trades_to_status_id_desc_idx ON trades (to_user, status, trade_id DESC);"),
        ("trades_from_user_idx", "CREATE INDEX IF NOT EXISTS trades_from_user_idx ON trades (from_user);"),

        ("dice_rolls_user_idx", "CREATE INDEX IF NOT EXISTS dice_rolls_user_idx ON dice_rolls (user_id);"),
        ("dice_rolls_status_idx", "CREATE INDEX IF NOT EXISTS dice_rolls_status_idx ON dice_rolls (status);"),
        ("dice_rolls_user_created_desc_idx",
         "CREATE INDEX IF NOT EXISTS dice_rolls_user_created_desc_idx ON dice_rolls (user_id, created_at DESC);"),

        ("shop_sales_user_created_desc_idx",
         "CREATE INDEX IF NOT EXISTS shop_sales_user_created_desc_idx ON shop_sales (user_id, created_at DESC);"),

        ("users_last_daily_idx", "CREATE INDEX IF NOT EXISTS users_last_daily_idx ON users (last_daily);"),
        ("users_dado_slot_idx", "CREATE INDEX IF NOT EXISTS users_dado_slot_idx ON users (dado_slot);"),
        ("users_extra_slot_idx", "CREATE INDEX IF NOT EXISTS users_extra_slot_idx ON users (extra_slot);"),

        ("bad_anime_until_idx", "CREATE INDEX IF NOT EXISTS bad_anime_until_idx ON bad_anime (until_ts);"),
        ("character_vault_updated_idx", "CREATE INDEX IF NOT EXISTS character_vault_updated_idx ON character_vault (updated_at DESC);"),

        ("top_cache_rank_idx", "CREATE INDEX IF NOT EXISTS top_cache_rank_idx ON top_anime_cache (rank);"),
    ]
    for name, sql in indexes:
        try:
            _run(sql)
        except Exception as e:
            print(f"⚠️ index {name} falhou (ok continuar):", e)


def init_db():
    # USERS base
    _run(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY
        );
        """
    )
    _ensure_columns_users()

    # COLEÇÃO
    _run(
        """
        CREATE TABLE IF NOT EXISTS user_collection (
            user_id BIGINT NOT NULL,
            character_id INT NOT NULL,
            character_name TEXT NOT NULL DEFAULT '',
            image TEXT,
            anime_title TEXT,
            custom_image TEXT,
            quantity INT DEFAULT 1,
            PRIMARY KEY (user_id, character_id)
        );
        """
    )
    _ensure_columns_user_collection()

    # TROCAS
    _run(
        """
        CREATE TABLE IF NOT EXISTS trades (
            trade_id SERIAL PRIMARY KEY,
            from_user BIGINT NOT NULL,
            to_user BIGINT NOT NULL,
            from_character_id INT NOT NULL,
            to_character_id INT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            created_at BIGINT NOT NULL
        );
        """
    )
    _run("ALTER TABLE trades ADD COLUMN IF NOT EXISTS created_at BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())::BIGINT);")

    # DADO rolls
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

    # LOJA (log)
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

    # imagens globais
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

    # ban
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

    # cache top
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

    # dado: blacklist + vault
    create_dado_tables()

    # achievements
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
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, f"user_{user_id}", "Minha Coleção", int(new_user_dice or 0), -1, 0, -1, 0),
    )


def get_user_row(user_id: int):
    return _run("SELECT * FROM users WHERE user_id=%s", (int(user_id),), fetch="one")


def get_user_row_safe(user_id: int) -> dict:
    row = get_user_row(user_id)
    return row or {
        "user_id": int(user_id),
        "nick": "User",
        "coins": 0,
        "level": 1,
        "commands": 0,
        "extra_dado": 0,
        "extra_slot": -1,
        "dado_balance": 0,
        "dado_slot": -1,
        "last_daily": 0,
    }


def get_user_by_nick(nick: str):
    return _run("SELECT * FROM users WHERE LOWER(nick)=LOWER(%s) LIMIT 1", (str(nick),), fetch="one")


def try_set_nick(user_id: int, nick: str) -> bool:
    try:
        _run("UPDATE users SET nick=%s WHERE user_id=%s", (str(nick), int(user_id)))
        return True
    except pg_errors.UniqueViolation:
        return False
    except Exception:
        return False


def set_user_nick(user_id: int, nick: str) -> bool:
    return try_set_nick(int(user_id), _sanitize_nick(nick))


def set_private_profile(user_id: int, is_private: bool):
    _run("UPDATE users SET private_profile=%s WHERE user_id=%s", (bool(is_private), int(user_id)))


def set_admin_photo(user_id: int, url: str):
    _run("UPDATE users SET admin_photo=%s WHERE user_id=%s", (str(url), int(user_id)))


def get_admin_photo_db(user_id: int) -> Optional[str]:
    row = _run("SELECT admin_photo FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return row.get("admin_photo")


def set_last_pedido(user_id: int, ts: int):
    """Compat: alguns fluxos do bot ainda setam last_pedido."""
    _run("UPDATE users SET last_pedido=%s WHERE user_id=%s", (int(ts), int(user_id)))


def set_collection_name(user_id: int, name: str):
    _run("UPDATE users SET collection_name=%s WHERE user_id=%s", (str(name), int(user_id)))


def get_collection_name(user_id: int) -> str:
    row = _run("SELECT COALESCE(collection_name,'Minha Coleção') AS n FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return str(row.get("n") or "Minha Coleção")


# ================================
# COINS
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
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur)

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
# COLEÇÃO (UNIQUE vs TOTAL)
# ================================
def count_unique(user_id: int) -> int:
    row = _run("SELECT COUNT(*)::int AS c FROM user_collection WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("c") or 0)


def count_total_qty(user_id: int) -> int:
    row = _run("SELECT COALESCE(SUM(quantity),0)::int AS s FROM user_collection WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("s") or 0)


def count_collection(user_id: int) -> int:
    return count_unique(user_id)


def get_collection_page(user_id: int, page: int, per_page: int):
    page = max(1, int(page))
    per_page = max(1, min(50, int(per_page)))

    total_row = _run(
        "SELECT COUNT(*)::int AS c FROM user_collection WHERE user_id=%s",
        (int(user_id),),
        fetch="one",
    ) or {}
    total = int(total_row.get("c") or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)

    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    itens = _run(
        """
        SELECT character_id, character_name, image, custom_image, COALESCE(anime_title,'') AS anime_title, quantity
        FROM user_collection
        WHERE user_id=%s
        ORDER BY quantity DESC, character_id DESC
        LIMIT %s OFFSET %s
        """,
        (int(user_id), int(per_page), int(offset)),
        fetch="all",
    ) or []

    return itens, total, total_pages


def list_collection_cards(user_id: int, limit: int = 200):
    rows = _run(
        """
        SELECT character_id, character_name, image, custom_image, COALESCE(anime_title,'') AS anime_title, quantity
        FROM user_collection
        WHERE user_id=%s
        ORDER BY quantity DESC, character_id ASC
        LIMIT %s
        """,
        (int(user_id), int(limit)),
        fetch="all",
    ) or []
    out = []
    for r in rows:
        out.append(
            {
                "character_id": int(r["character_id"]),
                "character_name": r.get("character_name") or "",
                "name": r.get("character_name") or "",  # compat
                "image": r.get("image"),
                "custom_image": r.get("custom_image"),
                "anime_title": r.get("anime_title") or "",
                "quantity": int(r.get("quantity") or 1),
            }
        )
    return out


def user_has_character(user_id: int, char_id: int) -> bool:
    row = _run(
        "SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s AND COALESCE(quantity,0) > 0",
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
            character_name = COALESCE(NULLIF(EXCLUDED.character_name,''), user_collection.character_name),
            image = COALESCE(NULLIF(EXCLUDED.image,''), user_collection.image),
            anime_title = COALESCE(NULLIF(EXCLUDED.anime_title,''), user_collection.anime_title)
        """,
        (int(user_id), int(char_id), str(name or ""), str(image or ""), str(anime_title) if anime_title else None),
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
        "SELECT COALESCE(quantity,0)::int AS q FROM user_collection WHERE user_id=%s AND character_id=%s",
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
# TROCAS
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
    """
    Troca segura (1 unidade por 1 unidade) SEM mudar user_id da PK.
    Corrigido para NÃO depender da linha do item depois que ela pode ter sido deletada:
      - Faz snapshot da metadata dos 2 itens ANTES de debitar
      - Debita
      - Credita usando o snapshot (upsert)
    """
    trade_id = int(trade_id)
    from_user = int(from_user)
    to_user = int(to_user)
    from_char = int(from_char)
    to_char = int(to_char)

    u1, u2 = (from_user, to_user) if from_user <= to_user else (to_user, from_user)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur)

                # lock do trade (garante "pendente")
                cur.execute("SELECT status FROM trades WHERE trade_id=%s FOR UPDATE", (trade_id,))
                tr = cur.fetchone()
                if not tr or tr.get("status") != "pendente":
                    conn.commit()
                    return False

                # barreira de ordem por users (evita deadlock)
                cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (u1,))
                cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (u2,))

                # trava e snapshot item A
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

                # trava e snapshot item B
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

                if not a or int(a.get("q") or 0) <= 0 or not b or int(b.get("q") or 0) <= 0:
                    cur.execute("UPDATE trades SET status='falhou' WHERE trade_id=%s", (trade_id,))
                    conn.commit()
                    return False

                # snapshot metadata (antes de debitar)
                a_name = (a.get("character_name") or f"#{from_char}")
                a_img = (a.get("custom_image") or a.get("image") or None)
                a_anime = (a.get("anime_title") or None)

                b_name = (b.get("character_name") or f"#{to_char}")
                b_img = (b.get("custom_image") or b.get("image") or None)
                b_anime = (b.get("anime_title") or None)

                # debita A
                if int(a["q"]) <= 1:
                    cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (from_user, from_char))
                else:
                    cur.execute("UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s", (from_user, from_char))

                # debita B
                if int(b["q"]) <= 1:
                    cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (to_user, to_char))
                else:
                    cur.execute("UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s", (to_user, to_char))

                # credita from_user recebe to_char (metadata do B)
                cur.execute(
                    """
                    INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
                    VALUES (%s, %s, %s, %s, %s, 1)
                    ON CONFLICT (user_id, character_id) DO UPDATE
                    SET quantity = user_collection.quantity + 1,
                        character_name = COALESCE(NULLIF(EXCLUDED.character_name,''), user_collection.character_name),
                        image = COALESCE(NULLIF(EXCLUDED.image,''), user_collection.image),
                        anime_title = COALESCE(NULLIF(EXCLUDED.anime_title,''), user_collection.anime_title)
                    """,
                    (from_user, to_char, str(b_name), b_img, b_anime),
                )

                # credita to_user recebe from_char (metadata do A)
                cur.execute(
                    """
                    INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
                    VALUES (%s, %s, %s, %s, %s, 1)
                    ON CONFLICT (user_id, character_id) DO UPDATE
                    SET quantity = user_collection.quantity + 1,
                        character_name = COALESCE(NULLIF(EXCLUDED.character_name,''), user_collection.character_name),
                        image = COALESCE(NULLIF(EXCLUDED.image,''), user_collection.image),
                        anime_title = COALESCE(NULLIF(EXCLUDED.anime_title,''), user_collection.anime_title)
                    """,
                    (to_user, from_char, str(a_name), a_img, a_anime),
                )

                cur.execute("UPDATE trades SET status='aceita' WHERE trade_id=%s", (trade_id,))
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
                _set_local_timeouts(cur)

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
# TOP CACHE
# ================================
def top_cache_last_updated() -> int:
    row = _run("SELECT COALESCE(MAX(updated_at),0)::int AS t FROM top_anime_cache", fetch="one") or {}
    return int(row.get("t") or 0)


def replace_top_anime_cache(items: List[Dict[str, Any]], updated_at: int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur, lock_timeout_ms=5000, statement_timeout_ms=20000)
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


# ================================
# COMANDOS/LEVEL (compat)
# ================================
def increment_commands_and_level(user_id: int, nick_fallback: str, comandos_por_nivel: int):
    """
    Compat com seu bot: incrementa 'commands' e recalcula 'level' sem corrida.
    Retorna dict com:
      old_level, nick_safe, commands, level
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur)

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
# DADO — Blacklist persistente + Vault
# ================================
def create_dado_tables():
    _run(
        """
        CREATE TABLE IF NOT EXISTS bad_anime (
          anime_id INT PRIMARY KEY,
          until_ts BIGINT NOT NULL,
          reason TEXT,
          updated_at BIGINT NOT NULL
        );
        """
    )
    _run(
        """
        CREATE TABLE IF NOT EXISTS character_vault (
          character_id INT PRIMARY KEY,
          character_name TEXT NOT NULL,
          image TEXT,
          anime_title TEXT,
          updated_at BIGINT NOT NULL
        );
        """
    )


def is_bad_anime(anime_id: int) -> bool:
    row = _run("SELECT until_ts FROM bad_anime WHERE anime_id=%s", (int(anime_id),), fetch="one")
    if not row:
        return False
    until_ts = int(row.get("until_ts") or 0)
    if until_ts <= int(time.time()):
        _run("DELETE FROM bad_anime WHERE anime_id=%s", (int(anime_id),))
        return False
    return True


def mark_bad_anime(anime_id: int, reason: str = ""):
    now = int(time.time())
    ttl = 7 * 24 * 3600
    until_ts = now + ttl
    _run(
        """
        INSERT INTO bad_anime (anime_id, until_ts, reason, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (anime_id) DO UPDATE
        SET until_ts=EXCLUDED.until_ts,
            reason=EXCLUDED.reason,
            updated_at=EXCLUDED.updated_at
        """,
        (int(anime_id), int(until_ts), str(reason or ""), int(now)),
    )


def vault_put_character(character_id: int, character_name: str, image: str = "", anime_title: str = ""):
    now = int(time.time())
    _run(
        """
        INSERT INTO character_vault (character_id, character_name, image, anime_title, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (character_id) DO UPDATE
        SET character_name=EXCLUDED.character_name,
            image=COALESCE(NULLIF(EXCLUDED.image,''), character_vault.image),
            anime_title=COALESCE(NULLIF(EXCLUDED.anime_title,''), character_vault.anime_title),
            updated_at=EXCLUDED.updated_at
        """,
        (int(character_id), str(character_name), str(image or ""), str(anime_title or ""), int(now)),
    )


def vault_random_character():
    row = _run(
        """
        SELECT character_id, character_name, image, anime_title
        FROM character_vault TABLESAMPLE SYSTEM (1)
        LIMIT 1
        """,
        fetch="one",
    )
    if row:
        return row

    import random
    c = _run("SELECT COUNT(*)::int AS c FROM character_vault", fetch="one") or {}
    total = int(c.get("c") or 0)
    if total <= 0:
        return None
    off = random.randint(0, max(0, total - 1))
    return _run(
        """
        SELECT character_id, character_name, image, anime_title
        FROM character_vault
        ORDER BY character_id ASC
        LIMIT 1 OFFSET %s
        """,
        (int(off),),
        fetch="one",
    )


# ================================
# STATS (compat do bot)
# ================================
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
        "collection_unique": int(count_unique(user_id)),
        "collection_total_qty": int(count_total_qty(user_id)),
        "dice": get_dice_roll_counts(user_id),
        "trades": get_trade_counts(user_id),
    )


# ================================
# LOJA (compat do bot)
# ================================
def record_shop_sale(user_id: int, character_id: int, created_at: Optional[int] = None):
    _run(
        "INSERT INTO shop_sales (user_id, character_id, created_at) VALUES (%s,%s,%s)",
        (int(user_id), int(character_id), int(created_at or time.time())),
    )


def sell_character_from_collection(user_id: int, char_id: int, coin_gain: int) -> bool:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur)

                cur.execute(
                    """
                    SELECT quantity::int AS q
                    FROM user_collection
                    WHERE user_id=%s AND character_id=%s
                    FOR UPDATE
                    """,
                    (int(user_id), int(char_id)),
                )
                row = cur.fetchone()
                if not row:
                    conn.commit()
                    return False

                q = int(row.get("q") or 0)
                if q <= 1:
                    cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))
                else:
                    cur.execute("UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))

                cur.execute("UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s", (int(coin_gain), int(user_id)))
                cur.execute("INSERT INTO shop_sales (user_id, character_id, created_at) VALUES (%s,%s,%s)", (int(user_id), int(char_id), int(time.time())))

                conn.commit()
                return True
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


# ================================
# ACHIEVEMENTS (compat)
# ================================
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

    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur)

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
                        "UPDATE users SET extra_dado = COALESCE(extra_dado,0) + %s WHERE user_id=%s",
                        (int(inserted * reward_extra_dado_per), int(user_id)),
                    )

                conn.commit()
                return inserted
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
