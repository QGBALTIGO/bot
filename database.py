# ================================
# database.py — Postgres (Railway) — revisado (pool + transações seguras)
# ================================

import os
import time
from contextlib import contextmanager
from typing import Optional, Tuple, List

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrado. No Railway, crie a variável DATABASE_URL com valor ${{Postgres.DATABASE_URL}}"
    )

# Pool (thread-safe). Evita compartilhar cursor/conexão globais entre updates concorrentes.
_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
_pool: ThreadedConnectionPool = ThreadedConnectionPool(
    _POOL_MIN, _POOL_MAX, DATABASE_URL, cursor_factory=RealDictCursor
)

# Mantidos apenas por compatibilidade (não use diretamente).
db = None
cursor = None


@contextmanager
def get_conn():
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor(commit: bool = False):
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def init_db():
    with get_cursor(commit=True) as cur:
        # USERS
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            nick TEXT,
            collection_name TEXT,
            fav_name TEXT,
            fav_image TEXT,
            coins INT DEFAULT 0,
            commands INT DEFAULT 0,
            level INT DEFAULT 1,
            xp INT DEFAULT 0,
            last_dado BIGINT DEFAULT 0,
            last_pedido BIGINT DEFAULT 0,
            private_profile BOOLEAN DEFAULT FALSE
        );
        """
        )

        # COLEÇÃO (quantity >= 1)
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS user_collection (
            user_id BIGINT NOT NULL,
            character_id INT NOT NULL,
            character_name TEXT NOT NULL,
            image TEXT NOT NULL,
            quantity INT NOT NULL DEFAULT 1,
            PRIMARY KEY (user_id, character_id)
        );
        """
        )

        # TROCAS
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS trades (
            trade_id SERIAL PRIMARY KEY,
            from_user BIGINT NOT NULL,
            to_user BIGINT NOT NULL,
            from_character_id INT NOT NULL,
            to_character_id INT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente'
        );
        """
        )

        # BATALHAS
        cur.execute(
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

        # LOJA (venda pendente)
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS shop_sales (
            sale_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            character_id INT NOT NULL,
            created_at BIGINT NOT NULL
        );
        """
        )

        # Constraints & índices (idempotentes)
        cur.execute(
            "ALTER TABLE user_collection ADD CONSTRAINT IF NOT EXISTS user_collection_quantity_check CHECK (quantity >= 1);"
        )
        cur.execute(
            "ALTER TABLE trades ADD CONSTRAINT IF NOT EXISTS trades_status_check CHECK (status IN ('pendente','aceita','recusada','cancelada'));"
        )

        # Nick único (parcial, ignora NULL)
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS users_nick_unique_idx ON users (nick) WHERE nick IS NOT NULL;"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS trades_to_status_id_idx ON trades (to_user, status, trade_id DESC);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS shop_sales_created_at_idx ON shop_sales (created_at);"
        )


# ---------------- USERS ----------------
def ensure_user_row(user_id: int, default_name: str):
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT 1 FROM users WHERE user_id=%s", (user_id,))
        if cur.fetchone():
            return
        cur.execute(
            "INSERT INTO users (user_id, nick, collection_name) VALUES (%s, %s, %s)",
            (user_id, default_name, "Minha Coleção"),
        )


def get_user_row(user_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        return cur.fetchone()


def get_user_by_nick(nick: str):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE LOWER(nick)=LOWER(%s) LIMIT 1", (nick,))
        return cur.fetchone()


def set_user_nick(user_id: int, nick: str):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET nick=%s WHERE user_id=%s", (nick, user_id))


def add_coin(user_id: int, amount: int):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE users SET coins=COALESCE(coins,0)+%s WHERE user_id=%s",
            (amount, user_id),
        )


def set_collection_name(user_id: int, name: str):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET collection_name=%s WHERE user_id=%s", (name, user_id))


def get_collection_name(user_id: int) -> str:
    with get_cursor() as cur:
        cur.execute("SELECT collection_name FROM users WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
        return row["collection_name"] if row and row["collection_name"] else "Minha Coleção"


def update_commands_and_level(user_id: int, commands: int, level: int):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE users SET commands=%s, level=%s WHERE user_id=%s",
            (commands, level, user_id),
        )


def update_commands_only(user_id: int, commands: int):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET commands=%s WHERE user_id=%s", (commands, user_id))


def set_last_dado(user_id: int, ts: int):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET last_dado=%s WHERE user_id=%s", (ts, user_id))


def set_last_pedido(user_id: int, ts: int):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET last_pedido=%s WHERE user_id=%s", (ts, user_id))


def set_favorite(user_id: int, fav_name: str, fav_image: str):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE users SET fav_name=%s, fav_image=%s WHERE user_id=%s",
            (fav_name, fav_image, user_id),
        )


def clear_favorite(user_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET fav_name=NULL, fav_image=NULL WHERE user_id=%s", (user_id,))


def set_private_profile(user_id: int, is_private: bool):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET private_profile=%s WHERE user_id=%s", (is_private, user_id))


# ---------------- COLEÇÃO ----------------
def count_collection(user_id: int) -> int:
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (user_id,))
        return int(cur.fetchone()["c"])


def get_collection_page(user_id: int, page: int, per_page: int):
    offset = (page - 1) * per_page
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT character_id, character_name, image, quantity
            FROM user_collection
            WHERE user_id=%s
            ORDER BY character_id ASC
            LIMIT %s OFFSET %s
            """,
            (user_id, per_page, offset),
        )
        return cur.fetchall() or []


def user_has_character(user_id: int, char_id: int) -> bool:
    with get_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s",
            (user_id, char_id),
        )
        return cur.fetchone() is not None


def add_character_to_collection(user_id: int, char_id: int, name: str, image: str):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO user_collection (user_id, character_id, character_name, image, quantity)
            VALUES (%s, %s, %s, %s, 1)
            ON CONFLICT (user_id, character_id) DO UPDATE SET
                quantity = user_collection.quantity + 1,
                character_name = EXCLUDED.character_name,
                image = EXCLUDED.image
            """,
            (user_id, char_id, name, image),
        )


def remove_one_from_collection(user_id: int, char_id: int) -> bool:
    """Remove 1 unidade do personagem (deleta linha se quantity chegar a 0)."""
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT quantity FROM user_collection WHERE user_id=%s AND character_id=%s FOR UPDATE",
                (user_id, char_id),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False
            q = int(row["quantity"])
            if q <= 1:
                cur.execute(
                    "DELETE FROM user_collection WHERE user_id=%s AND character_id=%s",
                    (user_id, char_id),
                )
            else:
                cur.execute(
                    "UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s",
                    (user_id, char_id),
                )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


# ---------------- TROCAS ----------------
def create_trade(from_user: int, to_user: int, from_char: int, to_char: int):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO trades (from_user, to_user, from_character_id, to_character_id, status)
            VALUES (%s, %s, %s, %s, 'pendente')
            """,
            (from_user, to_user, from_char, to_char),
        )


def get_latest_pending_trade_for_to_user(to_user: int):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT trade_id, from_user, from_character_id, to_character_id
            FROM trades
            WHERE to_user=%s AND status='pendente'
            ORDER BY trade_id DESC
            LIMIT 1
            """,
            (to_user,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return (
            int(row["trade_id"]),
            int(row["from_user"]),
            int(row["from_character_id"]),
            int(row["to_character_id"]),
        )


def mark_trade_status(trade_id: int, status: str):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE trades SET status=%s WHERE trade_id=%s", (status, trade_id))


def swap_trade_execute(trade_id: int, from_user: int, to_user: int, from_char: int, to_char: int) -> bool:
    """
    Executa a troca transferindo 1 unidade de cada personagem (com merge de quantity).
    Retorna False se algum dos lados já não tiver o personagem no momento da execução.
    """
    if from_char == to_char:
        with get_cursor(commit=True) as cur:
            cur.execute("UPDATE trades SET status='aceita' WHERE trade_id=%s", (trade_id,))
        return True

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT character_name, image, quantity FROM user_collection WHERE user_id=%s AND character_id=%s FOR UPDATE",
                (from_user, from_char),
            )
            row_a = cur.fetchone()
            cur.execute(
                "SELECT character_name, image, quantity FROM user_collection WHERE user_id=%s AND character_id=%s FOR UPDATE",
                (to_user, to_char),
            )
            row_b = cur.fetchone()

            if not row_a or not row_b:
                conn.rollback()
                return False

            a_name, a_img, a_q = row_a["character_name"], row_a["image"], int(row_a["quantity"])
            b_name, b_img, b_q = row_b["character_name"], row_b["image"], int(row_b["quantity"])

            # decrementa A
            if a_q <= 1:
                cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (from_user, from_char))
            else:
                cur.execute(
                    "UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s",
                    (from_user, from_char),
                )

            # decrementa B
            if b_q <= 1:
                cur.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (to_user, to_char))
            else:
                cur.execute(
                    "UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s",
                    (to_user, to_char),
                )

            # incrementa destino
            cur.execute(
                """
                INSERT INTO user_collection (user_id, character_id, character_name, image, quantity)
                VALUES (%s, %s, %s, %s, 1)
                ON CONFLICT (user_id, character_id) DO UPDATE SET
                    quantity = user_collection.quantity + 1,
                    character_name = EXCLUDED.character_name,
                    image = EXCLUDED.image
                """,
                (to_user, from_char, a_name, a_img),
            )
            cur.execute(
                """
                INSERT INTO user_collection (user_id, character_id, character_name, image, quantity)
                VALUES (%s, %s, %s, %s, 1)
                ON CONFLICT (user_id, character_id) DO UPDATE SET
                    quantity = user_collection.quantity + 1,
                    character_name = EXCLUDED.character_name,
                    image = EXCLUDED.image
                """,
                (from_user, to_char, b_name, b_img),
            )

            cur.execute("UPDATE trades SET status='aceita' WHERE trade_id=%s", (trade_id,))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


# ---------------- LOJA ----------------
def shop_list_user_chars(user_id: int, page: int, per_page: int):
    offset = (page - 1) * per_page
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (user_id,))
        total = int(cur.fetchone()["c"])
        total_pages = (total - 1) // per_page + 1 if total else 1

        cur.execute(
            """
            SELECT character_id, character_name
            FROM user_collection
            WHERE user_id=%s
            ORDER BY character_id ASC
            LIMIT %s OFFSET %s
            """,
            (user_id, per_page, offset),
        )
        rows = cur.fetchall() or []
        chars = [(int(r["character_id"]), r["character_name"]) for r in rows]
        return chars, total, total_pages


def shop_create_sale(user_id: int, char_id: int) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO shop_sales (user_id, character_id, created_at)
            VALUES (%s, %s, %s)
            RETURNING sale_id
            """,
            (user_id, char_id, int(time.time())),
        )
        return int(cur.fetchone()["sale_id"])


def shop_get_sale(sale_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT user_id, character_id FROM shop_sales WHERE sale_id=%s", (sale_id,))
        row = cur.fetchone()
        if not row:
            return None
        return (int(row["user_id"]), int(row["character_id"]))


def shop_delete_sale(sale_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM shop_sales WHERE sale_id=%s", (sale_id,))


def shop_cleanup_sales(max_age_seconds: int = 86400):
    cutoff = int(time.time()) - int(max_age_seconds)
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM shop_sales WHERE created_at < %s", (cutoff,))


# ---------------- BATALHAS ----------------
def upsert_battle(
    chat_id: int,
    p1_id: int,
    p2_id: int,
    p1_name: str,
    p2_name: str,
    player1_char=None,
    player2_char=None,
    player1_hp=None,
    player2_hp=None,
    vez=None,
):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
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
            """,
            (chat_id, p1_id, p2_id, p1_name, p2_name, player1_char, player2_char, player1_hp, player2_hp, vez),
        )


def get_battle(chat_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM battles WHERE chat_id=%s", (chat_id,))
        return cur.fetchone()


def delete_battle(chat_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM battles WHERE chat_id=%s", (chat_id,))


def battle_set_char(chat_id: int, user_id: int, char_value: str):
    battle = get_battle(chat_id)
    if not battle:
        return
    with get_cursor(commit=True) as cur:
        if int(battle["player1_id"]) == int(user_id):
            cur.execute("UPDATE battles SET player1_char=%s WHERE chat_id=%s", (char_value, chat_id))
        elif int(battle["player2_id"]) == int(user_id):
            cur.execute("UPDATE battles SET player2_char=%s WHERE chat_id=%s", (char_value, chat_id))


def battle_set_turn(chat_id: int, vez: int):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE battles SET vez=%s WHERE chat_id=%s", (vez, chat_id))


def battle_damage(chat_id: int, target: str, damage: int):
    with get_cursor(commit=True) as cur:
        if target == "p1":
            cur.execute(
                "UPDATE battles SET player1_hp = GREATEST(player1_hp - %s, 0) WHERE chat_id=%s",
                (damage, chat_id),
            )
        else:
            cur.execute(
                "UPDATE battles SET player2_hp = GREATEST(player2_hp - %s, 0) WHERE chat_id=%s",
                (damage, chat_id),
            )
