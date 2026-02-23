from telethon import TelegramClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import time
import aiohttp

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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def infoanime(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def buscar_multiplos_personagens(nome: str):
    query = """
    query ($search: String) {
      Page(perPage: 6) {
        characters(search: $search) {
          id
          siteUrl
          name {
            full
            native
          }
          image {
            large
          }
          description
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
                return data["data"]["Page"]["characters"]
    except Exception as e:
        print("Erro AniList Personagem:", e)
        return []


# ===== ANILIST PERSONAGENS =====
ANILIST_API = "https://graphql.anilist.co"
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# ===== BUSCAR MÚLTIPLOS PERSONAGENS =====
async def buscar_personagens(nome: str):
    query = """
    query ($search: String) {
      Page(perPage: 6) {
        characters(search: $search) {
          id
          name {
            full
            native
          }
          image {
            large
          }
        }
      }
    }
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": {"search": nome}}
        ) as resp:
            data = await resp.json()
            return data["data"]["Page"]["characters"]

# ===== BUSCAR PERSONAGEM POR ID =====
async def buscar_personagem_por_id(char_id: int):
    query = """
    query ($id: Int) {
      Character(id: $id) {
        id
        name {
          full
          native
        }
        image {
          large
        }
        description
        media(perPage: 10) {
          edges {
            node {
              title {
                romaji
                english
              }
              type
              siteUrl
            }
          }
        }
      }
    }
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": {"id": char_id}}
        ) as resp:
            data = await resp.json()
            return data["data"]["Character"]

# ===== COMANDO /PERSO =====
async def perso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Faltou o nome do personagem</b>\n\n"
            "Exemplo:\n<code>/perso Luffy</code>"
        )
        return

    nome = " ".join(context.args)
    msg = await update.message.reply_text("🔎 Buscando personagens...")

    personagens = await buscar_personagens(nome)
    if not personagens:
        await msg.edit_text("🚫 Nenhum personagem encontrado.")
        return

    botoes = []
    for p in personagens:
        nome_p = p["name"]["full"] or p["name"]["native"]
        botoes.append([
            InlineKeyboardButton(
                nome_p,
                callback_data=f"info_perso:{p['id']}"
            )
        ])

    await msg.edit_text(
        "🎭 <b>Escolha o personagem</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

# ===== CALLBACK INFO PERSONAGEM =====
async def callback_info_perso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    char_id = int(query.data.split(":")[1])
    personagem = await buscar_personagem_por_id(char_id)

    # 🔥 Apaga a mensagem das opções
    await query.message.delete()

    nome = personagem["name"]["full"]
    nome_native = personagem["name"].get("native", "")
    imagem = personagem["image"]["large"]

    texto = (
        f"🎭 <b>{nome}</b>\n"
        f"<i>{nome_native}</i>\n\n"
        f"📌 <b>Descrição:</b>\n"
        f"{(personagem['description'] or 'Sem descrição disponível.')[:600]}..."
    )

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎬 Ver obras do personagem",
                callback_data=f"obras_perso:{char_id}"
            )
        ]
    ])

    await query.message.reply_photo(
        photo=imagem,
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado
    )

# ===== CALLBACK OBRAS DO PERSONAGEM =====
async def callback_obras_perso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    char_id = int(query.data.split(":")[1])
    personagem = await buscar_personagem_por_id(char_id)

    animes = []
    mangas = []

    for edge in personagem["media"]["edges"]:
        obra = edge["node"]
        titulo = obra["title"]["english"] or obra["title"]["romaji"]
        if obra["type"] == "ANIME":
            animes.append(f"🎬 {titulo}")
        elif obra["type"] == "MANGA":
            mangas.append(f"📖 {titulo}")

    texto = "🎭 <b>Obras do personagem</b>\n\n"

    if animes:
        texto += "<b>🎬 Animes</b>\n" + "\n".join(animes) + "\n\n"
    if mangas:
        texto += "<b>📖 Mangás</b>\n" + "\n".join(mangas)

    await query.message.reply_text(texto, parse_mode="HTML")
    
# ===== COMANDO /pedido =====
async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "👋 <b>Olá!</b>\n\n"
        "🤖 Eu estou <b>online</b> e funcionando.\n\n"
        "📌 Você poderá usar:\n"
        "• <code>/anime</code>\n"
        "• <code>/manga</code>\n\n"
        "✨ Aguarde novidades!"
    )

# ===== COMANDO /anime =====
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not anti_spam(user_id):
        await update.message.reply_text(
            "⏳ Sem flood 😅\nTente novamente em alguns segundos."
        )
        return

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

    # ✅ GUARDA a mensagem de buscando
    msg_busca = await update.message.reply_html(
        "🔎 Buscando o anime pra você...\nAguarde um instante ⏳\n\n"
          "🚫 <b>Nada por aqui…</b>\n"
            "O anime que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
    )

    async with client:
        msg_id = await buscar_post(CANAL_ANIME, nome)

    # ❌ NÃO ACHOU
    if not msg_id:
        await msg_busca.delete()  # 👈 APAGA o "Buscando"

        await update.message.reply_html(
            "🚫 <b>Nada por aqui…</b>\n\n"
            "O anime que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        return

    # ✅ ACHOU
    await msg_busca.delete()  # 👈 APAGA o "Buscando"

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

# ===== COMANDO /manga =====
async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not anti_spam(user_id):
        await update.message.reply_text(
            "⏳ Sem flood 😅\nTente novamente em alguns segundos."
        )
        return

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

    msg_busca = await update.message.reply_html(
        "📚 Buscando o mangá pra você...\nAguarde um instante ⏳\n\n"
          "🚫 <b>Nada por aqui…</b>\n"
            "O anime que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
    )

    async with client:
        msg_id = await buscar_post(CANAL_MANGA, nome)

    if not msg_id:
        await msg_busca.delete()
        await update.message.reply_html(
            "🚫 <b>Nada por aqui…</b>\n\n"
            "O mangá que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        return

    await msg_busca.delete()

    keyboard = [[
        InlineKeyboardButton(
            "📖 Ler agora",
            url=f"https://t.me/{CANAL_MANGA}/{msg_id}"
        )
    ]]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_MANGA}",
        message_id=msg_id,
        reply_markup=reply_markup
    )

# ===== INICIAR BOT =====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("anime", anime))
app.add_handler(CallbackQueryHandler(callback_info_anime, pattern="^info_anime:"))
app.add_handler(CommandHandler("infoanime", infoanime))
app.add_handler(CommandHandler("infomanga", infomanga))
app.add_handler(CommandHandler("perso", infoperson))
app.add_handler(CallbackQueryHandler(callback_info_perso, pattern="^info_perso:"))
app.add_handler(CallbackQueryHandler(callback_info_person, pattern="^info_person:"))
app.add_handler(CallbackQueryHandler(callback_info_manga, pattern="^info_manga:"))
app.add_handler(CommandHandler("pedido", pedido))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("login", login))
app.add_handler(CommandHandler("manga", manga))
print("🤖 Bot rodando...")
app.run_polling()


























