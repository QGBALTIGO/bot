import sqlite3

db = sqlite3.connect("bot.db", check_same_thread=False)
cursor = db.cursor()

# ===== USUÁRIOS =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    nick TEXT,
    fav_name TEXT,
    fav_image TEXT,
    commands INTEGER DEFAULT 0,
    last_pedido INTEGER DEFAULT 0
)
""")

# ===== LEVEL / XP =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_levels (
    user_id INTEGER PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1
)
""")

def adicionar_xp(user_id: int):
    cursor.execute(
        "SELECT xp FROM user_levels WHERE user_id = ?",
        (user_id,)
    )
    data = cursor.fetchone()

    if data:
        xp = data[0] + 1
        level = (xp // 5) + 1
        cursor.execute(
            "UPDATE user_levels SET xp = ?, level = ? WHERE user_id = ?",
            (xp, level, user_id)
        )
    else:
        cursor.execute(
            "INSERT INTO user_levels (user_id, xp, level) VALUES (?, ?, ?)",
            (user_id, 1, 1)
        )

    db.commit()

# ===== SPAWN ATIVO =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS active_spawns (
    chat_id INTEGER PRIMARY KEY,
    character_id INTEGER,
    character_name TEXT,
    image TEXT,
    expires_at INTEGER
)
""")

# ===== COLEÇÃO =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_collection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    character_id INTEGER,
    character_name TEXT,
    image TEXT,
    captured_at INTEGER
)
""")

db.commit()

cursor.execute("ALTER TABLE users ADD COLUMN collection_name TEXT")
cursor.execute("ALTER TABLE users ADD COLUMN fav_image TEXT")
db.commit()
