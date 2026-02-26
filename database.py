# ================================
# database.py — Postgres (Railway) (BLINDADO: CONCORRÊNCIA + ATÔMICO + POOL)
# ================================

import os
import time
from contextlib import contextmanager
from typing import Optional, Dict, List, Any, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrado. No Railway, crie a variável DATABASE_URL com valor ${{Postgres.DATABASE_URL}}"
    )

# pool (thread-safe). Ajuste se quiser via env.
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

_pool = ThreadedConnectionPool(
    minconn=DB_POOL_MIN,
    maxconn=DB_POOL_MAX,
    dsn=DATABASE_URL,
)

# Backward-compat (evite usar!): existe só para não quebrar imports antigos
db = None
cursor = None


# ================================
# helpers
# ================================
@contextmanager
def _get_conn_cursor():
    """
    Pega conexão do pool e devolve (conn, cur).
    Commit automático ao sair sem erro; rollback em exceção.
    """
    conn = _pool.getconn()
    try:
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield conn, cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            try:
                cur.close()
            except Exception:
                pass
    finally:
        _pool.putconn(conn)


def _now_ts() -> int:
    return int(time.time())


def _ensure_columns_users(cur):
    """
    Migra tabela users antiga sem quebrar.
    """
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS nick TEXT;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS collection_name TEXT;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_name TEXT;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_image TEXT;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS coins INT DEFAULT 0;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS commands INT DEFAULT 0;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS level INT DEFAULT 1;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS xp INT DEFAULT 0;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS last_dado BIGINT DEFAULT 0;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS last_pedido BIGINT DEFAULT 0;""")

    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS private_profile BOOLEAN DEFAULT FALSE;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_photo TEXT;""")

    # DADO NOVO
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_balance INT DEFAULT 0;""")
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_slot BIGINT DEFAULT -1;""")

    # extra dado
    cur.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_dado INT DEFAULT 0;""")


def _try_create_indexes():
    with _get_conn_cursor() as (conn, cur):
        # unique nick
        try:
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS users_nick_unique
                ON users (LOWER(nick))
                WHERE nick IS NOT NULL;
            """)
        except Exception as e:
            # não pode travar o bot
            print("⚠️ Não consegui criar índice users_nick_unique (ok continuar). Erro:", e)

        # coleção
        cur.execute("CREATE INDEX IF NOT EXISTS user_collection_user_idx ON user_collection (user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS user_collection_char_idx ON user_collection (character_id);")

        # trades
        cur.execute("CREATE INDEX IF NOT EXISTS trades_to_user_idx ON trades (to_user);")
        cur.execute("CREATE INDEX IF NOT EXISTS trades_status_idx ON trades (status);")
        cur.execute("CREATE INDEX IF NOT EXISTS trades_to_status_idx ON trades (to_user, status);")

        # shop
        cur.execute("CREATE INDEX IF NOT EXISTS shop_sales_user_idx ON shop_sales (user_id);")

        # cache/top
        cur.execute("CREATE INDEX IF NOT EXISTS top_anime_cache_rank_idx ON top_anime_cache (rank);")

        # dado
        cur.execute("CREATE INDEX IF NOT EXISTS dice_rolls_user_idx ON dice_rolls (user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS dice_rolls_status_idx ON dice_rolls (status);")


# ================================
# INIT DB (com migração)
# ================================
def init_db():
    with _get_conn_cursor() as (conn, cur):
        # USERS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY
            );
        """)

        _ensure_columns_users(cur)

        # COLEÇÃO
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_collection (
                user_id BIGINT NOT NULL,
                character_id INT NOT NULL,
                character_name TEXT NOT NULL,
                image TEXT,
                anime_title TEXT,
                custom_image TEXT,
                quantity INT NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, character_id),
                CONSTRAINT user_collection_quantity_chk CHECK (quantity >= 1)
            );
        """)

        # TROCAS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id SERIAL PRIMARY KEY,
                from_user BIGINT NOT NULL,
                to_user BIGINT NOT NULL,
                from_character_id INT NOT NULL,
                to_character_id INT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                created_at BIGINT NOT NULL DEFAULT 0
            );
        """)

        # BATALHAS
        cur.execute("""
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

        # LOJA
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shop_sales (
                sale_id SERIAL PRIMARY KEY,
                user_id BIGINT,
                character_id INT,
                created_at BIGINT
            );
        """)

        # imagens globais
        cur.execute("""
            CREATE TABLE IF NOT EXISTS character_images (
                character_id INT PRIMARY KEY,
                image_url TEXT NOT NULL,
                updated_at BIGINT NOT NULL,
                updated_by BIGINT
            );
        """)

        # ban
        cur.execute("""
            CREATE TABLE IF NOT EXISTS banned_characters (
                character_id INT PRIMARY KEY,
                reason TEXT,
                created_at BIGINT NOT NULL,
                created_by BIGINT
            );
        """)

        # cache top 500
        cur.execute("""
            CREATE TABLE IF NOT EXISTS top_anime_cache (
                anime_id INT PRIMARY KEY,
                title TEXT NOT NULL,
                rank INT NOT NULL,
                updated_at BIGINT NOT NULL
            );
        """)

        # rolls dado
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dice_rolls (
                roll_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                dice_value INT NOT NULL,
                options_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at BIGINT NOT NULL
            );
        """)

    _try_create_indexes()


# ================================
# USERS
# ================================
def ensure_user_row(user_id: int, default_name: str, new_user_dice: int = 0):
    """
    Cria usuário se não existir (atômico).
    new_user_dice: saldo inicial só para usuário novo.
    """
    nick = (default_name or "user").strip() or "user"
    nick = nick.lower()

    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO users (user_id, nick, collection_name, dado_balance, dado_slot)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (int(user_id), nick, "Minha Coleção", int(new_user_dice or 0), -1))


def get_user_row(user_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT * FROM users WHERE user_id=%s", (int(user_id),))
        return cur.fetchone()


def get_user_by_nick(nick: str):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT * FROM users WHERE LOWER(nick)=LOWER(%s) LIMIT 1", (nick,))
        return cur.fetchone()


def set_user_nick(user_id: int, nick: str):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE users SET nick=%s WHERE user_id=%s", (nick, int(user_id)))


def try_set_user_nick_unique(user_id: int, nick: str) -> bool:
    """
    Tenta setar nick. Retorna False se violar unique.
    """
    with _get_conn_cursor() as (conn, cur):
        try:
            cur.execute("UPDATE users SET nick=%s WHERE user_id=%s", (nick, int(user_id)))
            return True
        except Exception:
            # unique violation ou outros
            return False


def add_coin(user_id: int, amount: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute(
            "UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s",
            (int(amount), int(user_id))
        )


def get_user_coins(user_id: int) -> int:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT COALESCE(coins,0) AS c FROM users WHERE user_id=%s", (int(user_id),))
        row = cur.fetchone()
        return int(row["c"] if row else 0)


def try_spend_coins(user_id: int, amount: int) -> bool:
    """
    Gasto atômico: só desconta se tiver saldo suficiente.
    """
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            UPDATE users
            SET coins = COALESCE(coins,0) - %s
            WHERE user_id=%s AND COALESCE(coins,0) >= %s
            RETURNING user_id
        """, (int(amount), int(user_id), int(amount)))
        return cur.fetchone() is not None


def set_collection_name(user_id: int, name: str):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE users SET collection_name=%s WHERE user_id=%s", (name, int(user_id)))


def get_collection_name(user_id: int) -> str:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT collection_name FROM users WHERE user_id=%s", (int(user_id),))
        row = cur.fetchone()
        return row["collection_name"] if row and row.get("collection_name") else "Minha Coleção"


def set_private_profile(user_id: int, is_private: bool):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE users SET private_profile=%s WHERE user_id=%s", (bool(is_private), int(user_id)))


def set_admin_photo(user_id: int, url: str):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE users SET admin_photo=%s WHERE user_id=%s", (url, int(user_id)))


def get_admin_photo_db(user_id: int) -> Optional[str]:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT admin_photo FROM users WHERE user_id=%s", (int(user_id),))
        row = cur.fetchone()
        return row["admin_photo"] if row and row.get("admin_photo") else None


# ================================
# LEVEL / COMMANDS (atômico)
# ================================
def inc_commands_and_get_levelup(user_id: int, comandos_por_nivel: int) -> Tuple[int, int, bool]:
    """
    Incrementa commands e calcula level atomico no DB.
    Retorna (commands, level, levelup).
    """
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            UPDATE users
            SET commands = COALESCE(commands,0) + 1
            WHERE user_id=%s
            RETURNING COALESCE(commands,0) AS commands, COALESCE(level,1) AS level
        """, (int(user_id),))
        row = cur.fetchone()
        if not row:
            return (0, 1, False)

        commands = int(row["commands"])
        old_level = int(row["level"] or 1)
        new_level = (commands // int(comandos_por_nivel)) + 1

        levelup = False
        if new_level > old_level:
            cur.execute("UPDATE users SET level=%s WHERE user_id=%s", (int(new_level), int(user_id)))
            levelup = True

        return (commands, new_level if levelup else old_level, levelup)


# ================================
# CARD: imagem global por personagem
# ================================
def set_global_character_image(character_id: int, image_url: str, updated_by: Optional[int] = None):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO character_images (character_id, image_url, updated_at, updated_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (character_id) DO UPDATE SET
                image_url = EXCLUDED.image_url,
                updated_at = EXCLUDED.updated_at,
                updated_by = EXCLUDED.updated_by
        """, (int(character_id), image_url, _now_ts(), updated_by))


def get_global_character_image(character_id: int) -> Optional[str]:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT image_url FROM character_images WHERE character_id=%s", (int(character_id),))
        row = cur.fetchone()
        return row["image_url"] if row and row.get("image_url") else None


def delete_global_character_image(character_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("DELETE FROM character_images WHERE character_id=%s", (int(character_id),))


# ================================
# Ban character
# ================================
def ban_character(character_id: int, reason: Optional[str] = None, created_by: Optional[int] = None):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO banned_characters (character_id, reason, created_at, created_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (character_id) DO UPDATE SET
                reason=EXCLUDED.reason,
                created_at=EXCLUDED.created_at,
                created_by=EXCLUDED.created_by
        """, (int(character_id), reason, _now_ts(), created_by))


def unban_character(character_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("DELETE FROM banned_characters WHERE character_id=%s", (int(character_id),))


def is_banned_character(character_id: int) -> bool:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT 1 FROM banned_characters WHERE character_id=%s", (int(character_id),))
        return cur.fetchone() is not None


# ================================
# COLEÇÃO
# ================================
def count_collection(user_id: int) -> int:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (int(user_id),))
        return int(cur.fetchone()["c"])


def get_collection_page(user_id: int, page: int, per_page: int):
    offset = (int(page) - 1) * int(per_page)

    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (int(user_id),))
        total = int(cur.fetchone()["c"])
        total_pages = (total - 1) // int(per_page) + 1 if total else 1

        cur.execute("""
            SELECT character_id, character_name
            FROM user_collection
            WHERE user_id=%s
            ORDER BY character_id ASC
            LIMIT %s OFFSET %s
        """, (int(user_id), int(per_page), int(offset)))

        itens = [(int(r["character_id"]), r["character_name"]) for r in (cur.fetchall() or [])]
        return itens, total, total_pages


def user_has_character(user_id: int, char_id: int) -> bool:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))
        return cur.fetchone() is not None


def add_character_to_collection(user_id: int, char_id: int, name: str, image: str, anime_title: Optional[str] = None):
    """
    Upsert atômico: se existir soma quantity; se não existir cria.
    """
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
            VALUES (%s, %s, %s, %s, %s, 1)
            ON CONFLICT (user_id, character_id) DO UPDATE SET
                quantity = user_collection.quantity + 1,
                character_name = EXCLUDED.character_name,
                image = COALESCE(EXCLUDED.image, user_collection.image),
                anime_title = COALESCE(EXCLUDED.anime_title, user_collection.anime_title)
        """, (int(user_id), int(char_id), name, image, anime_title))


def get_collection_character_full(user_id: int, char_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            SELECT character_id, character_name, image, custom_image, anime_title, quantity
            FROM user_collection
            WHERE user_id=%s AND character_id=%s
            LIMIT 1
        """, (int(user_id), int(char_id)))
        return cur.fetchone()


def get_collection_character(user_id: int, char_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            SELECT character_id, character_name, image
            FROM user_collection
            WHERE user_id=%s AND character_id=%s
            LIMIT 1
        """, (int(user_id), int(char_id)))
        return cur.fetchone()


def remove_one_from_collection(user_id: int, char_id: int) -> bool:
    """
    Remove 1 unidade ATÔMICA.
    - Se quantity>1, decrementa.
    - Se quantity=1, deleta.
    """
    with _get_conn_cursor() as (conn, cur):
        # tenta decrementar (q > 1)
        cur.execute("""
            UPDATE user_collection
            SET quantity = quantity - 1
            WHERE user_id=%s AND character_id=%s AND quantity > 1
            RETURNING character_id
        """, (int(user_id), int(char_id)))
        if cur.fetchone():
            return True

        # tenta deletar (q = 1)
        cur.execute("""
            DELETE FROM user_collection
            WHERE user_id=%s AND character_id=%s AND quantity = 1
            RETURNING character_id
        """, (int(user_id), int(char_id)))
        return cur.fetchone() is not None


# ================================
# FAVORITO
# ================================
def set_favorite_from_collection(user_id: int, char_name: str, image: str):
    with _get_conn_cursor() as (conn, cur):
        cur.execute(
            "UPDATE users SET fav_name=%s, fav_image=%s WHERE user_id=%s",
            (char_name, image, int(user_id))
        )


def clear_favorite(user_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE users SET fav_name=NULL, fav_image=NULL WHERE user_id=%s", (int(user_id),))


# ================================
# LOJA: extra_dado
# ================================
def add_extra_dado(user_id: int, amount: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE users SET extra_dado = COALESCE(extra_dado,0) + %s WHERE user_id=%s", (int(amount), int(user_id)))


def get_extra_dado(user_id: int) -> int:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT COALESCE(extra_dado,0) AS x FROM users WHERE user_id=%s", (int(user_id),))
        row = cur.fetchone()
        return int(row["x"] if row else 0)


def consume_extra_dado(user_id: int) -> bool:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            UPDATE users
            SET extra_dado = extra_dado - 1
            WHERE user_id=%s AND COALESCE(extra_dado,0) > 0
            RETURNING user_id
        """, (int(user_id),))
        return cur.fetchone() is not None


# ================================
# DADO NOVO: estado saldo/slot
# ================================
def get_dado_state(user_id: int) -> Optional[Dict[str, int]]:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT dado_balance, dado_slot FROM users WHERE user_id=%s", (int(user_id),))
        row = cur.fetchone()
        if not row:
            return None
        return {"b": int(row.get("dado_balance") or 0), "s": int(row.get("dado_slot") or -1)}


def set_dado_state(user_id: int, balance: int, slot: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE users SET dado_balance=%s, dado_slot=%s WHERE user_id=%s", (int(balance), int(slot), int(user_id)))


def inc_dado_balance(user_id: int, amount: int, max_balance: int = 18):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            UPDATE users
            SET dado_balance = LEAST(%s, COALESCE(dado_balance,0) + %s)
            WHERE user_id=%s
        """, (int(max_balance), int(amount), int(user_id)))


# ================================
# TOP CACHE (1x/dia)
# ================================
def top_cache_last_updated() -> int:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT COALESCE(MAX(updated_at),0) AS t FROM top_anime_cache")
        row = cur.fetchone()
        return int(row["t"] if row else 0)


def replace_top_anime_cache(items: List[Dict[str, Any]]):
    now = _now_ts()
    with _get_conn_cursor() as (conn, cur):
        cur.execute("TRUNCATE top_anime_cache")
        for it in items:
            cur.execute("""
                INSERT INTO top_anime_cache (anime_id, title, rank, updated_at)
                VALUES (%s, %s, %s, %s)
            """, (int(it["anime_id"]), str(it["title"]), int(it["rank"]), int(now)))


def get_top_anime_list(limit: int = 500) -> List[Dict[str, Any]]:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            SELECT anime_id, title, rank
            FROM top_anime_cache
            ORDER BY rank ASC
            LIMIT %s
        """, (int(limit),))
        return cur.fetchall() or []


# ================================
# DICE ROLLS
# ================================
def create_dice_roll(user_id: int, dice_value: int, options_json: str) -> int:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO dice_rolls (user_id, dice_value, options_json, status, created_at)
            VALUES (%s, %s, %s, 'pending', %s)
            RETURNING roll_id
        """, (int(user_id), int(dice_value), options_json, _now_ts()))
        return int(cur.fetchone()["roll_id"])


def get_dice_roll(roll_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT * FROM dice_rolls WHERE roll_id=%s", (int(roll_id),))
        return cur.fetchone()


def try_set_dice_roll_status(roll_id: int, from_status: str, to_status: str) -> bool:
    """
    Transição atômica de status, evita duplo clique.
    """
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            UPDATE dice_rolls
            SET status=%s
            WHERE roll_id=%s AND status=%s
            RETURNING roll_id
        """, (str(to_status), int(roll_id), str(from_status)))
        return cur.fetchone() is not None


def set_dice_roll_status(roll_id: int, status: str):
    # mantém compat
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE dice_rolls SET status=%s WHERE roll_id=%s", (str(status), int(roll_id)))


# ================================
# TROCAS
# ================================
def create_trade(from_user: int, to_user: int, from_char: int, to_char: int) -> int:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO trades (from_user, to_user, from_character_id, to_character_id, status, created_at)
            VALUES (%s, %s, %s, %s, 'pendente', %s)
            RETURNING trade_id
        """, (int(from_user), int(to_user), int(from_char), int(to_char), _now_ts()))
        row = cur.fetchone()
        return int(row["trade_id"]) if row and row.get("trade_id") is not None else 0


def get_trade_by_id(trade_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT * FROM trades WHERE trade_id=%s", (int(trade_id),))
        return cur.fetchone()


def get_latest_pending_trade_for_to_user(to_user: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            SELECT trade_id, from_user, from_character_id, to_character_id
            FROM trades
            WHERE to_user=%s AND status='pendente'
            ORDER BY trade_id DESC
            LIMIT 1
        """, (int(to_user),))
        row = cur.fetchone()
        if not row:
            return None
        return (int(row["trade_id"]), int(row["from_user"]), int(row["from_character_id"]), int(row["to_character_id"]))


def mark_trade_status(trade_id: int, status: str):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE trades SET status=%s WHERE trade_id=%s", (str(status), int(trade_id)))


def _move_one_unit(cur, from_user: int, to_user: int, char_id: int) -> bool:
    """
    Move 1 unidade do personagem entre usuários, respeitando quantity.
    Retorna False se o from_user não tiver.
    """
    # trava a linha do dono (se existir)
    cur.execute("""
        SELECT quantity, character_name, image, anime_title
        FROM user_collection
        WHERE user_id=%s AND character_id=%s
        FOR UPDATE
    """, (int(from_user), int(char_id)))
    row = cur.fetchone()
    if not row:
        return False

    qty = int(row.get("quantity") or 0)
    if qty <= 0:
        return False

    # decrementa/remover do from_user
    if qty > 1:
        cur.execute("""
            UPDATE user_collection
            SET quantity = quantity - 1
            WHERE user_id=%s AND character_id=%s
        """, (int(from_user), int(char_id)))
    else:
        cur.execute("""
            DELETE FROM user_collection
            WHERE user_id=%s AND character_id=%s
        """, (int(from_user), int(char_id)))

    # adiciona ao to_user (upsert soma)
    cur.execute("""
        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
        VALUES (%s, %s, %s, %s, %s, 1)
        ON CONFLICT (user_id, character_id) DO UPDATE SET
            quantity = user_collection.quantity + 1
    """, (int(to_user), int(char_id), row["character_name"], row.get("image"), row.get("anime_title")))

    return True


def swap_trade_execute(trade_id: int, from_user: int, to_user: int, from_char: int, to_char: int) -> bool:
    """
    Troca ATÔMICA + segura:
    - trava trade row
    - só executa se status='pendente'
    - move 1 unidade de cada lado (respeita quantity)
    - atualiza status pra 'aceita' se ok; 'falhou' se não
    """
    with _get_conn_cursor() as (conn, cur):
        # trava trade
        cur.execute("SELECT * FROM trades WHERE trade_id=%s FOR UPDATE", (int(trade_id),))
        tr = cur.fetchone()
        if not tr:
            return False
        if tr.get("status") != "pendente":
            return False

        # valida participantes pra evitar callback errado
        if int(tr["from_user"]) != int(from_user) or int(tr["to_user"]) != int(to_user):
            return False
        if int(tr["from_character_id"]) != int(from_char) or int(tr["to_character_id"]) != int(to_char):
            return False

        # move 1 unidade de cada lado
        a_ok = _move_one_unit(cur, int(from_user), int(to_user), int(from_char))
        b_ok = _move_one_unit(cur, int(to_user), int(from_user), int(to_char))

        if not a_ok or not b_ok:
            cur.execute("UPDATE trades SET status='falhou' WHERE trade_id=%s", (int(trade_id),))
            return False

        cur.execute("UPDATE trades SET status='aceita' WHERE trade_id=%s", (int(trade_id),))
        return True


# ================================
# BATALHAS
# ================================
def upsert_battle(chat_id: int, p1_id: int, p2_id: int, p1_name: str, p2_name: str,
                  player1_char=None, player2_char=None, player1_hp=None, player2_hp=None, vez=None):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO battles (chat_id, player1_id, player2_id, player1_name, player2_name,
                                 player1_char, player2_char, player1_hp, player2_hp, vez)
            VALUES (%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,100),COALESCE(%s,100),COALESCE(%s,0))
            ON CONFLICT (chat_id) DO UPDATE SET
                player1_id=EXCLUDED.player1_id,
                player2_id=EXCLUDED.player2_id,
                player1_name=EXCLUDED.player1_name,
                player2_name=EXCLUDED.player2_name,
                player1_char=COALESCE(EXCLUDED.player1_char, battles.player1_char),
                player2_char=COALESCE(EXCLUDED.player2_char, battles.player2_char),
                player1_hp=COALESCE(EXCLUDED.player1_hp, battles.player1_hp),
                player2_hp=COALESCE(EXCLUDED.player2_hp, battles.player2_hp),
                vez=COALESCE(EXCLUDED.vez, battles.vez)
        """, (int(chat_id), int(p1_id), int(p2_id), p1_name, p2_name, player1_char, player2_char, player1_hp, player2_hp, vez))


def get_battle(chat_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT * FROM battles WHERE chat_id=%s", (int(chat_id),))
        return cur.fetchone()


def delete_battle(chat_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("DELETE FROM battles WHERE chat_id=%s", (int(chat_id),))


def battle_set_char(chat_id: int, user_id: int, char_value: str):
    battle = get_battle(chat_id)
    if not battle:
        return
    with _get_conn_cursor() as (conn, cur):
        if int(battle["player1_id"]) == int(user_id):
            cur.execute("UPDATE battles SET player1_char=%s WHERE chat_id=%s", (char_value, int(chat_id)))
        elif int(battle["player2_id"]) == int(user_id):
            cur.execute("UPDATE battles SET player2_char=%s WHERE chat_id=%s", (char_value, int(chat_id)))


def battle_set_turn(chat_id: int, vez: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("UPDATE battles SET vez=%s WHERE chat_id=%s", (int(vez), int(chat_id)))


def battle_damage(chat_id: int, target: str, damage: int):
    with _get_conn_cursor() as (conn, cur):
        if target == "p1":
            cur.execute("UPDATE battles SET player1_hp = GREATEST(player1_hp - %s, 0) WHERE chat_id=%s", (int(damage), int(chat_id)))
        else:
            cur.execute("UPDATE battles SET player2_hp = GREATEST(player2_hp - %s, 0) WHERE chat_id=%s", (int(damage), int(chat_id)))


# ================================
# SHOP (sale table) — mantém compat
# ================================
def shop_create_sale(user_id: int, char_id: int) -> int:
    with _get_conn_cursor() as (conn, cur):
        cur.execute("""
            INSERT INTO shop_sales (user_id, character_id, created_at)
            VALUES (%s, %s, %s)
            RETURNING sale_id
        """, (int(user_id), int(char_id), _now_ts()))
        return int(cur.fetchone()["sale_id"])


def shop_get_sale(sale_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT user_id, character_id FROM shop_sales WHERE sale_id=%s", (int(sale_id),))
        row = cur.fetchone()
        if not row:
            return None
        return (int(row["user_id"]), int(row["character_id"]))


def shop_delete_sale(sale_id: int):
    with _get_conn_cursor() as (conn, cur):
        cur.execute("DELETE FROM shop_sales WHERE sale_id=%s", (int(sale_id),))


def shop_list_user_chars(user_id: int, page: int, per_page: int):
    offset = (int(page) - 1) * int(per_page)
    with _get_conn_cursor() as (conn, cur):
        cur.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (int(user_id),))
        total = int(cur.fetchone()["c"])
        total_pages = (total - 1) // int(per_page) + 1 if total else 1

        cur.execute("""
            SELECT character_id, character_name
            FROM user_collection
            WHERE user_id=%s
            ORDER BY character_id ASC
            LIMIT %s OFFSET %s
        """, (int(user_id), int(per_page), int(offset)))
        rows = cur.fetchall() or []
        chars = [(int(r["character_id"]), r["character_name"]) for r in rows]
        return chars, total, total_pages
