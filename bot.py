from telethon import TelegramClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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

# ===== COMANDO /foto =====
async def buscar_post(canal, termo):
    async for msg in client.iter_messages(canal, search=termo):
        if msg:
            link = f"https://t.me/{canal}/{msg.id}"
            foto = None

            if msg.media and isinstance(msg.media, MessageMediaPhoto):
                foto = msg.photo

            return link, foto

    return None, None
    
# ===== COMANDO /anime =====
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    await update.message.reply_text(
        "🔎 Buscando o anime pra você...\nAguarde um instante ⏳"
    )

    async with client:
        link = await buscar_anime(nome.lower())

    if link:
        keyboard = [
            [InlineKeyboardButton("▶️ Assistir agora", url=link)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_html(
            f"🍿 <b>A espera acabou.</b>\n"
            f"O momento chegou.\n\n"
            f"📺 <b>{nome.upper()}</b>\n\n"
            f"Clique no botão abaixo para assistir 👇",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_html(
            "🚫 <b>Nada por aqui…</b>\n\n"
            "O anime que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        
        # 👉 SE TIVER FOTO
    if msg.photo:
        await update.message.reply_photo(
            photo=msg.photo,
            caption=(
                f"🍿 <b>{nome.upper()}</b>\n\n"
                f"Clique no botão abaixo para assistir 👇"
            ),
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    else:
        await update.message.reply_html(
            f"🍿 <b>{nome.upper()}</b>\n\n"
            f"{link}",
            reply_markup=reply_markup
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

    await update.message.reply_text(
        "📚 Procurando o mangá pra você...\nAguarde um instante ⏳"
    )

    async with client:
        link = await buscar_manga(nome.lower())

    if link:
        keyboard = [
            [InlineKeyboardButton("📖 Ler agora", url=link)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_html(
            f"📚 <b>A espera acabou.</b>\n"
            f"A próxima leitura te chama.\n\n"
            f"📖 <b>{nome.upper()}</b>\n\n"
            f"Clique no botão abaixo para ler 👇",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_html(
            "🚫 <b>Nada por aqui…</b>\n\n"
            "O mangá que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        
# ===== INICIAR BOT =====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("anime", anime))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("manga", manga))
print("🤖 Bot rodando...")
app.run_polling()







