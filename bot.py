from telethon import TelegramClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import time
import aiohttp
from telegram.ext import MessageHandler, CallbackQueryHandler, filters
from database import db, cursor

# ===== ANTI-SPAM CONFIG =====
import time

ANTI_SPAM_TIME = 5  # segundos
last_command_time = {}

def anti_spam(user_id: int) -> bool:
    agora = time.time()

    if user_id in last_command_time:
        if agora - last_command_time[user_id] < ANTI_SPAM_TIME:
            return False

    last_command_time[user_id] = agora
    return True

# ===== DADOS =====
api_id = 34116600
api_hash = "b8f22be457ce73f65fad82315073fbc3"
BOT_TOKEN = "8001392073:AAEW64SRZI7BIY6l8reeKnNONu-6gjLt0Sg"
CANAL_ANIME = "Centraldeanimes_Baltigo"
CANAL_MANGA = "MangasBrasil"
CANAL_PEDIDOS = -1003895811362  # ID do canal fechado

# ===== TELETHON =====
client = TelegramClient("sessao_busca", api_id, api_hash)
async def buscar_post(canal, termo):
    async for msg in client.iter_messages(canal, search=termo):
        return msg.id
    return None

# ===============================
# 🔒 CANAL OBRIGATÓRIO
# ===============================
CANAL_OBRIGATORIO = -1003818375955  # SEU CANAL

# ===============================
# 🔐 VERIFICA SE USUÁRIO ESTÁ NO CANAL
# ===============================
async def usuario_no_canal(bot, user_id: int) -> bool:
    try:
        membro = await bot.get_chat_member(CANAL_OBRIGATORIO, user_id)
        return membro.status in ["member", "administrator", "creator"]
    except:
        return False

# ===============================
# ⛔ BLOQUEIO SE NÃO FOR MEMBRO
# ===============================
async def checar_canal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    esta_no_canal = await usuario_no_canal(context.bot, user_id)

    if not esta_no_canal:
        teclado = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📢 Entrar no canal",
                    url="https://t.me/SourcerBaltigo"
                )
            ]
        ])
        await update.message.reply_html(
            "🚫 <b>Acesso bloqueado</b>\n\n"
            "Para usar este bot, você precisa estar no nosso canal oficial 👇\n\n"
            "✅ Após entrar, volte e use o comando novamente.",
            reply_markup=teclado
        )
        return False

    return True
    
# ===== LOGIN =====
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def login(update, context):
    telegram_id = update.effective_user.id

    url = (
        "https://anilist.co/api/v2/oauth/authorize"
        "?client_id=36358"
        "&redirect_uri=https://loginbot-production-eb95.up.railway.app/callback"
        "&response_type=code"
        f"&state={telegram_id}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Conectar com AniList", url=url)]
    ])

    await update.message.reply_text(
        "🔑 Clique para conectar sua conta AniList:",
        reply_markup=keyboard
    )

logging.basicConfig(level=logging.INFO)

# ==================================================
# BANCO DE DADOS (SQLite – PERSISTENTE)
# ==================================================
db = sqlite3.connect("gacha.db", check_same_thread=False)
cursor = db.cursor()

# ---- USERS
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    nick TEXT,
    coins INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    commands INTEGER DEFAULT 0
)
""")

# ---- GIROS
cursor.execute("""
CREATE TABLE IF NOT EXISTS spins (
    user_id INTEGER PRIMARY KEY,
    spins INTEGER DEFAULT 1,
    last_spin INTEGER DEFAULT 0
)
""")

# ---- COLEÇÃO
cursor.execute("""
CREATE TABLE IF NOT EXISTS collection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    character_id INTEGER,
    character_name TEXT,
    anime_name TEXT,
    rarity TEXT,
    image TEXT,
    quantity INTEGER DEFAULT 1
)
""")

db.commit()

# ==================================================
# PERFIL DO USUÁRIO
# ==================================================
def get_user(user_id: int, name: str):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, nick) VALUES (?, ?)",
            (user_id, name)
        )
        db.commit()

    return True

# ==================================================
# SISTEMA DE GIROS (4 HORAS)
# ==================================================
SPIN_INTERVAL = 4 * 60 * 60
MAX_SPINS = 12

def atualizar_giros(user_id: int):
    agora = int(time.time())

    cursor.execute(
        "SELECT spins, last_spin FROM spins WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO spins (user_id, spins, last_spin) VALUES (?, ?, ?)",
            (user_id, 1, agora)
        )
        db.commit()
        return 1

    spins, last_spin = row
    ganho = (agora - last_spin) // SPIN_INTERVAL

    if ganho > 0:
        spins = min(MAX_SPINS, spins + ganho)
        last_spin = last_spin + ganho * SPIN_INTERVAL

        cursor.execute(
            "UPDATE spins SET spins = ?, last_spin = ? WHERE user_id = ?",
            (spins, last_spin, user_id)
        )
        db.commit()

    return spins

# ==================================================
# ANI LIST
# ==================================================
ANILIST_API = "https://graphql.anilist.co"

async def buscar_animes_populares():
    query = """
    query {
      Page(page: 1, perPage: 50) {
        media(type: ANIME, sort: POPULARITY_DESC, isAdult: false) {
          id
          title { romaji }
          coverImage { large }
        }
      }
    }
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query},
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            data = await resp.json()

    animes = data["data"]["Page"]["media"]
    random.shuffle(animes)
    return animes[:4]

async def buscar_personagens(anime_id: int):
    query = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        title { romaji }
        characters(perPage: 50) {
          nodes {
            id
            name { full }
            image { large }
            favourites
          }
        }
      }
    }
    """
    variables = {"id": anime_id}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            data = await resp.json()

    return data["data"]["Media"]

# ==================================================
# RARIDADES
# ==================================================
RARIDADES = [
    ("Comum", 55),
    ("Raro", 25),
    ("Épico", 12),
    ("Lendário", 6),
    ("Mítico", 2),
]

def sortear_raridade():
    r = random.randint(1, 100)
    total = 0
    for nome, chance in RARIDADES:
        total += chance
        if r <= total:
            return nome

def sortear_personagem(lista, raridade):
    lista = sorted(lista, key=lambda x: x["favourites"] or 0, reverse=True)
    total = len(lista)

    if raridade == "Comum":
        pool = lista[int(total*0.4):]
    elif raridade == "Raro":
        pool = lista[int(total*0.2):int(total*0.4)]
    elif raridade == "Épico":
        pool = lista[int(total*0.05):int(total*0.2)]
    elif raridade == "Lendário":
        pool = lista[:int(total*0.05)]
    else:
        pool = lista[:1]

    return random.choice(pool)

# ==================================================
# SALVAR PERSONAGEM
# ==================================================
def salvar_personagem(user_id, personagem, anime, raridade):
    cursor.execute("""
        SELECT id FROM collection
        WHERE user_id = ? AND character_id = ?
    """, (user_id, personagem["id"]))

    row = cursor.fetchone()
    if row:
        cursor.execute(
            "UPDATE collection SET quantity = quantity + 1 WHERE id = ?",
            (row[0],)
        )
        duplicata = True
    else:
        cursor.execute("""
            INSERT INTO collection
            (user_id, character_id, character_name, anime_name, rarity, image)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            personagem["id"],
            personagem["name"]["full"],
            anime,
            raridade,
            personagem["image"]["large"]
        ))
        duplicata = False

    db.commit()
    return duplicata

# ==================================================
# COMANDO /gacha
# ==================================================
async def gacha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.first_name)

    giros = atualizar_giros(user.id)
    if giros <= 0:
        await update.message.reply_text("⏳ Sem giros no momento.")
        return

    cursor.execute(
        "UPDATE spins SET spins = spins - 1 WHERE user_id = ?",
        (user.id,)
    )
    db.commit()

    animes = await buscar_animes_populares()
    keyboard = []

    for anime in animes:
        keyboard.append([
            InlineKeyboardButton(
                anime["title"]["romaji"],
                callback_data=f"anime:{anime['id']}"
            )
        ])

    await update.message.reply_text(
        "🎰 Escolha um anime:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================================================
# CALLBACK – ESCOLHA DO ANIME
# ==================================================
async def escolher_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    anime_id = int(query.data.split(":")[1])
    media = await buscar_personagens(anime_id)

    raridade = sortear_raridade()
    personagem = sortear_personagem(
        media["characters"]["nodes"],
        raridade
    )

    duplicata = salvar_personagem(
        query.from_user.id,
        personagem,
        media["title"]["romaji"],
        raridade
    )

    texto = (
        f"🎉 **CAPTURA!**\n\n"
        f"👤 {personagem['name']['full']}\n"
        f"📺 {media['title']['romaji']}\n"
        f"⭐ {raridade}\n"
    )

    if duplicata:
        texto += "\n♻️ Personagem repetido!"

    await query.message.reply_photo(
        photo=personagem["image"]["large"],
        caption=texto,
        parse_mode="Markdown"
    )

# ==================================================
# CONFIGURAÇÃO ANI LIST
# ==================================================
ANILIST_API = "https://graphql.anilist.co"

# ==================================================
# ==================================================
# CONFIGURAÇÃO DE ADMINS
# ==================================================

ADMINS = {
    1852596083, 6978699297, 5940138617, 7722180159, # coloque seus IDs aqui
}

ADMIN_PHOTOS = {
    # user_id: "https://link-da-imagem.jpg"
}

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def get_admin_photo(user_id: int):
    return ADMIN_PHOTOS.get(user_id)

# ==================================================
# /ADMINFOTO — DEFINIR FOTO PERSONALIZADA DE ADMIN
# ==================================================
async def adminfoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_html(
            "⛔ <b>Acesso negado</b>\n\n"
            "Este comando é exclusivo para <b>admins</b>."
        )
        return

    if not context.args:
        await update.message.reply_html(
            "👑 <b>Foto de Admin</b>\n\n"
            "Envie um link direto de imagem:\n"
            "<code>/adminfoto https://imagem.jpg</code>\n\n"
            "📌 Essa imagem será a <b>capa do seu perfil</b>."
        )
        return

    url = context.args[0]
    ADMIN_PHOTOS[user_id] = url

    await update.message.reply_photo(
        photo=url,
        caption=(
            "👑 <b>Foto de admin definida!</b>\n\n"
            "✨ Agora seu perfil usará essa imagem.\n"
            "👀 Veja com <code>/perfil</code>"
        ),
        parse_mode="HTML"
    )

# ==================================================
# BANCO DE DADOS (MEMÓRIA)
# ==================================================
USERS = {}

def get_user(user_id: int, name: str):
    if user_id not in USERS:
        USERS[user_id] = {
            "nick": name,
            "fav_character": None,
            "commands": 0,
            "level": 1
        }
    return USERS[user_id]

# ==================================================
# SISTEMA DE NÍVEL
# ==================================================
COMANDOS_POR_NIVEL = 100

async def registrar_comando(update: Update):
    user = get_user(
        update.effective_user.id,
        update.effective_user.first_name
    )

    user["commands"] += 1
    novo_nivel = (user["commands"] // COMANDOS_POR_NIVEL) + 1

    if novo_nivel > user["level"]:
        user["level"] = novo_nivel

        mensagem = (
            "🎉 <b>LEVEL UP!</b>\n\n"
            f"✨ Parabéns <b>{user['nick']}</b>!\n"
            f"⬆️ Você alcançou o <b>Nível {novo_nivel}</b>!\n\n"
            "🚀 Continue usando o bot!"
        )

        if update.message:
            await update.message.reply_html(mensagem)
        else:
            await update.effective_user.send_message(
                mensagem,
                parse_mode="HTML"
            )

# ==================================================
# BUSCAR PERSONAGEM NO ANILIST
# ==================================================
async def buscar_personagem(nome: str):
    query = """
    query ($search: String) {
      Character(search: $search) {
        id
        name { full }
        image { large }
      }
    }
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": {"search": nome}},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            data = await resp.json()
            return data.get("data", {}).get("Character")

# ==================================================
# /FAVORITAR
# ==================================================
async def favoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    await registrar_comando(update)

    if not context.args:
        await update.message.reply_html(
            "❤️ <b>Favoritar personagem</b>\n\n"
            "Use o nome <b>COMPLETO</b>:\n"
            "<code>/favoritar Monkey D. Luffy</code>"
        )
        return

    user = get_user(update.effective_user.id, update.effective_user.first_name)

    if user["fav_character"]:
        await update.message.reply_html(
            "⚠️ Você já tem um personagem favorito.\n"
            "Use <code>/desfavoritar</code> para trocar."
        )
        return

    nome = " ".join(context.args)
    personagem = await buscar_personagem(nome)

    if not personagem:
        await update.message.reply_html(
            "❌ <b>Personagem não encontrado</b>\n\n"
            "Verifique se o nome está completo e correto."
        )
        return

    user["fav_character"] = {
        "name": personagem["name"]["full"],
        "image": personagem["image"]["large"]
    }

    await update.message.reply_photo(
        photo=personagem["image"]["large"],
        caption=(
            "❤️ <b>PERSONAGEM FAVORITADO!</b>\n\n"
            f"🧧 <b>{personagem['name']['full']}</b>\n\n"
            "🎴 Agora ele é a capa do seu perfil!"
        ),
        parse_mode="HTML"
    )

# ==================================================
# /DESFAVORITAR
# ==================================================
async def desfavoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    await registrar_comando(update)

    user = USERS.get(update.effective_user.id)

    if not user or not user["fav_character"]:
        await update.message.reply_html(
            "💔 Você não tem personagem favorito."
        )
        return

    user["fav_character"] = None
    await update.message.reply_html("💔 Personagem removido.")

# ==================================================
# /NICK
# ==================================================
async def nick(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    await registrar_comando(update)

    if not context.args:
        await update.message.reply_html(
            "✏️ Use:\n<code>/nick SeuNome</code>"
        )
        return

    user = get_user(update.effective_user.id, update.effective_user.first_name)
    user["nick"] = " ".join(context.args)

    await update.message.reply_html(
        f"✨ Nick atualizado para <b>{user['nick']}</b>"
    )

# ==================================================
# /PERFIL
# ==================================================
async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    await registrar_comando(update)

    user_id = update.effective_user.id
    user = get_user(user_id, update.effective_user.first_name)

    fav = user["fav_character"]
    admin = is_admin(user_id)
    admin_photo = get_admin_photo(user_id)

    titulo = "👤 | <i>Admin</i>" if admin else "👤 | <i>User</i>"

    texto = (
        "🎴 <b>PERFIL DO USUÁRIO</b>\n\n"
        f"{titulo}: <b>{user['nick']}</b>\n\n"
        f"📚 | <i>Coleção</i>: <b>0</b>\n"
        f"⭐ | <i>Nível</i>: <b>{user['level']}</b>\n\n"
        "❤️ <i>Favorito</i>:\n"
    )

    texto += f"🧧 <b>{fav['name']} ✨</b>" if fav else "— Nenhum favorito"

    foto = admin_photo or (fav["image"] if fav else None)

    if foto:
        await update.message.reply_photo(
            photo=foto,
            caption=texto,
            parse_mode="HTML"
        )
    else:
        await update.message.reply_html(texto)

# ==================================================
# /NIVEL
# ==================================================
async def nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    await registrar_comando(update)

    user = get_user(update.effective_user.id, update.effective_user.first_name)

    comandos = user["commands"]
    nivel_atual = user["level"]

    proximo = nivel_atual * COMANDOS_POR_NIVEL
    faltam = max(proximo - comandos, 0)

    await update.message.reply_html(
        "📊 <b>SEU PROGRESSO</b>\n\n"
        f"👤 <b>{user['nick']}</b>\n\n"
        f"⭐ <i>Nível</i>: <b>{nivel_atual}</b>\n"
        f"⌨️ <i>Comandos usados</i>: <b>{comandos}</b>\n"
        f"⏳ <i>Faltam</i>: <b>{faltam}</b> comandos"
    )

# ===== ANILIST =====
ANILIST_API = "https://graphql.anilist.co"

async def buscar_multiplos_anilist(nome: str):
    query = """
    query ($search: String) {
      Page(perPage: 6) {
        media(search: $search, type: ANIME) {
          id
          siteUrl
          title {
            romaji
            english
            native
          }
          status
          averageScore
          startDate {
            day
            month
            year
          }
          genres
          trailer {
            site
            id
          }
        }
      }
    }
    """
    variables = {"search": nome}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANILIST_API,
                json={"query": query, "variables": variables},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data["data"]["Page"]["media"]
    except Exception as e:
        print("Erro AniList:", e)
        return []

# ===== COMANDO INFO =====
async def infoanime(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Faltou o nome!</b>\n\n"
            "Use assim:\n"
            "<code>/info nome do anime</code>\n\n"
            "📌 Exemplo:\n"
            "<code>/info Naruto</code>"
        )
        return

    nome = " ".join(context.args)
    msg = await update.message.reply_text("🔎 Buscando versões no AniList...")

    resultados = await buscar_multiplos_anilist(nome)
    if not resultados:
        await msg.edit_text("🚫 Não encontrei nenhum anime com esse nome.")
        return

    botoes = []
    for media in resultados:
        titulo = (
            media["title"]["english"]
            or media["title"]["romaji"]
            or media["title"]["native"]
        )
        botoes.append([
            InlineKeyboardButton(
                titulo,
                callback_data=f"info_anime:{media['id']}"
            )
        ])

    await msg.edit_text(
        "📌 <b>Encontrei várias versões</b>\n\n"
        "Escolha qual você quer ver:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

# ===== BUSCAR POR ID =====
async def buscar_anilist_por_id(anime_id: int):
    query = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        siteUrl
        title {
          romaji
          english
          native
        }
        status
        averageScore
        startDate {
          day
          month
          year
        }
        genres
        trailer {
          site
          id
        }
      }
    }
    """
    variables = {"id": anime_id}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables}
        ) as resp:
            data = await resp.json()
            return data["data"]["Media"]

# ===== CALLBACK =====
from telegram.ext import CallbackQueryHandler

async def callback_info_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    anime_id = int(query.data.split(":")[1])
    media = await buscar_anilist_por_id(anime_id)

    # 🔥 A ÚNICA ADIÇÃO PEDIDA
    await query.message.delete()

    titulo = (
        media["title"]["english"]
        or media["title"]["romaji"]
        or media["title"]["native"]
    )
    score = media.get("averageScore", "N/A")
    status = media.get("status", "N/A")
    genres = ", ".join(media.get("genres", [])) or "N/A"
    data = media.get("startDate", {})
    start_date = f"{data.get('day','?')}/{data.get('month','?')}/{data.get('year','?')}"

    texto = (
        f"<b>{titulo}</b>\n\n"
        f"<b>Pontuação:</b> <code>{score}</code>\n"
        f"<b>Situação:</b> <code>{status}</code>\n"
        f"<b>Gênero:</b> <code>{genres}</code>\n"
        f"<b>Lançamento:</b> <code>{start_date}</code>"
    )

    imagem = f"https://img.anili.st/media/{media['id']}"

    botoes = []
    trailer = media.get("trailer")
    if trailer and trailer["site"] == "youtube":
        botoes.append([
            InlineKeyboardButton(
                "🎬 Trailer",
                url=f"https://www.youtube.com/watch?v={trailer['id']}"
            )
        ])

    botoes.append([
        InlineKeyboardButton("📖 Descrição", url=media["siteUrl"])
    ])

    await context.bot.send_photo(
        chat_id=query.message.chat.id,
        photo=imagem,
        caption=texto,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

# ===== ANILIST MANGA =====
ANILIST_API = "https://graphql.anilist.co"

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

# ===== BUSCAR MÚLTIPLOS MANGÁS =====
async def buscar_multiplos_anilist_manga(nome: str):
    query = """
    query ($search: String) {
      Page(perPage: 6) {
        media(search: $search, type: MANGA) {
          id
          siteUrl
          title {
            romaji
            english
            native
          }
          status
          averageScore
          startDate {
            day
            month
            year
          }
          genres
        }
      }
    }
    """
    variables = {"search": nome}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANILIST_API,
                json={"query": query, "variables": variables},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data["data"]["Page"]["media"]
    except Exception as e:
        print("Erro AniList Manga:", e)
        return []

# ===== BUSCAR MANGÁ POR ID =====
async def buscar_anilist_manga_por_id(manga_id: int):
    query = """
    query ($id: Int) {
      Media(id: $id, type: MANGA) {
        id
        siteUrl
        title {
          romaji
          english
          native
        }
        status
        averageScore
        startDate {
          day
          month
          year
        }
        genres
      }
    }
    """
    variables = {"id": manga_id}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables}
        ) as resp:
            data = await resp.json()
            return data["data"]["Media"]

# ===== COMANDO INFOMANGA =====
async def infomanga(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Faltou o nome!</b>\n\n"
            "Use assim:\n"
            "<code>/infomanga nome do mangá</code>\n\n"
            "📌 Exemplo:\n"
            "<code>/infomanga Naruto</code>"
        )
        return

    nome = " ".join(context.args)
    msg = await update.message.reply_text("🔎 Buscando versões no AniList...")

    resultados = await buscar_multiplos_anilist_manga(nome)
    if not resultados:
        await msg.edit_text("🚫 Não encontrei nenhum mangá com esse nome.")
        return

    botoes = []
    for media in resultados:
        titulo = (
            media["title"]["english"]
            or media["title"]["romaji"]
            or media["title"]["native"]
        )
        botoes.append([
            InlineKeyboardButton(
                titulo,
                callback_data=f"info_manga:{media['id']}"
            )
        ])

    await msg.edit_text(
        "📌 <b>Encontrei várias versões</b>\n\n"
        "Escolha qual você quer ver:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

# ===== CALLBACK INFO MANGA =====
async def callback_info_manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    manga_id = int(query.data.split(":")[1])
    media = await buscar_anilist_manga_por_id(manga_id)

    # 🔥 APAGA a mensagem com os botões
    await query.message.delete()

    titulo = (
        media["title"]["english"]
        or media["title"]["romaji"]
        or media["title"]["native"]
    )
    score = media.get("averageScore", "N/A")
    status = media.get("status", "N/A")
    genres = ", ".join(media.get("genres", [])) or "N/A"
    data = media.get("startDate", {})
    start_date = f"{data.get('day','?')}/{data.get('month','?')}/{data.get('year','?')}"

    texto = (
        f"<b>{titulo}</b>\n\n"
        f"<b>Pontuação:</b> <code>{score}</code>\n"
        f"<b>Situação:</b> <code>{status}</code>\n"
        f"<b>Gênero:</b> <code>{genres}</code>\n"
        f"<b>Lançamento:</b> <code>{start_date}</code>"
    )

    imagem = f"https://img.anili.st/media/{media['id']}"

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Ver no AniList", url=media["siteUrl"])
        ]
    ])

    await query.message.reply_photo(
        photo=imagem,
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado
    )

# ===== ANILIST PERSONAGENS =====
ANILIST_API = "https://graphql.anilist.co"

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# ===== BUSCAR MÚLTIPLOS PERSONAGENS =====
async def buscar_multiplos_personagens(nome: str):
    query = """
    query ($search: String) {
      Page(perPage: 6) {
        characters(search: $search) {
          id
          name {
            full
          }
          image {
            large
          }
        }
      }
    }
    """
    variables = {"search": nome}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables}
        ) as resp:
            data = await resp.json()
            return data["data"]["Page"]["characters"]


# ===== BUSCAR PERSONAGEM POR ID =====
async def buscar_personagem_por_id(char_id: int):
    query = """
    query ($id: Int) {
      Character(id: $id) {
        id
        siteUrl
        name {
          full
        }
        image {
          large
        }
        gender
        dateOfBirth {
          day
          month
        }
        favourites
        media {
          edges {
            node {
              title {
                romaji
              }
              type
              startDate {
                year
              }
            }
            characterRole
          }
        }
      }
    }
    """
    variables = {"id": char_id}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables}
        ) as resp:
            data = await resp.json()
            return data["data"]["Character"]


# ===== COMANDO /perso =====
async def perso(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Faltou o nome!</b>\n\n"
            "Use assim:\n"
            "<code>/perso nome do personagem</code>\n\n"
            "📌 Exemplo:\n"
            "<code>/perso Luffy</code>"
        )
        return

    nome = " ".join(context.args)
    msg = await update.message.reply_text("🔎 Buscando personagens no AniList...")

    resultados = await buscar_multiplos_personagens(nome)
    if not resultados:
        await msg.edit_text("🚫 Não encontrei nenhum personagem.")
        return

    botoes = []
    for char in resultados:
        botoes.append([
            InlineKeyboardButton(
                char["name"]["full"],
                callback_data=f"info_perso:{char['id']}"
            )
        ])

    await msg.edit_text(
        "📌 <b>Encontrei várias opções</b>\n\n"
        "Escolha o personagem:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )


# ===== CALLBACK PERSONAGEM =====
async def callback_info_perso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    char_id = int(query.data.split(":")[1])
    personagem = await buscar_personagem_por_id(char_id)

    # 🔥 APAGA A MENSAGEM COM OS BOTÕES
    await query.message.delete()

    nome = personagem["name"]["full"]
    imagem = personagem["image"]["large"]

    genero = personagem.get("gender") or "Desconhecido"
    favs = personagem.get("favourites") or 0

    dob = personagem.get("dateOfBirth") or {}
    nascimento = (
        f"{dob.get('day','?')}/{dob.get('month','?')}"
        if dob.get("day") and dob.get("month")
        else "Desconhecido"
    )

    obra = "Desconhecida"
    tipo = "—"
    papel = "—"
    estreia = "—"

    if personagem["media"]["edges"]:
        edge = personagem["media"]["edges"][0]
        obra = edge["node"]["title"]["romaji"]
        tipo = edge["node"]["type"]
        papel = edge["characterRole"]
        estreia = edge["node"]["startDate"]["year"] or "—"

    texto = (
        f"<b>{nome}</b>\n\n"
        f"<b>Gênero:</b> <code>{genero}</code>\n"
        f"<b>Nascimento:</b> <code>{nascimento}</code>\n"
        f"<b>Favoritos:</b> <code>{favs}</code>\n\n"
        f"<b>Obra:</b> <code>{obra}</code>\n"
        f"<b>Tipo:</b> <code>{tipo}</code>\n"
        f"<b>Papel:</b> <code>{papel}</code>\n"
        f"<b>Estreia:</b> <code>{estreia}</code>"
    )

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔗 Ver no AniList",
                url=personagem["siteUrl"]
            )
        ]
    ])

    await query.message.chat.send_photo(
        photo=imagem,
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado
    )

# ===== COMANDO /pedido =====
async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    user_id = update.effective_user.id

    if not anti_spam(user_id):
        await update.message.reply_text(
            "⏳ Sem flood 😅\nTente novamente em alguns segundos."
        )
        return

    # ⛔ ANTIFLOOD
    if not pode_pedir(user_id):
        await update.message.reply_html(
            "⏳ <b>Pedido recente detectado</b>\n\n"
            "Você já fez um pedido nas últimas <b>12 horas</b>.\n"
            "🕒 Aguarde um pouco antes de enviar outro 🙂"
        )
        return

    # 👉 SEM TEXTO
    if not context.args:
        await update.message.reply_html(
            "📩 <b>Pedido de Anime ou Mangá</b>\n\n"
            "Use este comando para solicitar a adição de um conteúdo no canal.\n\n"
            "📝 <b>Como usar:</b>\n"
            "<code>/pedido nome do anime ou mangá</code>\n\n"
            "📌 <b>Exemplos:</b>\n"
            "<code>/pedido Naruto Shippuden</code>\n"
            "<code>/pedido Solo Leveling (mangá)</code>\n\n"
            "⏱️ <b>Limite:</b> 1 pedido a cada 12 horas"
        )
        return

    # 📌 TEXTO DO PEDIDO

    texto_pedido = " ".join(context.args)

async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    # 👉 1. SE NÃO TIVER TEXTO
    if not context.args:
        await update.message.reply_text(
            "📩 *Pedido de anime ou mangá*\n\n"
            "Use este comando para solicitar a adição de um anime ou mangá no canal 📚🎬\n\n"
            "📝 *Como usar:*\n"
            "`/pedido nome do anime ou mangá`\n\n"
            "📌 *Exemplo:*\n"
            "`/pedido Naruto Shippuden`"
            ,
            parse_mode="Markdown"
        )
        return

    texto_pedido = " ".join(context.args)
    user = update.effective_user

    # 📤 MENSAGEM QUE VAI PARA O CANAL FECHADO
    mensagem_canal = (
        "📥 <b>NOVO PEDIDO REGISTRADO</b>\n\n"
        f"👤 <b>Usuário:</b> {user.full_name}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n\n"
        f"📝 <b>Pedido:</b>\n"
        f"<i>{texto_pedido}</i>\n\n"
        "✅ <b>Status:</b> Pedido listado com sucesso!"
    )

    await context.bot.send_message(
        chat_id=CANAL_PEDIDOS,
        text=mensagem_canal,
        parse_mode="HTML"
    )

    # 📥 RESPOSTA PARA QUEM FEZ O PEDIDO
    await update.message.reply_html(
        f"✅ <b>{user.first_name}</b> [<code>{user.id}</code>]\n\n"
        f"Seu pedido <b>{texto_pedido}</b> já foi listado com sucesso!\n\n"
        "🕒 Agora é só aguardar que em breve estaremos postando.\n\n"
        "✨ Enquanto espera, aproveita para conhecer a central e os outros canais disponíveis!"
    )

# ===== BUSCAS =====
async def buscar_anime(nome):
    async for msg in client.iter_messages(CANAL_ANIME, search=nome):
        if msg.text:
            return f"https://t.me/{CANAL_ANIME}/{msg.id}"
    return None
async def buscar_manga(nome):
    async for msg in client.iter_messages(CANAL_MANGA, search=nome):
        if msg.text:
            return f"https://t.me/{CANAL_MANGA}/{msg.id}"
    return None

# ===== COMANDO /start =====
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🏴‍☠️ <b>Ahoy! Eu sou o Source Baltigo</b>\n\n"
        "⚡ Seu bot definitivo de <b>animes, mangás e personagens</b>.\n\n"
        "✨ O que eu sei fazer?\n\n"
        "• 🔍 Buscar infos completas de animes e mangás\n"
        "• 🎭 Mostrar personagens detalhados\n"
        "• 🔥 Rankings em alta\n"
        "• 🎲 Recomendações inteligentes e surpresas\n\n"
        "📢 <b>Onde eu brilho de verdade?</b>\n"
        "👉 Em <b>grupos</b>! Me adiciona em um grupo e deixa a mágica acontecer ✨"
    )

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Adicionar em um grupo",
                url="https://t.me/SourceBaltigo_bot?startgroup=start"
            )
        ],
        [
            InlineKeyboardButton(
                "⚔️ QG Baltigo ",
                url="t.me/QG_BALTIGO"
            )
        ]
    ])

    await update.message.reply_html(
        texto,
        reply_markup=teclado
    )

# ===== COMANDO /anime =====
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return

    # 🔒 Anti-spam
    if not anti_spam(user_id):
        await update.message.reply_text(
            "⏳ Sem flood 😅\nTente novamente em alguns segundos."
        )
        return

    # ❌ Sem nome do anime
    if not context.args:
        await update.message.reply_html(
            "🚫 <b>Ops! Algo faltou.</b>\n\n"
            "👉 <b>Formato correto:</b>\n"
            "<code>/anime nome do anime</code>\n\n"
            "🎬 <b>Exemplo:</b>\n"
            "<code>/anime naruto</code>"
        )
        return

    nome = " ".join(context.args)

    # ⏳ Mensagem de busca
    msg_busca = await update.message.reply_html(
        "🔎 Buscando o anime pra você...\n"
        "Aguarde um instante ⏳"


    )

    # 🔍 Buscar no canal
    async with client:
        msg_id = await buscar_post(CANAL_ANIME, nome)

    # ❌ NÃO ACHOU
    if not msg_id:
        await msg_busca.delete()

        await update.message.reply_html(
            "🚫 <b>Nada por aqui…</b>\n"
            "O anime que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        return

    # ✅ ACHOU
    await msg_busca.delete()

    keyboard = [[
        InlineKeyboardButton(
            "▶️ Assistir no canal",
            url=f"https://t.me/{CANAL_ANIME}/{msg_id}"
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_ANIME}",
        message_id=msg_id,
        reply_markup=reply_markup
    )

# ==================================================
# ===== COMANDO /manga =====
# ==================================================
async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return

    # Anti-spam (mantém se você já usa)
    if not anti_spam(user_id):
        await update.message.reply_text(
            "⏳ Sem flood 😅\nTente novamente em alguns segundos."
        )
        return

    # Sem argumentos
    if not context.args:
        await update.message.reply_html(
            "🚫 <b>Ops! Algo faltou.</b>\n\n"
            "👉 <b>Formato correto:</b>\n"
            "<code>/manga nome do mangá</code>\n\n"
            "📚 <b>Exemplo:</b>\n"
            "<code>/manga naruto</code>"
        )
        return

    nome = " ".join(context.args)

    # Mensagem de busca
    msg_busca = await update.message.reply_html(
        "📚 Buscando o mangá pra você...\n"
        "Aguarde um instante ⏳"
    )

    # Busca no canal
    async with client:
        msg_id = await buscar_post(CANAL_MANGA, nome)

    # ❌ Não encontrado (EXATAMENTE como você pediu)
    if not msg_id:
        await msg_busca.delete()
        await update.message.reply_html(
            "🚫 <b>Nada por aqui…</b>\n"
            "O mangá que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        return

    # Remove mensagem de busca
    await msg_busca.delete()

    # Botão "Ler agora"
    keyboard = [[
        InlineKeyboardButton(
            "📖 Ler agora",
            url=f"https://t.me/{CANAL_MANGA}/{msg_id}"
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Copia a mensagem do canal
    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_MANGA}",
        message_id=msg_id,
        reply_markup=reply_markup
    )

# ===============================
# 🔥 BUSCAR ANIMES EM ALTA
# ===============================
ANILIST_API = "https://graphql.anilist.co"
ANIMES_POR_PAGINA = 10

async def buscar_animes_em_alta(pagina: int):
    query = """
    query ($page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        media(sort: TRENDING_DESC, type: ANIME) {
          id
          siteUrl
          title {
            romaji
            english
          }
          averageScore
          popularity
        }
      }
    }
    """
    variables = {
        "page": pagina,
        "perPage": ANIMES_POR_PAGINA
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            data = await resp.json()
            return data["data"]["Page"]["media"]


# ===============================
# 🎨 FORMATAR TEXTO DO RANKING
# ===============================
def formatar_ranking(animes, pagina):
    inicio = (pagina - 1) * ANIMES_POR_PAGINA + 1
    texto = "🔥 <b>ANIMES EM ALTA AGORA</b> 🔥\n\n"

    for i, anime in enumerate(animes):
        posicao = inicio + i
        titulo = anime["title"]["english"] or anime["title"]["romaji"]
        score = anime["averageScore"] or "N/A"
        pop = anime["popularity"] or "N/A"

        emoji = "🏅"
        if posicao == 1:
            emoji = "🥇"
        elif posicao == 2:
            emoji = "🥈"
        elif posicao == 3:
            emoji = "🥉"

        texto += (
            f"{emoji} <b>{posicao}º</b> {titulo}\n"
            f"⭐ <b>Score:</b> <code>{score}</code>\n"
            f"👥 <b>Popularidade:</b> <code>{pop}</code>\n\n"
        )

    return texto


# ===============================
# 🔘 TECLADO DE NAVEGAÇÃO
# ===============================
def teclado_em_alta(pagina, site_url=None):
    botoes = []

    navegacao = []
    if pagina > 1:
        navegacao.append(
            InlineKeyboardButton(
                "⏪ Anterior",
                callback_data=f"emalta:{pagina - 1}"
            )
        )

    navegacao.append(
        InlineKeyboardButton(
            "⏩ Próximo",
            callback_data=f"emalta:{pagina + 1}"
        )
    )

    botoes.append(navegacao)

    if site_url:
        botoes.append([
            InlineKeyboardButton("📖 Ver no AniList", url=site_url)
        ])

    return InlineKeyboardMarkup(botoes)


# ===============================
# 📌 COMANDO /emalta
# ===============================
async def emalta(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    pagina = 1
    animes = await buscar_animes_em_alta(pagina)

    texto = formatar_ranking(animes, pagina)
    teclado = teclado_em_alta(pagina)

    await update.message.reply_html(texto, reply_markup=teclado)


# ===============================
# 🔁 CALLBACK PAGINAÇÃO
# ===============================
async def callback_emalta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pagina = int(query.data.split(":")[1])
    animes = await buscar_animes_em_alta(pagina)

    texto = formatar_ranking(animes, pagina)
    teclado = teclado_em_alta(pagina)

    await query.message.edit_text(
        texto,
        parse_mode="HTML",
        reply_markup=teclado
    )

# ===== RECOMENDAÇÕES ANIList =====
import random
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

ANILIST_API = "https://graphql.anilist.co"
MAX_PAGES = 3
PER_PAGE = 5

# ===== BUSCAR RECOMENDAÇÕES =====
async def buscar_recomendacoes(tipo: str, page: int):
    if tipo == "surpresa":
        page = random.randint(1, 100)  # top ~500 (5 por página)
        sort = random.choice(["SCORE_DESC", "POPULARITY_DESC"])
    else:
        sort_map = {
            "anime": "SCORE_DESC",
            "manga": "SCORE_DESC",
            "popular": "POPULARITY_DESC"
        }
        sort = sort_map[tipo]

    media_type = "MANGA" if tipo == "manga" else "ANIME"

    query = """
    query ($page: Int, $type: MediaType, $sort: [MediaSort], $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        media(type: $type, sort: $sort) {
          id
          siteUrl
          title {
            romaji
            english
          }
          averageScore
          popularity
          genres
          coverImage {
            extraLarge
          }
          startDate {
            year
          }
        }
      }
    }
    """

    variables = {
        "page": page,
        "type": media_type,
        "sort": [sort],
        "perPage": PER_PAGE
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            data = await resp.json()
            return data["data"]["Page"]["media"]

# ===== FORMATAR TEXTO =====
def formatar_lista(lista, tipo, page):
    titulo = f"🔥 <b>RECOMENDAÇÕES — {tipo.upper()}</b>\n📄 Página {page}/{MAX_PAGES}\n\n"
    texto = titulo

    for i, media in enumerate(lista, start=1):
        nome = media["title"]["english"] or media["title"]["romaji"]
        score = media["averageScore"] or "—"
        pop = media["popularity"] or "—"
        generos = ", ".join(media["genres"][:3]) if media["genres"] else "—"

        texto += (
            f"<b>{i}.</b> {nome}\n"
            f"⭐ <b>Score:</b> <code>{score}</code>\n"
            f"👥 <b>Popularidade:</b> <code>{pop}</code>\n"
            f"🎭 <b>Gêneros:</b> <code>{generos}</code>\n\n"
        )

    return texto

# ===== TECLADO =====
def teclado_recomenda(tipo, page):
    botoes = []

    if page > 1:
        botoes.append(
            InlineKeyboardButton("⬅️ Anterior", callback_data=f"rec:{tipo}:{page-1}")
        )
    if page < MAX_PAGES:
        botoes.append(
            InlineKeyboardButton("➡️ Próximo", callback_data=f"rec:{tipo}:{page+1}")
        )

    return InlineKeyboardMarkup([botoes]) if botoes else None

# ===== COMANDO /recomenda =====
async def recomenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html(
            "✨ <b>SISTEMA DE RECOMENDAÇÕES</b> ✨\n\n"
            "Escolha como você quer descobrir algo novo:\n\n"
            "🎬 <b>Anime</b>\n"
            "<code>/recomenda anime</code>\n"
            "Descubra animes bem avaliados para começar algo de qualidade.\n\n"
            "📚 <b>Mangá</b>\n"
            "<code>/recomenda manga</code>\n"
            "Boas recomendações de mangás para leitura.\n\n"
            "🔥 <b>Popular</b>\n"
            "<code>/recomenda popular</code>\n"
            "O que está bombando agora entre a comunidade.\n\n"
            "🎲 <b>Surpresa</b>\n"
            "<code>/recomenda surpresa</code>\n"
            "Uma recomendação aleatória para quem quer sair da bolha e se surpreender.\n\n"
            "💡 <i>Dica:</i> Use os botões para navegar entre as páginas."
        )
        return

    tipo = context.args[0].lower()
    if tipo not in ["anime", "manga", "popular", "surpresa"]:
        await update.message.reply_text("❌ Opção inválida.")
        return

    page = 1
    lista = await buscar_recomendacoes(tipo, page)

    # 🎲 SURPRESA → CARD
    if tipo == "surpresa":
        media = random.choice(lista)
        nome = media["title"]["english"] or media["title"]["romaji"]
        score = media["averageScore"] or "—"
        pop = media["popularity"] or "—"
        generos = ", ".join(media["genres"][:3]) if media["genres"] else "—"
        ano = media["startDate"]["year"] or "—"

        texto = (
            f"<b>{nome}</b>\n\n"
            f"<b>Score:</b> <code>{score}</code>\n"
            f"<b>Popularidade:</b> <code>{pop}</code>\n"
            f"<b>Gêneros:</b> <code>{generos}</code>\n"
            f"<b>Ano:</b> <code>{ano}</code>"
        )

        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Ver no AniList", url=media["siteUrl"])]
        ])

        await update.message.reply_photo(
            photo=media["coverImage"]["extraLarge"],
            caption=texto,
            parse_mode="HTML",
            reply_markup=teclado
        )
        return

    texto = formatar_lista(lista, tipo, page)
    await update.message.reply_html(
        texto,
        reply_markup=teclado_recomenda(tipo, page)
    )

# ===== CALLBACK =====
async def callback_recomenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, tipo, page = query.data.split(":")
    page = int(page)

    if page < 1 or page > MAX_PAGES:
        return

    lista = await buscar_recomendacoes(tipo, page)
    texto = formatar_lista(lista, tipo, page)

    await query.message.edit_text(
        texto,
        parse_mode="HTML",
        reply_markup=teclado_recomenda(tipo, page)
    )

# ==================================================
# COMANDO .cards — LISTA DE PERSONAGENS (AniList)
# ==================================================

ANILIST_API = "https://graphql.anilist.co"

# ==================================================
# BUSCAR PERSONAGENS DO ANIME
# ==================================================
async def buscar_cards(anime_nome: str, page: int = 1):
    query = """
    query ($search: String, $page: Int) {
      Page(page: 1, perPage: 1) {
        media(search: $search, type: ANIME) {
          id
          title {
            romaji
          }
          bannerImage
          coverImage {
            large
          }
          characters(page: $page, perPage: 15) {
            pageInfo {
              total
              currentPage
              lastPage
            }
            edges {
              node {
                id
                name {
                  full
                }
              }
            }
          }
        }
      }
    }
    """

    variables = {
        "search": anime_nome,
        "page": page
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            data = await resp.json()
            media = data.get("data", {}).get("Page", {}).get("media", [])
            return media[0] if media else None


# ==================================================
# FORMATAR TEXTO DO CARD
# ==================================================
def formatar_cards(media, page):
    chars = media["characters"]["edges"]
    info = media["characters"]["pageInfo"]

    texto = (
        f"📁 | <b>{media['title']['romaji']}</b>\n"
        f"ℹ️ | <b>{info['total']}</b>\n"
        f"🗂 | <b>{page}/{info['lastPage']}</b>\n\n"
    )

    for c in chars:
        texto += f"🧧 <b>{c['node']['id']}.</b> {c['node']['name']['full']}\n"

    return texto


# ==================================================
# TECLADO DE PAGINAÇÃO
# ==================================================
def teclado_cards(anime, page, last):
    botoes = []

    if page > 1:
        botoes.append(
            InlineKeyboardButton(
                "⬅️ Anterior",
                callback_data=f"cards:{anime}:{page-1}"
            )
        )

    if page < last:
        botoes.append(
            InlineKeyboardButton(
                "➡️ Próximo",
                callback_data=f"cards:{anime}:{page+1}"
            )
        )

    return InlineKeyboardMarkup([botoes]) if botoes else None


# ==================================================
# COMANDO .cards / /cards
# ==================================================
async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):

     # 🔒 VERIFICA CANAL OBRIGATÓRIO
    if not await checar_canal(update, context):
        return
        
    if not context.args:
        await update.message.reply_html(
            "📁 <b>Cards de personagens</b>\n\n"
            "Use:\n"
            "<code>/cards Nome do Anime</code>\n\n"
            "📌 Exemplo:\n"
            "<code>/cards One Piece</code>"
        )
        return

    anime = " ".join(context.args)
    media = await buscar_cards(anime, 1)

    if not media:
        await update.message.reply_html(
            "❌ <b>Anime não encontrado</b>\n\n"
            "💡 Tente usar o nome mais conhecido.\n"
            "Exemplo: <code>One Piece</code>"
        )
        return

    texto = formatar_cards(media, 1)
    last = media["characters"]["pageInfo"]["lastPage"]

    # 🔥 AQUI É O AJUSTE PEDIDO
    # usa banner do anime, se não tiver cai pro cover
    foto = media["bannerImage"] or media["coverImage"]["large"]

    await update.message.reply_photo(
        photo=foto,
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado_cards(anime, 1, last)
    )


# ==================================================
# CALLBACK DA PAGINAÇÃO
# ==================================================
async def callback_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, anime, page = query.data.split(":")
    page = int(page)

    media = await buscar_cards(anime, page)
    texto = formatar_cards(media, page)
    last = media["characters"]["pageInfo"]["lastPage"]

    await query.message.edit_caption(
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado_cards(anime, page, last)
    )

# ===== INICIAR BOT =====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("anime", anime))
app.add_handler(CommandHandler("infoanime", infoanime))
app.add_handler(CommandHandler("infomanga", infomanga))
app.add_handler(CommandHandler("perso", perso))
app.add_handler(CommandHandler("recomenda", recomenda))
app.add_handler(CallbackQueryHandler(callback_recomenda, pattern="^rec:"))
app.add_handler(CommandHandler("emalta", emalta))
app.add_handler(CallbackQueryHandler(callback_emalta, pattern="^emalta:"))
app.add_handler(CallbackQueryHandler(callback_info_perso, pattern="^info_perso:"))
app.add_handler(CallbackQueryHandler(callback_info_manga, pattern="^info_manga:"))
app.add_handler(CommandHandler("pedido", pedido))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("login", login))
app.add_handler(CommandHandler("manga", manga))
app.add_handler(CommandHandler("perfil", perfil))
app.add_handler(CommandHandler("adminfoto", adminfoto))
app.add_handler(CommandHandler("favoritar", favoritar))
app.add_handler(CommandHandler("desfavoritar", desfavoritar))
app.add_handler(CommandHandler("nick", nick))
app.add_handler(CommandHandler("nivel", nivel))
app.add_handler(CommandHandler("cards", cards))
app.add_handler(MessageHandler(filters.Regex(r"^\.cards"), cards))
app.add_handler(CallbackQueryHandler(callback_cards, pattern="^cards:"))
app.add_handler(CommandHandler("gacha", gacha))
app.add_handler(CallbackQueryHandler(escolher_anime, pattern="^anime:"))
app.run_polling()






