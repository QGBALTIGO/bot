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
