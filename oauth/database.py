import sqlite3

DB_NAME = "users.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id TEXT PRIMARY KEY,
            anilist_token TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_user_token(telegram_id, token):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR REPLACE INTO users (telegram_id, anilist_token) VALUES (?, ?)",
        (telegram_id, token)
    )

    conn.commit()
    conn.close()


def get_user_token(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT anilist_token FROM users WHERE telegram_id = ?",
        (telegram_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        return row[0]
    return None