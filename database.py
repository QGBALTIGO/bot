import sqlite3

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    user_id INTEGER PRIMARY KEY,
    nick TEXT,
    nivel INTEGER,
    xp INTEGER
)
""")

conn.commit()

import sqlite3

# conecta (ou cria) o banco
db = sqlite3.connect("database.db", check_same_thread=False)
cursor = db.cursor()

# ===============================
# TABELA DE USUÁRIOS
# ===============================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    nick TEXT,
    coins INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    commands INTEGER DEFAULT 0,
    last_gacha INTEGER DEFAULT 0
)
""")

# ===============================
# TABELA DE PERSONAGENS CAPTURADOS
# ===============================
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    character_id INTEGER,
    character_name TEXT,
    anime TEXT,
    rarity TEXT,
    quantity INTEGER DEFAULT 1
)
""")

db.commit()
