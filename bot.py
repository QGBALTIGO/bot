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
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html(
            "🚫 <b>Ops! Algo faltou.</b>\n\n"
            "👉 <b>Formato correto:</b>\n"
            "<code>/anime nome do anime</code>\n\n"
            "🎬 <b>Exemplo:</b>\n"
            "<code>/anime naruto</code>")
        return
    nome = " ".join(context.args)
    await update.message.reply_text("🔎 Buscando o anime pra você...\nAguarde um instante ⏳")
    async with client:
        link = await buscar_anime(nome.lower())
    if link:
        await update.message.reply_html(
    f"🍿 <b>A espera acabou.</b>\n"
    f"O momento chegou.\n\n"
    f"📺 <b>{nome.upper()}</b>\n\n"
    f"Entre, assista e desapareça do mundo por algumas horas.\n\n"
    f"🔗 <b>Disponível agora:</b>\n"
    f"{link}"
)
    else:
        await update.message.reply_html(
    "🚫 <b>Nada por aqui…</b>\n\n"
    "O anime que você procurou não foi encontrado no canal.\n\n"
    "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
)
        
# ===== COMANDO /manga =====
async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html(
            "🚫 <b>Ops! Algo faltou.</b>\n\n"
            "👉 <b>Formato correto:</b>\n"
            "<code>/manga nome do mangá</code>\n\n"
            "📖 <b>Exemplo:</b>\n"
            "<code>/manga one piece</code>"
        )
        return
    nome = " ".join(context.args)
    await update.message.reply_text("📚 Procurando o mangá...\nJá já te mando 📖")
    async with client:
        link = await buscar_manga(nome.lower())
    if link:
        await update.message.reply_html(
    f"📚 <b>A espera acabou.</b>\n"
    f"A próxima leitura te chama.\n\n"
    f"📖 <b>{nome.upper()}</b>\n\n"
    f"Prepare-se para virar páginas e esquecer do tempo.\n\n"
    f"🔗 <b>Leia agora:</b>\n"
    f"{link}"
)
    else:
        await update.message.reply_html(
    "🚫 <b>Nada por aqui…</b>\n\n"
    "O mangá que você procurou não foi encontrado no canal.\n\n"
    "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
)
        
# ===== INICIAR BOT =====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("anime", anime))
app.add_handler(CommandHandler("manga", manga))
print("🤖 Bot rodando...")
app.run_polling()



