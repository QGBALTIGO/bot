# ================================
# database.py — Postgres (Railway) (PRONTO + LOJA)
# ================================

import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrado. No Railway, crie a variável DATABASE_URL com valor ${{Postgres.DATABASE_URL}}"
    )

db = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
cursor = db.cursor()


def init_shop_extras():
    # coluna para rodadas extras de dado
    cursor.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS extra_dado INT DEFAULT 0;
    """)

    # coluna para foto custom no personagem
    cursor.execute("""
    ALTER TABLE user_collection
    ADD COLUMN IF NOT EXISTS custom_image TEXT;
    """)

    # pedidos de troca de foto
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS photo_requests (
        request_id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        character_id INT NOT NULL,
        new_url TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pendente',
        created_at BIGINT NOT NULL
    );
    """)

    db.commit()


def init_db():
    # USERS
    cursor.execute("""
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
        last_pedido BIGINT DEFAULT 0
    );
    """)

    # COLEÇÃO
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_collection (
        user_id BIGINT,
        character_id INT,
        character_name TEXT,
        image TEXT,
        quantity INT DEFAULT 1,
        PRIMARY KEY (user_id, character_id)
    );
    """)

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

    # LOJA (vendas pendentes simples) - pode manter mesmo que você não use mais botões
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shop_sales (
        sale_id SERIAL PRIMARY KEY,
        user_id BIGINT,
        character_id INT,
        created_at BIGINT
    );
    """)

    # private_profile
    cursor.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS private_profile BOOLEAN DEFAULT FALSE;
    """)

    # admin photo (persistente)
    cursor.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS admin_photo TEXT;
    """)

    db.commit()

    # garante colunas/tabelas da loja nova
    init_shop_extras()


# ---------------- USERS ----------------
def ensure_user_row(user_id: int, default_name: str):
    cursor.execute("SELECT 1 FROM users WHERE user_id=%s", (user_id,))
    if cursor.fetchone():
        return
    cursor.execute(
        "INSERT INTO users (user_id, nick, collection_name) VALUES (%s, %s, %s)",
        (user_id, default_name, "Minha Coleção")
    )
    db.commit()


def get_user_row(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    return cursor.fetchone()


def get_user_by_nick(nick: str):
    cursor.execute("SELECT * FROM users WHERE LOWER(nick)=LOWER(%s) LIMIT 1", (nick,))
    return cursor.fetchone()


def set_user_nick(user_id: int, nick: str):
    cursor.execute("UPDATE users SET nick=%s WHERE user_id=%s", (nick, user_id))
    db.commit()


def add_coin(user_id: int, amount: int):
    cursor.execute("UPDATE users SET coins = COALESCE(coins,0) + %s WHERE user_id=%s", (amount, user_id))
    db.commit()


def set_collection_name(user_id: int, name: str):
    cursor.execute("UPDATE users SET collection_name=%s WHERE user_id=%s", (name, user_id))
    db.commit()


def get_collection_name(user_id: int):
    cursor.execute("SELECT collection_name FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["collection_name"] if row and row["collection_name"] else "Minha Coleção"


def set_private_profile(user_id: int, is_private: bool):
    cursor.execute("UPDATE users SET private_profile=%s WHERE user_id=%s", (is_private, user_id))
    db.commit()


# ---------------- ADMIN FOTO (persistente) ----------------
def set_admin_photo(user_id: int, url: str):
    cursor.execute("UPDATE users SET admin_photo=%s WHERE user_id=%s", (url, user_id))
    db.commit()


def get_admin_photo_db(user_id: int):
    cursor.execute("SELECT admin_photo FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["admin_photo"] if row and row["admin_photo"] else None


# ================================
# CARD: foto global por personagem
# ================================

# dado extra
    cursor.execute("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS extra_dado INT DEFAULT 0;
    """)

    # anime_title (pro /card ficar bonito)
    cursor.execute("""
    ALTER TABLE user_collection
    ADD COLUMN IF NOT EXISTS anime_title TEXT;
    """)

    # custom_image (se você ainda usa por usuário em alguma parte)
    cursor.execute("""
    ALTER TABLE user_collection
    ADD COLUMN IF NOT EXISTS custom_image TEXT;
    """)

    # tabela global de imagem do personagem (vale pra todo mundo no /card)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS character_images (
        character_id INT PRIMARY KEY,
        image_url TEXT NOT NULL,
        updated_at BIGINT NOT NULL,
        updated_by BIGINT
    );
    """)

    # pedidos de troca de foto (aprovação)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS photo_requests (
        request_id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        character_id INT NOT NULL,
        new_url TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pendente',
        created_at BIGINT NOT NULL
    );
    """)

    db.commit()


def set_global_character_image(character_id: int, image_url: str, updated_by: int | None = None):
    cursor.execute("""
        INSERT INTO character_images (character_id, image_url, updated_at, updated_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (character_id) DO UPDATE SET
            image_url = EXCLUDED.image_url,
            updated_at = EXCLUDED.updated_at,
            updated_by = EXCLUDED.updated_by
    """, (character_id, image_url, int(time.time()), updated_by))
    db.commit()


def get_global_character_image(character_id: int):
    cursor.execute("SELECT image_url FROM character_images WHERE character_id=%s", (character_id,))
    row = cursor.fetchone()
    return row["image_url"] if row and row["image_url"] else None


def get_random_character_from_collection_full(user_id: int):
    """
    Retorna: character_id, character_name, image, quantity, anime_title
    (a foto global é puxada por get_global_character_image no bot)
    """
    cursor.execute("""
        SELECT character_id, character_name, image, quantity, anime_title
        FROM user_collection
        WHERE user_id=%s
        ORDER BY RANDOM()
        LIMIT 1
    """, (user_id,))
    
# ---------------- COLEÇÃO ----------------
def count_collection(user_id: int) -> int:
    cursor.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (user_id,))
    return int(cursor.fetchone()["c"])


def get_collection_page(user_id: int, page: int, per_page: int):
    offset = (page - 1) * per_page

    cursor.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (user_id,))
    total = int(cursor.fetchone()["c"])
    total_pages = (total - 1) // per_page + 1 if total else 1

    cursor.execute("""
        SELECT character_id, character_name
        FROM user_collection
        WHERE user_id=%s
        ORDER BY character_id ASC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset))
    itens = [(int(r["character_id"]), r["character_name"]) for r in cursor.fetchall()]
    return itens, total, total_pages


def user_has_character(user_id: int, char_id: int) -> bool:
    cursor.execute(
        "SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s",
        (user_id, char_id)
    )
    return cursor.fetchone() is not None


def add_character_to_collection(user_id: int, char_id: int, name: str, image: str):
    cursor.execute(
        "SELECT quantity FROM user_collection WHERE user_id=%s AND character_id=%s",
        (user_id, char_id)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "UPDATE user_collection SET quantity=quantity+1 WHERE user_id=%s AND character_id=%s",
            (user_id, char_id)
        )
    else:
        cursor.execute("""
            INSERT INTO user_collection (user_id, character_id, character_name, image, quantity)
            VALUES (%s, %s, %s, %s, 1)
        """, (user_id, char_id, name, image))
    db.commit()


def remove_one_from_collection(user_id: int, char_id: int) -> bool:
    cursor.execute(
        "SELECT quantity FROM user_collection WHERE user_id=%s AND character_id=%s",
        (user_id, char_id)
    )
    row = cursor.fetchone()
    if not row:
        return False

    q = int(row["quantity"] or 0)
    if q <= 1:
        cursor.execute(
            "DELETE FROM user_collection WHERE user_id=%s AND character_id=%s",
            (user_id, char_id)
        )
    else:
        cursor.execute(
            "UPDATE user_collection SET quantity=quantity-1 WHERE user_id=%s AND character_id=%s",
            (user_id, char_id)
        )

    db.commit()
    return True


def get_collection_character_full(user_id: int, char_id: int):
    cursor.execute("""
        SELECT character_id, character_name, image, custom_image, quantity
        FROM user_collection
        WHERE user_id=%s AND character_id=%s
        LIMIT 1
    """, (user_id, char_id))
    return cursor.fetchone()


# ---------------- FAVORITO POR ID (somente se tiver na coleção) ----------------
def get_collection_character(user_id: int, char_id: int):
    cursor.execute("""
        SELECT character_id, character_name, image
        FROM user_collection
        WHERE user_id=%s AND character_id=%s
        LIMIT 1
    """, (user_id, char_id))
    return cursor.fetchone()


def set_favorite_from_collection(user_id: int, char_name: str, image: str):
    cursor.execute(
        "UPDATE users SET fav_name=%s, fav_image=%s WHERE user_id=%s",
        (char_name, image, user_id)
    )
    db.commit()


def clear_favorite(user_id: int):
    cursor.execute("UPDATE users SET fav_name=NULL, fav_image=NULL WHERE user_id=%s", (user_id,))
    db.commit()


# ---------------- LOJA: dado extra ----------------
def add_extra_dado(user_id: int, amount: int):
    cursor.execute(
        "UPDATE users SET extra_dado = COALESCE(extra_dado,0) + %s WHERE user_id=%s",
        (amount, user_id)
    )
    db.commit()


def get_extra_dado(user_id: int) -> int:
    cursor.execute("SELECT COALESCE(extra_dado,0) AS x FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return int(row["x"] if row else 0)


def consume_extra_dado(user_id: int) -> bool:
    cursor.execute("SELECT COALESCE(extra_dado,0) AS x FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    x = int(row["x"] if row else 0)
    if x <= 0:
        return False
    cursor.execute("UPDATE users SET extra_dado = extra_dado - 1 WHERE user_id=%s", (user_id,))
    db.commit()
    return True


# ---------------- LOJA: foto custom com aprovação ----------------
def set_character_custom_image(user_id: int, char_id: int, url: str):
    cursor.execute("""
        UPDATE user_collection
        SET custom_image=%s
        WHERE user_id=%s AND character_id=%s
    """, (url, user_id, char_id))
    db.commit()


def create_photo_request(user_id: int, char_id: int, new_url: str) -> int:
    cursor.execute("""
        INSERT INTO photo_requests (user_id, character_id, new_url, status, created_at)
        VALUES (%s, %s, %s, 'pendente', %s)
        RETURNING request_id
    """, (user_id, char_id, new_url, int(time.time())))
    rid = int(cursor.fetchone()["request_id"])
    db.commit()
    return rid


def get_photo_request(request_id: int):
    cursor.execute("""
        SELECT request_id, user_id, character_id, new_url, status, created_at
        FROM photo_requests
        WHERE request_id=%s
    """, (request_id,))
    return cursor.fetchone()


def set_photo_request_status(request_id: int, status: str):
    cursor.execute("UPDATE photo_requests SET status=%s WHERE request_id=%s", (status, request_id))
    db.commit()


# ---------------- TROCAS ----------------
def create_trade(from_user: int, to_user: int, from_char: int, to_char: int):
    cursor.execute("""
        INSERT INTO trades (from_user, to_user, from_character_id, to_character_id, status)
        VALUES (%s, %s, %s, %s, 'pendente')
    """, (from_user, to_user, from_char, to_char))
    db.commit()


def get_latest_pending_trade_for_to_user(to_user: int):
    cursor.execute("""
        SELECT trade_id, from_user, from_character_id, to_character_id
        FROM trades
        WHERE to_user=%s AND status='pendente'
        ORDER BY trade_id DESC
        LIMIT 1
    """, (to_user,))
    row = cursor.fetchone()
    if not row:
        return None
    return (int(row["trade_id"]), int(row["from_user"]), int(row["from_character_id"]), int(row["to_character_id"]))


def mark_trade_status(trade_id: int, status: str):
    cursor.execute("UPDATE trades SET status=%s WHERE trade_id=%s", (status, trade_id))
    db.commit()


def swap_trade_execute(trade_id: int, from_user: int, to_user: int, from_char: int, to_char: int):
    cursor.execute("""
        UPDATE user_collection SET user_id=%s
        WHERE user_id=%s AND character_id=%s
    """, (to_user, from_user, from_char))

    cursor.execute("""
        UPDATE user_collection SET user_id=%s
        WHERE user_id=%s AND character_id=%s
    """, (from_user, to_user, to_char))

    cursor.execute("UPDATE trades SET status='aceita' WHERE trade_id=%s", (trade_id,))
    db.commit()


# ---------------- LOJA (lista antiga, pode manter) ----------------
def shop_list_user_chars(user_id: int, page: int, per_page: int):
    offset = (page - 1) * per_page
    cursor.execute("SELECT COUNT(*) AS c FROM user_collection WHERE user_id=%s", (user_id,))
    total = int(cursor.fetchone()["c"])
    total_pages = (total - 1) // per_page + 1 if total else 1

    cursor.execute("""
        SELECT character_id, character_name
        FROM user_collection
        WHERE user_id=%s
        ORDER BY character_id ASC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset))
    rows = cursor.fetchall()
    chars = [(int(r["character_id"]), r["character_name"]) for r in rows]
    return chars, total, total_pages


def shop_create_sale(user_id: int, char_id: int) -> int:
    cursor.execute("""
        INSERT INTO shop_sales (user_id, character_id, created_at)
        VALUES (%s, %s, %s)
        RETURNING sale_id
    """, (user_id, char_id, int(time.time())))
    sale_id = int(cursor.fetchone()["sale_id"])
    db.commit()
    return sale_id


def shop_get_sale(sale_id: int):
    cursor.execute("SELECT user_id, character_id FROM shop_sales WHERE sale_id=%s", (sale_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return (int(row["user_id"]), int(row["character_id"]))


def shop_delete_sale(sale_id: int):
    cursor.execute("DELETE FROM shop_sales WHERE sale_id=%s", (sale_id,))
    db.commit()


# ---------------- BATALHAS ----------------
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
    """, (chat_id, p1_id, p2_id, p1_name, p2_name, player1_char, player2_char, player1_hp, player2_hp, vez))
    db.commit()


def get_battle(chat_id: int):
    cursor.execute("SELECT * FROM battles WHERE chat_id=%s", (chat_id,))
    return cursor.fetchone()


def delete_battle(chat_id: int):
    cursor.execute("DELETE FROM battles WHERE chat_id=%s", (chat_id,))
    db.commit()


def battle_set_char(chat_id: int, user_id: int, char_value: str):
    battle = get_battle(chat_id)
    if not battle:
        return
    if int(battle["player1_id"]) == int(user_id):
        cursor.execute("UPDATE battles SET player1_char=%s WHERE chat_id=%s", (char_value, chat_id))
    elif int(battle["player2_id"]) == int(user_id):
        cursor.execute("UPDATE battles SET player2_char=%s WHERE chat_id=%s", (char_value, chat_id))
    db.commit()


def battle_set_turn(chat_id: int, vez: int):
    cursor.execute("UPDATE battles SET vez=%s WHERE chat_id=%s", (vez, chat_id))
    db.commit()


def battle_damage(chat_id: int, target: str, damage: int):
    if target == "p1":
        cursor.execute(
            "UPDATE battles SET player1_hp = GREATEST(player1_hp - %s, 0) WHERE chat_id=%s",
            (damage, chat_id)
        )
    else:
        cursor.execute(
            "UPDATE battles SET player2_hp = GREATEST(player2_hp - %s, 0) WHERE chat_id=%s",
            (damage, chat_id)
        )
    db.commit()
