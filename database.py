import mysql.connector
import os

db = mysql.connector.connect(
    host=os.getenv("MYSQLHOST"),
    user=os.getenv("MYSQLUSER"),
    password=os.getenv("MYSQLPASSWORD"),
    database=os.getenv("MYSQLDATABASE"),
    port=int(os.getenv("MYSQLPORT", 3306))
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
