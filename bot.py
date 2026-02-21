from telethon import TelegramClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===== DADOS =====
api_id = 34116600
api_hash = "b8f22be457ce73f65fad82315073fbc3"
BOT_TOKEN = "8001392073:AAEW64SRZI7BIY6l8reeKnNONu-6gjLt0Sg"

CANAL_ANIME = "Centraldeanimes_Baltigo"
CANAL_MANGA = "MangasBrasil"

# ===== TELETHON =====
client = TelegramClient("sessao_busca", api_id, api_hash)

# ===== CACHE E ANTI-SPAM =====
cache = {}          # { "naruto": link }
cooldown = {}       # { user_id: timestamp }
COOLDOWN_TIME = 10  # segundos

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

# ===== ANIList =====
def buscar_anilist(nome):
    url = "https://graphql.anilist.co"
    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        title { romaji }
        description(asHtml: false)
        averageScore
        coverImage { large }
      }
    }
    """
    variables = {"search": nome}
    r = requests.post(url, json={"query": query, "variables": variables})
    data = r.json()

    if not data.get("data") or not data["data"]["Media"]:
        return None

    return data["data"]["Media"]

# ===== BUSCAR LINK NO CANAL =====
async def buscar_link_canal(nome):
    async for msg in client.iter_messages(CANAL, search=nome, limit=20):
        if msg.text:
            return f"https://t.me/{CANAL}/{msg.id}"
    return None

# ===== COMANDO /anime =====
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Comando incompleto!\n\n"
            "👉 Use assim:\n"
            "/anime nome do anime\n\n"
            "📺 Exemplo:\n"
            "/anime naruto"
        )
        return

    nome = " ".join(context.args)

    msg = await update.message.reply_text("🔎 Buscando informações...")

    anime_info = buscar_anilist(nome)

    async with client:
        link_canal = await buscar_link_canal(nome)

    await msg.delete()

    if not anime_info:
        await update.message.reply_text("❌ Anime não encontrado.")
        return

    texto = (
        f"🍿 <b>{anime_info['title']['romaji']}</b>\n\n"
        f"⭐ Nota: {anime_info['averageScore']}\n\n"
        f"📖 <i>{anime_info['description'][:400]}...</i>\n\n"
        f"🔗 <b>Assistir no canal:</b>\n"
        f"{link_canal if link_canal else 'Link não encontrado no canal.'}"
    )

    await update.message.reply_photo(
        photo=anime_info["coverImage"]["large"],
        caption=texto,
        parse_mode="HTML"
    )
# ===== COMANDO /manga =====
async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Use assim: /manga one piece")
        return

    nome = " ".join(context.args)
    await update.message.reply_text("📚 Procurando mangá...")

    async with client:
        link = await buscar_manga(nome.lower())

    if link:
        await update.message.reply_text(
            f"📖 Mangá encontrado!\n\n"
            f"📚 {nome}\n"
            f"🔗 {link}"
        )
    else:
        await update.message.reply_text("❌ Mangá não encontrado.")

# ===== INICIAR BOT =====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("anime", anime))
app.add_handler(CommandHandler("manga", manga))

print("🤖 Bot rodando...")
app.run_polling()


