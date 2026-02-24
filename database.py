import os
import mysql.connector




db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
@@ -15,24 +12,6 @@

cursor = db.cursor(dictionary=True)



















def get_user(user_id: int, first_name: str):
    cursor.execute(
        "SELECT * FROM users WHERE user_id = %s",
