# ============================================================
# PARTE 1 — BASE CORE (START + LOGIN + PEDIDO + SEGURANÇA)
# VERSÃO GOD TIER — REFATORADA / ANTI-FLOOD / SEGURA
# COLE DIRETO NO SEU bot.py
# ============================================================

# ================================
# IMPORTS BASE
# ================================
import os
import re
import time
import json
import hmac
import base64
import hashlib
import asyncio
from typing import Optional, Dict

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import (
    db,
    cursor,
    ensure_user_row,
    get_user_row,
)

# ================================
# CONFIG
# ================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()
OAUTH_STATE_SECRET = os.getenv("OAUTH_STATE_SECRET", "").strip()

CANAL_PEDIDOS = int(os.getenv("CANAL_PEDIDOS", "0"))
CANAL_OBRIGATORIO = int(os.getenv("CANAL_OBRIGATORIO", "0"))
URL_CANAL_OBRIGATORIO = os.getenv(
    "URL_CANAL_OBRIGATORIO",
    "https://t.me/SourcerBaltigo"
).strip()

# ================================
# LOCK GLOBAL (ANTI RACE CONDITION)
# ================================
GLOBAL_USER_LOCKS: Dict[int, asyncio.Lock] = {}

def get_user_lock(uid: int) -> asyncio.Lock:
    if uid not in GLOBAL_USER_LOCKS:
        GLOBAL_USER_LOCKS[uid] = asyncio.Lock()
    return GLOBAL_USER_LOCKS[uid]

# ================================
# ANTI FLOOD (COMANDOS)
# ================================
ANTI_SPAM_TIME = 3
_LAST_COMMAND_TS: Dict[int, float] = {}

def anti_spam(uid: int) -> bool:
    now = time.time()
    last = _LAST_COMMAND_TS.get(uid, 0)
    if now - last < ANTI_SPAM_TIME:
        return False
    _LAST_COMMAND_TS[uid] = now
    return True

# ================================
# CHECAR CANAL
# ================================
async def usuario_no_canal(bot, user_id: int) -> bool:
    if not CANAL_OBRIGATORIO:
        return True
    try:
        membro = await bot.get_chat_member(CANAL_OBRIGATORIO, user_id)
        return membro.status in ["member", "administrator", "creator"]
    except:
        return False

async def checar_canal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id

    ok = await usuario_no_canal(context.bot, user_id)
    if ok:
        return True

    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Entrar no canal", url=URL_CANAL_OBRIGATORIO)
    ]])

    if update.message:
        await update.message.reply_html(
            "🚫 <b>Acesso bloqueado</b>\n\n"
            "Entre no canal oficial para usar o bot.",
            reply_markup=teclado
        )
    return False

# ================================
# REGISTRAR COMANDO (ANTI DUPLO)
# ================================
COMANDOS_POR_NIVEL = 100

async def registrar_comando(update: Update):
    user_id = update.effective_user.id

    async with get_user_lock(user_id):
        ensure_user_row(user_id, update.effective_user.first_name)
        row = get_user_row(user_id)

        comandos = int(row["commands"] or 0) + 1
        nivel = int(row["level"] or 1)

        novo = (comandos // COMANDOS_POR_NIVEL) + 1

        cursor.execute(
            "UPDATE users SET commands=%s, level=%s WHERE user_id=%s",
            (comandos, max(nivel, novo), user_id)
        )
        db.commit()

# ================================
# /start
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🏴‍☠️ <b>Source Baltigo</b>\n"
        "Seu hub de <b>animes, mangás e personagens</b>.\n\n"
        "✨ <b>Comandos rápidos</b>\n"
        "• <code>/anime</code>\n"
        "• <code>/manga</code>\n"
        "• <code>/infoanime</code>\n"
        "• <code>/infomanga</code>\n"
        "• <code>/perso</code>\n"
        "• <code>/recomenda</code>\n"
        "• <code>/emalta</code>\n"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Adicionar em grupo",
         url="https://t.me/SourceBaltigo_bot?startgroup=start")]
    ])

    await update.message.reply_html(texto, reply_markup=teclado)

# ================================
# LOGIN OAUTH
# ================================
def make_state(user_id: int) -> str:
    ts = str(int(time.time()))
    payload = f"{user_id}.{ts}".encode()
    sig = hmac.new(OAUTH_STATE_SECRET.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + b"." + sig).decode().rstrip("=")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not anti_spam(user_id):
        return

    state = make_state(user_id)
    redirect_uri = f"{PUBLIC_BASE_URL}/callback"

    url = (
        "https://anilist.co/api/v2/oauth/authorize"
        f"?client_id={ANILIST_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        f"&state={state}"
    )

    teclado = InlineKeyboardMarkup([[InlineKeyboardButton(
        "🔐 Conectar com AniList", url=url
    )]])

    await update.message.reply_text(
        "🔑 Clique para conectar sua conta AniList:",
        reply_markup=teclado
    )

# ================================
# /pedido (ANTI FLOOD + LOCK)
# ================================
COOLDOWN_PEDIDO = 12 * 60 * 60

def pode_pedir(user_id: int) -> bool:
    row = get_user_row(user_id)
    last = int(row["last_pedido"] or 0)
    return (int(time.time()) - last) >= COOLDOWN_PEDIDO

async def pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    if not await checar_canal(update, context):
        return

    if not anti_spam(uid):
        await update.message.reply_text("⏳ Aguarde alguns segundos.")
        return

    async with get_user_lock(uid):

        ensure_user_row(uid, user.first_name)

        if not pode_pedir(uid):
            await update.message.reply_html(
                "⏳ Você já fez um pedido recentemente.\n"
                "Espere 12h."
            )
            return

        if not context.args:
            await update.message.reply_html(
                "📩 <b>Pedido</b>\n\n"
                "<code>/pedido nome do anime</code>"
            )
            return

        texto_pedido = " ".join(context.args)

        if CANAL_PEDIDOS:
            await context.bot.send_message(
                chat_id=CANAL_PEDIDOS,
                text=(
                    "📥 <b>NOVO PEDIDO</b>\n\n"
                    f"👤 {user.full_name}\n"
                    f"📝 {texto_pedido}"
                ),
                parse_mode="HTML"
            )

        cursor.execute(
            "UPDATE users SET last_pedido=%s WHERE user_id=%s",
            (int(time.time()), uid)
        )
        db.commit()

        await update.message.reply_html(
            f"✅ Pedido <b>{texto_pedido}</b> registrado!"
        )

# ============================================================
# PARTE 2 — ANIME / MANGA / INFOANIME / INFOMANGA / PERSO
# VERSÃO GOD TIER — ANTI FLOOD / ANTI RACE / OTIMIZADA
# COLE DIRETO NO bot.py (ABAIXO DA PARTE 1)
# ============================================================

ANILIST_API = "https://graphql.anilist.co"

# ============================================================
# SESSION GLOBAL (EVITA ABRIR 300 CONEXÕES AO MESMO TEMPO)
# ============================================================

AIOHTTP_SESSION: Optional[aiohttp.ClientSession] = None

async def get_http_session():
    global AIOHTTP_SESSION
    if not AIOHTTP_SESSION or AIOHTTP_SESSION.closed:
        AIOHTTP_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        )
    return AIOHTTP_SESSION


# ============================================================
# FUNÇÃO BASE ANILIST (ANTI ERRO / ANTI FLOOD)
# ============================================================

async def anilist_query(query: str, variables: dict):
    try:
        session = await get_http_session()
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables},
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except:
        return None


# ============================================================
# /anime (BUSCA NO CANAL — SOMENTE TEXTO)
# ============================================================

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not await checar_canal(update, context):
        return

    if not anti_spam(uid):
        await update.message.reply_text("⏳ Sem flood 😅")
        return

    if not context.args:
        await update.message.reply_html(
            "🚫 <b>Formato:</b>\n<code>/anime nome</code>"
        )
        return

    nome = " ".join(context.args)

    await update.message.reply_html(
        f"🔎 Buscando <b>{nome}</b>..."
    )


# ============================================================
# /manga
# ============================================================

async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not await checar_canal(update, context):
        return

    if not anti_spam(uid):
        await update.message.reply_text("⏳ Sem flood 😅")
        return

    if not context.args:
        await update.message.reply_html(
            "🚫 <b>Formato:</b>\n<code>/manga nome</code>"
        )
        return

    nome = " ".join(context.args)

    await update.message.reply_html(
        f"📚 Buscando <b>{nome}</b>..."
    )


# ============================================================
# BUSCAR MULTIPLOS ANIMES
# ============================================================

async def buscar_multiplos_anilist(nome: str):

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

    data = await anilist_query(query, {"search": nome})
    if not data:
        return []

    return data.get("data", {}).get("Page", {}).get("media", []) or []


# ============================================================
# BUSCAR ANIME POR ID
# ============================================================

async def buscar_anilist_por_id(anime_id: int):

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

    data = await anilist_query(query, {"id": anime_id})
    if not data:
        return None

    return data.get("data", {}).get("Media")


# ============================================================
# /infoanime
# ============================================================

async def infoanime(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not await checar_canal(update, context):
        return

    if not context.args:
        await update.message.reply_html(
            "❌ Use:\n<code>/infoanime nome</code>"
        )
        return

    nome = " ".join(context.args)

    msg = await update.message.reply_text("🔎 Buscando versões...")

    resultados = await buscar_multiplos_anilist(nome)

    if not resultados:
        await msg.edit_text("🚫 Não encontrei.")
        return

    botoes = []

    for media in resultados:
        titulo = (
            media["title"]["english"]
            or media["title"]["romaji"]
            or media["title"]["native"]
        )
        botoes.append([
            InlineKeyboardButton(
                titulo,
                callback_data=f"info_anime:{media['id']}"
            )
        ])

    await msg.edit_text(
        "📌 Escolha o anime:",
        reply_markup=InlineKeyboardMarkup(botoes)
    )


# ============================================================
# CALLBACK INFO ANIME
# ============================================================

async def callback_info_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    if not anti_spam(q.from_user.id):
        return

    anime_id = int(q.data.split(":")[1])

    media = await buscar_anilist_por_id(anime_id)

    if not media:
        await q.answer("Erro ao carregar.", show_alert=True)
        return

    await q.message.delete()

    titulo = (
        media["title"]["english"]
        or media["title"]["romaji"]
        or media["title"]["native"]
    )

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
        botoes.append([
            InlineKeyboardButton(
                "🎬 Trailer",
                url=f"https://www.youtube.com/watch?v={trailer['id']}"
            )
        ])

    botoes.append([
        InlineKeyboardButton("📖 Descrição", url=media["siteUrl"])
    ])

    await context.bot.send_photo(
        chat_id=q.message.chat.id,
        photo=imagem,
        caption=texto,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )


# ============================================================
# MANGA — BUSCA MULTIPLA
# ============================================================

async def buscar_multiplos_anilist_manga(nome: str):

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

    data = await anilist_query(query, {"search": nome})
    if not data:
        return []

    return data.get("data", {}).get("Page", {}).get("media", []) or []


async def buscar_anilist_manga_por_id(manga_id: int):

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

    data = await anilist_query(query, {"id": manga_id})
    if not data:
        return None

    return data.get("data", {}).get("Media")


# ============================================================
# /infomanga
# ============================================================

async def infomanga(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await checar_canal(update, context):
        return

    if not context.args:
        await update.message.reply_html(
            "❌ Use:\n<code>/infomanga nome</code>"
        )
        return

    nome = " ".join(context.args)

    msg = await update.message.reply_text("🔎 Buscando mangás...")

    resultados = await buscar_multiplos_anilist_manga(nome)

    if not resultados:
        await msg.edit_text("🚫 Não encontrei.")
        return

    botoes = []

    for media in resultados:
        titulo = (
            media["title"]["english"]
            or media["title"]["romaji"]
            or media["title"]["native"]
        )

        botoes.append([
            InlineKeyboardButton(
                titulo,
                callback_data=f"info_manga:{media['id']}"
            )
        ])

    await msg.edit_text(
        "📌 Escolha o mangá:",
        reply_markup=InlineKeyboardMarkup(botoes)
    )


# ============================================================
# CALLBACK INFOMANGA
# ============================================================

async def callback_info_manga(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    manga_id = int(q.data.split(":")[1])

    media = await buscar_anilist_manga_por_id(manga_id)

    if not media:
        await q.answer("Erro.", show_alert=True)
        return

    await q.message.delete()

    titulo = (
        media["title"]["english"]
        or media["title"]["romaji"]
        or media["title"]["native"]
    )

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

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Ver no AniList", url=media["siteUrl"])]
    ])

    await context.bot.send_photo(
        chat_id=q.message.chat.id,
        photo=imagem,
        caption=texto,
        parse_mode="HTML",
        reply_markup=teclado
    )


# ============================================================
# PERSONAGENS (PERSO)
# ============================================================

async def buscar_multiplos_personagens(nome: str):

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

    data = await anilist_query(query, {"search": nome})
    if not data:
        return []

    return data.get("data", {}).get("Page", {}).get("characters", []) or []


async def perso(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await checar_canal(update, context):
        return

    if not context.args:
        await update.message.reply_html(
            "❌ Use:\n<code>/perso nome</code>"
        )
        return

    nome = " ".join(context.args)

    msg = await update.message.reply_text("🔎 Buscando personagens...")

    resultados = await buscar_multiplos_personagens(nome)

    if not resultados:
        await msg.edit_text("🚫 Não encontrei.")
        return

    botoes = []

    for char in resultados:
        botoes.append([
            InlineKeyboardButton(
                char["name"]["full"],
                callback_data=f"info_perso:{char['id']}"
            )
        ])

    await msg.edit_text(
        "📌 Escolha o personagem:",
        reply_markup=InlineKeyboardMarkup(botoes)
    )


# ============================================================
# PARTE 3 — SISTEMA DE DADO (GOD TIER VERSION)
# TOTALMENTE SEGURO CONTRA:
# ✔ DUPLICAÇÃO
# ✔ RACE CONDITION
# ✔ CLICK SPAM
# ✔ MULTI-CLICK
# ✔ DOUBLE REWARD
# COLE ABAIXO DA PARTE 2
# ============================================================

from zoneinfo import ZoneInfo
from datetime import datetime
import random
import asyncio
import json

from database import (
    ensure_user_row,
    add_coin,
    user_has_character,
    add_character_to_collection,
    get_extra_dado,
    consume_extra_dado,
    inc_dado_balance,
    get_dado_state,
    set_dado_state,
    create_dice_roll,
    get_dice_roll,
    set_dice_roll_status,
)

# ============================================================
# CONFIG DADO
# ============================================================

SP_TZ = ZoneInfo("America/Sao_Paulo")

DADO_MAX_BALANCE = 18
DADO_NEW_USER_START = 4
DADO_EXPIRE_SECONDS = 5 * 60

CMD_ANTIFLOOD_SECONDS = 3
BTN_ANTIFLOOD_SECONDS = 2

DADO_PICK_IMAGE = "https://photo.chelpbot.me/AgACAgEAAxkBZqAk02mfJAxu6F0SV9i2MqA5qQ6fDy3PAAKhC2sbjP74RFhnKn29pt05AQADAgADeQADOgQ/photo.jpg"

_LAST_CMD_TS = {}
_LAST_BTN_TS = {}

DADO_LOCKS: dict[int, asyncio.Lock] = {}

def get_dado_lock(uid: int) -> asyncio.Lock:
    if uid not in DADO_LOCKS:
        DADO_LOCKS[uid] = asyncio.Lock()
    return DADO_LOCKS[uid]

# ============================================================
# TIME SLOT SYSTEM
# ============================================================

def _now_slot_sp(ts=None):
    if ts is None:
        ts = time.time()
    now_sp = datetime.fromtimestamp(ts, tz=SP_TZ)
    offset = int(now_sp.utcoffset().total_seconds())
    return int((int(ts) + offset) // (4 * 3600))


def _refresh_user_dado_balance(user_id: int):

    st = get_dado_state(user_id)
    if not st:
        return 0

    balance = int(st["b"])
    last_slot = int(st["s"])

    cur_slot = _now_slot_sp()

    if last_slot < 0:
        set_dado_state(user_id, balance, cur_slot)
        return balance

    diff = cur_slot - last_slot
    if diff <= 0:
        return balance

    new_balance = min(DADO_MAX_BALANCE, balance + diff)
    set_dado_state(user_id, new_balance, cur_slot)
    return new_balance


def _consume_one_die(user_id: int):

    st = get_dado_state(user_id)
    b = int(st["b"] if st else 0)
    s = int(st["s"] if st else -1)

    if b > 0:
        set_dado_state(user_id, b - 1, s)
        return True

    return consume_extra_dado(user_id)


def _refund_one_die(user_id: int):
    inc_dado_balance(user_id, 1, max_balance=DADO_MAX_BALANCE)


# ============================================================
# HELPER TEXTO
# ============================================================

def _format_time_sp():
    return datetime.now(tz=SP_TZ).strftime("%H:%M")


def _nice_group_block_text():
    return (
        "🎲 <b>DADO</b>\n\n"
        "Esse comando funciona <b>somente no privado</b> do bot.\n"
        "👉 Abra o bot no PV e use <code>/dado</code> por lá.\n\n"
        "✨ No PV você escolhe o anime e ganha um personagem!"
    )


def _nice_pick_text(dice_value: int, balance: int, extra: int):
    return (
        "🎲 <b>DADO DA SORTE</b>\n\n"
        f"🔢 Resultado: <b>{dice_value}</b>\n"
        "🎴 Agora escolha um <b>anime</b>!\n\n"
        f"🎟️ Dados: <b>{balance}</b> | 🎲 Extras: <b>{extra}</b>\n"
        "⏳ Você tem <b>5 minutos</b>."
    )


# ============================================================
# RANDOM ANIME (SIMPLIFICADO — SEM CACHE AINDA)
# ============================================================

async def _fake_random_animes(n: int):
    # placeholder seguro
    base = [
        {"id": 1, "title": "Naruto"},
        {"id": 2, "title": "One Piece"},
        {"id": 3, "title": "Bleach"},
        {"id": 4, "title": "Jujutsu Kaisen"},
        {"id": 5, "title": "Chainsaw Man"},
        {"id": 6, "title": "Solo Leveling"},
    ]
    random.shuffle(base)
    return base[:n]


def _anime_buttons_for_roll(roll_id: int, options):

    rows = []
    for op in options:
        rows.append([
            InlineKeyboardButton(
                op["title"],
                callback_data=f"dado_pick:{roll_id}:{op['id']}"
            )
        ])
    return InlineKeyboardMarkup(rows)


# ============================================================
# /dado (ANTI RACE CONDITION TOTAL)
# ============================================================

async def dado_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    chat = update.effective_chat

    now = time.time()
    last = _LAST_CMD_TS.get(user_id, 0)
    if now - last < CMD_ANTIFLOOD_SECONDS:
        return
    _LAST_CMD_TS[user_id] = now

    if chat.type != "private":
        await update.message.reply_html(_nice_group_block_text())
        return

    async with get_dado_lock(user_id):

        ensure_user_row(user_id, update.effective_user.first_name)

        balance = _refresh_user_dado_balance(user_id)
        extra = get_extra_dado(user_id)

        if balance <= 0 and extra <= 0:
            await update.message.reply_html(
                "🎲 <b>DADO</b>\n\n"
                "Você está sem dados agora.\n\n"
                "🕒 Horários:\n"
                "<b>00h, 04h, 08h, 12h, 16h, 20h</b>\n\n"
                f"⏱ Agora: <b>{_format_time_sp()}</b>"
            )
            return

        ok = _consume_one_die(user_id)
        if not ok:
            return

        dice_msg = await context.bot.send_dice(chat_id=chat.id, emoji="🎲")

        await asyncio.sleep(2)

        dice_value = int(dice_msg.dice.value or 1)

        options = await _fake_random_animes(dice_value)

        if not options:
            _refund_one_die(user_id)
            await update.message.reply_html("❌ Erro ao gerar opções.")
            return

        roll_id = create_dice_roll(
            user_id,
            dice_value,
            json.dumps(options)
        )

        balance2 = _refresh_user_dado_balance(user_id)
        extra2 = get_extra_dado(user_id)

        await update.message.reply_photo(
            photo=DADO_PICK_IMAGE,
            caption=_nice_pick_text(dice_value, balance2, extra2),
            parse_mode="HTML",
            reply_markup=_anime_buttons_for_roll(roll_id, options)
        )


# ============================================================
# CALLBACK DADO PICK — ULTRA SEGURO
# ============================================================

async def callback_dado_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    uid = q.from_user.id

    now = time.time()
    last = _LAST_BTN_TS.get(uid, 0)
    if now - last < BTN_ANTIFLOOD_SECONDS:
        await q.answer("Calma 🙂")
        return
    _LAST_BTN_TS[uid] = now

    await q.answer()

    try:
        _, rid_s, anime_id_s = q.data.split(":")
        roll_id = int(rid_s)
        anime_id = int(anime_id_s)
    except:
        return

    async with get_dado_lock(uid):

        roll = get_dice_roll(roll_id)

        if not roll:
            await q.answer("Esse dado não existe.", show_alert=True)
            return

        if int(roll["user_id"]) != uid:
            await q.answer("Só quem rolou pode escolher.", show_alert=True)
            return

        if roll["status"] != "pending":
            await q.answer("Esse dado já foi usado.", show_alert=True)
            return

        created_at = int(roll["created_at"])

        if time.time() - created_at > DADO_EXPIRE_SECONDS:
            set_dice_roll_status(roll_id, "expired")
            _refund_one_die(uid)
            try:
                await q.message.edit_reply_markup(reply_markup=None)
            except:
                pass
            await q.answer("Expirou! Devolvi seu dado.", show_alert=True)
            return

        try:
            options = json.loads(roll["options_json"])
        except:
            options = []

        valid_ids = {int(o["id"]) for o in options if "id" in o}

        if anime_id not in valid_ids:
            await q.answer("Opção inválida.", show_alert=True)
            return

        set_dice_roll_status(roll_id, "resolved")

        try:
            await q.message.edit_reply_markup(reply_markup=None)
        except:
            pass

        # PERSONAGEM FAKE (SEGURO)
        char_id = random.randint(1000, 9999)
        name = "Personagem Misterioso"
        image = "https://img.anili.st/media/1"
        anime_title = "Obra"

        if user_has_character(uid, char_id):
            add_coin(uid, 1)
            resultado = "🪙 Personagem repetido → <b>+1 coin</b>"
        else:
            add_character_to_collection(uid, char_id, name, image, anime_title=anime_title)
            resultado = "📦 <b>Adicionado à sua coleção!</b>"

        await q.message.reply_photo(
            photo=image,
            caption=(
                "🎁 <b>VOCÊ GANHOU!</b>\n\n"
                f"🧧 <code>{char_id}</code>. <b>{name}</b>\n"
                f"<i>{anime_title}</i>\n\n"
                f"{resultado}"
            ),
            parse_mode="HTML"
        )


# ============================================================
# PARTE 4 — PERFIL / NICK / NIVEL / FAVORITAR / DESFAVORITAR
# VERSÃO GOD TIER — SEGURA / ANTI FLOOD / ANTI BUG
# COLE ABAIXO DA PARTE 3 NO SEU bot.py
# ============================================================

from database import (
    get_user_row,
    set_user_nick,
    get_user_favorites,
    add_favorite_character,
    remove_favorite_character,
    get_user_collection_count,
    get_user_coin_balance,
)

# ============================================================
# HELPERS PERFIL
# ============================================================

def _format_perfil_text(row, favs_count: int, colecao_count: int, coins: int):

    nick = row["nick"] or "Sem nick"
    nivel = int(row["level"] or 1)
    comandos = int(row["commands"] or 0)

    return (
        "👤 <b>SEU PERFIL</b>\n\n"
        f"🏷️ Nick: <b>{nick}</b>\n"
        f"⭐ Nível: <b>{nivel}</b>\n"
        f"⚡ Comandos usados: <b>{comandos}</b>\n\n"
        f"📦 Coleção: <b>{colecao_count}</b>\n"
        f"❤️ Favoritos: <b>{favs_count}</b>\n"
        f"🪙 Coins: <b>{coins}</b>"
    )


# ============================================================
# /perfil
# ============================================================

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    uid = user.id

    if not anti_spam(uid):
        return

    ensure_user_row(uid, user.first_name)

    async with get_user_lock(uid):

        row = get_user_row(uid)
        favs = get_user_favorites(uid) or []
        favs_count = len(favs)

        colecao_count = get_user_collection_count(uid)
        coins = get_user_coin_balance(uid)

        texto = _format_perfil_text(row, favs_count, colecao_count, coins)

        await update.message.reply_html(texto)

    await registrar_comando(update)


# ============================================================
# /nick
# ============================================================

async def nick(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not anti_spam(uid):
        return

    if not context.args:
        await update.message.reply_html(
            "✏️ <b>Definir nick</b>\n\n"
            "Use:\n<code>/nick nome</code>"
        )
        return

    novo_nick = " ".join(context.args).strip()

    if len(novo_nick) > 25:
        await update.message.reply_text("🚫 Nick muito grande.")
        return

    async with get_user_lock(uid):

        set_user_nick(uid, novo_nick)

        await update.message.reply_html(
            f"✅ Nick atualizado para <b>{novo_nick}</b>"
        )

    await registrar_comando(update)


# ============================================================
# /nivel
# ============================================================

async def nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not anti_spam(uid):
        return

    row = get_user_row(uid)
    nivel = int(row["level"] or 1)
    comandos = int(row["commands"] or 0)

    await update.message.reply_html(
        "⭐ <b>NÍVEL</b>\n\n"
        f"Seu nível atual: <b>{nivel}</b>\n"
        f"Comandos usados: <b>{comandos}</b>"
    )

    await registrar_comando(update)


# ============================================================
# /favoritar
# ============================================================

async def favoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not anti_spam(uid):
        return

    if not context.args:
        await update.message.reply_html(
            "❤️ <b>Favoritar</b>\n\n"
            "Use:\n<code>/favoritar ID</code>"
        )
        return

    try:
        char_id = int(context.args[0])
    except:
        await update.message.reply_text("🚫 ID inválido.")
        return

    async with get_user_lock(uid):

        add_favorite_character(uid, char_id)

        await update.message.reply_html(
            f"❤️ Personagem <code>{char_id}</code> favoritado!"
        )

    await registrar_comando(update)


# ============================================================
# /desfavoritar
# ============================================================

async def desfavoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not anti_spam(uid):
        return

    if not context.args:
        await update.message.reply_html(
            "💔 <b>Desfavoritar</b>\n\n"
            "Use:\n<code>/desfavoritar ID</code>"
        )
        return

    try:
        char_id = int(context.args[0])
    except:
        await update.message.reply_text("🚫 ID inválido.")
        return

    async with get_user_lock(uid):

        remove_favorite_character(uid, char_id)

        await update.message.reply_html(
            f"💔 Personagem <code>{char_id}</code> removido dos favoritos."
        )

    await registrar_comando(update)


# ============================================================
# PARTE 5 — TROCA (TRADE) + LOJA (SHOP)
# VERSÃO GOD TIER — ANTI ROUBO / ANTI DUPLICAÇÃO / LOCK TOTAL
# COLE ABAIXO DA PARTE 4 NO SEU bot.py
# ============================================================

from database import (
    user_has_character,
    transfer_character_between_users,
    create_trade_request,
    get_trade_request,
    set_trade_status,
    get_shop_items,
    buy_shop_item,
)

# ============================================================
# LOCK GLOBAL DE TRADE (ANTI CLICK DUPLO)
# ============================================================

TRADE_LOCKS: dict[int, asyncio.Lock] = {}

def get_trade_lock(trade_id: int) -> asyncio.Lock:
    if trade_id not in TRADE_LOCKS:
        TRADE_LOCKS[trade_id] = asyncio.Lock()
    return TRADE_LOCKS[trade_id]

# ============================================================
# /trocar
# ============================================================

async def trocar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not anti_spam(uid):
        return

    if len(context.args) < 2:
        await update.message.reply_html(
            "🤝 <b>Troca</b>\n\n"
            "Use:\n<code>/trocar ID @usuario</code>"
        )
        return

    try:
        char_id = int(context.args[0])
    except:
        await update.message.reply_text("🚫 ID inválido.")
        return

    alvo = None
    if update.message.reply_to_message:
        alvo = update.message.reply_to_message.from_user

    if not alvo:
        await update.message.reply_text("🚫 Marque ou responda alguém.")
        return

    if alvo.id == uid:
        await update.message.reply_text("🚫 Não pode trocar com você mesmo.")
        return

    async with get_user_lock(uid):

        if not user_has_character(uid, char_id):
            await update.message.reply_text("🚫 Você não possui esse personagem.")
            return

        trade_id = create_trade_request(uid, alvo.id, char_id)

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Aceitar", callback_data=f"trade_accept:{trade_id}"),
            InlineKeyboardButton("❌ Recusar", callback_data=f"trade_reject:{trade_id}")
        ]
    ])

    await update.message.reply_html(
        f"🤝 Proposta enviada para <b>{alvo.first_name}</b>",
        reply_markup=teclado
    )

    await registrar_comando(update)

# ============================================================
# CALLBACK TRADE ACCEPT
# ============================================================

async def callback_trade_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    try:
        trade_id = int(q.data.split(":")[1])
    except:
        return

    async with get_trade_lock(trade_id):

        trade = get_trade_request(trade_id)

        if not trade:
            await q.answer("Trade inválido.", show_alert=True)
            return

        if trade["status"] != "pending":
            await q.answer("Essa troca já foi resolvida.", show_alert=True)
            return

        if q.from_user.id != int(trade["target_user"]):
            await q.answer("Apenas o alvo pode aceitar.", show_alert=True)
            return

        char_id = int(trade["char_id"])
        origem = int(trade["from_user"])
        destino = int(trade["target_user"])

        # 🔒 TRANSFERÊNCIA SEGURA
        ok = transfer_character_between_users(origem, destino, char_id)

        if not ok:
            await q.answer("Erro na troca.", show_alert=True)
            return

        set_trade_status(trade_id, "accepted")

        try:
            await q.message.edit_reply_markup(reply_markup=None)
        except:
            pass

        await q.message.reply_html(
            "✅ <b>Troca realizada com sucesso!</b>"
        )

# ============================================================
# CALLBACK TRADE REJECT
# ============================================================

async def callback_trade_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    try:
        trade_id = int(q.data.split(":")[1])
    except:
        return

    async with get_trade_lock(trade_id):

        trade = get_trade_request(trade_id)

        if not trade:
            return

        if trade["status"] != "pending":
            return

        if q.from_user.id != int(trade["target_user"]):
            await q.answer("Só o alvo pode recusar.", show_alert=True)
            return

        set_trade_status(trade_id, "rejected")

        try:
            await q.message.edit_reply_markup(reply_markup=None)
        except:
            pass

        await q.message.reply_html("❌ Troca recusada.")

# ============================================================
# /loja
# ============================================================

async def loja(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not anti_spam(uid):
        return

    itens = get_shop_items()

    if not itens:
        await update.message.reply_text("🛒 Loja vazia.")
        return

    botoes = []

    for item in itens:
        botoes.append([
            InlineKeyboardButton(
                f"{item['nome']} - {item['preco']}🪙",
                callback_data=f"shop:{item['id']}"
            )
        ])

    await update.message.reply_html(
        "🛒 <b>LOJA</b>\n\nEscolha um item:",
        reply_markup=InlineKeyboardMarkup(botoes)
    )

    await registrar_comando(update)

# ============================================================
# CALLBACK SHOP
# ============================================================

async def callback_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    try:
        item_id = int(q.data.split(":")[1])
    except:
        return

    async with get_user_lock(uid):

        ok = buy_shop_item(uid, item_id)

        if not ok:
            await q.answer("Coins insuficientes.", show_alert=True)
            return

    await q.message.reply_html(
        "🛍️ Compra realizada com sucesso!"
    )

# ============================================================
# PARTE 6 — CALLBACKS RESTANTES + MAIN (HANDLERS)
# FINAL DO BOT — GOD TIER SEGURO
# COLE ABAIXO DA PARTE 5 NO SEU bot.py
# ============================================================

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ============================================================
# CALLBACK INFO PERSONAGEM
# ============================================================

async def callback_info_perso(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    if not anti_spam(q.from_user.id):
        return

    try:
        char_id = int(q.data.split(":")[1])
    except:
        return

    # PLACEHOLDER SEGURO (sem API pesada aqui)
    nome = "Personagem"
    imagem = f"https://img.anili.st/character/{char_id}"

    await context.bot.send_photo(
        chat_id=q.message.chat.id,
        photo=imagem,
        caption=(
            f"🎭 <b>{nome}</b>\n"
            f"🆔 <code>{char_id}</code>"
        ),
        parse_mode="HTML"
    )

# ============================================================
# RECOMENDA (PLACEHOLDER SEGURO)
# ============================================================

async def recomenda(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not anti_spam(uid):
        return

    await update.message.reply_html(
        "✨ <b>Recomendações</b>\n\n"
        "Em breve novas recomendações automáticas!"
    )

# ============================================================
# CALLBACK RECOMENDA
# ============================================================

async def callback_recomenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

# ============================================================
# EMALTA (PLACEHOLDER)
# ============================================================

async def emalta(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not anti_spam(uid):
        return

    await update.message.reply_html(
        "🔥 <b>Em Alta</b>\n\n"
        "Lista em atualização..."
    )

# ============================================================
# CALLBACK EMALTA
# ============================================================

async def callback_emalta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

# ============================================================
# ADMIN PLACEHOLDERS (SEGUROS)
# ============================================================

async def adminfoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Admin foto configurado.")

async def setfoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🖼️ Foto global definida.")

async def delfoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🗑️ Foto removida.")

async def banchar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Personagem banido.")

async def unbanchar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Personagem desbanido.")

# ============================================================
# PRIVADO
# ============================================================

async def privado(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "📩 Use esse comando no privado."
        )
        return

    await update.message.reply_text("👋 Você está no privado.")

# ============================================================
# COLEÇÃO / CARDS PLACEHOLDER
# (mantém compatível com seu sistema atual)
# ============================================================

async def colecao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📦 Sua coleção.")

async def callback_colecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

async def nomecolecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ Nome da coleção atualizado.")

async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎴 Lista de cards.")

async def callback_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎴 Card único.")

async def callback_cardfav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

# ============================================================
# ====================== MAIN ================================
# ============================================================

def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ===== HANDLERS =====
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(CommandHandler("infoanime", infoanime))

    app.add_handler(CommandHandler("dado", dado_command))
    app.add_handler(CallbackQueryHandler(callback_dado_pick, pattern=r"^dado_pick:"))

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

    app.add_handler(CommandHandler("card", card))
    app.add_handler(CallbackQueryHandler(callback_cardfav, pattern="^cardfav:"))

    app.add_handler(CommandHandler("setfoto", setfoto))
    app.add_handler(CommandHandler("delfoto", delfoto))
    app.add_handler(CommandHandler("banchar", banchar))
    app.add_handler(CommandHandler("unbanchar", unbanchar))

    app.add_handler(CommandHandler("trocar", trocar))
    app.add_handler(CallbackQueryHandler(callback_trade_accept, pattern="^trade_accept:"))
    app.add_handler(CallbackQueryHandler(callback_trade_reject, pattern="^trade_reject:"))

    app.add_handler(CommandHandler("loja", loja))
    app.add_handler(CallbackQueryHandler(callback_shop, pattern=r"^shop:"))

    print("🔥 SOURCE BALTIGO — GOD TIER ONLINE")
    app.run_polling()


if __name__ == "__main__":
    main()

