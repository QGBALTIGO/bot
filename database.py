# ================================
# database.py — Postgres (Railway)
# (ROBUSTO + MIGRAÇÃO + DADO + GIROS SLOT + CACHE + DAILY + CONQUISTAS + RANKINGS + STATS)
# ================================

import os
import re
import time
import psycopg
from psycopg.rows import dict_row
from psycopg import errors as pg_errors
from typing import Optional, Dict, List, Any, Tuple


# ================================
# CONEXÃO
# ================================
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrado. No Railway, crie a variável DATABASE_URL com valor ${{Postgres.DATABASE_URL}}"
    )

db = psycopg.connect(DATABASE_URL, cursor_factory=RealDictCursor)
db.autocommit = False  # a gente controla commit/rollback


# ================================
# HELPERS (ANTI TRANSAÇÃO ABORTADA)
# ================================
def _sanitize_nick(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "", s)
    # permite: a-z 0-9 _ .
    s = re.sub(r"[^a-z0-9_\.]", "", s)
    return s or "user"


def _run(sql: str, params: Tuple = (), fetch: str = "none"):
    """
    Executa 1 comando SQL com cursor LOCAL.
    fetch:
      - "none"    -> retorna None
      - "one"     -> retorna dict ou None
      - "all"     -> retorna list[dict]
    """
    cur = db.cursor()
    try:
        cur.execute(sql, params)
        if fetch == "one":
            row = cur.fetchone()
            db.commit()
            return row
        if fetch == "all":
            rows = cur.fetchall() or []
            db.commit()
            return rows
        db.commit()
        return None
    except Exception:
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


def _run_many(statements: List[Tuple[str, Tuple]]):
    """
    Executa vários comandos em sequência, todos com o MESMO cursor,
    mas com commit/rollback correto.
    Use apenas para migração/DDL (init_db).
    """
    cur = db.cursor()
    try:
        for sql, params in statements:
            cur.execute(sql, params)
        db.commit()
    except Exception:
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
# MIGRAÇÃO USERS
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

        # cooldowns antigos
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_dado BIGINT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_pedido BIGINT DEFAULT 0;", ()),

        # daily
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily BIGINT DEFAULT 0;", ()),

        # dado (saldo normal + slot 4h)
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_balance INT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_slot BIGINT DEFAULT -1;", ()),

        # giros (extra_dado) + slot
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_dado INT DEFAULT 0;", ()),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_slot BIGINT DEFAULT -1;", ()),
    ]
    _run_many(stmts)


def _dedupe_nicks_before_unique_index():
    """
    Renomeia nicks duplicados (case-insensitive) para evitar quebrar o índice UNIQUE.
    """
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

        # mantém o primeiro, muda o resto
        for uid in ids[1:]:
            _run("UPDATE users SET nick=%s WHERE user_id=%s", (f"{base}_{uid}", int(uid)))


def _ensure_achievements_table():
    _run("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            user_id BIGINT NOT NULL,
            achievement_key TEXT NOT NULL,
            unlocked_at BIGINT NOT NULL,
            PRIMARY KEY (user_id, achievement_key)
        );
    """)
    _run("""
        CREATE INDEX IF NOT EXISTS user_achievements_user_idx
        ON user_achievements (user_id);
    """)


def _try_create_indexes():
    """
    Cria índices isoladamente. Se falhar 1, não trava o resto.
    """
    # 1) dedupe + unique nick
    try:
        _dedupe_nicks_before_unique_index()
    except Exception as e:
        print("⚠️ Dedupe nicks falhou (ok continuar):", e)

    try:
        _run("""
            CREATE UNIQUE INDEX IF NOT EXISTS users_nick_unique
            ON users (LOWER(nick))
            WHERE nick IS NOT NULL;
        """)
    except Exception as e:
        print("⚠️ users_nick_unique falhou (ok continuar):", e)

    # 2) demais índices (um por um)
    indexes = [
        ("user_collection_user_idx", "CREATE INDEX IF NOT EXISTS user_collection_user_idx ON user_collection (user_id);"),
        ("trades_to_user_idx", "CREATE INDEX IF NOT EXISTS trades_to_user_idx ON trades (to_user);"),
        ("shop_sales_user_idx", "CREATE INDEX IF NOT EXISTS shop_sales_user_idx ON shop_sales (user_id);"),
        ("top_anime_cache_rank_idx", "CREATE INDEX IF NOT EXISTS top_anime_cache_rank_idx ON top_anime_cache (rank);"),
        ("dice_rolls_user_idx", "CREATE INDEX IF NOT EXISTS dice_rolls_user_idx ON dice_rolls (user_id);"),
        ("users_last_daily_idx", "CREATE INDEX IF NOT EXISTS users_last_daily_idx ON users (last_daily);"),
        ("users_dado_slot_idx", "CREATE INDEX IF NOT EXISTS users_dado_slot_idx ON users (dado_slot);"),
        ("users_extra_slot_idx", "CREATE INDEX IF NOT EXISTS users_extra_slot_idx ON users (extra_slot);"),
    ]

    for name, sql in indexes:
        try:
            _run(sql)
        except Exception as e:
            print(f"⚠️ Índice {name} falhou (ok continuar):", e)


# ================================
# INIT DB
# ================================
def init_db():
    # USERS base (mínimo)
    _run("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY
        );
    """)

    # migra users antiga
    _ensure_columns_users()

    # coleção
    _run("""
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
    """)

    # trocas
    _run("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id SERIAL PRIMARY KEY,
            from_user BIGINT,
            to_user BIGINT,
            from_character_id INT,
            to_character_id INT,
            status TEXT DEFAULT 'pendente'
        );
    """)

    # batalhas
    _run("""
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
    """)

    # loja
    _run("""
        CREATE TABLE IF NOT EXISTS shop_sales (
            sale_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            character_id INT,
            created_at BIGINT
        );
    """)

    # imagens globais
    _run("""
        CREATE TABLE IF NOT EXISTS character_images (
            character_id INT PRIMARY KEY,
            image_url TEXT NOT NULL,
            updated_at BIGINT NOT NULL,
            updated_by BIGINT
        );
    """)

    # ban
    _run("""
        CREATE TABLE IF NOT EXISTS banned_characters (
            character_id INT PRIMARY KEY,
            reason TEXT,
            created_at BIGINT NOT NULL,
            created_by BIGINT
        );
    """)

    # cache top 500
    _run("""
        CREATE TABLE IF NOT EXISTS top_anime_cache (
            anime_id INT PRIMARY KEY,
            title TEXT NOT NULL,
            rank INT NOT NULL,
            updated_at BIGINT NOT NULL
        );
    """)

    # rolls dado
    _run("""
        CREATE TABLE IF NOT EXISTS dice_rolls (
            roll_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            dice_value INT NOT NULL,
            options_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at BIGINT NOT NULL
        );
    """)

    # conquistas
    _ensure_achievements_table()

    # índices
    _try_create_indexes()


# ================================
# USERS
# ================================
def ensure_user_row(user_id: int, default_name: str, new_user_dice: int = 0):
    """
    Cria usuário se não existir.
    Se nick colidir no UNIQUE, tenta fallback.
    """
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
            try:
                db.rollback()
            except Exception:
                pass
            continue

    # último fallback
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


def set_user_nick(user_id: int, nick: str):
    # aqui o UNIQUE (users_nick_unique) vai garantir
    _run("UPDATE users SET nick=%s WHERE user_id=%s", (_sanitize_nick(nick), int(user_id)))


def add_coin(user_id: int, amount: int):
    _run("UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s", (int(amount), int(user_id)))


def get_user_coins(user_id: int) -> int:
    row = _run("SELECT COALESCE(coins,0)::int AS c FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("c") or 0)


def try_spend_coins(user_id: int, cost: int) -> bool:
    row = _run(
        """
        UPDATE users
        SET coins = COALESCE(coins,0) - %s
        WHERE user_id=%s AND COALESCE(coins,0) >= %s
        RETURNING coins
        """,
        (int(cost), int(user_id), int(cost)),
        fetch="one",
    )
    return row is not None


def set_collection_name(user_id: int, name: str):
    _run("UPDATE users SET collection_name=%s WHERE user_id=%s", (str(name), int(user_id)))


def get_collection_name(user_id: int) -> str:
    row = _run("SELECT collection_name FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return row.get("collection_name") or "Minha Coleção"


def set_private_profile(user_id: int, is_private: bool):
    _run("UPDATE users SET private_profile=%s WHERE user_id=%s", (bool(is_private), int(user_id)))


def set_admin_photo(user_id: int, url: str):
    _run("UPDATE users SET admin_photo=%s WHERE user_id=%s", (str(url), int(user_id)))


def get_admin_photo_db(user_id: int) -> Optional[str]:
    row = _run("SELECT admin_photo FROM users WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return row.get("admin_photo") or None


# ================================
# IMAGEM GLOBAL POR PERSONAGEM
# ================================
def set_global_character_image(character_id: int, image_url: str, updated_by: Optional[int] = None):
    _run(
        """
        INSERT INTO character_images (character_id, image_url, updated_at, updated_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (character_id) DO UPDATE SET
            image_url = EXCLUDED.image_url,
            updated_at = EXCLUDED.updated_at,
            updated_by = EXCLUDED.updated_by
        """,
        (int(character_id), str(image_url), int(time.time()), updated_by),
    )


def get_global_character_image(character_id: int) -> Optional[str]:
    row = _run("SELECT image_url FROM character_images WHERE character_id=%s", (int(character_id),), fetch="one") or {}
    return row.get("image_url") or None


def delete_global_character_image(character_id: int):
    _run("DELETE FROM character_images WHERE character_id=%s", (int(character_id),))


# ================================
# BAN
# ================================
def ban_character(character_id: int, reason: Optional[str] = None, created_by: Optional[int] = None):
    _run(
        """
        INSERT INTO banned_characters (character_id, reason, created_at, created_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (character_id) DO UPDATE SET
            reason=EXCLUDED.reason,
            created_at=EXCLUDED.created_at,
            created_by=EXCLUDED.created_by
        """,
        (int(character_id), reason, int(time.time()), created_by),
    )


def unban_character(character_id: int):
    _run("DELETE FROM banned_characters WHERE character_id=%s", (int(character_id),))


def is_banned_character(character_id: int) -> bool:
    row = _run("SELECT 1 FROM banned_characters WHERE character_id=%s", (int(character_id),), fetch="one")
    return row is not None


# ================================
# COLEÇÃO
# ================================
def count_collection(user_id: int) -> int:
    row = _run("SELECT COUNT(*)::int AS c FROM user_collection WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    return int(row.get("c") or 0)


def get_collection_page(user_id: int, page: int, per_page: int):
    page = max(1, int(page))
    per_page = max(1, int(per_page))
    offset = (page - 1) * per_page

    row = _run("SELECT COUNT(*)::int AS c FROM user_collection WHERE user_id=%s", (int(user_id),), fetch="one") or {}
    total = int(row.get("c") or 0)
    total_pages = (total - 1) // per_page + 1 if total else 1

    rows = _run(
        """
        SELECT character_id, character_name
        FROM user_collection
        WHERE user_id=%s
        ORDER BY character_id ASC
        LIMIT %s OFFSET %s
        """,
        (int(user_id), int(per_page), int(offset)),
        fetch="all",
    ) or []

    itens = [(int(r["character_id"]), r["character_name"]) for r in rows]
    return itens, total, total_pages


def user_has_character(user_id: int, char_id: int) -> bool:
    row = _run(
        "SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s",
        (int(user_id), int(char_id)),
        fetch="one",
    )
    return row is not None


def add_character_to_collection(user_id: int, char_id: int, name: str, image: str, anime_title: Optional[str] = None):
    # upsert por PK (user_id, character_id)
    _run(
        """
        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
        VALUES (%s, %s, %s, %s, %s, 1)
        ON CONFLICT (user_id, character_id) DO UPDATE SET
            quantity = user_collection.quantity + 1,
            character_name = EXCLUDED.character_name,
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
        _run(
            "UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s",
            (int(user_id), int(char_id)),
        )
    return True


# ================================
# FAVORITO
# ================================
def set_favorite_from_collection(user_id: int, char_name: str, image: str):
    _run(
        "UPDATE users SET fav_name=%s, fav_image=%s WHERE user_id=%s",
        (str(char_name), str(image), int(user_id)),
    )


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
    _run(
        "UPDATE users SET extra_dado=%s, extra_slot=%s WHERE user_id=%s",
        (int(extra), int(slot), int(user_id)),
    )


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
    _run(
        "UPDATE users SET extra_dado = COALESCE(extra_dado,0) + %s WHERE user_id=%s",
        (int(amount), int(user_id)),
    )


# COMPAT (bot antigo)
def get_extra_dado(user_id: int) -> int:
    st = get_extra_state(user_id)
    return int(st.get("x") or 0)


# ================================
# DADO: estado saldo/slot
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
    _run(
        "UPDATE users SET dado_balance=%s, dado_slot=%s WHERE user_id=%s",
        (int(balance), int(slot), int(user_id)),
    )


def inc_dado_balance(user_id: int, amount: int, max_balance: int = 18):
    row = _run(
        "SELECT COALESCE(dado_balance,0)::int AS b FROM users WHERE user_id=%s",
        (int(user_id),),
        fetch="one",
    ) or {}
    b = int(row.get("b") or 0)
    b2 = min(int(max_balance), b + int(amount))
    _run("UPDATE users SET dado_balance=%s WHERE user_id=%s", (int(b2), int(user_id)))


# ================================
# TOP CACHE
# ================================
def top_cache_last_updated() -> int:
    row = _run("SELECT COALESCE(MAX(updated_at),0)::bigint AS t FROM top_anime_cache", fetch="one") or {}
    return int(row.get("t") or 0)


def replace_top_anime_cache(items: List[Dict[str, Any]]):
    now = int(time.time())

    cur = db.cursor()
    try:
        cur.execute("TRUNCATE top_anime_cache")
        for it in items:
            cur.execute(
                """
                INSERT INTO top_anime_cache (anime_id, title, rank, updated_at)
                VALUES (%s, %s, %s, %s)
                """,
                (int(it["anime_id"]), str(it["title"]), int(it["rank"]), now),
            )
        db.commit()
    except Exception:
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


def get_top_anime_list(limit: int = 500) -> List[Dict[str, Any]]:
    return _run(
        """
        SELECT anime_id, title, rank
        FROM top_anime_cache
        ORDER BY rank ASC
        LIMIT %s
        """,
        (int(limit),),
        fetch="all",
    ) or []


# ================================
# DICE ROLLS
# ================================
def create_dice_roll(user_id: int, dice_value: int, options_json: str) -> int:
    row = _run(
        """
        INSERT INTO dice_rolls (user_id, dice_value, options_json, status, created_at)
        VALUES (%s, %s, %s, 'pending', %s)
        RETURNING roll_id
        """,
        (int(user_id), int(dice_value), str(options_json), int(time.time())),
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
# TROCAS (LOCK)
# ================================
def create_trade(from_user: int, to_user: int, from_char: int, to_char: int) -> int:
    row = _run(
        """
        INSERT INTO trades (from_user, to_user, from_character_id, to_character_id, status)
        VALUES (%s, %s, %s, %s, 'pendente')
        RETURNING trade_id
        """,
        (int(from_user), int(to_user), int(from_char), int(to_char)),
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


def swap_trade_execute(trade_id: int, from_user: int, to_user: int, from_char: int, to_char: int) -> bool:
    """
    Troca segura com lock (transação manual).
    """
    cur = db.cursor()
    try:
        cur.execute("BEGIN")

        cur.execute("SELECT status FROM trades WHERE trade_id=%s FOR UPDATE", (int(trade_id),))
        tr = cur.fetchone()
        if not tr or tr.get("status") != "pendente":
            cur.execute("ROLLBACK")
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
            cur.execute("COMMIT")
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
        cur.execute("COMMIT")
        return True

    except Exception:
        try:
            cur.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass


# ================================
# DAILY
# ================================
def claim_daily_reward(
    user_id: int,
    day_start_ts: int,
    coins_min: int = 1,
    coins_max: int = 3,
    giro_chance: float = 0.20,
):
    import random

    cur = db.cursor()
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
            db.commit()
            return None

        if random.random() < float(giro_chance):
            cur.execute(
                "UPDATE users SET extra_dado = COALESCE(extra_dado,0) + 1 WHERE user_id=%s",
                (int(user_id),),
            )
            db.commit()
            return {"type": "giro", "amount": 1}

        amount = random.randint(int(coins_min), int(coins_max))
        cur.execute(
            "UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s",
            (int(amount), int(user_id)),
        )
        db.commit()
        return {"type": "coins", "amount": int(amount)}

    except Exception:
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


def list_pending_trades_for_user(to_user: int, limit: int = 5):
    return _run(
        """
        SELECT trade_id, from_user, to_user, from_character_id, to_character_id, status
        FROM trades
        WHERE to_user=%s AND status='pendente'
        ORDER BY trade_id DESC
        LIMIT %s
        """,
        (int(to_user), int(limit)),
        fetch="all",
    ) or []


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
