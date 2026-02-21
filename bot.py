from telethon import TelegramClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import aiohttp

# ===== ANI CONFIG =====
ANILIST_API = "https://graphql.anilist.co"

async def buscar_anilist_id(nome: str, tipo: str):
    query = """
    query ($search: String) {
      Media(search: $search, type: %s) {
        id
      }
    }
    """ % tipo

    variables = {"search": nome}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables}
        ) as resp:
            data = await resp.json()
            return data["data"]["Media"]["id"] if data.get("data") else None
            
# ===== ANTI-SPAM CONFIG =====
ANTI_SPAM_TIME = 5  # segundos
last_command_time = {}

def anti_spam(user_id: int) -> bool:
    agora = time.time()

    if user_id in last_command_time:
        if agora - last_command_time[user_id] < ANTI_SPAM_TIME:
            return False

    last_command_time[user_id] = agora
    return True

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not anti_spam(user_id):
        await update.message.reply_text(
            "⏳ Calma aí!\nEspere alguns segundos antes de usar outro comando."
        )
        return

async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not anti_spam(user_id):
        await update.message.reply_text(
            "⏳ Sem flood 😅\nTente novamente em alguns segundos."
        )
        return

# ===== DADOS =====
api_id = 34116600
api_hash = "b8f22be457ce73f65fad82315073fbc3"
BOT_TOKEN = "8001392073:AAEW64SRZI7BIY6l8reeKnNONu-6gjLt0Sg"
CANAL_ANIME = "Centraldeanimes_Baltigo"
CANAL_MANGA = "MangasBrasil"

# ===== TELETHON =====
client = TelegramClient("sessao_busca", api_id, api_hash)
async def buscar_post(canal, termo):
    async for msg in client.iter_messages(canal, search=termo):
        return msg.id
    return None

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
        "📌 Em breve você poderá usar:\n"
        "• <code>/anime</code>\n"
        "• <code>/manga</code>\n\n"
        "✨ Aguarde novidades!"
    )

# ===== COMANDO /anime =====
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /anime nome do anime")
        return

    nome = " ".join(context.args)
    await update.message.reply_text("🔎 Buscando o anime pra você...\nAguarde um instante ⏳")

    async with client:
        msg_id = await buscar_post(CANAL_ANIME, nome)

    if not msg_id:
        await update.message.reply_text("❌ Anime não encontrado.")
        return

    keyboard = [[
        InlineKeyboardButton(
            "▶️ Assistir no canal",
            url=f"https://t.me/{CANAL_ANIME}/{msg_id}"
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 🔁 COPIA A MENSAGEM DO CANAL (com imagem + texto)
    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_ANIME}",
        message_id=msg_id,
        reply_markup=reply_markup
    )
        
# ===== COMANDO /manga =====
async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /manga nome do mangá")
        return

    nome = " ".join(context.args)
    await update.message.reply_text("🔎 Buscando o mangá...")

    async with client:
        msg_id = await buscar_post(CANAL_MANGA, nome)

    if not msg_id:
        await update.message.reply_text("❌ Mangá não encontrado.")
        return

    # 🔍 Busca o ID no AniList
    anilist_id = await buscar_anilist_id(nome, "MANGA")

    # 🔘 Botões
    keyboard = [
        [
            InlineKeyboardButton(
                "📖 Ler agora",
                url=f"https://t.me/{CANAL_MANGA}/{msg_id}"
            )
        ]
    ]

    if anilist_id:
        keyboard.append([
            InlineKeyboardButton(
                "📚 Ver no AniList",
                url=f"https://anilist.co/manga/{anilist_id}"
            )
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # 🔁 Copia a mensagem original do canal (imagem + texto)
    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_MANGA}",
        message_id=msg_id,
        reply_markup=reply_markup
    )
# ===== INICIAR BOT =====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("anime", anime))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("manga", manga))
print("🤖 Bot rodando...")
app.run_polling()



















