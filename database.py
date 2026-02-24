import sqlite3

# ================= CONEXÃO =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cursor = db.cursor()

# ================= TABELA USERS =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    nick TEXT,
    collection_name TEXT,
    fav_name TEXT,
    fav_image TEXT,
    coins INTEGER DEFAULT 0,
    commands INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0,
    last_dado INTEGER DEFAULT 0,
    last_pedido INTEGER DEFAULT 0
)
""")

# ================= TABELA USER COLLECTION =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_collection (
    user_id INTEGER,
    character_id INTEGER,
    character_name TEXT,
    image TEXT,
    quantity INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, character_id)
)
""")

# ================= TABELA SPAWNS ATIVOS =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS active_spawns (
    chat_id INTEGER PRIMARY KEY,
    character_id INTEGER,
    character_name TEXT,
    image TEXT,
    expires_at INTEGER
)
""")

# ================= TABELA USER LEVELS (LEGADO / COMPAT) =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_levels (
    user_id INTEGER PRIMARY KEY,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0
)
""")

db.commit()
