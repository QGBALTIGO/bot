import os
from pyrogram import Client
from aiohttp import ClientSession

TRIGGERS = os.environ.get("TRIGGERS", "/ !").split()
API_HASH = os.environ.get("22be457ce73f65fad82315073fbc3")
BOT_TOKEN = os.environ.get("8001392073:AAEW64SRZI7BIY6l8reeKnNONu-6gjLt0Sg")
BOT_NAME = os.environ.get("@SourceBaltigo_Bot")
DB_URL = os.environ.get("DATABASE_URL=mongodb+srv://kaykys468_db_user:oqSNFQ0Su4uWCcRT@cluster0.xxxxx.mongodb.net/anibot")
ANILIST_CLIENT = os.environ.get("36318")
ANILIST_SECRET = os.environ.get("0S7GDyIMBRrvmQI8M2Mc32FIdC1j9wgK4WVhUe0M")
ANILIST_REDIRECT_URL = os.environ.get("Ahttps://example.com", "https://anilist.co/api/v2/oauth/pin")
API_ID = int(os.environ.get("34116600"))
LOG_CHANNEL_ID = int(os.environ.get("-1003889677462"))
OWNER = list(filter(lambda x: x, map(int, os.environ.get("1852596083", "1005170481 804248372 1993696756").split())))  ## sudos can be included

DOWN_PATH = "anibot/downloads/"
HELP_DICT = dict()

session = ClientSession()
plugins = dict(root="anibot/plugins")
anibot = Client("anibot", bot_token=8001392073:AAEW64SRZI7BIY6l8reeKnNONu-6gjLt0Sg, api_id=34116600, api_hash=22be457ce73f65fad82315073fbc3, plugins=plugins)

has_user: bool = False
if os.environ.get('silasemanueI'):
    has_user: bool = True
    user = Client(os.environ.get('silasemanueI'), api_id=34116600, api_hash=22be457ce73f65fad82315073fbc3)

HELP_DICT['Group'] = '''
Group based commands:

/settings - Toggle stuff like whether to allow 18+ stuff in group or whether to notify about aired animes, etc and change UI

/disable - Disable use of a cmd in the group (Disable multiple cmds by adding space between them)
`/disable anime anilist me user`

/enable - Enable use of a cmd in the group (Enable multiple cmds by adding space between them)
`/enable anime anilist me user`

/disabled - List out disabled cmds
'''

HELP_DICT["Additional"] = """Use /reverse cmd to get reverse search via tracemoepy API
__Note: This works best on uncropped anime pic,
when used on cropped media, you may get result but it might not be too reliable__

Use /schedule cmd to get scheduled animes based on weekdays

Use /watch cmd to get watch order of searched anime

Use /fillers cmd to get a list of fillers for an anime

Use /quote cmd to get a random quote
"""

HELP_DICT["Anilist"] = """
Below is the list of basic anilist cmds for info on anime, character, manga, etc.

/anime - Use this cmd to get info on specific anime using keywords (anime name) or Anilist ID
(Can lookup info on sequels and prequels)

/anilist - Use this cmd to choose between multiple animes with similar names related to searched query
(Doesn't includes buttons for prequel and sequel)

/character - Use this cmd to get info on character

/manga - Use this cmd to get info on manga

/airing - Use this cmd to get info on airing status of anime

/top - Use this cmd to lookup top animes of a genre/tag or from all animes
(To get a list of available tags or genres send /gettags or /getgenres
'/gettags nsfw' for nsfw tags)

/user - Use this cmd to get info on an anilist user

/browse - Use this cmd to get updates about latest animes
"""

HELP_DICT["Oauth"] = """
This includes advanced anilist features

Use /auth or !auth cmd to get details on how to authorize your Anilist account with bot
Authorising yourself unlocks advanced features of bot like:
- adding anime/character/manga to favourites
- viewing your anilist data related to anime/manga in your searches which includes score, status, and favourites
- unlock /flex, /me, /activity and /favourites commands
- adding/updating anilist entry like completed or plan to watch/read
- deleting anilist entry

Use /flex or !flex cmd to get your anilist stats

Use /logout or !logout cmd to disconnect your Anilist account

Use /me or !me cmd to get your anilist recent activity
Can also use /activity or !activity

Use /favourites or !favourites cmd to get your anilist favourites

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
    await update.message.reply_text("🔎 Teste o anime pra você...\nAguarde um instante ⏳")

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
app.add_handler(CommandHandler("anime", anime))
app.add_handler(CommandHandler("manga", manga))

print("🤖 Bot rodando...")
app.run_polling()











