# bot.py
import os
import time
import random
import asyncio
import logging
import aiohttp

from telethon import TelegramClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

from database import (
    init_db, ensure_user, get_user, add_command_and_level,
    set_nick, set_favorite, clear_favorite,
    get_admin_photo, set_admin_photo,
    get_profile_counts, get_collection_name, set_collection_name,
    get_dado_state, set_dado_state, add_to_collection, add_coin,
    get_last_pedido, set_last_pedido,
    paginated_collection, collection_total
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()

CANAL_OBRIGATORIO = int(os.getenv("CANAL_OBRIGATORIO", "0"))
URL_CANAL_OBRIGATORIO = os.getenv("URL_CANAL_OBRIGATORIO", "https://t.me/SourcerBaltigo")

CANAL_ANIME = os.getenv("CANAL_ANIME", "Centraldeanimes_Baltigo")
CANAL_MANGA = os.getenv("CANAL_MANGA", "MangasBrasil")
CANAL_PEDIDOS = int(os.getenv("CANAL_PEDIDOS", "0"))

ADMINS = set(int(x) for x in os.getenv("ADMINS", "").replace(" ", "").split(",") if x.isdigit())

ANTI_SPAM_TIME = int(os.getenv("ANTI_SPAM_TIME", "5"))
COMANDOS_POR_NIVEL = int(os.getenv("COMANDOS_POR_NIVEL", "100"))
COOLDOWN_DADO = int(os.getenv("COOLDOWN_DADO", str(2 * 60 * 60)))
PEDIDO_COOLDOWN = int(os.getenv("PEDIDO_COOLDOWN", str(12 * 60 * 60)))
ITENS_POR_PAGINA = int(os.getenv("ITENS_POR_PAGINA", "10"))

ANILIST_API = "https://graphql.anilist.co"

telethon_client = TelegramClient("sessao_busca", API_ID, API_HASH)

_last_cmd = {}

def anti_spam(user_id: int) -> bool:
    now = time.time()
    last = _last_cmd.get(user_id, 0)
    if now - last < ANTI_SPAM_TIME:
        return False
    _last_cmd[user_id] = now
    return True

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

async def usuario_no_canal(bot, user_id: int) -> bool:
    if CANAL_OBRIGATORIO == 0:
        return True
    try:
        membro = await bot.get_chat_member(CANAL_OBRIGATORIO, user_id)
        return membro.status in ["member", "administrator", "creator"]
    except Exception:
        return False

async def checar_canal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    ok = await usuario_no_canal(context.bot, update.effective_user.id)
    if not ok:
        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Entrar no canal", url=URL_CANAL_OBRIGATORIO)]])
        await update.effective_message.reply_html(
            "🚫 <b>Acesso bloqueado</b>\n\n"
            "Para usar este bot, você precisa estar no nosso canal oficial 👇\n\n"
            "✅ Após entrar, volte e use o comando novamente.",
            reply_markup=teclado,
        )
        return False
    return True

async def touch_user(update: Update) -> None:
    ensure_user(update.effective_user.id, update.effective_user.first_name)

async def registrar_comando(update: Update) -> None:
    await touch_user(update)
    _, level, up = add_command_and_level(update.effective_user.id, COMANDOS_POR_NIVEL)
    if up:
        row = get_user(update.effective_user.id)
        mensagem = (
            "🎉 <b>LEVEL UP!</b>\n\n"
            f"✨ Parabéns <b>{row['nick']}</b>!\n"
            f"⬆️ Você alcançou o <b>Nível {level}</b>!\n\n"
            "🚀 Continue usando o bot!"
        )
        if update.message:
            await update.message.reply_html(mensagem)

async def buscar_post(canal: str, termo: str):
    async for msg in telethon_client.iter_messages(canal, search=termo):
        return msg.id
    return None

async def anilist_post(query: str, variables: dict) -> dict:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.post(ANILIST_API, json={"query": query, "variables": variables}) as r:
            return await r.json(content_type=None)

async def buscar_personagem(nome: str):
    query = """
    query ($search: String) {
      Character(search: $search) {
        id
        name { full }
        image { large }
      }
    }
    """
    data = await anilist_post(query, {"search": nome})
    return data.get("data", {}).get("Character")

# ---------------- COMANDOS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await touch_user(update)
    texto = (
        "🏴‍☠️ <b>Ahoy! Eu sou o Source Baltigo</b>\n\n"
        "⚡ Seu bot definitivo de <b>animes, mangás e personagens</b>.\n\n"
        "📢 <b>Onde eu brilho de verdade?</b>\n"
        "👉 Em <b>grupos</b>! Me adiciona em um grupo e deixa a mágica acontecer ✨"
    )
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Adicionar em um grupo", url="https://t.me/SourceBaltigo_bot?startgroup=start")],
        [InlineKeyboardButton("⚔️ QG Baltigo", url="https://t.me/QG_BALTIGO")],
    ])
    await update.message.reply_html(texto, reply_markup=teclado)

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id
    row = get_user(user_id)

    coins, total = get_profile_counts(user_id)
    nome_colecao = get_collection_name(user_id)

    admin = is_admin(user_id)
    admin_photo = get_admin_photo(user_id)

    titulo = "👤 | <i>Admin</i>" if admin else "👤 | <i>User</i>"
    texto = (
        "🎴 <b>PERFIL DO USUÁRIO</b>\n\n"
        f"{titulo}: <b>{row['nick']}</b>\n\n"
        f"📚 | <i>Coleção</i> (<i>{nome_colecao}</i>): <b>{total}</b>\n"
        f"🪙 | <i>Coins</i>: <b>{coins}</b>\n"
        f"⭐ | <i>Nível</i>: <b>{row['level']}</b>\n"
        f"⌨️ | <i>Comandos</i>: <b>{row['commands']}</b>\n\n"
        "❤️ <i>Favorito</i>:\n"
    )
    texto += f"🧧 <b>{row['fav_name']} ✨</b>" if row["fav_name"] else "— Nenhum favorito"

    foto = admin_photo or (row["fav_image"] if row["fav_image"] else None)
    if foto:
        await update.message.reply_photo(photo=foto, caption=texto, parse_mode="HTML")
    else:
        await update.message.reply_html(texto)

async def nick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)
    if not context.args:
        await update.message.reply_html("✏️ Use:\n<code>/nick SeuNome</code>")
        return
    novo = " ".join(context.args).strip()
    set_nick(update.effective_user.id, novo)
    await update.message.reply_html(f"✨ Nick atualizado para <b>{novo}</b>")

async def favoritar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    if not context.args:
        await update.message.reply_html(
            "❤️ <b>Favoritar personagem</b>\n\n"
            "Use o nome <b>COMPLETO</b>:\n"
            "<code>/favoritar Monkey D. Luffy</code>"
        )
        return

    user_id = update.effective_user.id
    row = get_user(user_id)
    if row["fav_name"]:
        await update.message.reply_html(
            "⚠️ Você já tem um personagem favorito.\n"
            "Use <code>/desfavoritar</code> para trocar."
        )
        return

    nome = " ".join(context.args)
    personagem = await buscar_personagem(nome)
    if not personagem:
        await update.message.reply_html(
            "❌ <b>Personagem não encontrado</b>\n\n"
            "Verifique se o nome está completo e correto."
        )
        return

    fav_name = personagem["name"]["full"]
    fav_image = personagem["image"]["large"]
    set_favorite(user_id, fav_name, fav_image)

    await update.message.reply_photo(
        photo=fav_image,
        caption=(
            "❤️ <b>PERSONAGEM FAVORITADO!</b>\n\n"
            f"🧧 <b>{fav_name}</b>\n\n"
            "🎴 Agora ele é a capa do seu perfil!"
        ),
        parse_mode="HTML"
    )

async def desfavoritar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    row = get_user(update.effective_user.id)
    if not row["fav_name"]:
        await update.message.reply_html("💔 Você não tem personagem favorito.")
        return

    clear_favorite(update.effective_user.id)
    await update.message.reply_html("💔 Personagem removido.")

async def adminfoto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_html("⛔ <b>Acesso negado</b>\n\nEste comando é exclusivo para <b>admins</b>.")
        return

    if not context.args:
        await update.message.reply_html(
            "👑 <b>Foto de Admin</b>\n\n"
            "Envie um link direto de imagem:\n"
            "<code>/adminfoto https://imagem.jpg</code>\n\n"
            "📌 Essa imagem será a <b>capa do seu perfil</b>."
        )
        return

    url = context.args[0].strip()
    set_admin_photo(user_id, url)
    await update.message.reply_photo(
        photo=url,
        caption=(
            "👑 <b>Foto de admin definida!</b>\n\n"
            "✨ Agora seu perfil usará essa imagem.\n"
            "👀 Veja com <code>/perfil</code>"
        ),
        parse_mode="HTML"
    )

async def anime_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        await update.message.reply_text("⏳ Sem flood 😅\nTente novamente em alguns segundos.")
        return

    await registrar_comando(update)

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
    msg_busca = await update.message.reply_html("🔎 Buscando o anime pra você...\nAguarde um instante ⏳")

    msg_id = await buscar_post(CANAL_ANIME, nome)
    if not msg_id:
        await msg_busca.delete()
        await update.message.reply_html(
            "🚫 <b>Nada por aqui…</b>\n"
            "O anime que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        return

    await msg_busca.delete()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Assistir no canal", url=f"https://t.me/{CANAL_ANIME}/{msg_id}")]])
    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_ANIME}",
        message_id=msg_id,
        reply_markup=keyboard
    )

async def manga_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not anti_spam(update.effective_user.id):
        await update.message.reply_text("⏳ Sem flood 😅\nTente novamente em alguns segundos.")
        return

    await registrar_comando(update)

    if not context.args:
        await update.message.reply_html(
            "🚫 <b>Ops! Algo faltou.</b>\n\n"
            "👉 <b>Formato correto:</b>\n"
            "<code>/manga nome do mangá</code>\n\n"
            "📚 <b>Exemplo:</b>\n"
            "<code>/manga naruto</code>"
        )
        return

    nome = " ".join(context.args)
    msg_busca = await update.message.reply_html("📚 Buscando o mangá pra você...\nAguarde um instante ⏳")

    msg_id = await buscar_post(CANAL_MANGA, nome)
    if not msg_id:
        await msg_busca.delete()
        await update.message.reply_html(
            "🚫 <b>Nada por aqui…</b>\n"
            "O mangá que você procurou não foi encontrado no canal.\n\n"
            "✨ <i>Dica:</i> tente outro nome ou uma grafia diferente."
        )
        return

    await msg_busca.delete()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📖 Ler agora", url=f"https://t.me/{CANAL_MANGA}/{msg_id}")]])
    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_MANGA}",
        message_id=msg_id,
        reply_markup=keyboard
    )

def pode_pedir(user_id: int) -> bool:
    last = get_last_pedido(user_id)
    return (int(time.time()) - last) >= PEDIDO_COOLDOWN

async def pedido_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await touch_user(update)

    if not anti_spam(update.effective_user.id):
        await update.message.reply_text("⏳ Sem flood 😅\nTente novamente em alguns segundos.")
        return

    if not pode_pedir(update.effective_user.id):
        await update.message.reply_html(
            "⏳ <b>Pedido recente detectado</b>\n\n"
            "Você já fez um pedido nas últimas <b>12 horas</b>.\n"
            "🕒 Aguarde um pouco antes de enviar outro 🙂"
        )
        return

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

    if CANAL_PEDIDOS == 0:
        await update.message.reply_html("⚠️ Configure <code>CANAL_PEDIDOS</code> (ID do canal).")
        return

    texto_pedido = " ".join(context.args).strip()
    user = update.effective_user

    mensagem_canal = (
        "📥 <b>NOVO PEDIDO REGISTRADO</b>\n\n"
        f"👤 <b>Usuário:</b> {user.full_name}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n\n"
        f"📝 <b>Pedido:</b>\n"
        f"<i>{texto_pedido}</i>\n\n"
        "✅ <b>Status:</b> Pedido listado com sucesso!"
    )

    await context.bot.send_message(chat_id=CANAL_PEDIDOS, text=mensagem_canal, parse_mode="HTML")
    set_last_pedido(update.effective_user.id, int(time.time()))

    await update.message.reply_html(
        f"✅ <b>{user.first_name}</b> [<code>{user.id}</code>]\n\n"
        f"Seu pedido <b>{texto_pedido}</b> já foi listado com sucesso!\n\n"
        "🕒 Agora é só aguardar que em breve estaremos postando.\n\n"
        "✨ Enquanto espera, aproveita para conhecer a central e os outros canais disponíveis!"
    )

async def dado_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id
    now = int(time.time())

    last_dado, coins = get_dado_state(user_id)
    if now - last_dado < COOLDOWN_DADO:
        falta = COOLDOWN_DADO - (now - last_dado)
        h = falta // 3600
        m = (falta % 3600) // 60
        await update.message.reply_text(f"⏳ Você já girou o dado!\n\n🎲 Tente novamente em **{h}h {m}m**", parse_mode="Markdown")
        return

    dice = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji="🎲")
    await asyncio.sleep(3)
    numero = dice.dice.value

    raridades = {
        1: (700, 1000, "💀 *Ruim*"),
        2: (500, 699, "😐 *Fraco*"),
        3: (300, 499, "⭐ *Médio*"),
        4: (150, 299, "🔥 *Forte*"),
        5: (50, 149, "💎 *Raro*"),
        6: (1, 49, "👑 *Lendário*")
    }
    page_min, page_max, raridade = raridades[numero]

    # pega personagem por popularidade (rápido e divertido)
    query = """
    query ($page: Int) {
      Page(page: $page, perPage: 1) {
        characters(sort: FAVOURITES_DESC) {
          id
          name { full }
          image { large }
        }
      }
    }
    """
    page = random.randint(page_min, page_max)
    data = await anilist_post(query, {"page": page})
    personagem = data["data"]["Page"]["characters"][0]

    added = add_to_collection(user_id, int(personagem["id"]), personagem["name"]["full"], personagem["image"]["large"])
    if not added:
        add_coin(user_id, 1)
        coins += 1
        resultado = "🪙 Personagem repetido → +1 Coin"
    else:
        resultado = "📦 Adicionado à coleção!"

    set_dado_state(user_id, now, coins)

    await update.message.reply_photo(
        photo=personagem["image"]["large"],
        caption=(
            "🎰 *DADO DA SORTE*\n\n"
            f"🎲 Número: `{numero}`\n"
            f"{raridade}\n\n"
            f"✨ *{personagem['name']['full']}*\n\n"
            f"{resultado}\n"
            f"🪙 Coins: `{coins}`"
        ),
        parse_mode="Markdown",
    )

async def colecao_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)
    await enviar_colecao(update, context, page=1, edit=False)

async def enviar_colecao(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, edit: bool):
    user_id = update.effective_user.id
    total = collection_total(user_id)
    if total <= 0:
        if edit and update.callback_query:
            await update.callback_query.message.edit_text("📦 Sua coleção está vazia.")
        else:
            await update.effective_message.reply_text("📦 Sua coleção está vazia.")
        return

    total_pages = (total - 1) // ITENS_POR_PAGINA + 1
    page = max(1, min(page, total_pages))
    offset = (page - 1) * ITENS_POR_PAGINA

    nome = get_collection_name(user_id)
    rows = paginated_collection(user_id, ITENS_POR_PAGINA, offset)

    texto = f"📚 *{nome}*\n\n📖 | *{page}/{total_pages}*\n\n"
    for r in rows:
        texto += f"🧧 `{r['character_id']}.` {r['character_name']}\n"

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"colecao:{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"colecao:{page+1}"))

    keyboard = InlineKeyboardMarkup([nav] if nav else [])

    if edit and update.callback_query:
        await update.callback_query.message.edit_text(texto, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(texto, parse_mode="Markdown", reply_markup=keyboard)

async def colecao_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    page = int(q.data.split(":")[1])
    await enviar_colecao(update, context, page=page, edit=True)

async def setcolecao_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    if not context.args:
        await update.message.reply_html("✏️ Para renomear a coleção use:\n<code>/setcolecao Nome da Coleção</code>")
        return

    name = " ".join(context.args).strip()
    set_collection_name(update.effective_user.id, name)
    await update.message.reply_text(f"✅ Nome da coleção atualizado para: {name}")

# ---------------- BOOT ----------------
async def post_init(app):
    init_db()
    await telethon_client.start()
    log.info("DB OK + Telethon OK")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Defina BOT_TOKEN no Railway.")
    if API_ID == 0 or not API_HASH:
        raise RuntimeError("Defina API_ID e API_HASH no Railway (Telethon).")

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("perfil", perfil))
    app.add_handler(CommandHandler("nick", nick_cmd))
    app.add_handler(CommandHandler("favoritar", favoritar_cmd))
    app.add_handler(CommandHandler("desfavoritar", desfavoritar_cmd))
    app.add_handler(CommandHandler("adminfoto", adminfoto_cmd))

    app.add_handler(CommandHandler("anime", anime_cmd))
    app.add_handler(CommandHandler("manga", manga_cmd))
    app.add_handler(CommandHandler("pedido", pedido_cmd))

    app.add_handler(CommandHandler("dado", dado_cmd))
    app.add_handler(CommandHandler("colecao", colecao_cmd))
    app.add_handler(CommandHandler("setcolecao", setcolecao_cmd))
    app.add_handler(CallbackQueryHandler(colecao_cb, pattern=r"^colecao:\d+$"))

    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
