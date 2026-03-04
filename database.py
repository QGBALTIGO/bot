# ================================
# database.py — Postgres (Railway)
# (POOL + TRANSACOES SEGURAS + MIGRACAO + DADO + GIROS SLOT + CACHE + DAILY + CONQUISTAS + RANKINGS + STATS + MINIAPP + ENGINE)
# ================================

import os
import re
import time
from typing import Optional, Dict, List, Any, Tuple

from psycopg.rows import dict_row
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado.")

# Pool (fundamental para concorrência)
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


def _set_local_timeouts(cur, lock_timeout_ms: int = 3000, statement_timeout_ms: int = 8000):
    """
    Evita requests presos por lock/consulta.
    Use apenas dentro de transações (SET LOCAL).
    """
    try:
        cur.execute("SET LOCAL lock_timeout = %s", (f"{int(lock_timeout_ms)}ms",))
        cur.execute("SET LOCAL statement_timeout = %s", (f"{int(statement_timeout_ms)}ms",))
    except Exception:
        # se o driver/ambiente rejeitar, não quebra
        pass

# ================================
# TOP500 JOBS (seed + progresso + txt)
# ================================
_run(
    """
    CREATE TABLE IF NOT EXISTS anilist_top500_jobs (
        job_id SERIAL PRIMARY KEY,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        created_by BIGINT,
        status TEXT NOT NULL,             -- 'seed_ready', 'building', 'done', 'error'
        seed_items INT NOT NULL,
        top_json TEXT NOT NULL,           -- lista JSON dos 500 (id + title)
        progress INT NOT NULL DEFAULT 0,  -- quantos dos 500 já processou (chars)
        txt_text TEXT NOT NULL DEFAULT '',-- txt parcial/final
        error_text TEXT
    );
    """
)
_run("CREATE INDEX IF NOT EXISTS anilist_top500_jobs_created_at_idx ON anilist_top500_jobs (created_at DESC);")
_run("CREATE INDEX IF NOT EXISTS anilist_top500_jobs_status_idx ON anilist_top500_jobs (status);")
        
# ================================
# MIGRAÇÃO / INIT
# ================================
def _ensure_columns_users():
    stmts = [
        # identidade / perfil
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS nick TEXT;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS collection_name TEXT;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_name TEXT;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_image TEXT;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS private_profile BOOLEAN DEFAULT FALSE;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_photo TEXT;", ()),

        # economia / progressão
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS coins INT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS commands INT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS level INT DEFAULT 1;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS xp INT DEFAULT 0;", ()),

        # cooldowns
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_dado BIGINT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_pedido BIGINT DEFAULT 0;", ()),

        # DAILY
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily BIGINT DEFAULT 0;", ()),

        # DADO (saldo normal + slot 4h)
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_balance INT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_slot BIGINT DEFAULT -1;", ()),

        # GIROS (extra_dado) + slot
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


def _try_create_indexes():
    # dedupe + unique nick
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
        # coleção
        ("user_collection_user_idx", "CREATE INDEX IF NOT EXISTS user_collection_user_idx ON user_collection (user_id);"),
        ("user_collection_char_idx", "CREATE INDEX IF NOT EXISTS user_collection_char_idx ON user_collection (character_id);"),
        ("collection_user_qty_idx", "CREATE INDEX IF NOT EXISTS collection_user_qty_idx ON user_collection (user_id, quantity DESC);"),

        # trades
        ("trades_to_user_idx", "CREATE INDEX IF NOT EXISTS trades_to_user_idx ON trades (to_user);"),
        ("trades_status_idx", "CREATE INDEX IF NOT EXISTS trades_status_idx ON trades (status);"),
        # crescimento: buscar pendentes por to_user (e ordenar por id desc)
        ("trades_to_status_id_desc_idx",
         "CREATE INDEX IF NOT EXISTS trades_to_status_id_desc_idx ON trades (to_user, status, trade_id DESC);"),
        # útil para stats (from_user OR to_user)
        ("trades_from_user_idx", "CREATE INDEX IF NOT EXISTS trades_from_user_idx ON trades (from_user);"),

        # dice_rolls
        ("dice_rolls_user_idx", "CREATE INDEX IF NOT EXISTS dice_rolls_user_idx ON dice_rolls (user_id);"),
        ("dice_rolls_status_idx", "CREATE INDEX IF NOT EXISTS dice_rolls_status_idx ON dice_rolls (status);"),
        # crescimento: histórico por user
        ("dice_rolls_user_created_desc_idx",
         "CREATE INDEX IF NOT EXISTS dice_rolls_user_created_desc_idx ON dice_rolls (user_id, created_at DESC);"),

        # top cache
        ("top_cache_rank_idx", "CREATE INDEX IF NOT EXISTS top_cache_rank_idx ON top_anime_cache (rank);"),

        # shop_sales
        ("shop_sales_user_idx", "CREATE INDEX IF NOT EXISTS shop_sales_user_idx ON shop_sales (user_id);"),
        ("shop_sales_user_created_desc_idx",
         "CREATE INDEX IF NOT EXISTS shop_sales_user_created_desc_idx ON shop_sales (user_id, created_at DESC);"),

        # users slots/daily (crescimento)
        ("users_last_daily_idx", "CREATE INDEX IF NOT EXISTS users_last_daily_idx ON users (last_daily);"),
        ("users_dado_slot_idx", "CREATE INDEX IF NOT EXISTS users_dado_slot_idx ON users (dado_slot);"),
        ("users_extra_slot_idx", "CREATE INDEX IF NOT EXISTS users_extra_slot_idx ON users (extra_slot);"),

        # dado extras
        ("bad_anime_until_idx", "CREATE INDEX IF NOT EXISTS bad_anime_until_idx ON bad_anime (until_ts);"),
        ("character_vault_updated_idx", "CREATE INDEX IF NOT EXISTS character_vault_updated_idx ON character_vault (updated_at DESC);"),

        # engine
        ("market_listings_seller_created_desc_idx",
         "CREATE INDEX IF NOT EXISTS market_listings_seller_created_desc_idx ON market_listings (seller_id, created_at DESC);"),
        ("market_listings_price_idx", "CREATE INDEX IF NOT EXISTS market_listings_price_idx ON market_listings (price);"),
        ("events_active_idx", "CREATE INDEX IF NOT EXISTS events_active_idx ON events (active);"),
    ]

    for name, sql in indexes:
        try:
            _run(sql)
        except Exception as e:
            print(f"⚠️ index {name} falhou (ok continuar):", e)


def init_db():
    # USERS base + colunas migráveis
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
            character_name TEXT NOT NULL,
            image TEXT,
            anime_title TEXT,
            custom_image TEXT,
            quantity INT DEFAULT 1,
            PRIMARY KEY (user_id, character_id)
        );
        """
    )

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

    # BATALHAS (tava no antigo)
    _run(
        """
        CREATE TABLE IF NOT EXISTS battles (
            chat_id BIGINT PRIMARY KEY,
            player1_id BIGINT,
            player2_id BIGINT,
            player1_name TEXT,
            player2_name TEXT,
            player1_char TEXT,
            player2_char TEXT,
            player1_hp INT DEFAULT 100,
            player2_hp INT DEFAULT 100,
            turno INT DEFAULT 0,
            vez INT DEFAULT 0
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

    # rolls dado
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

    _ensure_achievements_table()

    # tabelas extras
    try:
        create_engine_tables()
    except Exception as e:
        print("⚠️ create_engine_tables falhou (ok continuar):", e)
    try:
        create_dado_tables()
    except Exception as e:
        print("⚠️ create_dado_tables falhou (ok continuar):", e)

    # TOP500 pool (fonte única de personagens)
    try:
        create_characters_pool_tables()
    except Exception as e:
        print('⚠️ create_characters_pool_tables falhou (ok continuar):', e)

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
    """Tenta setar nick. Retorna False se violar unique."""
    try:
        _run("UPDATE users SET nick=%s WHERE user_id=%s", (str(nick), int(user_id)))
        return True
    except pg_errors.UniqueViolation:
        return False
    except Exception:
        return False


def set_user_nick(user_id: int, nick: str) -> bool:
    """Compatibilidade com o antigo: sanitiza e tenta setar."""
    return try_set_nick(int(user_id), _sanitize_nick(nick))


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
    """Quantidade de personagens únicos (linhas)."""
    row = _run("SELECT COUNT(*)::int AS c FROM user_collection WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("c") or 0)


def count_total_qty(user_id: int) -> int:
    """Quantidade total (somatório das quantidades)."""
    row = _run("SELECT COALESCE(SUM(quantity),0)::int AS s FROM user_collection WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("s") or 0)


def count_collection(user_id: int) -> int:
    """
    Compatibilidade com bot antigo:
    count_collection = contagem de itens únicos (COUNT linhas).
    """
    return count_unique(user_id)


def get_collection_page(user_id: int, page: int, per_page: int):
    """MiniApp/Loja: retorna (itens, total, total_pages)"""
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
        SELECT character_id, character_name, image, custom_image, anime_title, quantity
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
    """Compatível com versões antigas: devolve 'name' também."""
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
                "character_name": r["character_name"],
                "name": r["character_name"],  # compat
                "image": r.get("image"),
                "custom_image": r.get("custom_image"),
                "anime_title": r.get("anime_title") or "",
                "quantity": int(r.get("quantity") or 1),
            }
        )
    return out


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
    """Compatibilidade antiga: retorna apenas quantidade de giros."""
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


# ✅ FIX CRÍTICO: troca por QUANTIDADE (sem colisão de PK)
def swap_trade_execute(trade_id: int, from_user: int, to_user: int, from_char: int, to_char: int) -> bool:
    """
    Troca segura (1 unidade por 1 unidade) SEM mudar user_id da PK.
    - Debita 1 do from_user/from_char
    - Debita 1 do to_user/to_char
    - Credita 1 do from_user/to_char
    - Credita 1 do to_user/from_char

    Locks:
      - trava trade
      - trava user_collection em ordem consistente (evita deadlock)
    """
    trade_id = int(trade_id)
    from_user = int(from_user)
    to_user = int(to_user)
    from_char = int(from_char)
    to_char = int(to_char)

    # Ordem consistente de locks por user_id (reduz deadlock)
    u1, u2 = (from_user, to_user) if from_user <= to_user else (to_user, from_user)

    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur)

                # 1) lock do trade
                cur.execute("SELECT status FROM trades WHERE trade_id=%s FOR UPDATE", (trade_id,))
                tr = cur.fetchone()
                if not tr or tr.get("status") != "pendente":
                    conn.commit()
                    return False

                # 2) lock “barreira” por usuário (ordem fixa)
                #    trava a linha do users (rápido) pra dar ordem consistente
                cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (u1,))
                cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (u2,))

                # 3) lock nas duas linhas necessárias na coleção
                cur.execute(
                    """
                    SELECT quantity::int AS q
                    FROM user_collection
                    WHERE user_id=%s AND character_id=%s
                    FOR UPDATE
                    """,
                    (from_user, from_char),
                )
                a = cur.fetchone()

                cur.execute(
                    """
                    SELECT quantity::int AS q
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

                # --- Debita 1 do from_user/from_char
                if int(a["q"]) <= 1:
                    cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (from_user, from_char))
                else:
                    cur.execute(
                        "UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s",
                        (from_user, from_char),
                    )

                # --- Debita 1 do to_user/to_char
                if int(b["q"]) <= 1:
                    cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (to_user, to_char))
                else:
                    cur.execute(
                        "UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s",
                        (to_user, to_char),
                    )

                # --- Credita 1 do from_user/to_char (upsert)
                # pega metadata do item do to_user/to_char (antes de debitar, mas a gente já debitou; ainda podemos usar trades pra ids)
                # fallback: mantém nome/imagem/anime_title existentes se já tiver.
                cur.execute(
                    """
                    INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
                    SELECT %s, uc.character_id, uc.character_name, uc.image, uc.anime_title, 1
                    FROM user_collection uc
                    WHERE uc.user_id=%s AND uc.character_id=%s
                    LIMIT 1
                    ON CONFLICT (user_id, character_id) DO UPDATE
                    SET quantity = user_collection.quantity + 1
                    """,
                    (from_user, to_user, to_char),
                )
                # Se a linha não existir mais (porque q=1 e deletou), tenta usar trades + snapshot mínimo
                if cur.rowcount == 0:
                    cur.execute(
                        """
                        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
                        VALUES (%s, %s, %s, NULL, NULL, 1)
                        ON CONFLICT (user_id, character_id) DO UPDATE
                        SET quantity = user_collection.quantity + 1
                        """,
                        (from_user, to_char, f"#{to_char}"),
                    )

                # --- Credita 1 do to_user/from_char (upsert)
                cur.execute(
                    """
                    INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
                    SELECT %s, uc.character_id, uc.character_name, uc.image, uc.anime_title, 1
                    FROM user_collection uc
                    WHERE uc.user_id=%s AND uc.character_id=%s
                    LIMIT 1
                    ON CONFLICT (user_id, character_id) DO UPDATE
                    SET quantity = user_collection.quantity + 1
                    """,
                    (to_user, from_user, from_char),
                )
                if cur.rowcount == 0:
                    cur.execute(
                        """
                        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
                        VALUES (%s, %s, %s, NULL, NULL, 1)
                        ON CONFLICT (user_id, character_id) DO UPDATE
                        SET quantity = user_collection.quantity + 1
                        """,
                        (to_user, from_char, f"#{from_char}"),
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
    """
    Mantém sua abordagem (DELETE + INSERT), mas com transação única.
    Se quiser evoluir: UPSERT por anime_id (evita escrita total).
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur, lock_timeout_ms=5000, statement_timeout_ms=15000)

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
    """Incrementa commands e atualiza level de forma transacional e concorrente (FOR UPDATE)."""
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
    # ranking por UNIQUE (linhas). Se quiser por total, troque COUNT(*) por SUM(quantity).
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
                        """
                        UPDATE users
                        SET extra_dado = COALESCE(extra_dado,0) + %s
                        WHERE user_id=%s
                        """,
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


# ==========================================================
# BALTIGO ENGINE V4 TABLES
# ==========================================================
def create_engine_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS market_listings (
        listing_id SERIAL PRIMARY KEY,
        seller_id BIGINT,
        character TEXT,
        price INT,
        created_at BIGINT
    );
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS events (
        event_id SERIAL PRIMARY KEY,
        event_name TEXT,
        start_time BIGINT,
        end_time BIGINT,
        active BOOLEAN
    );
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS security_flags (
        user_id BIGINT PRIMARY KEY,
        risk_score INT,
        updated_at BIGINT
    );
    """)


# ==================================================
# DADO — Blacklist persistente + Vault (fallback definitivo)
# ==================================================
def create_dado_tables():
    _run("""
    CREATE TABLE IF NOT EXISTS bad_anime (
      anime_id INT PRIMARY KEY,
      until_ts BIGINT NOT NULL,
      reason TEXT,
      updated_at BIGINT NOT NULL
    );
    """)

    _run("""
    CREATE TABLE IF NOT EXISTS character_vault (
      character_id INT PRIMARY KEY,
      character_name TEXT NOT NULL,
      image TEXT,
      anime_title TEXT,
      updated_at BIGINT NOT NULL
    );
    """)


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
    _run("""
    INSERT INTO bad_anime (anime_id, until_ts, reason, updated_at)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (anime_id) DO UPDATE
    SET until_ts=EXCLUDED.until_ts,
        reason=EXCLUDED.reason,
        updated_at=EXCLUDED.updated_at
    """, (int(anime_id), int(until_ts), str(reason or ""), int(now)))


def vault_put_character(character_id: int, character_name: str, image: str = "", anime_title: str = ""):
    now = int(time.time())
    _run("""
    INSERT INTO character_vault (character_id, character_name, image, anime_title, updated_at)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (character_id) DO UPDATE
    SET character_name=EXCLUDED.character_name,
        image=COALESCE(NULLIF(EXCLUDED.image,''), character_vault.image),
        anime_title=COALESCE(NULLIF(EXCLUDED.anime_title,''), character_vault.anime_title),
        updated_at=EXCLUDED.updated_at
    """, (int(character_id), str(character_name), str(image or ""), str(anime_title or ""), int(now)))


# ✅ sem ORDER BY RANDOM() (melhor escala)
def vault_random_character():
    """
    Estratégia:
      1) tenta TABLESAMPLE (quase O(1))
      2) fallback: sorteia offset com COUNT + LIMIT/OFFSET
    """
    # 1) TABLESAMPLE (pode retornar 0 linhas em tabelas pequenas)
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

    # 2) fallback: offset aleatório
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


# ==========================================================
# MINIAPP: coleção/loja sem conflito
# ==========================================================
def get_collection_for_webapp(user_id: int, limit: int = 500):
    rows = _run(
        """
        SELECT character_id, character_name, image, custom_image, COALESCE(anime_title,'') AS anime_title, quantity
        FROM user_collection
        WHERE user_id=%s
        ORDER BY quantity DESC, character_id DESC
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
                "character_name": r["character_name"],
                "image": (r.get("custom_image") or r.get("image") or ""),
                "custom_image": (r.get("custom_image") or ""),
                "anime_title": r.get("anime_title") or "",
                "quantity": int(r.get("quantity") or 1),
            }
        )
    return out


def record_shop_sale(user_id: int, character_id: int, created_at: Optional[int] = None):
    _run(
        "INSERT INTO shop_sales (user_id, character_id, created_at) VALUES (%s,%s,%s)",
        (int(user_id), int(character_id), int(created_at or time.time())),
    )


def sell_character_from_collection(user_id: int, char_id: int, coin_gain: int) -> bool:
    """Venda segura (MiniApp Loja): remove 1 unidade do personagem e credita coins + log."""
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
                    cur.execute(
                        "DELETE FROM user_collection WHERE user_id=%s AND character_id=%s",
                        (int(user_id), int(char_id)),
                    )
                else:
                    cur.execute(
                        "UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s",
                        (int(user_id), int(char_id)),
                    )

                cur.execute(
                    "UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s",
                    (int(coin_gain), int(user_id)),
                )

                # log de venda
                cur.execute(
                    "INSERT INTO shop_sales (user_id, character_id, created_at) VALUES (%s,%s,%s)",
                    (int(user_id), int(char_id), int(time.time())),
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
# TOP500 JOB API
# ================================
import json as _json

def top500_job_create(created_by: int, seed_items: int, top_list: list[dict]) -> int:
    """
    top_list: [{"id": 123, "title": "..."}, ...] tamanho 500
    """
    now = int(time.time())
    row = _run(
        """
        INSERT INTO anilist_top500_jobs (created_at, updated_at, created_by, status, seed_items, top_json, progress, txt_text, error_text)
        VALUES (%s, %s, %s, 'seed_ready', %s, %s, 0, '', NULL)
        RETURNING job_id
        """,
        (now, now, int(created_by), int(seed_items), _json.dumps(top_list, ensure_ascii=False)),
        fetch="one",
    ) or {}
    return int(row.get("job_id") or 0)

def top500_job_get(job_id: int) -> Optional[dict]:
    return _run(
        """
        SELECT job_id, created_at, updated_at, created_by, status, seed_items, top_json, progress, txt_text, error_text
        FROM anilist_top500_jobs
        WHERE job_id=%s
        LIMIT 1
        """,
        (int(job_id),),
        fetch="one",
    )

def top500_job_latest() -> Optional[dict]:
    return _run(
        """
        SELECT job_id, created_at, updated_at, created_by, status, seed_items, top_json, progress, txt_text, error_text
        FROM anilist_top500_jobs
        ORDER BY created_at DESC
        LIMIT 1
        """,
        fetch="one",
    )

def top500_job_set_status(job_id: int, status: str, error_text: Optional[str] = None):
    now = int(time.time())
    _run(
        "UPDATE anilist_top500_jobs SET status=%s, updated_at=%s, error_text=%s WHERE job_id=%s",
        (str(status), now, error_text, int(job_id)),
    )

def top500_job_checkpoint(job_id: int, progress: int, txt_append: str):
    """
    Salva progresso + acrescenta txt (append) de forma segura.
    """
    now = int(time.time())
    _run(
        """
        UPDATE anilist_top500_jobs
        SET progress=%s,
            txt_text = COALESCE(txt_text,'') || %s,
            updated_at=%s
        WHERE job_id=%s
        """,
        (int(progress), str(txt_append), now, int(job_id)),
    )

def top500_job_mark_done(job_id: int):
    now = int(time.time())
    _run(
        "UPDATE anilist_top500_jobs SET status='done', updated_at=%s WHERE job_id=%s",
        (now, int(job_id)),
    )

def top500_job_read_top_list(job_row: dict) -> list[dict]:
    try:
        return _json.loads(job_row.get("top_json") or "[]") or []
    except Exception:
        return []


# ================================
# TOP500 POOL (FONTE ÚNICA)
# ================================
# Regras:
# - Sorteios (dado/cards/drops/loja) DEVEM usar somente characters_pool
# - AniList fica apenas como fallback de imagem (via id) se não houver setfoto
#
# Arquivo de import: top500_anilist_consolidado.txt
# Formatos aceitos:
#   "Nome (123)"
#   "- Nome (123)"
#   "#123 Anime Title"  (linha de anime, opcional)
#
# Observação: mantemos coleções antigas (LEGACY). O pool controla apenas o que é GERADO.
# ================================

def create_characters_pool_tables():
    _run(
        """
        CREATE TABLE IF NOT EXISTS characters_pool (
            character_id BIGINT PRIMARY KEY,
            name TEXT NOT NULL,
            anime TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at BIGINT DEFAULT 0
        );
        """
    )
    _run("CREATE INDEX IF NOT EXISTS characters_pool_anime_idx ON characters_pool (anime);")
    _run("CREATE INDEX IF NOT EXISTS characters_pool_active_idx ON characters_pool (is_active);")


def pool_import_top500_txt(file_path: str = "top500_anilist_consolidado.txt") -> dict:
    """
    Importa o pool a partir do TXT consolidado.
    - sem duplicação (PK + ON CONFLICT DO NOTHING)
    - idempotente (pode rodar quantas vezes quiser)
    Retorna: {inserted, skipped, total_lines}
    """
    inserted = 0
    skipped = 0
    total = 0
    now = int(time.time())

    # Cache simples de último anime encontrado (se o TXT tiver headers de anime)
    current_anime = "TOP500"

    # regex: pega "Nome (123)" mesmo com prefixo "-"
    rx = re.compile(r"^\s*-?\s*(?P<name>.+?)\s*\((?P<id>\d+)\)\s*$")

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            total += 1
            s = (line or "").strip()
            if not s:
                continue

            # header de anime: "#123 Nome do anime"
            if s.startswith("#"):
                # remove "#<rank>" se houver
                t = re.sub(r"^#\s*\d+\s*", "", s).strip()
                if t:
                    current_anime = t
                continue

            m = rx.match(s)
            if not m:
                continue

            char_id = int(m.group("id"))
            name = (m.group("name") or "").strip()
            anime = (current_anime or "TOP500").strip() or "TOP500"

            row = _run(
                """
                INSERT INTO characters_pool (character_id, name, anime, is_active, created_at)
                VALUES (%s, %s, %s, TRUE, %s)
                ON CONFLICT (character_id) DO NOTHING
                RETURNING character_id
                """,
                (int(char_id), str(name), str(anime), int(now)),
                fetch="one",
            )
            if row:
                inserted += 1
            else:
                skipped += 1

    return {"inserted": inserted, "skipped": skipped, "total_lines": total}


def pool_set_active(character_id: int, active: bool) -> bool:
    row = _run(
        "UPDATE characters_pool SET is_active=%s WHERE character_id=%s RETURNING character_id",
        (bool(active), int(character_id)),
        fetch="one",
    )
    return bool(row)


def pool_add_character(character_id: int, name: str, anime: str) -> bool:
    row = _run(
        """
        INSERT INTO characters_pool (character_id, name, anime, is_active, created_at)
        VALUES (%s, %s, %s, TRUE, %s)
        ON CONFLICT (character_id) DO UPDATE
        SET name=EXCLUDED.name,
            anime=EXCLUDED.anime
        RETURNING character_id
        """,
        (int(character_id), str(name), str(anime), int(time.time())),
        fetch="one",
    )
    return bool(row)


def pool_delete_character(character_id: int) -> bool:
    # "deletar" do pool = desativar, para não quebrar referências
    return pool_set_active(int(character_id), False)


def pool_random_animes(limit: int) -> List[dict]:
    """
    Retorna uma lista de animes aleatórios existentes no pool.
    Formato: [{anime: str}]
    """
    limit = max(1, min(int(limit), 6))
    rows = _run(
        """
        SELECT anime
        FROM (
            SELECT DISTINCT anime
            FROM characters_pool
            WHERE is_active=TRUE
        ) t
        ORDER BY RANDOM()
        LIMIT %s
        """,
        (int(limit),),
        fetch="all",
    ) or []
    out = []
    for r in rows:
        a = (r.get("anime") or "").strip()
        if a:
            out.append({"anime": a})
    return out


def pool_random_character(anime: Optional[str] = None) -> Optional[dict]:
    """
    Padrão: SELECT ... ORDER BY RANDOM() LIMIT 1
    (para pool ~5000 é ok. Se crescer muito, podemos trocar por TABLESAMPLE/OFFSET)
    Retorna: {character_id, name, anime}
    """
    if anime:
        row = _run(
            """
            SELECT character_id, name, anime
            FROM characters_pool
            WHERE is_active=TRUE AND anime=%s
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (str(anime),),
            fetch="one",
        )
    else:
        row = _run(
            """
            SELECT character_id, name, anime
            FROM characters_pool
            WHERE is_active=TRUE
            ORDER BY RANDOM()
            LIMIT 1
            """,
            fetch="one",
        )
    return row if isinstance(row, dict) else None


# ================================
# APAGAR PERSONAGEM -> +1 COIN
# ================================
# IMPORTANTE:
# - Isso é APENAS para a ação explícita do usuário "apagar".
# - NÃO usar em trade/swap, dado, loja (vender), etc.
# - Implementação transacional + idempotência por action_id (anti duplo clique)
# ================================

_run(
    """
    CREATE TABLE IF NOT EXISTS economy_actions (
        user_id BIGINT NOT NULL,
        action_id TEXT NOT NULL,
        created_at BIGINT NOT NULL,
        amount INT NOT NULL,
        reason TEXT NOT NULL,
        PRIMARY KEY (user_id, action_id)
    );
    """
)
_run("CREATE INDEX IF NOT EXISTS economy_actions_user_idx ON economy_actions (user_id);")


def delete_one_character_for_coin(user_id: int, character_id: int, action_id: str) -> int:
    """
    Remove 1 unidade do personagem da coleção e credita +1 coin.
    Retorna coins creditadas (0 ou 1).
    Idempotente por (user_id, action_id).
    """
    if not action_id:
        raise ValueError("action_id obrigatório")

    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                _set_local_timeouts(cur)

                # idempotência
                cur.execute(
                    "SELECT amount FROM economy_actions WHERE user_id=%s AND action_id=%s LIMIT 1",
                    (int(user_id), str(action_id)),
                )
                seen = cur.fetchone()
                if seen:
                    conn.commit()
                    return int(seen.get("amount") or 0)

                # trava a linha da coleção
                cur.execute(
                    """
                    SELECT quantity
                    FROM user_collection
                    WHERE user_id=%s AND character_id=%s
                    FOR UPDATE
                    """,
                    (int(user_id), int(character_id)),
                )
                row = cur.fetchone()
                if not row:
                    # registra action como 0 para bloquear retry infinito
                    cur.execute(
                        """
                        INSERT INTO economy_actions (user_id, action_id, created_at, amount, reason)
                        VALUES (%s,%s,%s,%s,%s)
                        """,
                        (int(user_id), str(action_id), int(time.time()), 0, "delete_character"),
                    )
                    conn.commit()
                    return 0

                q = int(row.get("quantity") or 0)
                if q <= 1:
                    cur.execute(
                        "DELETE FROM user_collection WHERE user_id=%s AND character_id=%s",
                        (int(user_id), int(character_id)),
                    )
                else:
                    cur.execute(
                        "UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s",
                        (int(user_id), int(character_id)),
                    )

                # credita coin
                cur.execute(
                    "UPDATE users SET coins=COALESCE(coins,0)+1 WHERE user_id=%s",
                    (int(user_id),),
                )

                # log idempotente
                cur.execute(
                    """
                    INSERT INTO economy_actions (user_id, action_id, created_at, amount, reason)
                    VALUES (%s,%s,%s,%s,%s)
                    """,
                    (int(user_id), str(action_id), int(time.time()), 1, "delete_character"),
                )

                conn.commit()
                return 1

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

