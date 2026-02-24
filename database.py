import os
import mysql.connector
from urllib.parse import urlparse

# pega a URL do Railway
url = urlparse(os.getenv("DATABASE_URL"))

db = mysql.connector.connect(
    host=url.hostname,
    user=url.username,
    password=url.password,
    database=url.path[1:],  # remove a /
    port=url.port
)

cursor = db.cursor(dictionary=True)

# cria tabela automaticamente
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
