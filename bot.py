import requests
from telethon import TelegramClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===== DADOS =====
API_ID = 34116600
API_HASH = "b8f22be457ce73f65fad82315073fbc3"
BOT_TOKEN = "8001392073:AAEW64SRZI7BIY6l8reeKnNONu-6gjLt0Sg"
CANAL = "Centraldeanimes_Baltigo"

# ===== TELETHON (USERBOT) =====
client = TelegramClient("sessao_busca", API_ID, API_HASH)

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

# ===== INICIAR =====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("anime", anime))

print("🤖 Bot rodando (AniList + Canal)...")
app.run_polling()
