import os
from urllib.parse import urlparse

DATABASE_URL = os.getenv("DATABASE_URL")

print("DATABASE_URL =", DATABASE_URL)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL NÃO CHEGOU NO BOT")

url = urlparse(DATABASE_URL)

print("HOST:", url.hostname)
print("PORT:", url.port)
print("DB:", url.path)
