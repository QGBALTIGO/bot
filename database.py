import os
import mysql.connector
from urllib.parse import urlparse

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrada. Verifique as variáveis no Railway.")

url = urlparse(DATABASE_URL)

db = mysql.connector.connect(
    host=url.hostname,
    user=url.username,
    password=url.password,
    database=url.path.lstrip("/"),
    port=url.port or 3306  # 👈 fallback de segurança
)

cursor = db.cursor(dictionary=True)

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    nick VARCHAR(255),
    fav_character_name TEXT,
    fav_character_image TEXT,
    xp INT DEFAULT 0,
    level INT DEFAULT 1
)
""")

db.commit()
