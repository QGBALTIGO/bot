import os
import mysql.connector

# ===============================
# CONEXÃO COM O MYSQL (RAILWAY)
# ===============================
db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    autocommit=True  # 🔒 garante que não perca dados
)

cursor = db.cursor(dictionary=True)

# ===============================
# TABELA DE USUÁRIOS
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
# FUNÇÕES UTILITÁRIAS
# ===============================

def get_user(user_id: int, first_name: str):
    """
    Busca o usuário.
    Se não existir, cria automaticamente.
    """
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


def add_command_and_level(user_id: int):
    """
    Soma 1 comando e recalcula o nível.
    """
    cursor.execute("""
        UPDATE users
        SET
            commands = commands + 1,
            level = FLOOR(commands / 100) + 1
        WHERE user_id = %s
    """, (user_id,))
