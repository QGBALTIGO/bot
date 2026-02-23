import time
import random
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telethon import TelegramClient
from database import db, cursor

# =====================================================
# CONFIGURAÇÕES
# =====================================================

BOT_TOKEN = "8001392073:AAEW64SRZI7BIY6l8reeKnNONu-6gjLt0Sg"
api_id = 34116600
api_hash = "b8f22be457ce73f65fad82315073fbc3"

CANAL_ANIME = "Centraldeanimes_Baltigo"
CANAL_MANGA = "MangasBrasil"
CANAL_PEDIDOS = -1003895811362
CANAL_OBRIGATORIO = -1003818375955

ANILIST_API = "https://graphql.anilist.co"

COMANDOS_POR_NIVEL = 100
ANTI_SPAM_TIME = 4

# =====================================================
# CLIENTES GLOBAIS
# =====================================================

client = TelegramClient("sessao_busca", api_id, api_hash)
last_command_time = {}
http_session = None

# =====================================================
# INICIALIZAÇÃO
# =====================================================

async def iniciar_servicos():
    global http_session
    await client.start()
    http_session = aiohttp.ClientSession()

# =====================================================
# ANTI SPAM
# =====================================================

def anti_spam(user_id: int):
    agora = time.time()
    ultimo = last_command_time.get(user_id, 0)

    if agora - ultimo < ANTI_SPAM_TIME:
        return False

    last_command_time[user_id] = agora
    return True

# =====================================================
# DATABASE
# =====================================================

def get_user(user_id: int, name: str):
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("""
            INSERT INTO users (telegram_id, nick)
            VALUES (?, ?)
        """, (user_id, name))
        db.commit()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        user = cursor.fetchone()

    return user

def pode_pedir(user_id: int):
    cursor.execute("SELECT last_pedido FROM users WHERE telegram_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result:
        return True

    ultimo = result[0]
    agora = int(time.time())

    return (agora - ultimo) > 43200  # 12h

async def registrar_comando(update: Update):
    user_id = update.effective_user.id
    name = update.effective_user.first_name

    user = get_user(user_id, name)

    comandos = user[4] + 1
    level = (comandos // COMANDOS_POR_NIVEL) + 1

    cursor.execute("""
        UPDATE users
        SET commands = ?, level = ?
        WHERE telegram_id = ?
    """, (comandos, level, user_id))

    db.commit()

# =====================================================
# CANAL OBRIGATÓRIO
# =====================================================

async def usuario_no_canal(bot, user_id: int):
    try:
        membro = await bot.get_chat_member(CANAL_OBRIGATORIO, user_id)
        return membro.status in ("member", "administrator", "creator")
    except:
        return False


async def checar_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await usuario_no_canal(context.bot, user_id):
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Entrar no canal", url="https://t.me/SourcerBaltigo")]
        ])
        await update.message.reply_text(
            "🚫 Você precisa entrar no canal para usar o bot.",
            reply_markup=teclado
        )
        return False
    return True


# =====================================================
# START
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id, update.effective_user.first_name)

    await update.message.reply_html(
        "🏴‍☠️ <b>Source Baltigo</b>\n\n"
        "⚡ Busque animes, mangás e personagens.\n\n"
        "📌 Comandos principais:\n"
        "• /anime nome\n"
        "• /manga nome\n"
        "• /perso nome\n"
        "• /emalta\n"
        "• /recomenda\n"
        "• /perfil\n"
        "• /favoritar\n"
        "• /pedido nome\n"
    )


# =====================================================
# PERFIL
# =====================================================

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    await registrar_comando(update)

    user_id = update.effective_user.id
    user = get_user(user_id, update.effective_user.first_name)

    nick = user[1]
    fav_name = user[2]
    fav_image = user[3]
    comandos = user[4]
    level = user[5]

    texto = (
        f"👤 <b>{nick}</b>\n\n"
        f"⭐ Nível: <b>{level}</b>\n"
        f"⌨️ Comandos: <b>{comandos}</b>\n\n"
        f"❤️ Favorito:\n"
        f"{fav_name if fav_name else 'Nenhum'}"
    )

    if fav_image:
        await update.message.reply_photo(
            fav_image,
            caption=texto,
            parse_mode="HTML"
        )
    else:
        await update.message.reply_html(texto)


# =====================================================
# NICK
# =====================================================

async def nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    if not context.args:
        await update.message.reply_text("Use: /nick novo_nome")
        return

    novo_nick = " ".join(context.args)

    cursor.execute("""
        UPDATE users
        SET nick = ?
        WHERE telegram_id = ?
    """, (novo_nick, update.effective_user.id))
    db.commit()

    await update.message.reply_text("✅ Nick atualizado com sucesso!")


# =====================================================
# NÍVEL
# =====================================================

async def nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    user = get_user(update.effective_user.id, update.effective_user.first_name)

    await update.message.reply_text(
        f"⭐ Seu nível atual é: {user[5]}\n"
        f"⌨️ Comandos usados: {user[4]}"
    )

# =====================================================
# ANILIST - FUNÇÕES BASE
# =====================================================

async def anilist_request(query, variables):
    async with http_session.post(
        ANILIST_API,
        json={"query": query, "variables": variables}
    ) as resp:
        return await resp.json()


# =====================================================
# /ANIME
# =====================================================

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        return

    await registrar_comando(update)

    if not context.args:
        await update.message.reply_text("Use: /anime nome")
        return

    nome = " ".join(context.args)

    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        title { romaji }
        coverImage { large }
        episodes
        status
        description
      }
    }
    """

    data = await anilist_request(query, {"search": nome})
    media = data["data"]["Media"]

    texto = (
        f"🎬 <b>{media['title']['romaji']}</b>\n\n"
        f"📺 Episódios: {media['episodes']}\n"
        f"📌 Status: {media['status']}\n\n"
        f"{media['description'][:900]}..."
    )

    await update.message.reply_photo(
        media["coverImage"]["large"],
        caption=texto,
        parse_mode="HTML"
    )


# =====================================================
# /MANGA
# =====================================================

async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        return

    await registrar_comando(update)

    if not context.args:
        await update.message.reply_text("Use: /manga nome")
        return

    nome = " ".join(context.args)

    query = """
    query ($search: String) {
      Media(search: $search, type: MANGA) {
        title { romaji }
        coverImage { large }
        chapters
        status
        description
      }
    }
    """

    data = await anilist_request(query, {"search": nome})
    media = data["data"]["Media"]

    texto = (
        f"📖 <b>{media['title']['romaji']}</b>\n\n"
        f"📚 Capítulos: {media['chapters']}\n"
        f"📌 Status: {media['status']}\n\n"
        f"{media['description'][:900]}..."
    )

    await update.message.reply_photo(
        media["coverImage"]["large"],
        caption=texto,
        parse_mode="HTML"
    )


# =====================================================
# /PERSO
# =====================================================

async def perso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        return

    await registrar_comando(update)

    if not context.args:
        await update.message.reply_text("Use: /perso nome")
        return

    nome = " ".join(context.args)

    query = """
    query ($search: String) {
      Character(search: $search) {
        name { full }
        image { large }
        description
      }
    }
    """

    data = await anilist_request(query, {"search": nome})
    char = data["data"]["Character"]

    texto = (
        f"👤 <b>{char['name']['full']}</b>\n\n"
        f"{char['description'][:900]}..."
    )

    await update.message.reply_photo(
        char["image"]["large"],
        caption=texto,
        parse_mode="HTML"
    )


# =====================================================
# /EMALTA
# =====================================================

async def emalta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        return

    await registrar_comando(update)

    query = """
    query {
      Page(page: 1, perPage: 5) {
        media(sort: TRENDING_DESC, type: ANIME) {
          title { romaji }
        }
      }
    }
    """

    data = await anilist_request(query, {})
    lista = data["data"]["Page"]["media"]

    texto = "🔥 <b>Animes em Alta</b>\n\n"
    for i, anime in enumerate(lista, 1):
        texto += f"{i}. {anime['title']['romaji']}\n"

    await update.message.reply_html(texto)


# =====================================================
# /RECOMENDA
# =====================================================

async def recomenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        return

    await registrar_comando(update)

    query = """
    query {
      Page(page: 1, perPage: 5) {
        media(type: ANIME, sort: POPULARITY_DESC) {
          title { romaji }
        }
      }
    }
    """

    data = await anilist_request(query, {})
    lista = data["data"]["Page"]["media"]

    texto = "🎯 <b>Recomendações</b>\n\n"
    for anime in lista:
        texto += f"• {anime['title']['romaji']}\n"

    await update.message.reply_html(texto)

# =====================================================
# /FAVORITAR (PERSONAGEM)
# =====================================================

async def favoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        return

    await registrar_comando(update)

    if not context.args:
        await update.message.reply_text("Use: /favoritar nome_do_personagem")
        return

    nome = " ".join(context.args)

    query = """
    query ($search: String) {
      Character(search: $search) {
        name { full }
        image { large }
      }
    }
    """

    data = await anilist_request(query, {"search": nome})
    char = data["data"]["Character"]

    cursor.execute("""
        UPDATE users
        SET fav_name = ?, fav_image = ?
        WHERE telegram_id = ?
    """, (
        char["name"]["full"],
        char["image"]["large"],
        update.effective_user.id
    ))
    db.commit()

    await update.message.reply_text(
        f"❤️ {char['name']['full']} foi definido como favorito!"
    )


# =====================================================
# /DESFAVORITAR
# =====================================================

async def desfavoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    cursor.execute("""
        UPDATE users
        SET fav_name = NULL,
            fav_image = NULL
        WHERE telegram_id = ?
    """, (update.effective_user.id,))
    db.commit()

    await update.message.reply_text("💔 Favorito removido com sucesso.")


# =====================================================
# /PEDIDO
# =====================================================

async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        return

    user_id = update.effective_user.id
    get_user(user_id, update.effective_user.first_name)

    if not pode_pedir(user_id):
        await update.message.reply_text("⏳ Você já fez um pedido nas últimas 12 horas.")
        return

    if not context.args:
        await update.message.reply_text("Use: /pedido nome do anime")
        return

    texto_pedido = " ".join(context.args)

    await context.bot.send_message(
        chat_id=CANAL_PEDIDOS,
        text=f"📥 <b>Novo pedido</b>\n\n🎬 {texto_pedido}\n👤 ID: {user_id}",
        parse_mode="HTML"
    )

    cursor.execute("""
        UPDATE users
        SET last_pedido = ?
        WHERE telegram_id = ?
    """, (int(time.time()), user_id))
    db.commit()

    await update.message.reply_text("✅ Pedido enviado com sucesso!")


# =====================================================
# BUSCA EM CANAIS (TELETHON)
# =====================================================

async def buscar_post(canal, termo):
    async for msg in client.iter_messages(canal, search=termo, limit=1):
        return msg.id
    return None


# =====================================================
# /ANIMEPOST (BUSCA NO CANAL)
# =====================================================

async def animepost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Use: /animepost nome")
        return

    nome = " ".join(context.args)
    msg_temp = await update.message.reply_text("🔎 Buscando no canal...")

    msg_id = await buscar_post(CANAL_ANIME, nome)

    if not msg_id:
        await msg_temp.edit_text("❌ Anime não encontrado no canal.")
        return

    await msg_temp.delete()

    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_ANIME}",
        message_id=msg_id
    )


# =====================================================
# /MANGAPOST (BUSCA NO CANAL)
# =====================================================

async def mangapost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Use: /mangapost nome")
        return

    nome = " ".join(context.args)
    msg_temp = await update.message.reply_text("🔎 Buscando no canal...")

    msg_id = await buscar_post(CANAL_MANGA, nome)

    if not msg_id:
        await msg_temp.edit_text("❌ Mangá não encontrado no canal.")
        return

    await msg_temp.delete()

    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_MANGA}",
        message_id=msg_id
    )

# =====================================================
# REGISTRO DE HANDLERS
# =====================================================

def registrar_handlers(app):
    # Básicos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("perfil", perfil))
    app.add_handler(CommandHandler("nick", nick))
    app.add_handler(CommandHandler("nivel", nivel))

    # AniList
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(CommandHandler("manga", manga))
    app.add_handler(CommandHandler("perso", perso))
    app.add_handler(CommandHandler("emalta", emalta))
    app.add_handler(CommandHandler("recomenda", recomenda))

    # Favoritos
    app.add_handler(CommandHandler("favoritar", favoritar))
    app.add_handler(CommandHandler("desfavoritar", desfavoritar))

    # Pedidos
    app.add_handler(CommandHandler("pedido", pedido))

    # Busca em canais
    app.add_handler(CommandHandler("animepost", animepost))
    app.add_handler(CommandHandler("mangapost", mangapost))
