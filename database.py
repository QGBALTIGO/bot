# ================================
# database.py
# Compatível com bot.py
# Railway + PostgreSQL
# ================================

import os
import time
import random
from typing import Optional, List, Dict

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL")

pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row}
)

# =========================================================
# INIT
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

            cur.execute(
                "UPDATE users SET nick=%s WHERE user_id=%s",
                (nick,user_id)
            )
            conn.commit()

            return True

def set_private_profile(user_id:int,value:bool):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE users SET private_profile=%s WHERE user_id=%s",
                (value,user_id)
            )

def set_admin_photo(user_id:int,url:str):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE users SET admin_photo=%s WHERE user_id=%s",
                (url,user_id)
            )

def get_admin_photo_db(user_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT admin_photo FROM users WHERE user_id=%s",
                (user_id,)
            )
            r=cur.fetchone()

            return r["admin_photo"] if r else None

def set_collection_name(user_id:int,name:str):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE users SET collection_name=%s WHERE user_id=%s",
                (name,user_id)
            )

def get_collection_name(user_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT collection_name FROM users WHERE user_id=%s",
                (user_id,)
            )
            r=cur.fetchone()

            return r["collection_name"] if r else "Minha Coleção"

# =========================================================
# COINS
# =========================================================

def add_coin(user_id:int,amount:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE users SET coins=coins+%s WHERE user_id=%s",
                (amount,user_id)
            )

def get_user_coins(user_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT coins FROM users WHERE user_id=%s",
                (user_id,)
            )

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
# COLEÇÃO
# =========================================================

def count_collection(user_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT COUNT(*) FROM user_collection WHERE user_id=%s",
                (user_id,)
            )

            return cur.fetchone()["count"]

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

def user_has_character(user_id:int,char_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT 1 FROM user_collection WHERE user_id=%s AND character_id=%s",
                (user_id,char_id)
            )

            return cur.fetchone()!=None

def remove_one_from_collection(user_id:int,char_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            UPDATE user_collection
            SET quantity=quantity-1
            WHERE user_id=%s AND character_id=%s
            """,(user_id,char_id))

# =========================================================
# TROCAS
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

            cur.execute(
                "SELECT * FROM trades WHERE trade_id=%s",
                (trade_id,)
            )

            return cur.fetchone()

def mark_trade_status(trade_id:int,status:str):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE trades SET status=%s WHERE trade_id=%s",
                (status,trade_id)
            )

def swap_trade_execute(*args):

    return True

# =========================================================
# DADO
# =========================================================

def get_dado_state(user_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT dado_balance FROM users WHERE user_id=%s",
                (user_id,)
            )

            r=cur.fetchone()

            return {"b":r["dado_balance"],"s":0}

def set_dado_state(user_id:int,balance:int,slot:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE users SET dado_balance=%s WHERE user_id=%s",
                (balance,user_id)
            )

def inc_dado_balance(user_id:int,amount:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE users SET dado_balance=dado_balance+%s WHERE user_id=%s",
                (amount,user_id)
            )

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

def consume_extra_dado(user_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "UPDATE users SET extra_dado=extra_dado-1 WHERE user_id=%s AND extra_dado>0",
                (user_id,)
            )

# =========================================================
# DAILY
# =========================================================

def claim_daily_reward(user_id:int):

    coins=random.randint(1,3)

    add_coin(user_id,coins)

    return {"type":"coins","amount":coins}

# =========================================================
# STATS
# =========================================================

def get_user_stats(user_id:int):

    user=get_user_row(user_id)

    return {
        "coins":user["coins"],
        "level":user["level"],
        "commands":user["commands"]
    }

# =========================================================
# ACHIEVEMENTS
# =========================================================

def list_user_achievement_keys(user_id:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT key FROM achievements WHERE user_id=%s",
                (user_id,)
            )

            return [x["key"] for x in cur.fetchall()]

def grant_achievements_and_reward(user_id:int,keys:list,reward:int):

    with pool.connection() as conn:
        with conn.cursor() as cur:

            for k in keys:

                cur.execute(
                    "INSERT INTO achievements VALUES(%s,%s,%s)",
                    (user_id,k,int(time.time()))
                )

            add_extra_dado(user_id,len(keys)*reward)

            return len(keys)
