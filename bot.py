from telethon import TelegramClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import time
from telegram.ext import InlineQueryHandler
from telegram import InlineQueryResultArticle, InputTextMessageContent

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
CANAL_PEDIDOS = -1003895811362  # ID do canal fechado

# ===== TELETHON =====
client = TelegramClient("sessao_busca", api_id, api_hash)
async def buscar_post(canal, termo):
    async for msg in client.iter_messages(canal, search=termo):
        return msg.id
    return None

# ===== ENTRADA CANAIS =====
from telegram.error import BadRequest

async def usuario_no_canal(context, user_id: int) -> bool:
    try:
        membro_anime = await context.bot.get_chat_member(-1001823020280, user_id)
        if membro_anime.status in ["member", "administrator", "creator"]:
            return True
    except BadRequest:
        pass

    try:
        membro_manga = await context.bot.get_chat_member(-1001834602691, user_id)
        if membro_manga.status in ["member", "administrator", "creator"]:
            return True
    except BadRequest:
        pass

    return False

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def bloquear_se_nao_membro(update, context) -> bool:
    user_id = update.effective_user.id
    if await usuario_no_canal(context, user_id):
        return False  # pode usar o bot

    keyboard = [
        [InlineKeyboardButton("🎬 Canal de Animes", url="t.me/Centraldeanimes_Baltigo")],
        [InlineKeyboardButton("📚 Canal de Mangás", url="t.me/MangasBrasil")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_html(
        "🔒 <b>Acesso restrito</b>\n\n"
        "Para usar os comandos do bot, você precisa estar em <b>pelo menos um</b> dos canais abaixo 👇",
        reply_markup=reply_markup
    )
    return True
            
# ===== CONFIG ANTIFLOOD =====
PEDIDO_COOLDOWN = 12 * 60 * 60  # 12 horas
ultimo_pedido = {}

def pode_pedir(user_id: int) -> bool:
    agora = time.time()
    if user_id in ultimo_pedido:
        if agora - ultimo_pedido[user_id] < PEDIDO_COOLDOWN:
            return False
    ultimo_pedido[user_id] = agora
    return True


# ===== COMANDO /pedido =====
async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

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

# ===== BUSCAS INLINE =====
async def inline_busca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.lower().strip()

    if not query:
        return

    resultados = []

    async with client:
        # 🔍 BUSCA ANIMES
        async for msg in client.iter_messages(CANAL_ANIME, search=query, limit=5):
            resultados.append(
                InlineQueryResultArticle(
                    id=f"anime_{msg.id}",
                    title=f"🎬 Anime: {query.title()}",
                    description="Clique para assistir",
                    input_message_content=InputTextMessageContent(
                        f"🎬 *Anime encontrado!*\n\n"
                        f"🔗 https://t.me/{CANAL_ANIME}/{msg.id}",
                        parse_mode="Markdown"
                    )
                )
            )

        # 🔍 BUSCA MANGÁS
        async for msg in client.iter_messages(CANAL_MANGA, search=query, limit=5):
            resultados.append(
                InlineQueryResultArticle(
                    id=f"manga_{msg.id}",
                    title=f"📚 Mangá: {query.title()}",
                    description="Clique para ler",
                    input_message_content=InputTextMessageContent(
                        f"📚 *Mangá encontrado!*\n\n"
                        f"🔗 https://t.me/{CANAL_MANGA}/{msg.id}",
                        parse_mode="Markdown"
                    )
                )
            )

    if resultados:
        await update.inline_query.answer(
            resultados,
            cache_time=5,
            is_personal=True
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
        msg_id = await buscar_post(CANAL_ANIME, nome)

    if not msg_id:
        await update.message.reply_html(
            "🚫 <b>Nada por aqui…</b>\n\n"
            "O anime que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        return

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
    if not context.args:
        await update.message.reply_html(
            "🚫 <b>Ops! Algo faltou.</b>\n\n"
            "👉 <b>Formato correto:</b>\n"
            "<code>/manga nome do mangá</code>\n\n"
            "🎬 <b>Exemplo:</b>\n"
            "<code>/manga naruto</code>"
        )
        return

    nome = " ".join(context.args)
    await update.message.reply_text("📚 Buscando o mangá pra você...\nAguarde um instante ⏳")

    async with client:
        msg_id = await buscar_post(CANAL_MANGA, nome)

    if not msg_id:
        await update.message.reply_html(
             "🚫 <b>Nada por aqui…</b>\n\n"
            "O mangá que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        return

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
app.add_handler(InlineQueryHandler(inline_busca))
app.add_handler(CommandHandler("pedido", pedido))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("manga", manga))
print("🤖 Bot rodando...")
app.run_polling()





