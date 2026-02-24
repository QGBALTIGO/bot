import os
import mysql.connector

# ===============================
# CONEXÃO COM MYSQL (RAILWAY)
# ===============================
db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    autocommit=True
)

cursor = db.cursor(dictionary=True)

# ===============================
# TABELA USERS (SEM ÍNDICES AQUI)
# ===============================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    nick VARCHAR(255),
    fav_character_name TEXT,
    fav_character_image TEXT,
    commands INT DEFAULT 0,
    level INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ===============================
# FUNÇÕES
# ===============================
def get_user(user_id: int, first_name: str):
    cursor.execute(
        "SELECT * FROM users WHERE user_id = %s",
        (user_id,)
    )
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, nick) VALUES (%s, %s)",
            (user_id, first_name)
        )

        cursor.execute(
            "SELECT * FROM users WHERE user_id = %s",
            (user_id,)
        )
        user = cursor.fetchone()

    return user


def add_command(user_id: int):
    cursor.execute("""
        UPDATE users
        SET commands = commands + 1,
            level = FLOOR(commands / 100) + 1
        WHERE user_id = %s
    """, (user_id,))
