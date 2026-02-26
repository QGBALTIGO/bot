# ================================
# database.py — Postgres (Railway) (ORGANIZADO + MIGRAÇÃO + DEDUPE NICK + ÍNDICES SEGUROS)
# ================================

import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, List, Any, Tuple

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrado. No Railway, crie a variável DATABASE_URL com valor ${{Postgres.DATABASE_URL}}"
    )

db = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
cursor = db.cursor()


# ================================
# helpers
# ================================
def _commit():
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _ensure_columns_users():
    """
    Migra tabela users antiga sem quebrar.
    """
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS nick TEXT;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS collection_name TEXT;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_name TEXT;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS fav_image TEXT;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS coins INT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS commands INT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS level INT DEFAULT 1;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS xp INT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS last_dado BIGINT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS last_pedido BIGINT DEFAULT 0;""")

    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS private_profile BOOLEAN DEFAULT FALSE;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_photo TEXT;""")

    # DADO NOVO
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_balance INT DEFAULT 0;""")
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS dado_slot BIGINT DEFAULT -1;""")

    # extra dado
    cursor.execute("""ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_dado INT DEFAULT 0;""")


def _dedupe_nicks_before_unique():
    """
    Corrige nicks duplicados antes de criar índice UNIQUE (case-insensitive).
    Regras:
      - nick NULL/vazio => 'user_<user_id>'
      - duplicados => mantém o primeiro (menor user_id), renomeia demais para '<nick>_<user_id>'
    """
    # 1) normaliza nicks vazios
    cursor.execute("""
        UPDATE users
        SET nick = 'user_' || user_id::text
        WHERE nick IS NULL OR BTRIM(nick) = '';
    """)

    # 2) resolve duplicados (case-insensitive)
    cursor.execute("""
        WITH ranked AS (
            SELECT
                user_id,
                nick,
                ROW_NUMBER() OVER (PARTITION BY LOWER(nick) ORDER BY user_id ASC) AS rn
            FROM users
            WHERE nick IS NOT NULL AND BTRIM(nick) <> ''
        )
        UPDATE users u
        SET nick = LOWER(r.nick) || '_' || u.user_id::text
        FROM ranked r
        WHERE u.user_id = r.user_id
          AND r.rn > 1;
    """)


def _try_create_indexes():
    """
    Cria índices de forma resistente:
    - Deduplica nicks
    - Tenta criar índice UNIQUE
    - Cria os demais índices um a um com rollback por falha
    """
    # garante que não está em transação abortada
    try:
        db.rollback()
    except Exception:
        pass

    # 1) dedupe nicks antes do unique
    try:
        _dedupe_nicks_before_unique()
        _commit()
    except Exception as e:
        db.rollback()
        print("⚠️ Não consegui deduplicar nicks antes do índice (ok continuar). Erro:", e)

    # 2) índice unique nick (não pode travar o bot)
    try:
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS users_nick_unique
            ON users (LOWER(nick))
            WHERE nick IS NOT NULL;
        """)
        _commit()
    except Exception as e:
        db.rollback()
        print("⚠️ Não consegui criar índice users_nick_unique (ok continuar). Erro:", e)

    # 3) demais índices — cada um isolado
    indexes = [
        ("user_collection_user_idx", "CREATE INDEX IF NOT EXISTS user_collection_user_idx ON user_collection (user_id);"),
        ("trades_to_user_idx", "CREATE INDEX IF NOT EXISTS trades_to_user_idx ON trades (to_user);"),
        ("shop_sales_user_idx", "CREATE INDEX IF NOT EXISTS shop_sales_user_idx ON shop_sales (user_id);"),
        ("top_anime_cache_rank_idx", "CREATE INDEX IF NOT EXISTS top_anime_cache_rank_idx ON top_anime_cache (rank);"),
        ("dice_rolls_user_idx", "CREATE INDEX IF NOT EXISTS dice_rolls_user_idx ON dice_rolls (user_id);"),
    ]

    for name, sql in indexes:
        try:
            cursor.execute(sql)
            _commit()
        except Exception as e:
            db.rollback()
            print(f"⚠️ Não consegui criar índice {name} (ok continuar). Erro:", e)


# ================================
# INIT DB (com migração)
# ================================
def init_db():
    # USERS (mínimo)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY
        );
    """)
    _commit()

    # MIGRA users antiga
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

    _try_create_indexes()


# ================================
# USERS
# ================================
def ensure_user_row(user_id: int, default_name: str, new_user_dice: int = 0):
    """
    Cria usuário se não existir.
    new_user_dice: saldo inicial (só aplica para novos de verdade).
    """
    cursor.execute("SELECT 1 FROM users WHERE user_id=%s", (user_id,))
    if cursor.fetchone():
        return

    nick = (default_name or "user").strip()
    if not nick:
        nick = "user"

    # evita criar vários "user" iguais — ajuda o índice UNIQUE
    base = nick.lower()
    if base == "user":
        base = f"user_{int(user_id)}"

    cursor.execute("""
        INSERT INTO users (
            user_id, nick, collection_name,
            dado_balance, dado_slot
        )
        VALUES (%s, %s, %s, %s, %s)
    """, (int(user_id), base, "Minha Coleção", int(new_user_dice or 0), -1))

    _commit()


def get_user_row(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (int(user_id),))
    return cursor.fetchone()


def get_user_by_nick(nick: str):
    cursor.execute("SELECT * FROM users WHERE LOWER(nick)=LOWER(%s) LIMIT 1", (nick,))
    return cursor.fetchone()


def set_user_nick(user_id: int, nick: str):
    cursor.execute("UPDATE users SET nick=%s WHERE user_id=%s", (nick, int(user_id)))
    _commit()


def add_coin(user_id: int, amount: int):
    cursor.execute("UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s", (int(amount), int(user_id)))
    _commit()


def get_user_coins(user_id: int) -> int:
    cursor.execute("SELECT COALESCE(coins,0) AS c FROM users WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    return int(row["c"] if row else 0)


def try_spend_coins(user_id: int, amount: int) -> bool:
    """
    Desconta coins somente se tiver saldo suficiente (atômico).
    """
    cursor.execute("""
        UPDATE users
        SET coins = COALESCE(coins,0) - %s
        WHERE user_id=%s AND COALESCE(coins,0) >= %s
        RETURNING user_id
    """, (int(amount), int(user_id), int(amount)))
    ok = cursor.fetchone() is not None
    _commit()
    return ok


def set_collection_name(user_id: int, name: str):
    cursor.execute("UPDATE users SET collection_name=%s WHERE user_id=%s", (name, int(user_id)))
    _commit()


def get_collection_name(user_id: int) -> str:
    cursor.execute("SELECT collection_name FROM users WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    return row["collection_name"] if row and row.get("collection_name") else "Minha Coleção"


def set_private_profile(user_id: int, is_private: bool):
    cursor.execute("UPDATE users SET private_profile=%s WHERE user_id=%s", (bool(is_private), int(user_id)))
    _commit()


def set_admin_photo(user_id: int, url: str):
    cursor.execute("UPDATE users SET admin_photo=%s WHERE user_id=%s", (url, int(user_id)))
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
    """, (int(character_id), image_url, int(time.time()), updated_by))
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
    cursor.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (int(user_id),))
    return int(cursor.fetchone()["c"])


def get_collection_page(user_id: int, page: int, per_page: int):
    offset = (int(page) - 1) * int(per_page)

    cursor.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (int(user_id),))
    total = int(cursor.fetchone()["c"])
    total_pages = (total - 1) // int(per_page) + 1 if total else 1

    cursor.execute("""
        SELECT character_id, character_name
        FROM user_collection
        WHERE user_id=%s
        ORDER BY character_id ASC
        LIMIT %s OFFSET %s
    """, (int(user_id), int(per_page), int(offset)))
    itens = [(int(r["character_id"]), r["character_name"]) for r in (cursor.fetchall() or [])]
    return itens, total, total_pages


def user_has_character(user_id: int, char_id: int) -> bool:
    cursor.execute("SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s", (int(user_id), int(char_id)))
    return cursor.fetchone() is not None


def add_character_to_collection(user_id: int, char_id: int, name: str, image: str, anime_title: Optional[str] = None):
    # UPSERT atômico (evita race condition)
    cursor.execute("""
        INSERT INTO user_collection (user_id, character_id, character_name, image, anime_title, quantity)
        VALUES (%s, %s, %s, %s, %s, 1)
        ON CONFLICT (user_id, character_id) DO UPDATE SET
            quantity = user_collection.quantity + 1,
            character_name = EXCLUDED.character_name,
            image = COALESCE(EXCLUDED.image, user_collection.image),
            anime_title = COALESCE(EXCLUDED.anime_title, user_collection.anime_title)
    """, (int(user_id), int(char_id), name, image, anime_title))
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
    """
    Remove 1 unidade ATÔMICO:
    - se quantity>1 decrementa
    - se quantity=1 apaga
    """
    # tenta decrementar
    cursor.execute("""
        UPDATE user_collection
        SET quantity = quantity - 1
        WHERE user_id=%s AND character_id=%s AND quantity > 1
        RETURNING character_id
    """, (int(user_id), int(char_id)))
    if cursor.fetchone():
        _commit()
        return True

    # tenta deletar
    cursor.execute("""
        DELETE FROM user_collection
        WHERE user_id=%s AND character_id=%s AND quantity = 1
        RETURNING character_id
    """, (int(user_id), int(char_id)))
    ok = cursor.fetchone() is not None
    _commit()
    return ok


# ================================
# FAVORITO
# ================================
def set_favorite_from_collection(user_id: int, char_name: str, image: str):
    cursor.execute(
        "UPDATE users SET fav_name=%s, fav_image=%s WHERE user_id=%s",
        (char_name, image, int(user_id))
    )
    _commit()


def clear_favorite(user_id: int):
    cursor.execute("UPDATE users SET fav_name=NULL, fav_image=NULL WHERE user_id=%s", (int(user_id),))
    _commit()


# ================================
# LOJA: extra_dado
# ================================
def add_extra_dado(user_id: int, amount: int):
    cursor.execute("UPDATE users SET extra_dado = COALESCE(extra_dado,0) + %s WHERE user_id=%s", (int(amount), int(user_id)))
    _commit()


def get_extra_dado(user_id: int) -> int:
    cursor.execute("SELECT COALESCE(extra_dado,0) AS x FROM users WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    return int(row["x"] if row else 0)


def consume_extra_dado(user_id: int) -> bool:
    cursor.execute("""
        UPDATE users
        SET extra_dado = extra_dado - 1
        WHERE user_id=%s AND COALESCE(extra_dado,0) > 0
        RETURNING user_id
    """, (int(user_id),))
    ok = cursor.fetchone() is not None
    _commit()
    return ok


# ================================
# DADO NOVO: estado saldo/slot
# ================================
def get_dado_state(user_id: int) -> Optional[Dict[str, int]]:
    cursor.execute("SELECT dado_balance, dado_slot FROM users WHERE user_id=%s", (int(user_id),))
    row = cursor.fetchone()
    if not row:
        return None
    return {"b": int(row.get("dado_balance") or 0), "s": int(row.get("dado_slot") or -1)}


def set_dado_state(user_id: int, balance: int, slot: int):
    cursor.execute("UPDATE users SET dado_balance=%s, dado_slot=%s WHERE user_id=%s", (int(balance), int(slot), int(user_id)))
    _commit()


def inc_dado_balance(user_id: int, amount: int, max_balance: int = 18):
    cursor.execute("""
        UPDATE users
        SET dado_balance = LEAST(%s, COALESCE(dado_balance,0) + %s)
        WHERE user_id=%s
    """, (int(max_balance), int(amount), int(user_id)))
    _commit()


# ================================
# TOP CACHE (1x/dia)
# ================================
def top_cache_last_updated() -> int:
    cursor.execute("SELECT COALESCE(MAX(updated_at),0) AS t FROM top_anime_cache")
    row = cursor.fetchone()
    return int(row["t"] if row else 0)


def replace_top_anime_cache(items: List[Dict[str, Any]]):
    now = int(time.time())
    cursor.execute("TRUNCATE top_anime_cache")
    for it in items:
        cursor.execute("""
            INSERT INTO top_anime_cache (anime_id, title, rank, updated_at)
            VALUES (%s, %s, %s, %s)
        """, (int(it["anime_id"]), str(it["title"]), int(it["rank"]), int(now)))
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
    """, (int(user_id), int(dice_value), options_json, int(time.time())))
    rid = int(cursor.fetchone()["roll_id"])
    _commit()
    return rid


def get_dice_roll(roll_id: int):
    cursor.execute("SELECT * FROM dice_rolls WHERE roll_id=%s", (int(roll_id),))
    return cursor.fetchone()


def set_dice_roll_status(roll_id: int, status: str):
    cursor.execute("UPDATE dice_rolls SET status=%s WHERE roll_id=%s", (str(status), int(roll_id)))
    _commit()


def try_set_dice_roll_status(roll_id: int, from_status: str, to_status: str) -> bool:
    """
    Troca status de forma atômica (anti duplo-clique).
    """
    cursor.execute("""
        UPDATE dice_rolls
        SET status=%s
        WHERE roll_id=%s AND status=%s
        RETURNING roll_id
    """, (str(to_status), int(roll_id), str(from_status)))
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


def swap_trade_execute(trade_id: int, from_user: int, to_user: int, from_char: int, to_char: int) -> bool:
    """
    Executa troca dentro de transação com locks.
    Observação: Mantém lógica simples (um item por id).
    """
    try:
        cursor.execute("BEGIN")

        cursor.execute("SELECT status FROM trades WHERE trade_id=%s FOR UPDATE", (int(trade_id),))
        tr = cursor.fetchone()
        if not tr or tr.get("status") != "pendente":
            cursor.execute("ROLLBACK")
            return False

        # lock linhas de posse
        cursor.execute("""
            SELECT quantity FROM user_collection
            WHERE user_id=%s AND character_id=%s
            FOR UPDATE
        """, (int(from_user), int(from_char)))
        a = cursor.fetchone()

        cursor.execute("""
            SELECT quantity FROM user_collection
            WHERE user_id=%s AND character_id=%s
            FOR UPDATE
        """, (int(to_user), int(to_char)))
        b = cursor.fetchone()

        if not a or not b:
            cursor.execute("UPDATE trades SET status='falhou' WHERE trade_id=%s", (int(trade_id),))
            cursor.execute("COMMIT")
            return False

        # troca (se ambos não tiverem o mesmo char já, isso funciona; se tiver, pode colidir)
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
            db.rollback()
        return False


# ================================
# BATALHAS
# ================================
def upsert_battle(chat_id: int, p1_id: int, p2_id: int, p1_name: str, p2_name: str,
                  player1_char=None, player2_char=None, player1_hp=None, player2_hp=None, vez=None):
    cursor.execute("""
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
    _commit()


def get_battle(chat_id: int):
    cursor.execute("SELECT * FROM battles WHERE chat_id=%s", (int(chat_id),))
    return cursor.fetchone()


def delete_battle(chat_id: int):
    cursor.execute("DELETE FROM battles WHERE chat_id=%s", (int(chat_id),))
    _commit()


def battle_set_char(chat_id: int, user_id: int, char_value: str):
    battle = get_battle(chat_id)
    if not battle:
        return
    if int(battle["player1_id"]) == int(user_id):
        cursor.execute("UPDATE battles SET player1_char=%s WHERE chat_id=%s", (char_value, int(chat_id)))
    elif int(battle["player2_id"]) == int(user_id):
        cursor.execute("UPDATE battles SET player2_char=%s WHERE chat_id=%s", (char_value, int(chat_id)))
    _commit()


def battle_set_turn(chat_id: int, vez: int):
    cursor.execute("UPDATE battles SET vez=%s WHERE chat_id=%s", (int(vez), int(chat_id)))
    _commit()


def battle_damage(chat_id: int, target: str, damage: int):
    if target == "p1":
        cursor.execute("UPDATE battles SET player1_hp = GREATEST(player1_hp - %s, 0) WHERE chat_id=%s", (int(damage), int(chat_id)))
    else:
        cursor.execute("UPDATE battles SET player2_hp = GREATEST(player2_hp - %s, 0) WHERE chat_id=%s", (int(damage), int(chat_id)))
    _commit()


# ================================
# SHOP
# ================================
def shop_create_sale(user_id: int, char_id: int) -> int:
    cursor.execute("""
        INSERT INTO shop_sales (user_id, character_id, created_at)
        VALUES (%s, %s, %s)
        RETURNING sale_id
    """, (int(user_id), int(char_id), int(time.time())))
    sale_id = int(cursor.fetchone()["sale_id"])
    _commit()
    return sale_id


def shop_get_sale(sale_id: int):
    cursor.execute("SELECT user_id, character_id FROM shop_sales WHERE sale_id=%s", (int(sale_id),))
    row = cursor.fetchone()
    if not row:
        return None
    return (int(row["user_id"]), int(row["character_id"]))


def shop_delete_sale(sale_id: int):
    cursor.execute("DELETE FROM shop_sales WHERE sale_id=%s", (int(sale_id),))
    _commit()


def shop_list_user_chars(user_id: int, page: int, per_page: int):
    offset = (int(page) - 1) * int(per_page)
    cursor.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (int(user_id),))
    total = int(cursor.fetchone()["c"])
    total_pages = (total - 1) // int(per_page) + 1 if total else 1

    cursor.execute("""
        SELECT character_id, character_name
        FROM user_collection
        WHERE user_id=%s
        ORDER BY character_id ASC
        LIMIT %s OFFSET %s
    """, (int(user_id), int(per_page), int(offset)))
    rows = cursor.fetchall() or []
    chars = [(int(r["character_id"]), r["character_name"]) for r in rows]
    return chars, total, total_pages

def claim_daily_reward(user_id: int, day_start_ts: int, coins_min: int = 1, coins_max: int = 3, giro_chance: float = 0.20):
    """
    Resgata daily 1x por dia (atômico).
    - day_start_ts: timestamp do começo do dia no fuso que você escolher (SP_TZ no bot).
    Retorna:
      None se já resgatou hoje
      dict se resgatou: {"type": "coins"|"giro", "amount": int}
    """
    import random

    try:
        cursor.execute("BEGIN")

        # trava e garante 1x por dia (atômico)
        cursor.execute("""
            UPDATE users
            SET last_daily=%s
            WHERE user_id=%s AND COALESCE(last_daily,0) < %s
            RETURNING user_id
        """, (int(day_start_ts), int(user_id), int(day_start_ts)))

        ok = cursor.fetchone() is not None
        if not ok:
            cursor.execute("ROLLBACK")
            return None

        # decide recompensa
        if random.random() < float(giro_chance):
            # giro = +1 extra_dado
            cursor.execute("""
                UPDATE users
                SET extra_dado = COALESCE(extra_dado,0) + 1
                WHERE user_id=%s
            """, (int(user_id),))
            cursor.execute("COMMIT")
            return {"type": "giro", "amount": 1}

        amount = random.randint(int(coins_min), int(coins_max))
        cursor.execute("""
            UPDATE users
            SET coins = COALESCE(coins,0) + %s
            WHERE user_id=%s
        """, (int(amount), int(user_id)))

        cursor.execute("COMMIT")
        return {"type": "coins", "amount": int(amount)}

    except Exception:
        try:
            cursor.execute("ROLLBACK")
        except Exception:
            db.rollback()
        raise


def list_pending_trades_for_user(to_user: int, limit: int = 5):
    """
    Retorna últimas trocas pendentes pro usuário.
    """
    cursor.execute("""
        SELECT trade_id, from_user, to_user, from_character_id, to_character_id, status
        FROM trades
        WHERE to_user=%s AND status='pendente'
        ORDER BY trade_id DESC
        LIMIT %s
    """, (int(to_user), int(limit)))
    return cursor.fetchall() or []
