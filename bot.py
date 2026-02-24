# ================================
# bot.py — SOURCE BALTIGO (COMPLETO)
# ================================

# ==================================================
# 0) IMPORTS
# ==================================================
import os
import re
import time
import json
import random
import asyncio
from typing import Optional, Dict, Any, List, Tuple

import aiohttp
from telethon import TelegramClient

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from database import (
    db,
    cursor,
    init_db,
    ensure_user_row,
    get_user_row,
    set_user_nick,
    add_coin,
    set_collection_name,
    get_collection_name,
    count_collection,
    get_collection_page,
    user_has_character,
    add_character_to_collection,
    swap_trade_execute,
    create_trade,
    get_latest_pending_trade_for_to_user,
    mark_trade_status,
    upsert_battle,
    get_battle,
    delete_battle,
    battle_set_char,
    battle_set_turn,
    battle_damage,
    shop_create_sale,
    shop_get_sale,
    shop_delete_sale,
    shop_list_user_chars,
)

# ==================================================
# 1) CONFIG (TUDO VIA VARIÁVEIS DO RAILWAY)
# ==================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()

CANAL_ANIME = os.getenv("CANAL_ANIME", "").strip().lstrip("@")
CANAL_MANGA = os.getenv("CANAL_MANGA", "").strip().lstrip("@")
CANAL_PEDIDOS = int(os.getenv("CANAL_PEDIDOS", "0"))

CANAL_OBRIGATORIO = int(os.getenv("CANAL_OBRIGATORIO", "0"))
URL_CANAL_OBRIGATORIO = os.getenv("URL_CANAL_OBRIGATORIO", "https://t.me/SourcerBaltigo").strip()

ADMINS_RAW = os.getenv("ADMINS", "").strip()

ANILIST_API = "https://graphql.anilist.co"

# ==================================================
# 2) VALIDADORES BÁSICOS
# ==================================================
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado. Crie a variável BOT_TOKEN no Railway.")
if not API_ID or not API_HASH:
    raise RuntimeError("API_ID/API_HASH não encontrados. Crie as variáveis API_ID e API_HASH no Railway.")
if not CANAL_ANIME or not CANAL_MANGA:
    # não travo o bot se você quiser usar só parte dos comandos
    print("⚠️ Aviso: CANAL_ANIME ou CANAL_MANGA não definidos.")
if not CANAL_PEDIDOS:
    print("⚠️ Aviso: CANAL_PEDIDOS não definido.")
if not CANAL_OBRIGATORIO:
    print("⚠️ Aviso: CANAL_OBRIGATORIO não definido (checar canal ficará inativo).")

# ==================================================
# 3) TELETHON CLIENT (busca em canais)
# ==================================================
client = TelegramClient("sessao_busca", API_ID, API_HASH)

async def buscar_post(canal: str, termo: str) -> Optional[int]:
    """Retorna o message_id do primeiro post que bater no search."""
    async for msg in client.iter_messages(canal, search=termo):
        return msg.id
    return None

# ==================================================
# 4) ANTI-SPAM
# ==================================================
ANTI_SPAM_TIME = 5  # segundos
last_command_time: Dict[int, float] = {}

def anti_spam(user_id: int) -> bool:
    agora = time.time()
    if user_id in last_command_time and (agora - last_command_time[user_id] < ANTI_SPAM_TIME):
        return False
    last_command_time[user_id] = agora
    return True

# ==================================================
# 5) ADMINS
# ==================================================
def parse_admins(raw: str) -> set:
    if not raw:
        return set()
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids

ADMINS = parse_admins(ADMINS_RAW)

ADMIN_PHOTOS: Dict[int, str] = {}  # (se quiser depois persistir, dá pra jogar no DB)

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def get_admin_photo(user_id: int) -> Optional[str]:
    return ADMIN_PHOTOS.get(user_id)

# ==================================================
# 6) CANAL OBRIGATÓRIO (TRAVA)
# ==================================================
async def usuario_no_canal(bot, user_id: int) -> bool:
    if not CANAL_OBRIGATORIO:
        return True  # se não configurou, não bloqueia
    try:
        membro = await bot.get_chat_member(CANAL_OBRIGATORIO, user_id)
        return membro.status in ["member", "administrator", "creator"]
    except:
        return False

async def checar_canal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    esta_no_canal = await usuario_no_canal(context.bot, user_id)

    if not esta_no_canal:
        teclado = InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 Entrar no canal", url=URL_CANAL_OBRIGATORIO)
        ]])
        if update.message:
            await update.message.reply_html(
                "🚫 <b>Acesso bloqueado</b>\n\n"
                "Para usar este bot, você precisa estar no nosso canal oficial 👇\n\n"
                "✅ Após entrar, volte e use o comando novamente.",
                reply_markup=teclado
            )
        return False

    return True

# ==================================================
# 7) SISTEMA DE NÍVEL (SALVO NO POSTGRES)
# ==================================================
COMANDOS_POR_NIVEL = 100

async def registrar_comando(update: Update):
    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

    row = get_user_row(user_id)
    commands = int(row["commands"] or 0) + 1
    level = int(row["level"] or 1)

    novo_nivel = (commands // COMANDOS_POR_NIVEL) + 1
    if novo_nivel > level:
        # atualiza
        cursor.execute(
            "UPDATE users SET commands=%s, level=%s WHERE user_id=%s",
            (commands, novo_nivel, user_id)
        )
        db.commit()

        mensagem = (
            "🎉 <b>LEVEL UP!</b>\n\n"
            f"✨ Parabéns <b>{row['nick']}</b>!\n"
            f"⬆️ Você alcançou o <b>Nível {novo_nivel}</b>!\n\n"
            "🚀 Continue usando o bot!"
        )
        if update.message:
            await update.message.reply_html(mensagem)
        return

    cursor.execute("UPDATE users SET commands=%s WHERE user_id=%s", (commands, user_id))
    db.commit()

# ==================================================
# 8) /start
# ==================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🏴‍☠️ <b>Source Baltigo</b>\n"
        "Seu hub de <b>animes, mangás e personagens</b>.\n\n"
        "✨ <b>Comandos rápidos</b>\n"
        "• <code>/anime</code> — buscar anime no canal\n"
        "• <code>/manga</code> — buscar mangá no canal\n"
        "• <code>/infoanime</code> — info completa do anime\n"
        "• <code>/infomanga</code> — info completa do mangá\n"
        "• <code>/perso</code> — info do personagem\n"
        "• <code>/recomenda</code> — recomendações\n"
        "• <code>/emalta</code> — ranking do momento\n\n"
        "📢 Me adicione em um grupo pra aproveitar melhor."
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Adicionar em um grupo", url="https://t.me/SourceBaltigo_bot?startgroup=start")],
        [InlineKeyboardButton("⚔️ QG Baltigo", url="t.me/QG_BALTIGO")]
    ])

    await update.message.reply_photo(
        photo="https://photo.chelpbot.me/AgACAgEAAxkBZpDL8mmeFx3it__n9zwKhDWr-EiaijwiAAIdDGsbjP7wRDMvEtZUPvYtAQADAgADeQADOgQ/photo.jpg",
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado
    )

# ==================================================
# 9) /login (AniList OAuth)
# ==================================================
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    url = (
        "https://anilist.co/api/v2/oauth/authorize"
        "?client_id=36358"
        "&redirect_uri=https://loginbot-production-eb95.up.railway.app/callback"
        "&response_type=code"
        f"&state={telegram_id}"
    )

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔐 Conectar com AniList", url=url)]])
    await update.message.reply_text("🔑 Clique para conectar sua conta AniList:", reply_markup=keyboard)

# ==================================================
# 10) /adminfoto
# ==================================================
async def adminfoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_html(
            "⛔ <b>Acesso negado</b>\n\n"
            "Este comando é exclusivo para <b>admins</b>."
        )
        return

    if not context.args:
        await update.message.reply_html(
            "👑 <b>Foto de Admin</b>\n\n"
            "Envie um link direto de imagem:\n"
            "<code>/adminfoto https://imagem.jpg</code>\n\n"
            "📌 Essa imagem será a <b>capa do seu perfil</b>."
        )
        return

    url = context.args[0]
    ADMIN_PHOTOS[user_id] = url

    await update.message.reply_photo(
        photo=url,
        caption=(
            "👑 <b>Foto de admin definida!</b>\n\n"
            "✨ Agora seu perfil usará essa imagem.\n"
            "👀 Veja com <code>/perfil</code>"
        ),
        parse_mode="HTML"
    )

# ==================================================
# 11) PERFIL / NICK / NIVEL / FAVORITO (POSTGRES)
# ==================================================
async def nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    await registrar_comando(update)
    ensure_user_row(update.effective_user.id, update.effective_user.first_name)

    # se mandar só /nick
    if not context.args:
        await update.message.reply_html(
            "✏️ <b>DEFINIR NICK</b>\n\n"
            "Seu nick precisa ser:\n"
            "• <b>Uma palavra</b> (sem espaços)\n"
            "• <b>Único</b> (ninguém mais pode ter)\n\n"
            "📌 <b>Como usar:</b>\n"
            "<code>/nick bredesozail</code>\n\n"
            "✅ Permitido: letras, números e _ (underline)\n"
            "❌ Não pode: espaços, acentos e símbolos"
        )
        return

    # pega o nick como 1 palavra (se vier mais de 1, rejeita)
    if len(context.args) != 1:
        await update.message.reply_html(
            "❌ <b>Nick inválido</b>\n\n"
            "Seu nick deve ser <b>apenas uma palavra</b>.\n\n"
            "📌 Exemplo:\n"
            "<code>/nick bredesozail</code>"
        )
        return

    raw = context.args[0].strip()

    # normaliza para comparar (e salvar) em minúsculo
    nick_novo = raw.lower()

    # regras: 3 a 16 chars (ajuste se quiser)
    if not (3 <= len(nick_novo) <= 16):
        await update.message.reply_html(
            "❌ <b>Tamanho inválido</b>\n\n"
            "Seu nick precisa ter entre <code>3</code> e <code>16</code> caracteres."
        )
        return

    # só letras/números/underscore
    if not re.fullmatch(r"[a-z0-9_]+", nick_novo):
        await update.message.reply_html(
            "❌ <b>Formato inválido</b>\n\n"
            "Use apenas:\n"
            "• letras (a-z)\n"
            "• números (0-9)\n"
            "• underline (_) \n\n"
            "📌 Exemplo:\n"
            "<code>/nick rei_dos_piratas</code>"
        )
        return

    user_id = update.effective_user.id

    # tenta salvar — se já existir, o Postgres vai bloquear por causa do índice UNIQUE
    try:
        cursor.execute("UPDATE users SET nick=%s WHERE user_id=%s", (nick_novo, user_id))
        db.commit()

    except Exception:
        db.rollback()
        await update.message.reply_html(
            "🚫 <b>Nick indisponível</b>\n\n"
            f"O nick <code>{nick_novo}</code> já está em uso.\n"
            "Tente outro 🙂"
        )
        return

    await update.message.reply_html(
        "✅ <b>Nick definido!</b>\n\n"
        f"Agora seu nick é: <code>{nick_novo}</code>"
    )

async def nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)
    row = get_user_row(user_id)

    comandos = int(row["commands"] or 0)
    nivel_atual = int(row["level"] or 1)

    proximo = nivel_atual * COMANDOS_POR_NIVEL
    faltam = max(proximo - comandos, 0)

    await update.message.reply_html(
        "📊 <b>SEU PROGRESSO</b>\n\n"
        f"👤 <b>{row['nick']}</b>\n\n"
        f"⭐ <i>Nível</i>: <b>{nivel_atual}</b>\n"
        f"⌨️ <i>Comandos usados</i>: <b>{comandos}</b>\n"
        f"⏳ <i>Faltam</i>: <b>{faltam}</b> comandos"
    )

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    ensure_user_row(update.effective_user.id, update.effective_user.first_name)



    # 1) decidir qual perfil mostrar:
    # - se tiver argumento: /perfil nick
    # - se não: seu próprio perfil
    alvo_row = None
    alvo_nick = None

    if context.args:
        # nick único = 1 palavra
        alvo_nick = context.args[0].strip()
        from database import get_user_by_nick
        alvo_row = get_user_by_nick(alvo_nick)

        if not alvo_row:
            await update.message.reply_html(
                "❌ <b>Usuário não encontrado</b>\n\n"
                "Verifique se o nick está correto.\n"
                "📌 Exemplo: <code>/perfil bredesozail</code>"
            )
            return
    else:
        from database import get_user_row
        alvo_row = get_user_row(update.effective_user.id)

    # fallback
    if not alvo_row:
        await update.message.reply_text("❌ Não consegui carregar o perfil agora.")
        return

    # 2) dados comuns
    user_id = int(alvo_row["user_id"])
    nick = alvo_row["nick"] or "User"

    fav_name = alvo_row.get("fav_name")
    fav_image = alvo_row.get("fav_image")

    # 3) se perfil privado e quem está vendo NÃO é o dono
    private_on = bool(alvo_row.get("private_profile"))

    if private_on and user_id != update.effective_user.id:
        texto = (
            f" | User: {nick}\n\n"
            "🔐 | <b>Private Profile!</b>\n\n"
            "❤️ <b>Favorite:</b>\n"
        )
        if fav_name:
            texto += f"🧧 1. <b>{fav_name}</b> ✨"
        else:
            texto += "— Nenhum favorito"

        # mostra com foto do favorito se tiver
        if fav_image:
            await update.message.reply_photo(photo=fav_image, caption=texto, parse_mode="HTML")
        else:
            await update.message.reply_html(texto)
        return

    # 4) perfil normal (seu ou público)
    from database import count_collection
    total_colecao = count_collection(user_id)

    coins = int(alvo_row.get("coins") or 0)
    level = int(alvo_row.get("level") or 1)
    nome_colecao = alvo_row.get("collection_name") or "Minha Coleção"

    texto = (
        f" | User: {nick}\n\n"

        f"📚 | <i>Coleção</i>: <b>{total_colecao}</b>\n"
        f"🪙 | <i>Coins</i>: <b>{coins}</b>\n"
        f"⭐ | <i>Nível</i>: <b>{level}</b>\n\n"
        "❤️ <i>Favorito</i>:\n"
    )

    if fav_name:
        texto += f"🧧 1. <b>{fav_name}</b> ✨"
    else:
        texto += "— Nenhum favorito"

    # foto: mantém sua lógica (admin foto > favorito > sem foto)
    foto = get_admin_photo(user_id) or fav_image

    if foto:
        await update.message.reply_photo(photo=foto, caption=texto, parse_mode="HTML")
    else:
        await update.message.reply_html(texto)

async def privado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    ensure_user_row(update.effective_user.id, update.effective_user.first_name)

    if not context.args:
        await update.message.reply_html(
            "🔐 <b>PERFIL PRIVADO</b>\n\n"
            "Ative para esconder suas infos (os outros só veem “Private Profile” + favorito).\n\n"
            "✅ <b>Como usar:</b>\n"
            "<code>/privado on</code>\n"
            "<code>/privado off</code>"
        )
        return

    opt = context.args[0].lower()
    if opt not in ("on", "off"):
        await update.message.reply_html("❌ Use <code>/privado on</code> ou <code>/privado off</code>.")
        return

    from database import set_private_profile
    set_private_profile(update.effective_user.id, opt == "on")

    if opt == "on":
        await update.message.reply_html("🔐 <b>Perfil privado ativado!</b>")
    else:
        await update.message.reply_html("🔓 <b>Perfil privado desativado!</b>")

async def favoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    ensure_user_row(user_id, update.effective_user.first_name)
    row = get_user_row(user_id)

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

    cursor.execute(
        "UPDATE users SET fav_name=%s, fav_image=%s WHERE user_id=%s",
        (personagem["name"]["full"], personagem["image"]["large"], user_id)
    )
    db.commit()

    await update.message.reply_photo(
        photo=personagem["image"]["large"],
        caption=(
            "❤️ <b>PERSONAGEM FAVORITADO!</b>\n\n"
            f"🧧 <b>{personagem['name']['full']}</b>\n\n"
            "🎴 Agora ele é a capa do seu perfil!"
        ),
        parse_mode="HTML"
    )

async def desfavoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)
    row = get_user_row(user_id)

    if not row["fav_name"]:
        await update.message.reply_html("💔 Você não tem personagem favorito.")
        return

    cursor.execute("UPDATE users SET fav_name=NULL, fav_image=NULL WHERE user_id=%s", (user_id,))
    db.commit()
    await update.message.reply_html("💔 Personagem removido.")

# ==================================================
# 12) /anime e /manga (busca no canal)
# ==================================================
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await checar_canal(update, context):
        return
    if not anti_spam(user_id):
        await update.message.reply_text("⏳ Sem flood 😅\nTente novamente em alguns segundos.")
        return

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

    msg_busca = await update.message.reply_html(
        "🔎 Buscando o anime pra você...\n"
        "Aguarde um instante ⏳"
    )

    async with client:
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

    keyboard = [[InlineKeyboardButton("▶️ Assistir no canal", url=f"https://t.me/{CANAL_ANIME}/{msg_id}")]]
    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_ANIME}",
        message_id=msg_id,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await checar_canal(update, context):
        return
    if not anti_spam(user_id):
        await update.message.reply_text("⏳ Sem flood 😅\nTente novamente em alguns segundos.")
        return

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

    msg_busca = await update.message.reply_html(
        "📚 Buscando o mangá pra você...\n"
        "Aguarde um instante ⏳"
    )

    async with client:
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

    keyboard = [[InlineKeyboardButton("📖 Ler agora", url=f"https://t.me/{CANAL_MANGA}/{msg_id}")]]
    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=f"@{CANAL_MANGA}",
        message_id=msg_id,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================================================
# 13) /pedido (mantive seu texto)
# ==================================================
COOLDOWN_PEDIDO = 12 * 60 * 60  # 12h

def pode_pedir(user_id: int) -> bool:
    ensure_user_row(user_id, "User")
    row = get_user_row(user_id)
    last_pedido = int(row["last_pedido"] or 0)
    agora = int(time.time())
    return (agora - last_pedido) >= COOLDOWN_PEDIDO

async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    user_id = update.effective_user.id

    if not anti_spam(user_id):
        await update.message.reply_text("⏳ Sem flood 😅\nTente novamente em alguns segundos.")
        return

    if not pode_pedir(user_id):
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

    texto_pedido = " ".join(context.args)
    user = update.effective_user

    mensagem_canal = (
        "📥 <b>NOVO PEDIDO REGISTRADO</b>\n\n"
        f"👤 <b>Usuário:</b> {user.full_name}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n\n"
        f"📝 <b>Pedido:</b>\n"
        f"<i>{texto_pedido}</i>\n\n"
        "✅ <b>Status:</b> Pedido listado com sucesso!"
    )

    if CANAL_PEDIDOS:
        await context.bot.send_message(
            chat_id=CANAL_PEDIDOS,
            text=mensagem_canal,
            parse_mode="HTML"
        )

    ensure_user_row(user_id, user.first_name)
    cursor.execute("UPDATE users SET last_pedido=%s WHERE user_id=%s", (int(time.time()), user_id))
    db.commit()

    await update.message.reply_html(
        f"✅ <b>{user.first_name}</b> [<code>{user.id}</code>]\n\n"
        f"Seu pedido <b>{texto_pedido}</b> já foi listado com sucesso!\n\n"
        "🕒 Agora é só aguardar que em breve estaremos postando.\n\n"
        "✨ Enquanto espera, aproveita para conhecer a central e os outros canais disponíveis!"
    )

# ==================================================
# 14) /infoanime (REFEITO / AJUSTADO)
# ==================================================
async def buscar_multiplos_anilist(nome: str) -> List[dict]:
    query = """
    query ($search: String) {
      Page(perPage: 6) {
        media(search: $search, type: ANIME) {
          id
          siteUrl
          title { romaji english native }
          status
          averageScore
          startDate { day month year }
          genres
          trailer { site id }
        }
      }
    }
    """
    variables = {"search": nome}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANILIST_API,
                json={"query": query, "variables": variables},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data["data"]["Page"]["media"]
    except Exception as e:
        print("Erro AniList:", e)
        return []

async def buscar_anilist_por_id(anime_id: int) -> dict:
    query = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        siteUrl
        title { romaji english native }
        status
        averageScore
        startDate { day month year }
        genres
        trailer { site id }
      }
    }
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(ANILIST_API, json={"query": query, "variables": {"id": anime_id}}) as resp:
            data = await resp.json()
            return data["data"]["Media"]

async def infoanime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    if not context.args:
        await update.message.reply_html(
            "❌ <b>Faltou o nome!</b>\n\n"
            "Use assim:\n"
            "<code>/infoanime nome do anime</code>\n\n"
            "📌 Exemplo:\n"
            "<code>/infoanime Naruto</code>"
        )
        return

    nome = " ".join(context.args)
    msg = await update.message.reply_text("🔎 Buscando versões no AniList...")

    resultados = await buscar_multiplos_anilist(nome)
    if not resultados:
        await msg.edit_text("🚫 Não encontrei nenhum anime com esse nome.")
        return

    botoes = []
    for media in resultados:
        titulo = media["title"]["english"] or media["title"]["romaji"] or media["title"]["native"]
        botoes.append([InlineKeyboardButton(titulo, callback_data=f"info_anime:{media['id']}")])

    await msg.edit_text(
        "📌 <b>Encontrei várias versões</b>\n\n"
        "Escolha qual você quer ver:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

async def callback_info_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    anime_id = int(query.data.split(":")[1])
    media = await buscar_anilist_por_id(anime_id)

    # apaga lista
    await query.message.delete()

    titulo = media["title"]["english"] or media["title"]["romaji"] or media["title"]["native"]
    score = media.get("averageScore", "N/A")
    status = media.get("status", "N/A")
    genres = ", ".join(media.get("genres", [])) or "N/A"
    data = media.get("startDate", {})
    start_date = f"{data.get('day','?')}/{data.get('month','?')}/{data.get('year','?')}"

    texto = (
        f"<b>{titulo}</b>\n\n"
        f"<b>Pontuação:</b> <code>{score}</code>\n"
        f"<b>Situação:</b> <code>{status}</code>\n"
        f"<b>Gênero:</b> <code>{genres}</code>\n"
        f"<b>Lançamento:</b> <code>{start_date}</code>"
    )

    imagem = f"https://img.anili.st/media/{media['id']}"

    botoes = []
    trailer = media.get("trailer")
    if trailer and trailer.get("site") == "youtube":
        botoes.append([InlineKeyboardButton("🎬 Trailer", url=f"https://www.youtube.com/watch?v={trailer['id']}")])

    botoes.append([InlineKeyboardButton("📖 Descrição", url=media["siteUrl"])])

    await context.bot.send_photo(
        chat_id=query.message.chat.id,
        photo=imagem,
        caption=texto,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

# ==================================================
# 15) /infomanga (REFEITO / AJUSTADO)
# ==================================================
async def buscar_multiplos_anilist_manga(nome: str) -> List[dict]:
    query = """
    query ($search: String) {
      Page(perPage: 6) {
        media(search: $search, type: MANGA) {
          id
          siteUrl
          title { romaji english native }
          status
          averageScore
          startDate { day month year }
          genres
        }
      }
    }
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANILIST_API,
                json={"query": query, "variables": {"search": nome}},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data["data"]["Page"]["media"]
    except Exception as e:
        print("Erro AniList Manga:", e)
        return []

async def buscar_anilist_manga_por_id(manga_id: int) -> dict:
    query = """
    query ($id: Int) {
      Media(id: $id, type: MANGA) {
        id
        siteUrl
        title { romaji english native }
        status
        averageScore
        startDate { day month year }
        genres
      }
    }
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(ANILIST_API, json={"query": query, "variables": {"id": manga_id}}) as resp:
            data = await resp.json()
            return data["data"]["Media"]

async def infomanga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    if not context.args:
        await update.message.reply_html(
            "❌ <b>Faltou o nome!</b>\n\n"
            "Use assim:\n"
            "<code>/infomanga nome do mangá</code>"
        )
        return

    nome = " ".join(context.args)
    msg = await update.message.reply_text("🔎 Buscando versões no AniList...")

    resultados = await buscar_multiplos_anilist_manga(nome)
    if not resultados:
        await msg.edit_text("🚫 Não encontrei nenhum mangá com esse nome.")
        return

    botoes = []
    for media in resultados:
        titulo = media["title"]["english"] or media["title"]["romaji"] or media["title"]["native"]
        botoes.append([InlineKeyboardButton(titulo, callback_data=f"info_manga:{media['id']}")])

    await msg.edit_text(
        "📌 <b>Encontrei várias versões</b>\n\nEscolha uma:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

async def callback_info_manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    manga_id = int(query.data.split(":")[1])
    media = await buscar_anilist_manga_por_id(manga_id)

    await query.message.delete()

    titulo = media["title"]["english"] or media["title"]["romaji"] or media["title"]["native"]
    score = media.get("averageScore", "N/A")
    status = media.get("status", "N/A")
    genres = ", ".join(media.get("genres", [])) or "N/A"
    data = media.get("startDate", {})
    start_date = f"{data.get('day','?')}/{data.get('month','?')}/{data.get('year','?')}"

    texto = (
        f"<b>{titulo}</b>\n\n"
        f"<b>Pontuação:</b> <code>{score}</code>\n"
        f"<b>Situação:</b> <code>{status}</code>\n"
        f"<b>Gêneros:</b> <code>{genres}</code>\n"
        f"<b>Lançamento:</b> <code>{start_date}</code>"
    )

    imagem = f"https://img.anili.st/media/{media['id']}"

    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("📖 Ver no AniList", url=media["siteUrl"])]])
    await context.bot.send_photo(
        chat_id=query.message.chat.id,
        photo=imagem,
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado
    )

# ==================================================
# 16) /perso (REFEITO / AJUSTADO)
# ==================================================
async def buscar_multiplos_personagens(nome: str) -> List[dict]:
    query = """
    query ($search: String) {
      Page(perPage: 6) {
        characters(search: $search) {
          id
          name { full }
          image { large }
        }
      }
    }
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(ANILIST_API, json={"query": query, "variables": {"search": nome}}) as resp:
            data = await resp.json()
            return data["data"]["Page"]["characters"]

async def buscar_personagem_por_id(char_id: int) -> dict:
    query = """
    query ($id: Int) {
      Character(id: $id) {
        id
        siteUrl
        name { full }
        image { large }
        gender
        dateOfBirth { day month }
        favourites
        media {
          edges {
            node {
              title { romaji }
              type
              startDate { year }
            }
            characterRole
          }
        }
      }
    }
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(ANILIST_API, json={"query": query, "variables": {"id": char_id}}) as resp:
            data = await resp.json()
            return data["data"]["Character"]

async def perso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    if not context.args:
        await update.message.reply_html(
            "❌ <b>Faltou o nome!</b>\n\n"
            "Use assim:\n"
            "<code>/perso nome do personagem</code>\n\n"
            "📌 Exemplo:\n"
            "<code>/perso Luffy</code>"
        )
        return

    nome = " ".join(context.args)
    msg = await update.message.reply_text("🔎 Buscando personagens no AniList...")

    resultados = await buscar_multiplos_personagens(nome)
    if not resultados:
        await msg.edit_text("🚫 Não encontrei nenhum personagem.")
        return

    botoes = []
    for char in resultados:
        botoes.append([InlineKeyboardButton(char["name"]["full"], callback_data=f"info_perso:{char['id']}")])

    await msg.edit_text(
        "📌 <b>Encontrei várias opções</b>\n\n"
        "Escolha o personagem:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

async def callback_info_perso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    char_id = int(query.data.split(":")[1])
    personagem = await buscar_personagem_por_id(char_id)

    await query.message.delete()

    nome = personagem["name"]["full"]
    imagem = personagem["image"]["large"]
    genero = personagem.get("gender") or "Desconhecido"
    favs = personagem.get("favourites") or 0

    dob = personagem.get("dateOfBirth") or {}
    nascimento = (
        f"{dob.get('day','?')}/{dob.get('month','?')}"
        if dob.get("day") and dob.get("month")
        else "Desconhecido"
    )

    obra = "Desconhecida"
    tipo = "—"
    papel = "—"
    estreia = "—"

    if personagem.get("media", {}).get("edges"):
        edge = personagem["media"]["edges"][0]
        obra = edge["node"]["title"]["romaji"]
        tipo = edge["node"]["type"]
        papel = edge["characterRole"]
        estreia = edge["node"]["startDate"]["year"] or "—"

    texto = (
        f"<b>{nome}</b>\n\n"
        f"<b>Gênero:</b> <code>{genero}</code>\n"
        f"<b>Nascimento:</b> <code>{nascimento}</code>\n"
        f"<b>Favoritos:</b> <code>{favs}</code>\n\n"
        f"<b>Obra:</b> <code>{obra}</code>\n"
        f"<b>Tipo:</b> <code>{tipo}</code>\n"
        f"<b>Papel:</b> <code>{papel}</code>\n"
        f"<b>Estreia:</b> <code>{estreia}</code>"
    )

    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Ver no AniList", url=personagem["siteUrl"])]])

    await context.bot.send_photo(
        chat_id=query.message.chat.id,
        photo=imagem,
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado
    )

# ==================================================
# 17) /emalta (REFEITO / AJUSTADO)
# ==================================================
ANIMES_POR_PAGINA = 10

async def buscar_animes_em_alta(pagina: int) -> List[dict]:
    query = """
    query ($page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        media(sort: TRENDING_DESC, type: ANIME) {
          id
          siteUrl
          title { romaji english }
          averageScore
          popularity
        }
      }
    }
    """
    variables = {"page": pagina, "perPage": ANIMES_POR_PAGINA}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            data = await resp.json()
            return data["data"]["Page"]["media"]

def formatar_ranking(animes: List[dict], pagina: int) -> str:
    inicio = (pagina - 1) * ANIMES_POR_PAGINA + 1
    texto = "🔥 <b>ANIMES EM ALTA AGORA</b> 🔥\n\n"

    for i, anime in enumerate(animes):
        posicao = inicio + i
        titulo = anime["title"]["english"] or anime["title"]["romaji"]
        score = anime["averageScore"] or "N/A"
        pop = anime["popularity"] or "N/A"

        emoji = "🏅"
        if posicao == 1:
            emoji = "🥇"
        elif posicao == 2:
            emoji = "🥈"
        elif posicao == 3:
            emoji = "🥉"

        texto += (
            f"{emoji} <b>{posicao}º</b> {titulo}\n"
            f"⭐ <b>Score:</b> <code>{score}</code>\n"
            f"👥 <b>Popularidade:</b> <code>{pop}</code>\n\n"
        )

    return texto

def teclado_em_alta(pagina: int) -> InlineKeyboardMarkup:
    navegacao = []
    if pagina > 1:
        navegacao.append(InlineKeyboardButton("⏪ Anterior", callback_data=f"emalta:{pagina - 1}"))
    navegacao.append(InlineKeyboardButton("⏩ Próximo", callback_data=f"emalta:{pagina + 1}"))
    return InlineKeyboardMarkup([navegacao])

async def emalta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    pagina = 1
    animes = await buscar_animes_em_alta(pagina)
    await update.message.reply_html(formatar_ranking(animes, pagina), reply_markup=teclado_em_alta(pagina))

async def callback_emalta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pagina = int(query.data.split(":")[1])
    animes = await buscar_animes_em_alta(pagina)

    await query.message.edit_text(
        formatar_ranking(animes, pagina),
        parse_mode="HTML",
        reply_markup=teclado_em_alta(pagina)
    )

# ==================================================
# 18) /recomenda (REFEITO / AJUSTADO)
# ==================================================
MAX_PAGES = 3
PER_PAGE = 5

async def buscar_recomendacoes(tipo: str, page: int) -> List[dict]:
    if tipo == "surpresa":
        page = random.randint(1, 100)
        sort = random.choice(["SCORE_DESC", "POPULARITY_DESC"])
    else:
        sort_map = {"anime": "SCORE_DESC", "manga": "SCORE_DESC", "popular": "POPULARITY_DESC"}
        sort = sort_map[tipo]

    media_type = "MANGA" if tipo == "manga" else "ANIME"

    query = """
    query ($page: Int, $type: MediaType, $sort: [MediaSort], $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        media(type: $type, sort: $sort) {
          id
          siteUrl
          title { romaji english }
          averageScore
          popularity
          genres
          coverImage { extraLarge }
          startDate { year }
        }
      }
    }
    """
    variables = {"page": page, "type": media_type, "sort": [sort], "perPage": PER_PAGE}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            data = await resp.json()
            return data["data"]["Page"]["media"]

def formatar_lista(lista: List[dict], tipo: str, page: int) -> str:
    titulo = f"🔥 <b>RECOMENDAÇÕES — {tipo.upper()}</b>\n📄 Página {page}/{MAX_PAGES}\n\n"
    texto = titulo
    for i, media in enumerate(lista, start=1):
        nome = media["title"]["english"] or media["title"]["romaji"]
        score = media["averageScore"] or "—"
        pop = media["popularity"] or "—"
        generos = ", ".join(media["genres"][:3]) if media["genres"] else "—"
        texto += (
            f"<b>{i}.</b> {nome}\n"
            f"⭐ <b>Score:</b> <code>{score}</code>\n"
            f"👥 <b>Popularidade:</b> <code>{pop}</code>\n"
            f"🎭 <b>Gêneros:</b> <code>{generos}</code>\n\n"
        )
    return texto

def teclado_recomenda(tipo: str, page: int) -> Optional[InlineKeyboardMarkup]:
    botoes = []
    if page > 1:
        botoes.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"rec:{tipo}:{page-1}"))
    if page < MAX_PAGES:
        botoes.append(InlineKeyboardButton("➡️ Próximo", callback_data=f"rec:{tipo}:{page+1}"))
    return InlineKeyboardMarkup([botoes]) if botoes else None

async def recomenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    if not context.args:
        await update.message.reply_html(
            "✨ <b>SISTEMA DE RECOMENDAÇÕES</b> ✨\n\n"
            "Escolha como você quer descobrir algo novo:\n\n"
            "🎬 <b>Anime</b>\n"
            "<code>/recomenda anime</code>\n"
            "Descubra animes bem avaliados para começar algo de qualidade.\n\n"
            "📚 <b>Mangá</b>\n"
            "<code>/recomenda manga</code>\n"
            "Boas recomendações de mangás para leitura.\n\n"
            "🔥 <b>Popular</b>\n"
            "<code>/recomenda popular</code>\n"
            "O que está bombando agora entre a comunidade.\n\n"
            "🎲 <b>Surpresa</b>\n"
            "<code>/recomenda surpresa</code>\n"
            "Uma recomendação aleatória para quem quer sair da bolha e se surpreender.\n\n"
            "💡 <i>Dica:</i> Use os botões para navegar entre as páginas."
        )
        return

    tipo = context.args[0].lower()
    if tipo not in ["anime", "manga", "popular", "surpresa"]:
        await update.message.reply_text("❌ Opção inválida.")
        return

    page = 1
    lista = await buscar_recomendacoes(tipo, page)

    if tipo == "surpresa":
        media = random.choice(lista)
        nome = media["title"]["english"] or media["title"]["romaji"]
        score = media["averageScore"] or "—"
        pop = media["popularity"] or "—"
        generos = ", ".join(media["genres"][:3]) if media["genres"] else "—"
        ano = media["startDate"]["year"] or "—"

        texto = (
            f"<b>{nome}</b>\n\n"
            f"<b>Score:</b> <code>{score}</code>\n"
            f"<b>Popularidade:</b> <code>{pop}</code>\n"
            f"<b>Gêneros:</b> <code>{generos}</code>\n"
            f"<b>Ano:</b> <code>{ano}</code>"
        )

        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Ver no AniList", url=media["siteUrl"])]])

        await update.message.reply_photo(
            photo=media["coverImage"]["extraLarge"],
            caption=texto,
            parse_mode="HTML",
            reply_markup=teclado
        )
        return

    texto = formatar_lista(lista, tipo, page)
    await update.message.reply_html(texto, reply_markup=teclado_recomenda(tipo, page))

async def callback_recomenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, tipo, page = query.data.split(":")
    page = int(page)

    if page < 1 or page > MAX_PAGES:
        return

    lista = await buscar_recomendacoes(tipo, page)
    texto = formatar_lista(lista, tipo, page)

    await query.message.edit_text(
        texto,
        parse_mode="HTML",
        reply_markup=teclado_recomenda(tipo, page)
    )

# ==================================================
# 19) /cards e .cards (mantive)
# ==================================================
async def buscar_cards(anime_nome: str, page: int = 1) -> Optional[dict]:
    query = """
    query ($search: String, $page: Int) {
      Page(page: 1, perPage: 1) {
        media(search: $search, type: ANIME) {
          title { romaji }
          bannerImage
          coverImage { large }
          characters(page: $page, perPage: 15) {
            pageInfo { total currentPage lastPage }
            edges {
              node { id name { full } }
            }
          }
        }
      }
    }
    """
    variables = {"search": anime_nome, "page": page}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            data = await resp.json()
            media = data.get("data", {}).get("Page", {}).get("media", [])
            return media[0] if media else None

def formatar_cards(media: dict, page: int) -> str:
    chars = media["characters"]["edges"]
    info = media["characters"]["pageInfo"]
    texto = (
        f"📁 | <b>{media['title']['romaji']}</b>\n"
        f"ℹ️ | <b>{info['total']}</b>\n"
        f"🗂 | <b>{page}/{info['lastPage']}</b>\n\n"
    )
    for c in chars:
        texto += f"🧧 <b>{c['node']['id']}.</b> {c['node']['name']['full']}\n"
    return texto

def teclado_cards(anime: str, page: int, last: int) -> Optional[InlineKeyboardMarkup]:
    botoes = []
    if page > 1:
        botoes.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"cards:{anime}:{page-1}"))
    if page < last:
        botoes.append(InlineKeyboardButton("➡️ Próximo", callback_data=f"cards:{anime}:{page+1}"))
    return InlineKeyboardMarkup([botoes]) if botoes else None

async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return

    if not context.args:
        await update.message.reply_html(
            "📁 <b>Cards de personagens</b>\n\n"
            "Use:\n"
            "<code>/cards Nome do Anime</code>\n\n"
            "📌 Exemplo:\n"
            "<code>/cards One Piece</code>"
        )
        return

    anime_nome = " ".join(context.args)
    media = await buscar_cards(anime_nome, 1)

    if not media:
        await update.message.reply_html(
            "❌ <b>Anime não encontrado</b>\n\n"
            "💡 Tente usar o nome mais conhecido.\n"
            "Exemplo: <code>One Piece</code>"
        )
        return

    texto = formatar_cards(media, 1)
    last = media["characters"]["pageInfo"]["lastPage"]
    foto = media.get("bannerImage") or media["coverImage"]["large"]

    await update.message.reply_photo(
        photo=foto,
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado_cards(anime_nome, 1, last)
    )

async def callback_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, anime_nome, page = query.data.split(":")
    page = int(page)

    media = await buscar_cards(anime_nome, page)
    texto = formatar_cards(media, page)
    last = media["characters"]["pageInfo"]["lastPage"]

    await query.message.edit_caption(
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado_cards(anime_nome, page, last)
    )

# ==================================================
# 20) /dado + /colecao + /nomecolecao (POSTGRES)
# ==================================================
COOLDOWN_DADO = 2 * 60 * 60  # 2h
ITENS_POR_PAGINA = 10

async def buscar_personagem_por_popularidade(page_min: int, page_max: int) -> dict:
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
    async with aiohttp.ClientSession() as session:
        async with session.post(ANILIST_API, json={"query": query, "variables": {"page": page}}) as resp:
            data = await resp.json()
            return data["data"]["Page"]["characters"][0]

async def dado_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    agora = int(time.time())

    ensure_user_row(user_id, update.effective_user.first_name)
    row = get_user_row(user_id)
    last_dado = int(row["last_dado"] or 0)
    coins = int(row["coins"] or 0)

    if agora - last_dado < COOLDOWN_DADO:
        falta = COOLDOWN_DADO - (agora - last_dado)
        horas = falta // 3600
        minutos = (falta % 3600) // 60
        await update.message.reply_text(
            f"⏳ Você já girou o dado!\n\n"
            f"🎲 Tente novamente em **{horas}h {minutos}m**",
            parse_mode="Markdown"
        )
        return

    dice = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
    await asyncio.sleep(3)
    numero = dice.dice.value

    raridades = {
        1: (700, 1000, "💀 *Ruim*"),
        2: (500, 699, "😐 *Fraco*"),
        3: (300, 499, "⭐ *Médio*"),
        4: (150, 299, "🔥 *Forte*"),
        5: (50, 149, "💎 *Raro*"),
        6: (1, 49, "👑 *Lendário*"),
    }

    page_min, page_max, raridade = raridades[numero]
    personagem = await buscar_personagem_por_popularidade(page_min, page_max)

    repetido = user_has_character(user_id, personagem["id"])

    if repetido:
        coins += 1
        add_coin(user_id, 1)
        resultado = "🪙 Personagem repetido → +1 Coin"
    else:
        add_character_to_collection(
            user_id,
            personagem["id"],
            personagem["name"]["full"],
            personagem["image"]["large"]
        )
        resultado = "📦 Adicionado à coleção!"

    cursor.execute("UPDATE users SET last_dado=%s WHERE user_id=%s", (agora, user_id))
    db.commit()

    row2 = get_user_row(user_id)
    coins2 = int(row2["coins"] or 0)

    await update.message.reply_photo(
        photo=personagem["image"]["large"],
        caption=(
            "🎰 *DADO DA SORTE*\n\n"
            f"🎲 Número: `{numero}`\n"
            f"{raridade}\n\n"
            f"✨ *{personagem['name']['full']}*\n\n"
            f"{resultado}\n"
            f"🪙 Coins: `{coins2}`"
        ),
        parse_mode="Markdown"
    )

async def enviar_colecao(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

    nome = get_collection_name(user_id) or "Minha Coleção"
    itens, total, total_paginas = get_collection_page(user_id, page, ITENS_POR_PAGINA)

    if not itens:
        if update.message:
            await update.message.reply_text("📦 Sua coleção está vazia.")
        else:
            await update.callback_query.message.reply_text("📦 Sua coleção está vazia.")
        return

    texto = f"📚 *{nome}*\n\n📖 | *{page}/{total_paginas}*\n\n"
    for cid, nomep in itens:
        texto += f"🧧 `{cid}.` {nomep}\n"

    botoes = []
    if page > 1:
        botoes.append(InlineKeyboardButton("◀️", callback_data=f"colecao:{page-1}"))
    if page < total_paginas:
        botoes.append(InlineKeyboardButton("▶️", callback_data=f"colecao:{page+1}"))

    target = update.message if update.message else update.callback_query.message
    await target.reply_text(
        texto,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([botoes]) if botoes else None
    )

async def colecao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await enviar_colecao(update, context, 1)

async def callback_colecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[1])
    await enviar_colecao(update, context, page)

async def nomecolecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

    if not context.args:
        await update.message.reply_text(
            "Use: `/nomecolecao Nome da Coleção`",
            parse_mode="Markdown"
        )
        return

    nome = " ".join(context.args)
    set_collection_name(user_id, nome)
    await update.message.reply_text(f"📚 Coleção renomeada para *{nome}*", parse_mode="Markdown")

# ==================================================
# 21) /trocar (POSTGRES)
# ==================================================
async def trocar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Você precisa **responder a mensagem do usuário** para trocar.\n\n"
            "Exemplo:\n"
            "`(responder mensagem)`\n"
            "`/trocar 10 25`",
            parse_mode="Markdown"
        )
        return

    if len(context.args) != 2:
        await update.message.reply_text("Use:\n`/trocar SEU_ID ID_DELE`", parse_mode="Markdown")
        return

    from_user = update.effective_user.id
    to_user = update.message.reply_to_message.from_user.id
    from_char = int(context.args[0])
    to_char = int(context.args[1])

    if not user_has_character(from_user, from_char):
        await update.message.reply_text("❌ Esse personagem não é seu.")
        return
    if not user_has_character(to_user, to_char):
        await update.message.reply_text("❌ O outro usuário não possui esse personagem.")
        return

    create_trade(from_user, to_user, from_char, to_char)

    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aceitar", callback_data="trade_accept"),
        InlineKeyboardButton("❌ Recusar", callback_data="trade_reject"),
    ]])

    await update.message.reply_text(
        "🔁 **Pedido de troca enviado!**\n\n"
        "Apenas o usuário marcado pode responder.",
        parse_mode="Markdown",
        reply_markup=teclado
    )

async def callback_trade_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    trade = get_latest_pending_trade_for_to_user(user_id)
    if not trade:
        await query.answer("Nenhuma troca pendente.", show_alert=True)
        return

    trade_id, from_user, from_char, to_char = trade
    swap_trade_execute(trade_id, from_user, user_id, from_char, to_char)
    await query.message.edit_text("✅ **Troca realizada com sucesso!**", parse_mode="Markdown")

async def callback_trade_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    trade = get_latest_pending_trade_for_to_user(user_id)
    if not trade:
        await query.answer("Nenhuma troca pendente.", show_alert=True)
        return

    trade_id, *_ = trade
    mark_trade_status(trade_id, "recusada")
    await query.message.edit_text("❌ **Troca recusada.**", parse_mode="Markdown")

# ==================================================
# 22) /loja (POSTGRES) — SIMPLES
#     - lista personagens do usuário e permite vender
# ==================================================
def _shop_keyboard(chars: List[Tuple[int, str]], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for cid, cname in chars:
        rows.append([InlineKeyboardButton(f"🧧 {cid}. {cname}", callback_data=f"shop:sell:{cid}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⏪", callback_data=f"shop:page:{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="shop:noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("⏩", callback_data=f"shop:page:{page+1}"))
    rows.append(nav)

    return InlineKeyboardMarkup(rows)

async def loja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

    page = 1
    per_page = 8
    chars, total, total_pages = shop_list_user_chars(user_id, page, per_page)

    if not chars:
        await update.message.reply_html(
            "🛒 <b>LOJA</b>\n\n"
            "📦 Sua coleção está vazia.\n"
            "Use <code>/dado</code> para conseguir personagens."
        )
        return

    await update.message.reply_html(
        "🛒 <b>LOJA</b>\n\n"
        "Escolha um personagem para vender.\n"
        "⚠️ Ao vender, você recebe <b>+1 coin</b> e o personagem sai da coleção.",
        reply_markup=_shop_keyboard(chars, page, total_pages)
    )

async def callback_loja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    # shop:page:X | shop:sell:CID | shop:noop
    action = parts[1]

    user_id = query.from_user.id
    ensure_user_row(user_id, query.from_user.first_name)

    if action == "noop":
        return

    if action == "page":
        page = int(parts[2])
        per_page = 8
        chars, total, total_pages = shop_list_user_chars(user_id, page, per_page)

        if not chars:
            await query.message.edit_text(
                "🛒 <b>LOJA</b>\n\n"
                "📦 Sua coleção está vazia.\n"
                "Use <code>/dado</code> para conseguir personagens.",
                parse_mode="HTML"
            )
            return

        await query.message.edit_text(
            "🛒 <b>LOJA</b>\n\n"
            "Escolha um personagem para vender.\n"
            "⚠️ Ao vender, você recebe <b>+1 coin</b> e o personagem sai da coleção.",
            parse_mode="HTML",
            reply_markup=_shop_keyboard(chars, page, total_pages)
        )
        return

    if action == "sell":
        char_id = int(parts[2])
        if not user_has_character(user_id, char_id):
            await query.answer("Você não tem esse personagem.", show_alert=True)
            return

        # cria uma "venda pendente"
        sale_id = shop_create_sale(user_id, char_id)

        teclado = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confirmar", callback_data=f"sell_confirm:{sale_id}:yes"),
            InlineKeyboardButton("❌ Cancelar", callback_data=f"sell_confirm:{sale_id}:no"),
        ]])

        await query.message.reply_html(
            "🛒 <b>Confirmar venda</b>\n\n"
            f"Você quer mesmo vender o personagem <code>{char_id}</code>?\n\n"
            "✅ Você ganha <b>+1 coin</b>\n"
            "⚠️ O personagem sai da sua coleção.",
            reply_markup=teclado
        )

async def callback_confirmar_venda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # sell_confirm:SALEID:yes/no
    _, sale_id, decision = query.data.split(":")
    sale_id = int(sale_id)

    sale = shop_get_sale(sale_id)
    if not sale:
        await query.answer("Venda expirada.", show_alert=True)
        return

    user_id, char_id = sale
    if query.from_user.id != user_id:
        await query.answer("Essa venda não é sua.", show_alert=True)
        return

    if decision == "no":
        shop_delete_sale(sale_id)
        await query.message.edit_text("❌ Venda cancelada.", parse_mode="HTML")
        return

    # yes
    if not user_has_character(user_id, char_id):
        shop_delete_sale(sale_id)
        await query.message.edit_text("⚠️ Você não tem mais esse personagem.", parse_mode="HTML")
        return

    # remove da coleção (delete linha)
    cursor.execute(
        "DELETE FROM user_collection WHERE user_id=%s AND character_id=%s",
        (user_id, char_id)
    )
    add_coin(user_id, 1)
    shop_delete_sale(sale_id)
    db.commit()

    await query.message.edit_text("✅ Venda concluída! 🪙 +1 coin", parse_mode="HTML")

async def callback_venda_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # compat com seu handler "sell_yes/sell_no" (fica só como fallback)
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("✅ Ok!")

# ==================================================
# 23) /batalha (POSTGRES) — só escolhe personagem da coleção
# ==================================================
def _battle_pick_keyboard(user_id: int, opponent_id: int, chat_id: int) -> InlineKeyboardMarkup:
    # pega 8 primeiros personagens do user pra escolher
    chars, total, total_pages = shop_list_user_chars(user_id, 1, 8)
    rows = []
    for cid, cname in chars:
        rows.append([InlineKeyboardButton(f"🧧 {cid}. {cname}", callback_data=f"battle:pick:{user_id}:{cid}")])
    rows.append([InlineKeyboardButton("✅ Estou pronto", callback_data="battle:ready")])
    return InlineKeyboardMarkup(rows)

async def batalha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user1 = update.effective_user

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "**⚔️ COMO DESAFIAR**\n\n"
            "👉 Responda a mensagem do jogador que deseja desafiar.\n\n"
            "_A arena aguarda sangue novo..._",
            parse_mode="Markdown"
        )
        return

    user2 = update.message.reply_to_message.from_user
    if user1.id == user2.id:
        return

    ensure_user_row(user1.id, user1.first_name)
    ensure_user_row(user2.id, user2.first_name)

    # cria batalha
    upsert_battle(
        chat.id,
        user1.id, user2.id,
        user1.first_name, user2.first_name
    )

    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aceitar batalha", callback_data="battle:accept")
    ]])

    await update.message.reply_text(
        f"⚔️ **{user1.first_name} desafiou {user2.first_name}!**\n\n"
        "✅ Clique para aceitar e escolher personagem.",
        parse_mode="Markdown",
        reply_markup=teclado
    )

async def batalha_aceite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    battle = get_battle(query.message.chat.id)
    if not battle:
        await query.answer("Batalha não encontrada.", show_alert=True)
        return

    # só o player2 pode aceitar
    if query.from_user.id != battle["player2_id"]:
        await query.answer("Apenas o desafiado pode aceitar.", show_alert=True)
        return

    await query.message.reply_text(
        "⚔️ **BATALHA INICIADA!**\n\n"
        "Cada jogador precisa escolher um personagem da própria coleção.\n"
        "Use os botões abaixo.",
        parse_mode="Markdown"
    )

    # manda escolha pro player1
    await query.message.reply_text(
        f"🧩 **{battle['player1_name']}**, escolha seu personagem:",
        parse_mode="Markdown",
        reply_markup=_battle_pick_keyboard(battle["player1_id"], battle["player2_id"], battle["chat_id"])
    )

    # manda escolha pro player2
    await query.message.reply_text(
        f"🧩 **{battle['player2_name']}**, escolha seu personagem:",
        parse_mode="Markdown",
        reply_markup=_battle_pick_keyboard(battle["player2_id"], battle["player1_id"], battle["chat_id"])
    )

async def batalha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split(":")
    # atacar | battle:pick:UID:CID | battle:ready
    battle = get_battle(query.message.chat.id)
    if not battle:
        await query.answer("Batalha não encontrada.", show_alert=True)
        return

    if query.data == "atacar":
        # turno simples: vez alternada
        user_id = query.from_user.id
        vez = int(battle["vez"] or 0)

        # vez = 1 (player1), 2 (player2)
        if (vez == 1 and user_id != battle["player1_id"]) or (vez == 2 and user_id != battle["player2_id"]):
            await query.answer("Não é sua vez.", show_alert=True)
            return

        dano = random.randint(10, 25)
        if vez == 1:
            battle_damage(battle["chat_id"], target="p2", damage=dano)
            battle_set_turn(battle["chat_id"], 2)
            battle = get_battle(battle["chat_id"])
            await query.message.reply_text(
                f"⚔️ {battle['player1_name']} atacou e deu **{dano}** de dano!\n"
                f"❤️ HP {battle['player2_name']}: {battle['player2_hp']}",
                parse_mode="Markdown"
            )
        else:
            battle_damage(battle["chat_id"], target="p1", damage=dano)
            battle_set_turn(battle["chat_id"], 1)
            battle = get_battle(battle["chat_id"])
            await query.message.reply_text(
                f"⚔️ {battle['player2_name']} atacou e deu **{dano}** de dano!\n"
                f"❤️ HP {battle['player1_name']}: {battle['player1_hp']}",
                parse_mode="Markdown"
            )

        # fim?
        if int(battle["player1_hp"]) <= 0 or int(battle["player2_hp"]) <= 0:
            winner = battle["player1_name"] if int(battle["player1_hp"]) > 0 else battle["player2_name"]
            await query.message.reply_text(f"🏆 **{winner} venceu a batalha!**", parse_mode="Markdown")
            delete_battle(battle["chat_id"])
        return

    if len(data) >= 2 and data[0] == "battle" and data[1] == "pick":
        pick_user_id = int(data[2])
        char_id = int(data[3])

        if query.from_user.id != pick_user_id:
            await query.answer("Esse menu não é seu.", show_alert=True)
            return

        # regra pedida: só pode escolher personagem que o usuário tem na coleção
        if not user_has_character(pick_user_id, char_id):
            await query.answer("Você não tem esse personagem na coleção.", show_alert=True)
            return

        # salva char
        battle_set_char(battle["chat_id"], pick_user_id, str(char_id))

        await query.message.reply_text(
            f"✅ Personagem escolhido: <code>{char_id}</code>",
            parse_mode="HTML"
        )
        return

    if query.data == "battle:ready":
        battle = get_battle(query.message.chat.id)
        if not battle:
            return

        if not battle["player1_char"] or not battle["player2_char"]:
            await query.answer("Ainda falta alguém escolher personagem.", show_alert=True)
            return

        # inicia hp e vez
        upsert_battle(
            battle["chat_id"],
            battle["player1_id"], battle["player2_id"],
            battle["player1_name"], battle["player2_name"],
            player1_char=battle["player1_char"],
            player2_char=battle["player2_char"],
            player1_hp=100,
            player2_hp=100,
            vez=1
        )

        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar")]])

        await query.message.reply_text(
            "⚔️ **BATALHA PRONTA!**\n\n"
            f"🧧 {battle['player1_name']} escolheu: `{battle['player1_char']}`\n"
            f"🧧 {battle['player2_name']} escolheu: `{battle['player2_char']}`\n\n"
            "🎮 Começa o Player 1! Clique em **Atacar**.",
            parse_mode="Markdown",
            reply_markup=teclado
        )
        return

# ==================================================
# 24) /personagem (placeholder simples)
# ==================================================
async def personagem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "🧩 <b>Personagem</b>\n\n"
        "Esse comando fica reservado para futuras funções.\n"
        "Por enquanto, use <code>/perso</code> para ver informações."
    )

# ==================================================
# 25) MAIN (handlers EXATOS como você pediu)
# ==================================================
def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ===== HANDLERS (EXATOS DA SUA LISTA) =====
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(CommandHandler("infoanime", infoanime))
    app.add_handler(CommandHandler("dado", dado_command))
    app.add_handler(CommandHandler("colecao", colecao_command))
    app.add_handler(CallbackQueryHandler(callback_colecao, pattern="^colecao:"))
    app.add_handler(CommandHandler("nomecolecao", nomecolecao))
    app.add_handler(CommandHandler("infomanga", infomanga))
    app.add_handler(CallbackQueryHandler(callback_info_manga, pattern="^info_manga:"))
    app.add_handler(CommandHandler("perso", perso))
    app.add_handler(CommandHandler("recomenda", recomenda))
    app.add_handler(CallbackQueryHandler(callback_recomenda, pattern="^rec:"))
    app.add_handler(CommandHandler("emalta", emalta))
    app.add_handler(CallbackQueryHandler(callback_emalta, pattern="^emalta:"))
    app.add_handler(CallbackQueryHandler(callback_info_perso, pattern="^info_perso:"))
    app.add_handler(CallbackQueryHandler(callback_info_anime, pattern="^info_anime:"))
    app.add_handler(CommandHandler("pedido", pedido))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("manga", manga))
    app.add_handler(CommandHandler("perfil", perfil))
    app.add_handler(CommandHandler("privado", privado))
    app.add_handler(CommandHandler("adminfoto", adminfoto))
    app.add_handler(CommandHandler("favoritar", favoritar))
    app.add_handler(CommandHandler("desfavoritar", desfavoritar))
    app.add_handler(CommandHandler("nick", nick))
    app.add_handler(CommandHandler("nivel", nivel))
    app.add_handler(CommandHandler("cards", cards))
    app.add_handler(MessageHandler(filters.Regex(r"^\.cards"), cards))
    app.add_handler(CallbackQueryHandler(callback_cards, pattern="^cards:"))
    app.add_handler(CommandHandler("batalha", batalha_command))
    app.add_handler(CommandHandler("personagem", personagem_command))
    app.add_handler(CallbackQueryHandler(batalha_aceite_callback, pattern="battle:accept"))
    app.add_handler(CallbackQueryHandler(batalha_callback, pattern="atacar"))
    app.add_handler(CommandHandler("trocar", trocar))
    app.add_handler(CallbackQueryHandler(callback_trade_accept, pattern="^trade_accept$"))
    app.add_handler(CallbackQueryHandler(callback_trade_reject, pattern="^trade_reject$"))
    app.add_handler(CommandHandler("loja", loja))
    app.add_handler(CallbackQueryHandler(callback_loja, pattern="^shop:"))
    app.add_handler(CallbackQueryHandler(callback_confirmar_venda, pattern="^sell_confirm:"))
    app.add_handler(CallbackQueryHandler(callback_venda_final, pattern="^sell_yes:|^sell_no"))

    print("✅ Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()
