# ================= IMPORTS =================
from telethon import TelegramClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import time
import aiohttp

# ================= CONFIG =================
api_id = 34116600
api_hash = "b8f22be457ce73f65fad82315073fbc3"
BOT_TOKEN = "8001392073:AAEW64SRZI7BIY6l8reeKnNONu-6gjLt0Sg"

CANAL_ANIME = "Centraldeanimes_Baltigo"
CANAL_MANGA = "MangasBrasil"

# ================= TELETHON =================
client = TelegramClient("sessao_busca", api_id, api_hash)

# ================= ANTI-SPAM =================
ANTI_SPAM_TIME = 5
last_command_time = {}

def anti_spam(user_id: int) -> bool:
    agora = time.time()
    if user_id in last_command_time:
        if agora - last_command_time[user_id] < ANTI_SPAM_TIME:
            return False
    last_command_time[user_id] = agora
    return True

# ================= BUSCAR POST NO CANAL =================
async def buscar_post(canal, termo):
    async for msg in client.iter_messages(canal, search=termo):
        return msg.id
    return None

# ================= ANIList (API PÚBLICA) =================
async def buscar_anilist_id(titulo: str, tipo: str):
    query = """
    query ($search: String, $type: MediaType) {
      Media(search: $search, type: $type) {
        id
      }
    }
    """
    variables = {
        "search": titulo,
        "type": tipo
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": variables}
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("data", {}).get("Media", {}).get("id")

# ================= /start =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "👋 <b>Olá!</b>\n\n"
        "🤖 Bot online e funcionando.\n\n"
        "📌 Comandos disponíveis:\n"
        "• <code>/anime nome</code>\n"
        "• <code>/manga nome</code>"
    )

# ================= /anime =================
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not anti_spam(user_id):
        await update.message.reply_text("⏳ Aguarde alguns segundos.")
        return

    if not context.args:
        await update.message.reply_text("Use: /anime nome do anime")
        return

    nome = " ".join(context.args)
    await update.message.reply_text("🔎 Buscando o anime...")

    async with client:
        msg_id = await buscar_post(CANAL_ANIME, nome)

    if not msg_id:
        await update.message.reply_text("❌ Anime não encontrado.")
        return

    anilist_id = await buscar_anilist_id(nome, "ANIME")

    keyboard = [
        [InlineKeyboardButton("▶️ Assistir no canal",
         url=f"https://t.me/{CANAL_ANIME}/{msg_id}")]
    ]

    if anilist_id:
        keyboard.append([
            InlineKeyboardButton(
                "🎬 Ver no AniList",
                url=f"https://anilist.co/anime/{anilist_id}"
            )
        ])

    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_ANIME}",
        message_id=msg_id,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= /manga =================
async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not anti_spam(user_id):
        await update.message.reply_text("⏳ Aguarde alguns segundos.")
        return

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

    anilist_id = await buscar_anilist_id(nome, "MANGA")

    keyboard = [
        [InlineKeyboardButton("📖 Ler no canal",
         url=f"https://t.me/{CANAL_MANGA}/{msg_id}")]
    ]

    if anilist_id:
        keyboard.append([
            InlineKeyboardButton(
                "📚 Ver no AniList",
                url=f"https://anilist.co/manga/{anilist_id}"
            )
        ])

    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_MANGA}",
        message_id=msg_id,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= RUN =================
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("anime", anime))
app.add_handler(CommandHandler("manga", manga))

print("🤖 Bot rodando...")
app.run_polling()
