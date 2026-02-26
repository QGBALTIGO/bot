# ================================
# database.py — Postgres (Railway)
# (ORGANIZADO + MIGRAÇÃO + DADO + GIROS SLOT + CACHE + DAILY + CONQUISTAS + RANKINGS + STATS)
# ================================

import os
import re
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, List, Any

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrado. No Railway, crie a variável DATABASE_URL com valor ${{Postgres.DATABASE_URL}}"
    )

# conexão
db = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
db.autocommit = False
cursor = db.cursor()


# ================================
# helpers
# ================================
def _commit():
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise


def _rollback_silent():
    try:
        db.rollback()
    except Exception:
        pass


def _sanitize_nick(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^a-z0-9_\.]", "", s)
    return s or "user"


# ================================
# MIGRAÇÃO USERS
# ================================
def _ensure_columns_users():
    """
    Migra tabela users antiga sem quebrar.
    """
    # identidade / perfil
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS nick TEXT;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS collection_name TEXT;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_name TEXT;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_image TEXT;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS private_profile BOOLEAN DEFAULT FALSE;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_photo TEXT;""")

    # economia / progressão
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS coins INT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS commands INT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS level INT DEFAULT 1;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS xp INT DEFAULT 0;""")

    # cooldowns antigos
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS last_dado BIGINT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS last_pedido BIGINT DEFAULT 0;""")




    # DAILY
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily BIGINT DEFAULT 0;""")

    # DADO (saldo normal + slot 4h)
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_balance INT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_slot BIGINT DEFAULT -1;""")  # <-- FALTAVA

    # GIROS (extra_dado) + slot (01/04/07/10/13/16/19/22)
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_dado INT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_slot BIGINT DEFAULT -1;""")








def _dedupe_nicks_before_unique_index():
    """
    Evita falha ao criar índice UNIQUE por causa de nick duplicado.
    Renomeia duplicados automaticamente para nick_userid.
    """
    cursor.execute("""
        SELECT LOWER(nick) AS n, COUNT(*)::int AS c
        FROM users
        WHERE nick IS NOT NULL
        GROUP BY LOWER(nick)
        HAVING COUNT(*) > 1
    """)
    dups = cursor.fetchall() or []

    for r in dups:
        base = _sanitize_nick(r.get("n") or "user")

        cursor.execute("""
            SELECT user_id
            FROM users
            WHERE LOWER(nick)=LOWER(%s)
            ORDER BY user_id ASC
        """, (base,))
        ids = [int(x["user_id"]) for x in (cursor.fetchall() or [])]
        if len(ids) <= 1:
            continue

        # mantém o primeiro, muda os demais
        for uid in ids[1:]:
            cursor.execute("UPDATE users SET nick=%s WHERE user_id=%s", (f"{base}_{uid}", uid))



# ================================
# CONQUISTAS: TABELA
# ================================
def _ensure_achievements_table():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            user_id BIGINT NOT NULL,
            achievement_key TEXT NOT NULL,
            unlocked_at BIGINT NOT NULL,
            PRIMARY KEY (user_id, achievement_key)
        );
    """)
    _commit()

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS user_achievements_user_idx
        ON user_achievements (user_id);
    """)
    _commit()


# ================================
# INDEXES (anti quebra)
# ================================
def _try_create_indexes():
    """
    Cria índices e NÃO deixa uma transação abortada travar o resto.
    """
    # dedupe + unique nick (isolado)
    try:
        _dedupe_nicks_before_unique_index()
        _commit()
    except Exception as e:
        _rollback_silent()
        print("⚠️ Não consegui deduplicar nicks (ok continuar). Erro:", e)

    try:
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS users_nick_unique
            ON users (LOWER(nick))
            WHERE nick IS NOT NULL;
        """)
        _commit()
    except Exception as e:
        _rollback_silent()
        print("⚠️ Não consegui criar índice users_nick_unique (ok continuar). Erro:", e)

    # demais índices: 1 por 1 (NUNCA trava o resto)
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
            cursor.execute(sql)
            _commit()
        except Exception as e:
            _rollback_silent()
            print(f"⚠️ Não consegui criar índice {name} (ok continuar). Erro:", e)


# ================================
# INIT DB (com migração)
# ================================
def init_db():
    # USERS base
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY
        );
    """)
    _commit()

    # migração users
    _ensure_columns_users()
    _commit()

    # COLEÇÃO
    cursor.execute("""
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
    _commit()

    # TROCAS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id SERIAL PRIMARY KEY,
            from_user BIGINT,
            to_user BIGINT,
            from_character_id INT,
            to_character_id INT,
            status TEXT DEFAULT 'pendente'
        );
    """)
    _commit()

    # BATALHAS
    cursor.execute("""
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
    _commit()

    # LOJA
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_sales (
            sale_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            character_id INT,
            created_at BIGINT
        );
    """)
    _commit()

    # imagens globais
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS character_images (
            character_id INT PRIMARY KEY,
            image_url TEXT NOT NULL,
            updated_at BIGINT NOT NULL,
            updated_by BIGINT
        );
    """)
    _commit()

    # ban
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banned_characters (
            character_id INT PRIMARY KEY,
            reason TEXT,
            created_at BIGINT NOT NULL,
            created_by BIGINT
        );
    """)
    _commit()

    # cache top 500
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS top_anime_cache (
            anime_id INT PRIMARY KEY,
            title TEXT NOT NULL,
            rank INT NOT NULL,
            updated_at BIGINT NOT NULL
        );
    """)
    _commit()

    # rolls dado
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dice_rolls (
            roll_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            dice_value INT NOT NULL,
            options_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at BIGINT NOT NULL
        );
    """)
    _commit()

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
    Nick é UNIQUE (lower). Se der conflito, cria fallback com _userid.
    """
    user_id = int(user_id)

    cursor.execute("SELECT 1 FROM users WHERE user_id=%s", (user_id,))
    if cursor.fetchone():
        return

    base = _sanitize_nick(default_name)


    candidates = [base, f"{base}_{user_id}", f"user_{user_id}"]

    for nick in candidates:
        try:
            cursor.execute("""
                INSERT INTO users (
                    user_id, nick, collection_name,
                    dado_balance, dado_slot,
                    extra_dado, extra_slot,
                    last_daily
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                nick,
                "Minha Coleção",
                int(new_user_dice or 0),
                -1,
                0,
                -1,
                0
            ))
            _commit()
            return
        except psycopg2.errors.UniqueViolation:
            _rollback_silent()
            continue
        except Exception:
            _rollback_silent()
            raise

    # fallback final
    nick = f"user_{user_id}"
    cursor.execute("""
        INSERT INTO users (
            user_id, nick, collection_name,
            dado_balance, dado_slot,
            extra_dado, extra_slot,
            last_daily
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (user_id, nick, "Minha Coleção", int(new_user_dice or 0), -1, 0, -1, 0))
    _commit()


def get_user_row(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (int(user_id),))
    return cursor.fetchone()


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
    cursor.execute("SELECT * FROM users WHERE LOWER(nick)=LOWER(%s) LIMIT 1", (str(nick),))
    return cursor.fetchone()


def set_user_nick(user_id: int, nick: str):
    cursor.execute("UPDATE users SET nick=%s WHERE user_id=%s", (_sanitize_nick(nick), int(user_id)))



    _commit()


def add_coin(user_id: int, amount: int):
    cursor.execute("UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s", (int(amount), int(user_id)))
    _commit()


def get_user_coins(user_id: int) -> int:
    cursor.execute("SELECT COALESCE(coins,0)::int AS c FROM users WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    return int(row["c"] if row else 0)


def try_spend_coins(user_id: int, cost: int) -> bool:
    cursor.execute("""
        UPDATE users
        SET coins = COALESCE(coins,0) - %s
        WHERE user_id=%s AND COALESCE(coins,0) >= %s
        RETURNING coins
    """, (int(cost), int(user_id), int(cost)))
    ok = cursor.fetchone() is not None
    _commit()
    return ok


def set_collection_name(user_id: int, name: str):
    cursor.execute("UPDATE users SET collection_name=%s WHERE user_id=%s", (str(name), int(user_id)))
    _commit()


def get_collection_name(user_id: int) -> str:
    cursor.execute("SELECT collection_name FROM users WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    return row["collection_name"] if row and row.get("collection_name") else "Minha Coleção"


def set_private_profile(user_id: int, is_private: bool):
    cursor.execute("UPDATE users SET private_profile=%s WHERE user_id=%s", (bool(is_private), int(user_id)))
    _commit()


def set_admin_photo(user_id: int, url: str):
    cursor.execute("UPDATE users SET admin_photo=%s WHERE user_id=%s", (str(url), int(user_id)))
    _commit()


def get_admin_photo_db(user_id: int) -> Optional[str]:
    cursor.execute("SELECT admin_photo FROM users WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    return row["admin_photo"] if row and row.get("admin_photo") else None


# ================================
# CARD: imagem global por personagem
# ================================
def set_global_character_image(character_id: int, image_url: str, updated_by: Optional[int] = None):
    cursor.execute("""
        INSERT INTO character_images (character_id, image_url, updated_at, updated_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (character_id) DO UPDATE SET
            image_url = EXCLUDED.image_url,
            updated_at = EXCLUDED.updated_at,
            updated_by = EXCLUDED.updated_by
    """, (int(character_id), str(image_url), int(time.time()), updated_by))
    _commit()


def get_global_character_image(character_id: int) -> Optional[str]:
    cursor.execute("SELECT image_url FROM character_images WHERE character_id=%s", (int(character_id),))
    row = cursor.fetchone()
    return row["image_url"] if row and row.get("image_url") else None


def delete_global_character_image(character_id: int):
    cursor.execute("DELETE FROM character_images WHERE character_id=%s", (int(character_id),))
    _commit()


# ================================
# Ban character
# ================================
def ban_character(character_id: int, reason: Optional[str] = None, created_by: Optional[int] = None):
    cursor.execute("""
        INSERT INTO banned_characters (character_id, reason, created_at, created_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (character_id) DO UPDATE SET
            reason=EXCLUDED.reason,
            created_at=EXCLUDED.created_at,
            created_by=EXCLUDED.created_by
    """, (int(character_id), reason, int(time.time()), created_by))
    _commit()


def unban_character(character_id: int):
    cursor.execute("DELETE FROM banned_characters WHERE character_id=%s", (int(character_id),))
    _commit()


def is_banned_character(character_id: int) -> bool:
    cursor.execute("SELECT 1 FROM banned_characters WHERE character_id=%s", (int(character_id),))
    return cursor.fetchone() is not None


# ================================
# COLEÇÃO
# ================================
def count_collection(user_id: int) -> int:
    cursor.execute("SELECT COUNT(*)::int AS c FROM user_collection WHERE user_id=%s", (int(user_id),))
    return int(cursor.fetchone()["c"])


def get_collection_page(user_id: int, page: int, per_page: int):
    offset = (page - 1) * per_page

    cursor.execute("SELECT COUNT(*)::int AS c FROM user_collection WHERE user_id=%s", (int(user_id),))
    total = int(cursor.fetchone()["c"])
    total_pages = (total - 1) // per_page + 1 if total else 1

    cursor.execute("""
        SELECT character_id, character_name
        FROM user_collection
        WHERE user_id=%s
        ORDER BY character_id ASC
        LIMIT %s OFFSET %s
    """, (int(user_id), int(per_page), int(offset)))
    itens = [(int(r["character_id"]), r["character_name"]) for r in cursor.fetchall()]
    return itens, total, total_pages


def user_has_character(user_id: int, char_id: int) -> bool:
    cursor.execute("SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))
    return cursor.fetchone() is not None


def add_character_to_collection(user_id: int, char_id: int, name: str, image: str, anime_title: Optional[str] = None):
    cursor.execute("SELECT quantity FROM user_collection WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))
    row = cursor.fetchone()
    if row:
        cursor.execute("""
            UPDATE user_collection
            SET quantity=quantity+1
            WHERE user_id=%s AND character_id=%s
        """, (int(user_id), int(char_id)))
    else:
        cursor.execute("""
            INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
            VALUES (%s, %s, %s, %s, %s, 1)
        """, (int(user_id), int(char_id), str(name), str(image), anime_title))
    _commit()


def get_collection_character_full(user_id: int, char_id: int):
    cursor.execute("""
        SELECT character_id, character_name, image, custom_image, anime_title, quantity
        FROM user_collection
        WHERE user_id=%s AND character_id=%s
        LIMIT 1
    """, (int(user_id), int(char_id)))
    return cursor.fetchone()


def get_collection_character(user_id: int, char_id: int):
    cursor.execute("""
        SELECT character_id, character_name, image
        FROM user_collection
        WHERE user_id=%s AND character_id=%s
        LIMIT 1
    """, (int(user_id), int(char_id)))
    return cursor.fetchone()


def remove_one_from_collection(user_id: int, char_id: int) -> bool:
    cursor.execute("SELECT quantity FROM user_collection WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))
    row = cursor.fetchone()
    if not row:
        return False

    q = int(row["quantity"] or 0)
    if q <= 1:
        cursor.execute("DELETE FROM user_collection WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))
    else:
        cursor.execute("""
            UPDATE user_collection
            SET quantity=quantity-1
            WHERE user_id=%s AND character_id=%s
        """, (int(user_id), int(char_id)))
    _commit()
    return True


# ================================
# FAVORITO
# ================================
def set_favorite_from_collection(user_id: int, char_name: str, image: str):
    cursor.execute(
        "UPDATE users SET fav_name=%s, fav_image=%s WHERE user_id=%s",
        (str(char_name), str(image), int(user_id))
    )
    _commit()


def clear_favorite(user_id: int):
    cursor.execute("UPDATE users SET fav_name=NULL, fav_image=NULL WHERE user_id=%s", (int(user_id),))
    _commit()


# ================================
# GIROS (extra_dado) + SLOT
# ================================





def get_extra_state(user_id: int) -> dict:
    cursor.execute(
        "SELECT COALESCE(extra_dado,0)::int AS x, COALESCE(extra_slot,-1)::bigint AS s FROM users WHERE user_id=%s",
        (int(user_id),)
    )
    row = cursor.fetchone() or {}
    return {"x": int(row.get("x") or 0), "s": int(row.get("s") or -1)}


def set_extra_state(user_id: int, extra: int, slot: int):
    cursor.execute(
        "UPDATE users SET extra_dado=%s, extra_slot=%s WHERE user_id=%s",
        (int(extra), int(slot), int(user_id))
    )
    _commit()


def consume_extra_dado(user_id: int) -> bool:
    cursor.execute("""
        UPDATE users
        SET extra_dado = COALESCE(extra_dado,0) - 1
        WHERE user_id=%s AND COALESCE(extra_dado,0) > 0
        RETURNING extra_dado
    """, (int(user_id),))
    ok = cursor.fetchone() is not None
    _commit()
    return ok


def add_extra_dado(user_id: int, amount: int):
    cursor.execute("UPDATE users SET extra_dado = COALESCE(extra_dado,0) + %s WHERE user_id=%s", (int(amount), int(user_id)))
    _commit()



# ================================
# DADO: estado saldo/slot
# ================================
def get_dado_state(user_id: int) -> Optional[Dict[str, int]]:
    cursor.execute("SELECT dado_balance, dado_slot FROM users WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    if not row:
        return None
    return {"b": int(row.get("dado_balance") or 0), "s": int(row.get("dado_slot") or -1)}


def set_dado_state(user_id: int, balance: int, slot: int):
    cursor.execute(
        "UPDATE users SET dado_balance=%s, dado_slot=%s WHERE user_id=%s",
        (int(balance), int(slot), int(user_id))
    )
    _commit()


def inc_dado_balance(user_id: int, amount: int, max_balance: int = 18):
    cursor.execute("SELECT COALESCE(dado_balance,0)::int AS b FROM users WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    b = int(row["b"] if row else 0)
    b2 = min(int(max_balance), b + int(amount))
    cursor.execute("UPDATE users SET dado_balance=%s WHERE user_id=%s", (int(b2), int(user_id)))
    _commit()


# ================================
# TOP CACHE
# ================================
def top_cache_last_updated() -> int:
    cursor.execute("SELECT COALESCE(MAX(updated_at),0)::bigint AS t FROM top_anime_cache")
    row = cursor.fetchone()
    return int(row["t"] if row else 0)


def replace_top_anime_cache(items: List[Dict[str, Any]]):
    now = int(time.time())
    cursor.execute("TRUNCATE top_anime_cache")
    for it in items:
        cursor.execute("""
            INSERT INTO top_anime_cache (anime_id, title, rank, updated_at)
            VALUES (%s, %s, %s, %s)
        """, (int(it["anime_id"]), str(it["title"]), int(it["rank"]), now))
    _commit()


def get_top_anime_list(limit: int = 500) -> List[Dict[str, Any]]:
    cursor.execute("""
        SELECT anime_id, title, rank
        FROM top_anime_cache
        ORDER BY rank ASC
        LIMIT %s
    """, (int(limit),))
    return cursor.fetchall() or []


# ================================
# DICE ROLLS
# ================================
def create_dice_roll(user_id: int, dice_value: int, options_json: str) -> int:
    cursor.execute("""
        INSERT INTO dice_rolls (user_id, dice_value, options_json, status, created_at)
        VALUES (%s, %s, %s, 'pending', %s)
        RETURNING roll_id
    """, (int(user_id), int(dice_value), str(options_json), int(time.time())))
    rid = int(cursor.fetchone()["roll_id"])
    _commit()
    return rid


def get_dice_roll(roll_id: int):
    cursor.execute("SELECT * FROM dice_rolls WHERE roll_id=%s", (int(roll_id),))
    return cursor.fetchone()


def set_dice_roll_status(roll_id: int, status: str):
    cursor.execute("UPDATE dice_rolls SET status=%s WHERE roll_id=%s", (str(status), int(roll_id)))
    _commit()


def try_set_dice_roll_status(roll_id: int, expected: str, new_status: str) -> bool:
    cursor.execute("""
        UPDATE dice_rolls
        SET status=%s
        WHERE roll_id=%s AND status=%s
        RETURNING roll_id
    """, (str(new_status), int(roll_id), str(expected)))
    ok = cursor.fetchone() is not None
    _commit()
    return ok


# ================================
# TROCAS
# ================================
def create_trade(from_user: int, to_user: int, from_char: int, to_char: int) -> int:
    cursor.execute("""
        INSERT INTO trades (from_user, to_user, from_character_id, to_character_id, status)
        VALUES (%s, %s, %s, %s, 'pendente')
        RETURNING trade_id
    """, (int(from_user), int(to_user), int(from_char), int(to_char)))
    row = cursor.fetchone()
    _commit()
    return int(row["trade_id"]) if row and row.get("trade_id") is not None else 0


def get_trade_by_id(trade_id: int):
    cursor.execute("SELECT * FROM trades WHERE trade_id=%s", (int(trade_id),))
    return cursor.fetchone()


def get_latest_pending_trade_for_to_user(to_user: int):
    cursor.execute("""
        SELECT trade_id, from_user, from_character_id, to_character_id
        FROM trades
        WHERE to_user=%s AND status='pendente'
        ORDER BY trade_id DESC
        LIMIT 1
    """, (int(to_user),))
    row = cursor.fetchone()
    if not row:
        return None
    return (int(row["trade_id"]), int(row["from_user"]), int(row["from_character_id"]), int(row["to_character_id"]))


def mark_trade_status(trade_id: int, status: str):
    cursor.execute("UPDATE trades SET status=%s WHERE trade_id=%s", (str(status), int(trade_id)))
    _commit()


def swap_trade_execute(trade_id: int, from_user: int, to_user: int, from_char: int, to_char: int):
    """
    Troca segura com lock. Retorna True/False.
    """
    try:
        cursor.execute("BEGIN")

        cursor.execute("SELECT status FROM trades WHERE trade_id=%s FOR UPDATE", (int(trade_id),))
        tr = cursor.fetchone()
        if not tr or tr.get("status") != "pendente":
            cursor.execute("ROLLBACK")
            return False

        cursor.execute("""
            SELECT 1 FROM user_collection
            WHERE user_id=%s AND character_id=%s
            FOR UPDATE
        """, (int(from_user), int(from_char)))
        a_ok = cursor.fetchone() is not None

        cursor.execute("""
            SELECT 1 FROM user_collection
            WHERE user_id=%s AND character_id=%s
            FOR UPDATE
        """, (int(to_user), int(to_char)))
        b_ok = cursor.fetchone() is not None

        if not a_ok or not b_ok:
            cursor.execute("UPDATE trades SET status='falhou' WHERE trade_id=%s", (int(trade_id),))
            cursor.execute("COMMIT")
            return False

        cursor.execute("""
            UPDATE user_collection
            SET user_id=%s
            WHERE user_id=%s AND character_id=%s
        """, (int(to_user), int(from_user), int(from_char)))

        cursor.execute("""
            UPDATE user_collection
            SET user_id=%s
            WHERE user_id=%s AND character_id=%s
        """, (int(from_user), int(to_user), int(to_char)))

        cursor.execute("UPDATE trades SET status='aceita' WHERE trade_id=%s", (int(trade_id),))
        cursor.execute("COMMIT")
        return True

    except Exception:
        try:
            cursor.execute("ROLLBACK")
        except Exception:
            pass
        raise


# ================================
# DAILY
# ================================
def claim_daily_reward(
    user_id: int,
    day_start_ts: int,
    coins_min: int = 1,
    coins_max: int = 3,
    giro_chance: float = 0.20
):
    import random
    try:
        cursor.execute("""
            UPDATE users
            SET last_daily=%s
            WHERE user_id=%s AND COALESCE(last_daily,0) < %s
            RETURNING user_id
        """, (int(day_start_ts), int(user_id), int(day_start_ts)))

        ok = cursor.fetchone() is not None
        if not ok:
            _commit()
            return None

        if random.random() < float(giro_chance):
            cursor.execute("""
                UPDATE users
                SET extra_dado = COALESCE(extra_dado,0) + 1
                WHERE user_id=%s
            """, (int(user_id),))
            _commit()
            return {"type": "giro", "amount": 1}

        amount = random.randint(int(coins_min), int(coins_max))
        cursor.execute("""
            UPDATE users
            SET coins = COALESCE(coins,0) + %s
            WHERE user_id=%s
        """, (int(amount), int(user_id)))
        _commit()
        return {"type": "coins", "amount": int(amount)}

    except Exception:
        _rollback_silent()
        raise


def list_pending_trades_for_user(to_user: int, limit: int = 5):
    cursor.execute("""
        SELECT trade_id, from_user, to_user, from_character_id, to_character_id, status
        FROM trades
        WHERE to_user=%s AND status='pendente'
        ORDER BY trade_id DESC
        LIMIT %s
    """, (int(to_user), int(limit)))
    return cursor.fetchall() or []


# ================================
# RANKINGS
# ================================
def get_top_by_level(limit: int = 10):
    cursor.execute("""
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
    """, (int(limit),))
    return cursor.fetchall() or []


def get_top_by_coins(limit: int = 10):
    cursor.execute("""
        SELECT user_id,
               COALESCE(nick, 'User') AS nick,
               COALESCE(coins, 0) AS coins,
               COALESCE(level, 1) AS level
        FROM users
        ORDER BY COALESCE(coins,0) DESC,
                 COALESCE(level,1) DESC,
                 user_id ASC
        LIMIT %s
    """, (int(limit),))
    return cursor.fetchall() or []


def get_top_by_collection(limit: int = 10):
    cursor.execute("""
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
    """, (int(limit),))
    return cursor.fetchall() or []


# ================================
# STATS / CONQUISTAS
# ================================
def get_collection_unique_count(user_id: int) -> int:
    cursor.execute("SELECT COUNT(*)::int AS c FROM user_collection WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    return int(row["c"] if row else 0)


def get_collection_total_quantity(user_id: int) -> int:
    cursor.execute("SELECT COALESCE(SUM(quantity),0)::int AS s FROM user_collection WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    return int(row["s"] if row else 0)


def get_dice_roll_counts(user_id: int) -> dict:
    cursor.execute("""
        SELECT
          COUNT(*)::int AS total,
          COALESCE(SUM((status='resolved')::int),0)::int AS resolved,
          COALESCE(SUM((status='expired')::int),0)::int AS expired,
          COALESCE(SUM((status='pending')::int),0)::int AS pending
        FROM dice_rolls
        WHERE user_id=%s
    """, (int(user_id),))
    r = cursor.fetchone() or {}
    return {
        "total": int(r.get("total") or 0),
        "resolved": int(r.get("resolved") or 0),
        "expired": int(r.get("expired") or 0),
        "pending": int(r.get("pending") or 0),
    }


def get_trade_counts(user_id: int) -> dict:
    cursor.execute("""
        SELECT
          COUNT(*)::int AS total,
          COALESCE(SUM((status='pendente')::int),0)::int AS pendente,
          COALESCE(SUM((status='aceita')::int),0)::int AS aceita,
          COALESCE(SUM((status='recusada')::int),0)::int AS recusada,
          COALESCE(SUM((status='falhou')::int),0)::int AS falhou
        FROM trades
        WHERE from_user=%s OR to_user=%s
    """, (int(user_id), int(user_id)))
    r = cursor.fetchone() or {}
    return {
        "total": int(r.get("total") or 0),
        "pendente": int(r.get("pendente") or 0),
        "aceita": int(r.get("aceita") or 0),
        "recusada": int(r.get("recusada") or 0),
        "falhou": int(r.get("falhou") or 0),
    }


def get_user_stats(user_id: int) -> dict:
    cursor.execute("""
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
    """, (int(user_id),))
    u = cursor.fetchone() or {}

    unique_count = get_collection_unique_count(user_id)
    total_qty = get_collection_total_quantity(user_id)
    dice = get_dice_roll_counts(user_id)
    trades = get_trade_counts(user_id)

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
        "collection_unique": int(unique_count),
        "collection_total_qty": int(total_qty),
        "dice": dice,
        "trades": trades,
    }


# ================================
# CONQUISTAS
# ================================
def list_user_achievement_keys(user_id: int) -> set[str]:
    cursor.execute("""
        SELECT achievement_key
        FROM user_achievements
        WHERE user_id=%s
    """, (int(user_id),))
    rows = cursor.fetchall() or []
    return {str(r["achievement_key"]) for r in rows if r.get("achievement_key")}


def count_user_achievements(user_id: int) -> int:
    cursor.execute("SELECT COUNT(*)::int AS c FROM user_achievements WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    return int(row["c"] if row else 0)


def grant_achievements_and_reward(user_id: int, new_keys: list[str], reward_extra_dado_per: int = 1) -> int:
    if not new_keys:
        return 0

    now = int(time.time())
    new_keys = [str(k) for k in new_keys if k]

    try:
        cursor.execute("BEGIN")

        inserted = 0
        for k in new_keys:
            cursor.execute("""
                INSERT INTO user_achievements (user_id, achievement_key, unlocked_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, achievement_key) DO NOTHING
            """, (int(user_id), k, now))
            inserted += int(cursor.rowcount or 0)

        if inserted > 0 and reward_extra_dado_per > 0:
            cursor.execute("""
                UPDATE users
                SET extra_dado = COALESCE(extra_dado,0) + %s
                WHERE user_id=%s
            """, (int(inserted * reward_extra_dado_per), int(user_id)))

        cursor.execute("COMMIT")
        return inserted

    except Exception:
        try:
            cursor.execute("ROLLBACK")
        except Exception:
            pass
        raise
