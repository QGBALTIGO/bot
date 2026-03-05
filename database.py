import os
import time
import random
import re
from typing import Optional, List, Dict, Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não definido")

pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row}
)

# =========================================================
# INIT / TABLES
# =========================================================

def init_db():
    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            CREATE TABLE IF NOT EXISTS users(
                user_id BIGINT PRIMARY KEY,
                nick TEXT,
                coins INT DEFAULT 0,
                level INT DEFAULT 1,
                commands INT DEFAULT 0,
                dado_balance INT DEFAULT 0,
                extra_dado INT DEFAULT 0,
                private_profile BOOLEAN DEFAULT FALSE,
                collection_name TEXT DEFAULT 'Minha Coleção',
                fav_name TEXT,
                fav_image TEXT,
                admin_photo TEXT,
                last_pedido BIGINT DEFAULT 0,
                last_daily BIGINT DEFAULT 0
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS user_collection(
                user_id BIGINT,
                character_id INT,
                character_name TEXT,
                image TEXT,
                custom_image TEXT,
                anime_title TEXT,
                quantity INT DEFAULT 1,
                PRIMARY KEY(user_id, character_id)
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS trades(
                trade_id SERIAL PRIMARY KEY,
                from_user BIGINT,
                to_user BIGINT,
                from_character_id INT,
                to_character_id INT,
                status TEXT,
                created_at BIGINT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS dice_rolls(
                roll_id SERIAL PRIMARY KEY,
                user_id BIGINT,
                dice_value INT,
                options_json TEXT,
                status TEXT,
                created_at BIGINT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS characters_pool(
                character_id INT PRIMARY KEY,
                character_name TEXT,
                anime_id INT,
                anime_title TEXT,
                role TEXT,
                active BOOLEAN DEFAULT TRUE
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS character_images(
                character_id INT PRIMARY KEY,
                image_url TEXT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS banned_characters(
                character_id INT PRIMARY KEY
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS achievements(
                user_id BIGINT,
                key TEXT,
                created_at BIGINT
            )
            """)

            conn.commit()

# =========================================================
# USERS
# =========================================================

def ensure_user_row(user_id:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users(user_id) VALUES(%s) ON CONFLICT DO NOTHING",
                (user_id,)
            )

def get_user_row(user_id:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id=%s",(user_id,))
            return cur.fetchone()

def get_user_by_nick(nick:str):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE nick=%s",(nick,))
            return cur.fetchone()

def try_set_nick(user_id:int,nick:str):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET nick=%s WHERE user_id=%s",(nick,user_id))
            conn.commit()
            return True

def set_private_profile(user_id:int,value:bool):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET private_profile=%s WHERE user_id=%s",(value,user_id))

def set_admin_photo(user_id:int,url:str):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET admin_photo=%s WHERE user_id=%s",(url,user_id))

def get_admin_photo_db(user_id:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT admin_photo FROM users WHERE user_id=%s",(user_id,))
            r=cur.fetchone()
            return r["admin_photo"] if r else None

def set_collection_name(user_id:int,name:str):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET collection_name=%s WHERE user_id=%s",(name,user_id))

def get_collection_name(user_id:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT collection_name FROM users WHERE user_id=%s",(user_id,))
            r=cur.fetchone()
            return r["collection_name"] if r else "Minha Coleção"

def set_last_pedido(user_id:int,ts:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET last_pedido=%s WHERE user_id=%s",(ts,user_id))

# =========================================================
# COINS
# =========================================================

def add_coin(user_id:int,amount:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET coins=coins+%s WHERE user_id=%s",(amount,user_id))

def get_user_coins(user_id:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT coins FROM users WHERE user_id=%s",(user_id,))
            r=cur.fetchone()
            return r["coins"] if r else 0

def try_spend_coins(user_id:int,amount:int):
    coins=get_user_coins(user_id)
    if coins<amount:
        return False
    add_coin(user_id,-amount)
    return True

def spend_coins_and_add_giro(user_id:int,price:int):
    if not try_spend_coins(user_id,price):
        return False
    add_extra_dado(user_id,1)
    return True

# =========================================================
# LEVEL
# =========================================================

def increment_commands_and_level(user_id:int,nick_fallback:str,per_level:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE users SET commands=commands+1 WHERE user_id=%s",
                (user_id,)
            )

            cur.execute(
                "SELECT commands,level FROM users WHERE user_id=%s",
                (user_id,)
            )

            r=cur.fetchone()

            commands=r["commands"]
            level=r["level"]

            new_level=(commands//per_level)+1

            if new_level>level:

                cur.execute(
                    "UPDATE users SET level=%s WHERE user_id=%s",
                    (new_level,user_id)
                )

            return {
                "commands":commands,
                "level":new_level,
                "nick_safe":nick_fallback,
                "old_level":level
            }

# =========================================================
# COLLECTION
# =========================================================

def count_collection(user_id:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM user_collection WHERE user_id=%s",(user_id,))
            return cur.fetchone()["count"]

def get_collection_page(user_id:int,page:int,per_page:int=20):
    with pool.connection() as conn:
        with conn.cursor() as cur:

            offset=(page-1)*per_page

            cur.execute("""
            SELECT * FROM user_collection
            WHERE user_id=%s
            LIMIT %s OFFSET %s
            """,(user_id,per_page,offset))

            return cur.fetchall()

def add_character_to_collection(user_id:int,char_id:int,name:str,image:str,anime:str):
    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            INSERT INTO user_collection
            (user_id,character_id,character_name,image,anime_title)
            VALUES(%s,%s,%s,%s,%s)
            ON CONFLICT(user_id,character_id)
            DO UPDATE SET quantity=user_collection.quantity+1
            """,(user_id,char_id,name,image,anime))

def list_collection_cards(user_id:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM user_collection WHERE user_id=%s",(user_id,))
            return cur.fetchall()

# =========================================================
# TRADES
# =========================================================

def create_trade(a,b,c,d):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO trades
            (from_user,to_user,from_character_id,to_character_id,status,created_at)
            VALUES(%s,%s,%s,%s,'pendente',%s)
            RETURNING trade_id
            """,(a,b,c,d,int(time.time())))
            return cur.fetchone()["trade_id"]

def get_trade_by_id(trade_id:int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM trades WHERE trade_id=%s",(trade_id,))
            return cur.fetchone()

def swap_trade_execute(*args):
    return True

# =========================================================
# POOL TOP500
# =========================================================

def pool_import_top500_txt(path:str):

    anime_id=None
    anime_title=None
    role=None

    with open(path,"r",encoding="utf-8") as f:

        for line in f:

            line=line.strip()

            if line.startswith("#"):

                m=re.search(r"#\d+ (.+) \((\d+)\)",line)
                if m:
                    anime_title=m.group(1)
                    anime_id=int(m.group(2))

            elif line.endswith(":"):

                role=line.replace(":","")

            elif line.startswith("-"):

                m=re.search(r"- (.+) \((\d+)\)",line)

                if m:

                    name=m.group(1)
                    char_id=int(m.group(2))

                    with pool.connection() as conn:
                        with conn.cursor() as cur:

                            cur.execute("""
                            INSERT INTO characters_pool
                            (character_id,character_name,anime_id,anime_title,role)
                            VALUES(%s,%s,%s,%s,%s)
                            ON CONFLICT DO NOTHING
                            """,(char_id,name,anime_id,anime_title,role))

def pool_random_character():

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT * FROM characters_pool
            WHERE active=TRUE
            ORDER BY RANDOM()
            LIMIT 1
            """)

            return cur.fetchone()

# =========================================================
# EXTRA DADO
# =========================================================

def get_extra_dado(user_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT extra_dado FROM users WHERE user_id=%s",
                (user_id,)
            )

            r=cur.fetchone()

            return r["extra_dado"] if r else 0

def add_extra_dado(user_id:int,amount:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE users SET extra_dado=extra_dado+%s WHERE user_id=%s",
                (amount,user_id)
            )

# =========================================================
# DAILY
# =========================================================

def claim_daily_reward(user_id:int):

    coins=random.randint(1,3)

    add_coin(user_id,coins)

    return {"type":"coins","amount":coins}
