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

# ===== FUNÇÃO ANIList =====
def buscar_anime(nome):
    url = "https://graphql.anilist.co"
    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        title {
          romaji
        }
        description(asHtml: false)
        averageScore
        siteUrl
        coverImage {
          large
        }
      }
    }
    """
    variables = {"search": nome}
    response = requests.post(url, json={"query": query, "variables": variables})
    data = response.json()

    if "data" not in data or data["data"]["Media"] is None:
        return None

    return data["data"]["Media"]

# ===== COMANDO /anime =====
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Use assim:\n\n"
            "👉 /anime nome do anime\n"
            "Exemplo: /anime naruto"
        )
        return

    nome = " ".join(context.args)
    msg = await update.message.reply_text("🔎 Procurando informações no AniList...")

    anime = buscar_anime(nome)

    await msg.delete()

    if not anime:
        await update.message.reply_text("❌ Anime não encontrado.")
        return

    texto = (
        f"🍿 <b>{anime['title']['romaji']}</b>\n\n"
        f"⭐ Nota: {anime['averageScore']}\n\n"
        f"📖 <i>{anime['description'][:500]}...</i>\n\n"
        f"🔗 <a href='{anime['siteUrl']}'>Ver no AniList</a>"
    )

    await update.message.reply_photo(
        photo=anime["coverImage"]["large"],
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

