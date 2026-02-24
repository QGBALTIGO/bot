db = sqlite3.connect("bot.db", check_same_thread=False)
cursor = db.cursor()

# =========================
# USUÁRIOS
# =========================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    nick TEXT,
    collection_name TEXT,
    fav_name TEXT,
    fav_image TEXT,
    commands INTEGER DEFAULT 0,
    last_pedido INTEGER DEFAULT 0
)
""")

# =========================
# LEVEL / XP
# =========================
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_levels (
    user_id INTEGER PRIMARY KEY,
@@ -46,7 +51,9 @@ def adicionar_xp(user_id: int):

    db.commit()

# =========================
# SPAWN ATIVO
# =========================
cursor.execute("""
CREATE TABLE IF NOT EXISTS active_spawns (
    chat_id INTEGER PRIMARY KEY,
@@ -57,7 +64,9 @@ def adicionar_xp(user_id: int):
)
""")

# =========================
# COLEÇÃO
# =========================
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_collection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
@@ -70,7 +79,3 @@ def adicionar_xp(user_id: int):
""")

db.commit()
