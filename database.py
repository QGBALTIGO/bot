import sqlite3

# ==================================================
# CONEXÃO COM O BANCO
# ==================================================
db = sqlite3.connect("bot.db", check_same_thread=False)
cursor = db.cursor()

# ==================================================
# TABELA PRINCIPAL DE USUÁRIOS (UNIFICADA)
# ==================================================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,              -- telegram_id
    nick TEXT,                                -- nickname do usuário
    collection_name TEXT,                     -- nome da coleção (se usar)
    fav_character_name TEXT,                  -- personagem favorito
    fav_character_image TEXT,                 -- imagem do favorito
    commands INTEGER DEFAULT 0,               -- comandos usados
    level INTEGER DEFAULT 1,                  -- nível atual
    xp INTEGER DEFAULT 0,                     -- XP acumulado
    last_pedido INTEGER DEFAULT 0             -- cooldown / controle
)
""")

# ==================================================
# SPAWN ATIVO (EVENTOS / DROP)
# ==================================================
cursor.execute("""
CREATE TABLE IF NOT EXISTS active_spawns (
    chat_id INTEGER PRIMARY KEY,
    character_id INTEGER,
    character_name TEXT,
    image TEXT,
    expires_at INTEGER
)
""")

# ==================================================
# COLEÇÃO DE PERSONAGENS
# ==================================================
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_collection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    character_id INTEGER,
    character_name TEXT,
    image TEXT,
    captured_at INTEGER
)
""")

db.commit()
