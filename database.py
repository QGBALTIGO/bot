# =========================================
# DATABASE COMPLETO COMPATÍVEL COM BOT.PY
# =========================================

import os
import time
import random
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

# =========================================
# INIT
# =========================================

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
                PRIMARY KEY(user_id,character_id)
            )
            """)

            conn.commit()

# =========================================
# USERS
# =========================================

def ensure_user_row(user_id): pass
def get_user_row(user_id): return {}
def get_user_by_nick(nick): return {}
def set_private_profile(user_id,value): pass
def set_admin_photo(user_id,url): pass
def get_admin_photo_db(user_id): return None
def set_collection_name(user_id,name): pass
def get_collection_name(user_id): return "Minha Coleção"
def set_last_pedido(user_id,ts): pass
def try_set_nick(user_id,nick): return True

# =========================================
# LEVEL
# =========================================

def increment_commands_and_level(user_id,nick_fallback,per_level):
    return {
        "commands":0,
        "level":1,
        "nick_safe":nick_fallback,
        "old_level":1
    }

# =========================================
# COINS
# =========================================

def add_coin(user_id,amount): pass
def get_user_coins(user_id): return 0
def get_top_by_level(): return []
def try_spend_coins(user_id,amount): return True
def spend_coins_and_add_giro(user_id,price): return True

# =========================================
# COLLECTION
# =========================================

def count_collection(user_id): return 0
def get_collection_page(user_id,page,per_page=20): return []
def user_has_character(user_id,char_id): return False
def add_character_to_collection(user_id,char_id,name,image,anime): pass
def get_collection_character_full(user_id,char_id): return None
def get_collection_character(user_id,char_id): return None
def remove_one_from_collection(user_id,char_id): pass
def set_favorite_from_collection(user_id,name,image): pass
def clear_favorite(user_id): pass
def list_collection_cards(user_id): return []
def get_collection_quantities(user_id,char_ids): return {}

# =========================================
# TRADES
# =========================================

def create_trade(a,b,c,d): return 0
def get_trade_by_id(trade_id): return None
def get_latest_pending_trade_for_to_user(user_id): return None
def mark_trade_status(trade_id,status): pass
def swap_trade_execute(*args): return True
def list_pending_trades_for_user(user_id): return []

# =========================================
# CACHE TOP ANIME
# =========================================

def top_cache_last_updated(): return 0
def replace_top_anime_cache(*args): pass
def get_top_anime_list(): return []

# =========================================
# DADO
# =========================================

def create_dice_roll(*args): return 0
def get_dice_roll(*args): return None
def set_dice_roll_status(*args): pass
def try_set_dice_roll_status(*args): return True
def get_dado_state(user_id): return {"b":0,"s":0}
def set_dado_state(*args): pass
def inc_dado_balance(*args): pass

# =========================================
# EXTRA DADO
# =========================================

def get_extra_dado(user_id): return 0
def add_extra_dado(user_id,amount): pass
def consume_extra_dado(user_id): pass

# =========================================
# DAILY
# =========================================

def claim_daily_reward(user_id):
    coins=random.randint(1,3)
    return {"type":"coins","amount":coins}

# =========================================
# IMAGE / BAN
# =========================================

def set_global_character_image(*args): pass
def get_global_character_image(*args): return None
def delete_global_character_image(*args): pass
def ban_character(*args): pass
def unban_character(*args): pass
def is_banned_character(*args): return False

# =========================================
# RANKING / STATS
# =========================================

def get_top_by_coins(): return []
def get_top_by_collection(): return []
def get_user_stats(user_id): return {}
def list_user_achievement_keys(user_id): return []
def grant_achievements_and_reward(user_id,keys): return 0

# =========================================
# TOP500 JOB
# =========================================

def top500_job_create(): return 0
def top500_job_get(*args): return None
def top500_job_latest(): return None
def top500_job_set_status(*args): pass
def top500_job_checkpoint(*args): pass
def top500_job_mark_done(*args): pass
def top500_job_read_top_list(): return []

# =========================================
# TOP500 POOL
# =========================================

def create_characters_pool_tables(): pass
def pool_import_top500_txt(path): pass
def pool_add_character(*args): pass
def pool_delete_character(*args): pass
def pool_set_active(*args): pass
def pool_random_character(): return None
def delete_one_character_for_coin(*args): pass
