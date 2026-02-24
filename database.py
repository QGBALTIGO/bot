import sqlite3

db = sqlite3.connect("bot.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    nick TEXT,
    fav_name TEXT,
    fav_image TEXT,
    commands INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_pedido INTEGER DEFAULT 0
)
""")

db.commit()


CREATE TABLE IF NOT EXISTS user_levels (
    user_id INTEGER PRIMARY KEY,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0
);
# Atualiza XP
cursor.execute("SELECT xp FROM user_levels WHERE user_id = ?", (user_id,))
data = cursor.fetchone()

if data:
    xp = data[0] + 1
    level = (xp // 5) + 1
    cursor.execute("UPDATE user_levels SET xp = ?, level = ? WHERE user_id = ?", (xp, level, user_id))
else:
    cursor.execute("INSERT INTO user_levels (user_id, xp, level) VALUES (?, ?, ?)", (user_id, 1, 1))
