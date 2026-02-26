# ============================================================
# DATABASE.PY — SOURCE BALTIGO GOD TIER
# BANCO COMPLETO COMPATÍVEL COM TODAS AS PARTES DO BOT
# COLE COMO: database.py
# ============================================================

import os
import json
import time
import psycopg2
import psycopg2.extras

# ============================================================
# CONEXÃO
# ============================================================

DB_URL = os.getenv("DATABASE_URL")

db = psycopg2.connect(DB_URL, sslmode="require")
db.autocommit = False

cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# ============================================================
# INIT TABLES (RODA AUTOMATICO)
# ============================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    name TEXT,
    nick TEXT,
    level INT DEFAULT 1,
    commands INT DEFAULT 0,
    coins INT DEFAULT 0,
    last_pedido BIGINT DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS dado_state (
    user_id BIGINT PRIMARY KEY,
    b INT DEFAULT 0,
    s INT DEFAULT -1
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS dado_extra (
    user_id BIGINT PRIMARY KEY,
    extra INT DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS dice_rolls (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    dice_value INT,
    options_json TEXT,
    status TEXT DEFAULT 'pending',
    created_at BIGINT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS collection (
    user_id BIGINT,
    char_id BIGINT,
    name TEXT,
    image TEXT,
    anime_title TEXT,
    PRIMARY KEY(user_id, char_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS favorites (
    user_id BIGINT,
    char_id BIGINT,
    PRIMARY KEY(user_id, char_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    from_user BIGINT,
    target_user BIGINT,
    char_id BIGINT,
    status TEXT DEFAULT 'pending'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS shop (
    id SERIAL PRIMARY KEY,
    nome TEXT,
    preco INT
)
""")

db.commit()

# ============================================================
# USERS
# ============================================================

def ensure_user_row(user_id: int, name: str = ""):
    cursor.execute(
        "INSERT INTO users (user_id,name) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (user_id, name)
    )
    db.commit()

def get_user_row(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    if not row:
        return {"user_id":user_id,"nick":None,"level":1,"commands":0}
    return row

def set_user_nick(user_id: int, nick: str):
    cursor.execute(
        "UPDATE users SET nick=%s WHERE user_id=%s",
        (nick, user_id)
    )
    db.commit()

# ============================================================
# COINS
# ============================================================

def add_coin(user_id:int, amount:int):
    cursor.execute(
        "UPDATE users SET coins = coins + %s WHERE user_id=%s",
        (amount, user_id)
    )
    db.commit()

def get_user_coin_balance(user_id:int):
    cursor.execute("SELECT coins FROM users WHERE user_id=%s",(user_id,))
    r = cursor.fetchone()
    return int(r["coins"] if r else 0)

# ============================================================
# COLLECTION
# ============================================================

def user_has_character(user_id:int, char_id:int):
    cursor.execute(
        "SELECT 1 FROM collection WHERE user_id=%s AND char_id=%s",
        (user_id,char_id)
    )
    return bool(cursor.fetchone())

def add_character_to_collection(user_id:int, char_id:int, name:str, image:str, anime_title:str=""):
    cursor.execute(
        """
        INSERT INTO collection (user_id,char_id,name,image,anime_title)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        """,
        (user_id,char_id,name,image,anime_title)
    )
    db.commit()

def get_user_collection_count(user_id:int):
    cursor.execute(
        "SELECT COUNT(*) AS c FROM collection WHERE user_id=%s",
        (user_id,)
    )
    r = cursor.fetchone()
    return int(r["c"] if r else 0)

# ============================================================
# FAVORITES
# ============================================================

def add_favorite_character(user_id:int,char_id:int):
    cursor.execute(
        "INSERT INTO favorites VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (user_id,char_id)
    )
    db.commit()

def remove_favorite_character(user_id:int,char_id:int):
    cursor.execute(
        "DELETE FROM favorites WHERE user_id=%s AND char_id=%s",
        (user_id,char_id)
    )
    db.commit()

def get_user_favorites(user_id:int):
    cursor.execute(
        "SELECT char_id FROM favorites WHERE user_id=%s",
        (user_id,)
    )
    return cursor.fetchall() or []

# ============================================================
# DADO STATE
# ============================================================

def get_dado_state(user_id:int):
    cursor.execute("SELECT * FROM dado_state WHERE user_id=%s",(user_id,))
    return cursor.fetchone()

def set_dado_state(user_id:int,b:int,s:int):
    cursor.execute("""
    INSERT INTO dado_state VALUES (%s,%s,%s)
    ON CONFLICT (user_id)
    DO UPDATE SET b=EXCLUDED.b, s=EXCLUDED.s
    """,(user_id,b,s))
    db.commit()

def inc_dado_balance(user_id:int, amount:int, max_balance:int=18):
    cursor.execute("SELECT b FROM dado_state WHERE user_id=%s",(user_id,))
    r = cursor.fetchone()
    if not r:
        set_dado_state(user_id,amount,-1)
        return
    new = min(max_balance,int(r["b"])+amount)
    set_dado_state(user_id,new,-1)

# ============================================================
# DADO EXTRA
# ============================================================

def get_extra_dado(user_id:int):
    cursor.execute("SELECT extra FROM dado_extra WHERE user_id=%s",(user_id,))
    r = cursor.fetchone()
    return int(r["extra"] if r else 0)

def consume_extra_dado(user_id:int):
    cursor.execute(
        "UPDATE dado_extra SET extra=extra-1 WHERE user_id=%s AND extra>0",
        (user_id,)
    )
    db.commit()
    return cursor.rowcount>0

# ============================================================
# DICE ROLL
# ============================================================

def create_dice_roll(user_id:int,dice_value:int,options_json:str):
    cursor.execute(
        """
        INSERT INTO dice_rolls (user_id,dice_value,options_json,status,created_at)
        VALUES (%s,%s,%s,'pending',%s) RETURNING id
        """,
        (user_id,dice_value,options_json,int(time.time()))
    )
    rid = cursor.fetchone()["id"]
    db.commit()
    return rid

def get_dice_roll(rid:int):
    cursor.execute("SELECT * FROM dice_rolls WHERE id=%s",(rid,))
    return cursor.fetchone()

def set_dice_roll_status(rid:int,status:str):
    cursor.execute(
        "UPDATE dice_rolls SET status=%s WHERE id=%s",
        (status,rid)
    )
    db.commit()

# ============================================================
# TRADES
# ============================================================

def create_trade_request(from_user:int,target_user:int,char_id:int):
    cursor.execute(
        """
        INSERT INTO trades (from_user,target_user,char_id,status)
        VALUES (%s,%s,%s,'pending') RETURNING id
        """,
        (from_user,target_user,char_id)
    )
    tid = cursor.fetchone()["id"]
    db.commit()
    return tid

def get_trade_request(trade_id:int):
    cursor.execute("SELECT * FROM trades WHERE id=%s",(trade_id,))
    return cursor.fetchone()

def set_trade_status(trade_id:int,status:str):
    cursor.execute(
        "UPDATE trades SET status=%s WHERE id=%s",
        (status,trade_id)
    )
    db.commit()

def transfer_character_between_users(origem:int,destino:int,char_id:int):

    cursor.execute(
        "SELECT * FROM collection WHERE user_id=%s AND char_id=%s",
        (origem,char_id)
    )
    row = cursor.fetchone()

    if not row:
        return False

    cursor.execute(
        "DELETE FROM collection WHERE user_id=%s AND char_id=%s",
        (origem,char_id)
    )

    cursor.execute(
        """
        INSERT INTO collection (user_id,char_id,name,image,anime_title)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        """,
        (destino,char_id,row["name"],row["image"],row["anime_title"])
    )

    db.commit()
    return True

# ============================================================
# SHOP
# ============================================================

def get_shop_items():
    cursor.execute("SELECT * FROM shop ORDER BY id ASC")
    return cursor.fetchall()

def buy_shop_item(user_id:int,item_id:int):

    cursor.execute("SELECT preco FROM shop WHERE id=%s",(item_id,))
    item = cursor.fetchone()
    if not item:
        return False

    preco = int(item["preco"])

    cursor.execute("SELECT coins FROM users WHERE user_id=%s",(user_id,))
    row = cursor.fetchone()
    if not row or int(row["coins"]) < preco:
        return False

    cursor.execute(
        "UPDATE users SET coins=coins-%s WHERE user_id=%s",
        (preco,user_id)
    )

    db.commit()
    return True

# ============================================================
# 🔥 FIM DATABASE GOD TIER
# ============================================================
