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
from typing import Optional, Dict, Any, List, Tuple, Set

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
    get_user_by_nick,
    set_private_profile,
    set_admin_photo,
    get_admin_photo_db,
    add_coin,
    get_user_coins,
    try_spend_coins,
    set_collection_name,
    get_collection_name,
    count_collection,
    get_collection_page,
    user_has_character,
    add_character_to_collection,
    get_collection_character_full,
    get_collection_character,
    remove_one_from_collection,
    set_favorite_from_collection,
    clear_favorite,
    swap_trade_execute,
    create_trade,
    get_trade_by_id,
    get_latest_pending_trade_for_to_user,
    mark_trade_status,
    list_pending_trades_for_user,
    top_cache_last_updated,
    replace_top_anime_cache,
    get_top_anime_list,
    create_dice_roll,
    get_dice_roll,
    set_dice_roll_status,
    try_set_dice_roll_status,
    get_dado_state,
    set_dado_state,
    inc_dado_balance,
    get_extra_dado,
    add_extra_dado,
    consume_extra_dado,
    claim_daily_reward,
    set_global_character_image,
    get_global_character_image,
    delete_global_character_image,
    ban_character,
    unban_character,
    is_banned_character,
    get_user_coins,
    claim_daily_reward,
    list_pending_trades_for_user,
    try_spend_coins,
    add_extra_dado,
    get_top_by_level,
    get_top_by_coins,
    get_top_by_collection,
    get_user_stats,
    list_user_achievement_keys,
    grant_achievements_and_reward,
)

from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

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
# CRÍTICO: Telethon precisa ser iniciado (connect) antes de usar iter_messages.
# Vamos iniciar no startup do PTB mais abaixo (quando você mandar a parte do main/app).
client = TelegramClient("sessao_busca", API_ID, API_HASH)

# Locks por canal para evitar 100 buscas simultâneas no mesmo canal (protege rate limit e CPU)
_channel_search_locks: Dict[str, asyncio.Lock] = {}
_channel_search_cache: Dict[Tuple[str, str], Tuple[float, Optional[int]]] = {}
CHANNEL_SEARCH_TTL = 20  # segundos (cache curto anti-spam)

def _get_lock_for_channel(canal: str) -> asyncio.Lock:
    lock = _channel_search_locks.get(canal)
    if lock is None:
        lock = asyncio.Lock()
        _channel_search_locks[canal] = lock
    return lock

async def buscar_post(canal: str, termo: str) -> Optional[int]:
    """Retorna o message_id do primeiro post que bater no search."""
    # Cache curto: se 100 pessoas buscarem a mesma coisa, 99 não batem no Telegram de novo
    key = (canal, termo.lower().strip())
    now = time.time()
    cached = _channel_search_cache.get(key)
    if cached and (now - cached[0] <= CHANNEL_SEARCH_TTL):
        return cached[1]

    lock = _get_lock_for_channel(canal)
    async with lock:
        # Recheca cache após pegar lock (evita thundering herd)
        cached = _channel_search_cache.get(key)
        if cached and (time.time() - cached[0] <= CHANNEL_SEARCH_TTL):
            return cached[1]

        try:
            async for msg in client.iter_messages(canal, search=termo):
                _channel_search_cache[key] = (time.time(), msg.id)
                return msg.id
        except Exception:
            _channel_search_cache[key] = (time.time(), None)
            return None

# ==================================================
# 4) ANTI-SPAM (MELHORADO PARA CONCORRÊNCIA)
# ==================================================
# O seu anti_spam original era global e simples — funciona, mas falha em:
# - comandos diferentes (um bloqueia o outro)
# - callbacks spammados
# - concorrência (2 tasks podem passar “ao mesmo tempo” em casos extremos)
#
# Aqui vira rate limit por "chave" (ex.: comando/callback) e com lock por usuário.

ANTI_SPAM_TIME = 5  # segundos (mantive o mesmo valor)
_rate_state: Dict[Tuple[int, str], float] = {}
_user_rate_locks: Dict[int, asyncio.Lock] = {}

def _get_user_lock(user_id: int) -> asyncio.Lock:
    lock = _user_rate_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_rate_locks[user_id] = lock
    return lock

async def anti_spam(user_id: int, key: str = "global", window: int = ANTI_SPAM_TIME) -> bool:
    """
    Rate limit por usuário + chave.
    Ex:
      await anti_spam(user_id, "cmd:/dado", 3)
      await anti_spam(user_id, "cb:dado_pick", 2)
    """
    now = time.time()
    lock = _get_user_lock(user_id)
    async with lock:
        k = (user_id, key)
        last = _rate_state.get(k, 0.0)
        if now - last < window:
            return False
        _rate_state[k] = now
        return True

# Anti “double click” / callback duplicado (mesmo callback_query.id)
_seen_callback_ids: Dict[int, float] = {}
CALLBACK_DEDUPE_TTL = 30  # segundos

def callback_dedupe(callback_query_id: int) -> bool:
    """
    Retorna True se ainda NÃO vimos esse callback_query.id (ou seja, pode processar).
    Retorna False se for repetido (duplo clique / retry do Telegram).
    """
    now = time.time()
    # limpeza barata
    if len(_seen_callback_ids) > 5000:
        cutoff = now - CALLBACK_DEDUPE_TTL
        for k, ts in list(_seen_callback_ids.items()):
            if ts < cutoff:
                _seen_callback_ids.pop(k, None)

    ts = _seen_callback_ids.get(callback_query_id)
    if ts and (now - ts <= CALLBACK_DEDUPE_TTL):
        return False
    _seen_callback_ids[callback_query_id] = now
    return True

# ==================================================
# 5) ADMINS
# ==================================================
def parse_admins(raw: str) -> Set[int]:
    if not raw:
        return set()
    ids: Set[int] = set()
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
# Cache de membership para não chamar get_chat_member toda hora (caro e rate-limited)
_member_cache: Dict[int, Tuple[float, bool]] = {}
MEMBER_CACHE_TTL = 120  # segundos

async def usuario_no_canal(bot, user_id: int) -> bool:
    if not CANAL_OBRIGATORIO:
        return True  # se não configurou, não bloqueia

    now = time.time()
    cached = _member_cache.get(user_id)
    if cached and (now - cached[0] <= MEMBER_CACHE_TTL):
        return cached[1]

    try:
        membro = await bot.get_chat_member(CANAL_OBRIGATORIO, user_id)
        ok = membro.status in ["member", "administrator", "creator"]
        _member_cache[user_id] = (time.time(), ok)
        return ok
    except Exception:
        _member_cache[user_id] = (time.time(), False)
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

# Lock por usuário: impede corrida (2 updates simultâneos do mesmo user duplicarem nível/mensagens)
_level_locks: Dict[int, asyncio.Lock] = {}

def _get_level_lock(user_id: int) -> asyncio.Lock:
    lock = _level_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _level_locks[user_id] = lock
    return lock

async def registrar_comando(update: Update):
    """
    Incrementa contador de comandos e sobe o nível quando necessário.
    - Atômico por usuário (lock)
    - Evita cursor global (crítico em concorrência)
    """
    user = update.effective_user
    if not user:
        return

    user_id = user.id
    ensure_user_row(user_id, user.first_name)

    # Segurança: se update vier sem message, não tentamos responder
    lock = _get_level_lock(user_id)
    async with lock:
        cur = db.cursor()
        try:
            # 1) trava a linha do usuário (FOR UPDATE) e calcula tudo de forma consistente
            cur.execute(
                """
                WITH old AS (
                    SELECT
                        COALESCE(commands, 0) AS old_commands,
                        COALESCE(level, 1)    AS old_level,
                        COALESCE(nick, %s)    AS nick_safe
                    FROM users
                    WHERE user_id = %s
                    FOR UPDATE
                ),
                upd AS (
                    UPDATE users
                    SET
                        commands = (SELECT old_commands FROM old) + 1,
                        level = GREATEST(
                            (SELECT old_level FROM old),
                            (((SELECT old_commands FROM old) + 1) / %s) + 1
                        )
                    WHERE user_id = %s
                    RETURNING commands, level
                )
                SELECT
                    (SELECT old_level FROM old)    AS old_level,
                    (SELECT nick_safe FROM old)    AS nick_safe,
                    (SELECT commands FROM upd)     AS commands,
                    (SELECT level FROM upd)        AS level
                ;
                """,
                (user.first_name, user_id, COMANDOS_POR_NIVEL, user_id),
            )
            data = cur.fetchone()
            db.commit()

            if not data:
                return

            old_level = int(data["old_level"])
            new_level = int(data["level"])
            nick_safe = data.get("nick_safe") or user.first_name

            if new_level > old_level:
                mensagem = (
                    "🎉 <b>LEVEL UP!</b>\n\n"
                    f"✨ Parabéns <b>{nick_safe}</b>!\n"
                    f"⬆️ Você alcançou o <b>Nível {new_level}</b>!\n\n"
                    "🚀 Continue usando o bot!"
                )
                if update.message:
                    await update.message.reply_html(mensagem)

        except Exception:
            db.rollback()
            # Não explode o bot por falha de DB (em escala, isso mata a estabilidade)
            return
        finally:
            try:
                cur.close()
            except Exception:
                pass

# ==================================================
# 8) /start
# ==================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Rate limit leve no /start (não muda texto, só protege spam)
    if update.effective_user:
        ok = await anti_spam(update.effective_user.id, key="cmd:/start", window=3)
        if not ok:
            return

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

    if update.message:
        await update.message.reply_photo(
            photo="https://photo.chelpbot.me/AgACAgEAAxkBZpDL8mmeFx3it__n9zwKhDWr-EiaijwiAAIdDGsbjP7wRDMvEtZUPvYtAQADAgADeQADOgQ/photo.jpg",
            caption=texto,
            parse_mode="HTML",
            reply_markup=teclado
        )

# ==================================================
# 9) /login (AniList OAuth)
# ==================================================
import hmac, hashlib, base64

ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()
OAUTH_STATE_SECRET = os.getenv("OAUTH_STATE_SECRET", "").strip()

def make_state(user_id: int) -> str:
    # state = user_id.timestamp.signature
    # Segurança: se o secret estiver vazio, state vira previsível e abre brecha
    ts = str(int(time.time()))
    payload = f"{user_id}.{ts}".encode()

    # Se SECRET não existir, ainda gera algo, mas /login vai bloquear com aviso (sem quebrar bot)
    secret = (OAUTH_STATE_SECRET or "MISSING_SECRET").encode()

    sig = hmac.new(secret, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + b"." + sig).decode().rstrip("=")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        ok = await anti_spam(update.effective_user.id, key="cmd:/login", window=5)
        if not ok:
            return

    # Validações de config (sem remover funcionalidade; só impede rodar inseguro/quebrado)
    if not ANILIST_CLIENT_ID or not PUBLIC_BASE_URL or not OAUTH_STATE_SECRET:
        if update.message:
            await update.message.reply_text("🔑 Clique para conectar sua conta AniList:")
        return

    telegram_id = update.effective_user.id
    state = make_state(telegram_id)
    redirect_uri = f"{PUBLIC_BASE_URL}/callback"

    url = (
        "https://anilist.co/api/v2/oauth/authorize"
        f"?client_id={ANILIST_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        f"&state={state}"
    )

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔐 Conectar com AniList", url=url)]])
    if update.message:
        await update.message.reply_text("🔑 Clique para conectar sua conta AniList:", reply_markup=keyboard)

# ==================================================
# 10) /adminfoto (PERSISTENTE + TESTE)
# ==================================================
_adminfoto_locks: Dict[int, asyncio.Lock] = {}

def _get_adminfoto_lock(user_id: int) -> asyncio.Lock:
    lock = _adminfoto_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _adminfoto_locks[user_id] = lock
    return lock

async def adminfoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return

    user_id = user.id

    # Anti-spam específico
    ok = await anti_spam(user_id, key="cmd:/adminfoto", window=5)
    if not ok:
        return

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

    url = context.args[0].strip()

    if len(url) > 500:
        await update.message.reply_html("❌ Envie um link válido começando com http:// ou https://")
        return

    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_html("❌ Envie um link válido começando com http:// ou https://")
        return

    ensure_user_row(user_id, user.first_name)

    # Serializa por usuário pra evitar gravações concorrentes e leitura inconsistente
    lock = _get_adminfoto_lock(user_id)
    async with lock:
        from database import set_admin_photo, get_admin_photo_db

        # salva no banco
        try:
            set_admin_photo(user_id, url)
        except Exception:
            # não altera textos; apenas falha silenciosa/segura
            await update.message.reply_html("❌ Não consegui salvar sua foto agora.")
            return

        # confirma que salvou (lê de volta)
        try:
            saved = get_admin_photo_db(user_id)
        except Exception:
            saved = None

        if not saved:
            await update.message.reply_html("❌ Não consegui salvar sua foto agora.")
            return

        # tenta enviar a foto — se o link não for direto, o Telegram vai falhar aqui
        try:
            await update.message.reply_photo(
                photo=saved,
                caption=(
                    "👑 <b>Foto de admin definida!</b>\n\n"
                    "✨ Agora seu perfil usará essa imagem.\n"
                    "👀 Veja com <code>/perfil</code>"
                ),
                parse_mode="HTML"
            )
        except Exception:
            # Se não conseguir mandar como foto, manda como texto (mas a foto ficou salva)
            await update.message.reply_html(
                "⚠️ Salvei sua foto, mas o Telegram não conseguiu enviar a prévia.\n\n"
                "Isso acontece quando o link não é uma imagem direta.\n"
                "Tente um link que termine com <code>.jpg</code>, <code>.png</code> ou <code>.webp</code>.\n\n"
                f"✅ Link salvo:\n<code>{saved}</code>"
            )

# ==================================================
# 11) PERFIL / NICK / NIVEL / FAVORITO (POSTGRES)
# ==================================================

# Locks por usuário para ações que escrevem em perfil (anti-race / anti-duplicação)
_profile_locks: Dict[int, asyncio.Lock] = {}

def _get_profile_lock(user_id: int) -> asyncio.Lock:
    lock = _profile_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _profile_locks[user_id] = lock
    return lock


# ------------------------------
# /nick
# ------------------------------
async def nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    # rate limit específico
    ok = await anti_spam(update.effective_user.id, key="cmd:/nick", window=4)
    if not ok:
        return

    await registrar_comando(update)
    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

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
    nick_novo = raw.lower()

    # regras: 3 a 16 chars
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

    lock = _get_profile_lock(user_id)
    async with lock:
        cur = db.cursor()
        try:
            # Atualiza nick de forma segura (cursor por operação).
            # Conflito de UNIQUE deve cair no except e manter texto original.
            cur.execute("UPDATE users SET nick=%s WHERE user_id=%s", (nick_novo, user_id))
            db.commit()
        except Exception:
            db.rollback()
            await update.message.reply_html(
                "🚫 <b>Nick indisponível</b>\n\n"
                f"O nick <code>{nick_novo}</code> já está em uso.\n"
                "Tente outro 🙂"
            )
            return
        finally:
            try:
                cur.close()
            except Exception:
                pass

    await update.message.reply_html(
        "✅ <b>Nick definido!</b>\n\n"
        f"Agora seu nick é: <code>{nick_novo}</code>"
    )


# ------------------------------
# /nivel
# ------------------------------
async def nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    ok = await anti_spam(update.effective_user.id, key="cmd:/nivel", window=3)
    if not ok:
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


# ------------------------------
# /perfil
# CRÍTICO: havia 2 defs. Agora só existe UMA.
# ------------------------------
async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    ok = await anti_spam(update.effective_user.id, key="cmd:/perfil", window=3)
    if not ok:
        return

    await registrar_comando(update)

    viewer_id = update.effective_user.id
    ensure_user_row(viewer_id, update.effective_user.first_name)

    # 1) decidir qual perfil mostrar
    if context.args:
        alvo_nick = context.args[0].strip()
        try:
            alvo_row = get_user_by_nick(alvo_nick)
        except Exception:
            alvo_row = None

        if not alvo_row:
            await update.message.reply_html(
                "❌ <b>Usuário não encontrado</b>\n\n"
                "Verifique se o nick está correto.\n"
                "📌 Exemplo: <code>/perfil bredesozail</code>"
            )
            return
    else:
        alvo_row = get_user_row(viewer_id)

    if not alvo_row:
        await update.message.reply_text("❌ Não consegui carregar o perfil agora.")
        return

    # 2) dados do alvo
    user_id = int(alvo_row["user_id"])
    nick = alvo_row.get("nick") or "User"

    fav_name = alvo_row.get("fav_name")
    fav_image = alvo_row.get("fav_image")
    private_on = bool(alvo_row.get("private_profile"))

    # título (admin/user)
    titulo = "👤 | <i>Admin</i>" if is_admin(user_id) else "👤 | <i>User</i>"

    # prioridade de foto: admin_photo persistente > fav_image
    foto = None
    try:
        from database import get_admin_photo_db
        foto = get_admin_photo_db(user_id) or fav_image
    except Exception:
        foto = fav_image

    # 3) perfil privado
    if private_on:
        texto = (
            "🎴 <b>PERFIL DO USUÁRIO</b>\n\n"
            f"{titulo}: <b>{nick}</b>\n\n"
            "🔐 | <b>Private Profile!</b>\n\n"
            "❤️ <b>Favorite:</b>\n"
        )

        if fav_name:
            texto += f"🧧 <b>{fav_name}</b> ✨"
        else:
            texto += "— Nenhum favorito"

        if foto:
            await update.message.reply_photo(photo=foto, caption=texto, parse_mode="HTML")
        else:
            await update.message.reply_html(texto)
        return

    # 4) perfil público
    total_colecao = count_collection(user_id)
    coins = int(alvo_row.get("coins") or 0)
    level = int(alvo_row.get("level") or 1)

    texto = (
        "🎴 <b>PERFIL DO USUÁRIO</b>\n\n"
        f"{titulo}: <b>{nick}</b>\n\n"
        f"📚 | <i>Coleção</i>: <b>{total_colecao}</b>\n"
        f"🪙 | <i>Coins</i>: <b>{coins}</b>\n"
        f"⭐ | <i>Nível</i>: <b>{level}</b>\n\n"
        "❤️ <i>Favorito</i>:\n"
    )

    if fav_name:
        texto += f"🧧 <b>{fav_name}</b> ✨"
    else:
        texto += "— Nenhum favorito"

    if foto:
        await update.message.reply_photo(photo=foto, caption=texto, parse_mode="HTML")
    else:
        await update.message.reply_html(texto)


# ------------------------------
# /privado
# ------------------------------
async def privado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    ok = await anti_spam(update.effective_user.id, key="cmd:/privado", window=4)
    if not ok:
        return

    await registrar_comando(update)

    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

    if not context.args:
        await update.message.reply_html(
            "🔐 <b>PERFIL PRIVADO</b>\n\n"
            "Ative para esconder suas infos (os outros só veem “Private Profile” + favorito).\n\n"
            "✅ <b>Como usar:</b>\n"
            "<code>/privado on</code>\n"
            "<code>/privado off</code>"
        )
        return

    opt = context.args[0].lower().strip()
    if opt not in ("on", "off"):
        await update.message.reply_html("❌ Use <code>/privado on</code> ou <code>/privado off</code>.")
        return

    lock = _get_profile_lock(user_id)
    async with lock:
        try:
            set_private_profile(user_id, opt == "on")
        except Exception:
            # sem mudar texto, apenas não explode
            return

    if opt == "on":
        await update.message.reply_html("🔐 <b>Perfil privado ativado!</b>")
    else:
        await update.message.reply_html("🔓 <b>Perfil privado desativado!</b>")


# ------------------------------
# /favoritar
# ------------------------------
async def favoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    ok = await anti_spam(update.effective_user.id, key="cmd:/favoritar", window=4)
    if not ok:
        return

    await registrar_comando(update)

    if not context.args:
        await update.message.reply_html(
            "❤️ <b>Favoritar personagem</b>\n\n"
            "Use o ID do personagem que você já tem na coleção:\n"
            "<code>/favoritar 12345</code>"
        )
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_html(
            "❌ Use apenas o ID numérico.\n\n"
            "Exemplo:\n"
            "<code>/favoritar 12345</code>"
        )
        return

    user_id = update.effective_user.id
    char_id = int(context.args[0])

    ensure_user_row(user_id, update.effective_user.first_name)
    row = get_user_row(user_id)

    if row["fav_name"]:
        await update.message.reply_html(
            "⚠️ Você já tem um personagem favorito.\n"
            "Use <code>/desfavoritar</code> para trocar."
        )
        return

    from database import get_collection_character, set_favorite_from_collection

    lock = _get_profile_lock(user_id)
    async with lock:
        # re-checa dentro do lock para evitar corrida (2 /favoritar simultâneos)
        row = get_user_row(user_id)
        if row["fav_name"]:
            await update.message.reply_html(
                "⚠️ Você já tem um personagem favorito.\n"
                "Use <code>/desfavoritar</code> para trocar."
            )
            return

        item = get_collection_character(user_id, char_id)
        if not item:
            await update.message.reply_html(
                "❌ <b>Você não tem esse personagem na sua coleção.</b>\n\n"
                "Só dá pra favoritar personagens que você já possui."
            )
            return

        try:
            set_favorite_from_collection(user_id, item["character_name"], item["image"])
        except Exception:
            return

    await update.message.reply_photo(
        photo=item["image"],
        caption=(
            "❤️ <b>PERSONAGEM FAVORITADO!</b>\n\n"
            f"🧧 <b>{item['character_name']}</b>\n\n"
            "🎴 Agora ele é a capa do seu perfil!"
        ),
        parse_mode="HTML"
    )


# ------------------------------
# /desfavoritar
# ------------------------------
async def desfavoritar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    ok = await anti_spam(update.effective_user.id, key="cmd:/desfavoritar", window=4)
    if not ok:
        return

    await registrar_comando(update)

    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)
    row = get_user_row(user_id)

    if not row["fav_name"]:
        await update.message.reply_html("💔 Você não tem personagem favorito.")
        return

    from database import clear_favorite

    lock = _get_profile_lock(user_id)
    async with lock:
        try:
            clear_favorite(user_id)
        except Exception:
            return

    await update.message.reply_html("💔 Personagem removido.")
# ==================================================
 # 12) /anime e /manga (busca no canal)
# ==================================================
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await checar_canal(update, context):
        return
    if not await anti_spam(user_id):
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
    if not await anti_spam(user_id):
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

    if not await anti_spam(user_id):
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

def _is_direct_image_url(url: str) -> bool:
    url = (url or "").strip().lower()
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    return url.endswith(".jpg") or url.endswith(".jpeg") or url.endswith(".png") or url.endswith(".webp")


# ==================================================
# 19) /cards + callback_cards  (AniList GraphQL) + filtro coleção
#    /cards Nome do Anime
#    /cards s Nome do Anime  -> só os que TEM
#    /cards f Nome do Anime  -> só os que FALTA
#    Também aceita Anime por ID:
#      /cards 15125
#      /cards s 15125
# ==================================================

import secrets
from typing import Optional, List, Dict, Tuple

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes

# usa seu ANILIST_API, checar_canal, registrar_comando, anti_spam, callback_dedupe, db
# e o seu ensure_user_row já existente no arquivo.

# ================================
# Infra: sessão HTTP reutilizável + cache + locks
# ================================
_ANILIST_TIMEOUT = aiohttp.ClientTimeout(total=15)

# cache curto para evitar bater no AniList em spam/concorrência
_anilist_cache: Dict[Tuple[str, str, int], Tuple[float, Optional[dict]]] = {}
ANILIST_CACHE_TTL = 20  # segundos

_anilist_locks: Dict[Tuple[str, str], asyncio.Lock] = {}
def _get_anilist_lock(kind: str, key: str) -> asyncio.Lock:
    k = (kind, key)
    lock = _anilist_locks.get(k)
    if lock is None:
        lock = asyncio.Lock()
        _anilist_locks[k] = lock
    return lock

# trava por token do /cards: impede 100 cliques simultâneos virar 100 refetch
_cards_token_locks: Dict[str, asyncio.Lock] = {}
def _get_cards_token_lock(token: str) -> asyncio.Lock:
    lock = _cards_token_locks.get(token)
    if lock is None:
        lock = asyncio.Lock()
        _cards_token_locks[token] = lock
    return lock

# TTL do menu (evita bot_data crescer infinito)
CARDS_CTX_TTL = 15 * 60  # 15 min

def _cards_ctx_cleanup(bot_data: dict):
    ctx = bot_data.get("cards_ctx")
    if not ctx:
        return
    now = time.time()
    # limpeza leve (não faz sempre pesado)
    if len(ctx) < 200:
        return
    for token, data in list(ctx.items()):
        created = float((data or {}).get("created_at") or 0.0)
        if created and now - created > CARDS_CTX_TTL:
            ctx.pop(token, None)

async def _anilist_post(session: aiohttp.ClientSession, query: str, variables: dict) -> Optional[dict]:
    try:
        async with session.post(ANILIST_API, json={"query": query, "variables": variables}) as resp:
            return await resp.json()
    except Exception:
        return None

# ================================
# DB helper: qty_map em batch (SEM cursor global)
# ================================
def _get_user_qty_map(user_id: int, char_ids: List[int]) -> Dict[int, int]:
    if not char_ids:
        return {}

    placeholders = ",".join(["%s"] * len(char_ids))
    sql = f"""
        SELECT character_id, quantity
        FROM user_collection
        WHERE user_id=%s AND character_id IN ({placeholders})
    """

    cur = db.cursor()
    try:
        cur.execute(sql, (user_id, *char_ids))
        rows = cur.fetchall() or []
    finally:
        try:
            cur.close()
        except Exception:
            pass

    out: Dict[int, int] = {}
    for r in rows:
        out[int(r["character_id"])] = int(r.get("quantity") or 0)
    return out

# ================================
# AniList fetch por nome / id (com cache + lock)
# ================================
async def buscar_cards_por_nome(anime_nome: str, page: int, session: aiohttp.ClientSession) -> Optional[dict]:
    query = """
    query ($search: String, $page: Int) {
      Page(page: 1, perPage: 1) {
        media(search: $search, type: ANIME) {
          id
          title { romaji }
          bannerImage
          coverImage { large }
          characters(page: $page, perPage: 15) {
            pageInfo { total currentPage lastPage }
            edges { node { id name { full } } }
          }
        }
      }
    }
    """
    search = anime_nome.strip()
    cache_key = ("q", search.lower(), int(page))
    now = time.time()

    cached = _anilist_cache.get(cache_key)
    if cached and (now - cached[0] <= ANILIST_CACHE_TTL):
        return cached[1]

    lock = _get_anilist_lock("q", search.lower())
    async with lock:
        cached = _anilist_cache.get(cache_key)
        if cached and (time.time() - cached[0] <= ANILIST_CACHE_TTL):
            return cached[1]

        data = await _anilist_post(session, query, {"search": search, "page": int(page)})
        media_list = (data.get("data", {}) or {}).get("Page", {}).get("media", []) if data else []
        media = media_list[0] if media_list else None

        if not media or not media.get("characters") or not media["characters"].get("edges"):
            _anilist_cache[cache_key] = (time.time(), None)
            return None

        _anilist_cache[cache_key] = (time.time(), media)
        return media

async def buscar_cards_por_id(anime_id: int, page: int, session: aiohttp.ClientSession) -> Optional[dict]:
    query = """
    query ($id: Int, $page: Int) {
      Media(id: $id, type: ANIME) {
        id
        title { romaji }
        bannerImage
        coverImage { large }
        characters(page: $page, perPage: 15) {
          pageInfo { total currentPage lastPage }
          edges { node { id name { full } } }
        }
      }
    }
    """
    aid = int(anime_id)
    cache_key = ("id", str(aid), int(page))
    now = time.time()

    cached = _anilist_cache.get(cache_key)
    if cached and (now - cached[0] <= ANILIST_CACHE_TTL):
        return cached[1]

    lock = _get_anilist_lock("id", str(aid))
    async with lock:
        cached = _anilist_cache.get(cache_key)
        if cached and (time.time() - cached[0] <= ANILIST_CACHE_TTL):
            return cached[1]

        data = await _anilist_post(session, query, {"id": aid, "page": int(page)})
        media = (data.get("data", {}) or {}).get("Media") if data else None

        if not media or not media.get("characters") or not media["characters"].get("edges"):
            _anilist_cache[cache_key] = (time.time(), None)
            return None

        _anilist_cache[cache_key] = (time.time(), media)
        return media

# ================================
# Formatação
# ================================
def _header_cards(media: dict, page: int) -> Tuple[str, int, int, str]:
    info = media["characters"]["pageInfo"]
    titulo = (media.get("title") or {}).get("romaji") or "Anime"
    total_chars = int(info.get("total") or 0)
    last_page = int(info.get("lastPage") or 1)
    anime_id = int(media.get("id") or 0)
    header = (
        f"📁 | <b>{titulo}</b>\n"
        f"ℹ️ | <b>{anime_id}</b>\n"
        f"🗂 | <b>{page}/{last_page}</b>\n\n"
    )
    return header, total_chars, last_page, titulo

def formatar_cards(media: dict, page: int, mode: str, qty_map: Dict[int, int]) -> Tuple[str, int]:
    header, _, last_page, _ = _header_cards(media, page)
    chars = media["characters"]["edges"]

    texto = header
    linhas = 0

    for c in chars:
        node = c.get("node") or {}
        cid = node.get("id")
        nome = ((node.get("name") or {}).get("full")) or "—"
        if cid is None:
            continue

        cid = int(cid)
        qty = int(qty_map.get(cid, 0))
        tem = qty > 0

        if mode == "s" and not tem:
            continue
        if mode == "f" and tem:
            continue

        if mode == "a":
            texto += f"🧧 <b>{cid}.</b> {nome}\n"
        elif mode == "s":
            texto += f"✅ <b>{cid}.</b> {nome} <i>({qty}x)</i>\n"
        else:
            texto += f"✖️ <b>{cid}.</b> {nome} <i>(0x)</i>\n"

        linhas += 1

    if linhas == 0:
        if mode == "s":
            texto += "⚠️ Você não tem nenhum personagem dessa obra.\n"
        elif mode == "f":
            texto += "✅ Você já tem todos os personagens dessa obra.\n"
        else:
            texto += "⚠️ Não encontrei personagens para mostrar.\n"

    return texto, linhas

def _build_keyboard(token: str, page: int, last: int) -> Optional[InlineKeyboardMarkup]:
    if last <= 1:
        return None

    botoes = []
    if page > 1:
        botoes.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"cards:{token}:{page-1}"))
    if page < last:
        botoes.append(InlineKeyboardButton("➡️ Próximo", callback_data=f"cards:{token}:{page+1}"))

    return InlineKeyboardMarkup([botoes]) if botoes else None

# ================================
# Anti-flood leve + permissão + expiração
# ================================
def _cards_can_click(context: ContextTypes.DEFAULT_TYPE, token: str, user_id: int) -> Tuple[bool, str]:
    data = context.bot_data.get("cards_ctx", {}).get(token)
    if not data:
        return False, "Esse menu expirou. Envie /cards de novo."

    created = float((data.get("created_at") or 0.0))
    if created and (time.time() - created > CARDS_CTX_TTL):
        # expira
        try:
            context.bot_data.get("cards_ctx", {}).pop(token, None)
        except Exception:
            pass
        return False, "Esse menu expirou. Envie /cards de novo."

    owner_id = int(data.get("owner_id") or 0)
    if user_id != owner_id:
        return False, "Apenas quem usou /cards pode mexer."

    flood = context.bot_data.setdefault("cards_flood", {})
    key = f"{user_id}:{token}"
    now = time.time()
    last = float(flood.get(key) or 0.0)
    if now - last < 1.2:
        return False, "Calma 🙂 (aguarde 1s)"
    flood[key] = now
    return True, ""

# ================================
# /cards
# ================================
async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    # rate limit por comando
    ok = await anti_spam(update.effective_user.id, key="cmd:/cards", window=3)
    if not ok:
        return

    await registrar_comando(update)

    if not context.args:
        await update.message.reply_html(
            "📁 <b>Cards de personagens</b>\n\n"
            "Use:\n"
            "<code>/cards Nome do Anime</code>\n"
            "<code>/cards s Nome do Anime</code>\n"
            "<code>/cards f Nome do Anime</code>\n\n"
            "Também aceita ID:\n"
            "<code>/cards 15125</code>"
        )
        return

    mode = "a"
    args = list(context.args)
    if args and args[0].lower() in ("s", "f"):
        mode = args[0].lower()
        args = args[1:]

    if not args:
        await update.message.reply_html("❌ Use: <code>/cards Nome do Anime</code>")
        return

    termo = " ".join(args).strip()
    page = 1
    user_id = update.effective_user.id

    # limpa ctx quando necessário
    _cards_ctx_cleanup(context.bot_data)

    # Reutiliza UMA sessão por request (ainda local), mas sem criar 2x/3x dentro das funções.
    async with aiohttp.ClientSession(timeout=_ANILIST_TIMEOUT) as session:
        if termo.isdigit():
            media = await buscar_cards_por_id(int(termo), page, session)
            kind = "id"
            query_value = str(int(termo))
        else:
            media = await buscar_cards_por_nome(termo, page, session)
            kind = "q"
            query_value = termo

    if not media:
        await update.message.reply_html(
            "❌ <b>Anime não encontrado</b>\n\n"
            "💡 Tente usar o nome mais conhecido.\n"
            "Exemplo: <code>One Piece</code>"
        )
        return

    char_ids = [int((e.get("node") or {}).get("id")) for e in media["characters"]["edges"] if (e.get("node") or {}).get("id")]
    qty_map = _get_user_qty_map(user_id, char_ids)

    texto, linhas = formatar_cards(media, page, mode, qty_map)

    _, _, last_page, _ = _header_cards(media, page)
    keyboard = None

    if linhas > 0:
        token = secrets.token_urlsafe(6)
        context.bot_data.setdefault("cards_ctx", {})[token] = {
            "owner_id": user_id,
            "mode": mode,
            "kind": kind,
            "query": query_value,
            "created_at": time.time(),
        }
        keyboard = _build_keyboard(token, page, last_page)

    foto = media.get("bannerImage") or (media.get("coverImage") or {}).get("large")

    if foto:
        await update.message.reply_photo(
            photo=foto,
            caption=texto,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_html(texto, reply_markup=keyboard)

# ================================
# callback_cards
# ================================
async def callback_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    # Deduplicação (duplo clique / retry do Telegram)
    if not callback_dedupe(q.id):
        try:
            await q.answer()
        except Exception:
            pass
        return

    # cards:TOKEN:PAGE
    try:
        _, token, page_s = q.data.split(":")
        page = int(page_s)
    except Exception:
        await q.answer("Erro ao carregar página.", show_alert=True)
        return

    ok, msg = _cards_can_click(context, token, q.from_user.id)
    if not ok:
        await q.answer(msg, show_alert=True)
        return

    # rate limit por callback (extra)
    if not await anti_spam(q.from_user.id, key="cb:cards", window=1):
        await q.answer("Calma 🙂 (aguarde 1s)", show_alert=True)
        return

    cfg = context.bot_data.get("cards_ctx", {}).get(token)
    if not cfg:
        await q.answer("Esse menu expirou. Envie /cards de novo.", show_alert=True)
        return

    # trava por token pra evitar 100 fetch simultâneos do mesmo menu
    lock = _get_cards_token_lock(token)
    async with lock:
        mode = cfg["mode"]
        kind = cfg["kind"]
        query_value = cfg["query"]
        owner_id = int(cfg["owner_id"])

        async with aiohttp.ClientSession(timeout=_ANILIST_TIMEOUT) as session:
            if kind == "id":
                media = await buscar_cards_por_id(int(query_value), page, session)
            else:
                media = await buscar_cards_por_nome(str(query_value), page, session)

        if not media:
            await q.answer("Não consegui carregar agora.", show_alert=True)
            return

        char_ids = [int((e.get("node") or {}).get("id")) for e in media["characters"]["edges"] if (e.get("node") or {}).get("id")]
        qty_map = _get_user_qty_map(owner_id, char_ids)

        texto, linhas = formatar_cards(media, page, mode, qty_map)

        _, _, last_page, _ = _header_cards(media, page)
        keyboard = _build_keyboard(token, page, last_page) if linhas > 0 else None

        try:
            if q.message and getattr(q.message, "photo", None):
                await q.message.edit_caption(caption=texto, parse_mode="HTML", reply_markup=keyboard)
            else:
                await q.message.edit_text(text=texto, parse_mode="HTML", reply_markup=keyboard)
            await q.answer()
        except Exception:
            await q.answer("Não consegui atualizar essa mensagem. Envie /cards de novo.", show_alert=True)
            return

# ==================================================
# HELPERS ANILIST — Character por ID ou Nome (com sessão local + timeout)
# ==================================================
async def _anilist_character_by_id(char_id: int) -> dict | None:
    query = """
    query ($id: Int) {
      Character(id: $id) {
        id
        name { full }
        image { large }
        media(perPage: 1, sort: POPULARITY_DESC) {
          nodes { title { romaji english native } }
        }
      }
    }
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            data = await _anilist_post(session, query, {"id": int(char_id)})
        if not data:
            return None

        ch = data.get("data", {}).get("Character")
        if not ch:
            return None

        nodes = (ch.get("media") or {}).get("nodes") or []
        obra = "—"
        if nodes:
            t = nodes[0].get("title") or {}
            obra = (t.get("romaji") or t.get("english") or t.get("native") or "—").strip() or "—"

        return {
            "id": int(ch["id"]),
            "name": (ch.get("name") or {}).get("full") or "—",
            "image": (ch.get("image") or {}).get("large"),
            "obra": obra,
        }
    except Exception:
        return None

async def _anilist_character_by_name(name: str) -> dict | None:
    query = """
    query ($search: String) {
      Page(page: 1, perPage: 1) {
        characters(search: $search) {
          id
          name { full }
          image { large }
          media(perPage: 1, sort: POPULARITY_DESC) {
            nodes { title { romaji english native } }
          }
        }
      }
    }
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            data = await _anilist_post(session, query, {"search": str(name)})
        if not data:
            return None

        chars = data.get("data", {}).get("Page", {}).get("characters") or []
        if not chars:
            return None

        ch = chars[0]
        nodes = (ch.get("media") or {}).get("nodes") or []
        obra = "—"
        if nodes:
            t = nodes[0].get("title") or {}
            obra = (t.get("romaji") or t.get("english") or t.get("native") or "—").strip() or "—"

        return {
            "id": int(ch["id"]),
            "name": (ch.get("name") or {}).get("full") or "—",
            "image": (ch.get("image") or {}).get("large"),
            "obra": obra,
        }
    except Exception:
        return None

def _extract_leading_id(text: str) -> int | None:
    text = (text or "").strip()
    m = re.match(r"^\s*(\d{1,10})\s*([.)-])?\s*(.*)$", text)
    if not m:
        return None
    if m.group(2) or (m.group(3) and m.group(3).strip()):
        return int(m.group(1))
    return None

# ==================================================
# /card ID ou NOME — GLOBAL (mostra mesmo sem ter na coleção)
# ==================================================
async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    ok = await anti_spam(update.effective_user.id, key="cmd:/card", window=3)
    if not ok:
        return

    await registrar_comando(update)

    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

    if not context.args:
        await update.message.reply_html(
            "👤 <b>Card</b>\n\n"
            "Use:\n"
            "<code>/card ID</code>\n"
            "<code>/card Nome do personagem</code>\n"
            "<code>/card ID. Nome</code>\n\n"
            "Exemplos:\n"
            "<code>/card 20</code>\n"
            "<code>/card Naruto</code>\n"
            "<code>/card 20. Naruto</code>"
        )
        return

    termo = " ".join(context.args).strip()

    leading_id = _extract_leading_id(termo)
    if leading_id is not None:
        info = await _anilist_character_by_id(leading_id)
    else:
        if termo.isdigit():
            info = await _anilist_character_by_id(int(termo))
        else:
            info = await _anilist_character_by_name(termo)

    if not info:
        await update.message.reply_html("❌ Não encontrei esse personagem no AniList.")
        return

    char_id = int(info["id"])

    from database import get_collection_character_full, get_global_character_image

    item = get_collection_character_full(user_id, char_id)
    tem = item is not None
    qty = int(item.get("quantity") or 0) if tem else 0
    mark = "✅" if tem else "✖️"

    foto = get_global_character_image(char_id) or info.get("image")

    caption = (
        "👤 | Card Cr.\n\n"
        f"🧧 <code>{char_id}</code>. <b>{info['name']}</b>\n"
        f"{info['obra']}\n\n"
        f"{mark} ({qty}x)"
    )

    reply_markup = None
    if tem:
        reply_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("❤️ Favoritar", callback_data=f"cardfav:{user_id}:{char_id}")
        ]])

    if foto:
        await update.message.reply_photo(photo=foto, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_html(caption, reply_markup=reply_markup)

# ==================================================
# CALLBACK: botão ❤️ Favoritar do /card
# ==================================================
_cardfav_locks: Dict[int, asyncio.Lock] = {}

def _get_cardfav_lock(user_id: int) -> asyncio.Lock:
    lock = _cardfav_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _cardfav_locks[user_id] = lock
    return lock

async def callback_cardfav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    # Dedup (duplo clique/retry)
    if not callback_dedupe(q.id):
        try:
            await q.answer()
        except Exception:
            pass
        return

    # cardfav:OWNER_ID:CHAR_ID
    try:
        _, owner_id, char_id = q.data.split(":")
        owner_id = int(owner_id)
        char_id = int(char_id)
    except Exception:
        try:
            await q.answer()
        except Exception:
            pass
        return

    if q.from_user.id != owner_id:
        await q.answer("Esse botão não é seu.", show_alert=True)
        return

    # rate limit por callback
    if not await anti_spam(q.from_user.id, key="cb:cardfav", window=2):
        await q.answer("Calma 🙂 (aguarde 1s)", show_alert=True)
        return

    from database import (
        get_collection_character_full,
        set_favorite_from_collection,
        get_global_character_image,
        get_user_row,
    )

    lock = _get_cardfav_lock(owner_id)
    async with lock:
        item = get_collection_character_full(owner_id, char_id)
        if not item:
            await q.answer("Você não tem esse personagem na coleção.", show_alert=True)
            return

        fav_img = get_global_character_image(char_id) or item.get("image")

        # Se já é o favorito atual, evita regravar e evita duplicar “marcação” no texto
        row = get_user_row(owner_id)
        if row and row.get("fav_name") == item.get("character_name") and (row.get("fav_image") == fav_img):
            await q.answer("Favorito definido!", show_alert=True)
            return

        try:
            set_favorite_from_collection(owner_id, item["character_name"], fav_img)
        except Exception:
            await q.answer("Não consegui salvar agora.", show_alert=True)
            return

    await q.answer("Favorito definido!", show_alert=True)

    # opcional: tenta “marcar” no texto que foi favoritado (sem duplicar)
    try:
        suffix = "\n\n❤️ <b>Definido como favorito!</b>"
        if q.message and q.message.caption:
            if "Definido como favorito!" not in q.message.caption:
                await q.edit_message_caption(
                    caption=q.message.caption + suffix,
                    parse_mode="HTML",
                    reply_markup=q.message.reply_markup
                )
        elif q.message and q.message.text:
            if "Definido como favorito!" not in q.message.text:
                await q.edit_message_text(
                    text=q.message.text + suffix,
                    parse_mode="HTML",
                    reply_markup=q.message.reply_markup
                )
    except Exception:
        pass

# ============================================
# HELPERS (já deve existir _is_direct_image_url)
# ============================================
def _parse_setfoto_lines(text: str):
    """
    Aceita linhas nos formatos:
      ID LINK
      ID - LINK
      ID | LINK
      ID: LINK
    Ignora linhas vazias.
    Retorna lista de (id:int, url:str) e lista de erros (str).
    """
    out = []
    errs = []
    if not text:
        return out, errs

    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue

        line2 = line.replace(" - ", " ").replace("-", " ")
        line2 = line2.replace(" | ", " ").replace("|", " ")
        line2 = line2.replace(": ", " ").replace(":", " ")
        parts = [p for p in line2.split() if p.strip()]

        if len(parts) < 2:
            errs.append(f"Linha {i}: formato inválido.")
            continue

        if not parts[0].isdigit():
            errs.append(f"Linha {i}: ID não é numérico.")
            continue

        cid = int(parts[0])
        url = parts[1].strip()

        if not _is_direct_image_url(url):
            errs.append(f"Linha {i}: link não é direto (.jpg/.png/.webp).")
            continue

        out.append((cid, url))

    return out, errs


# ==================================================
# ADMIN: /setfoto  (GLOBAL, lote opcional)
# - 1 por comando: /setfoto ID LINK
# - lote: /setfoto (respondendo msg com várias linhas "ID - LINK")
# ==================================================

_admin_ops_lock = asyncio.Lock()
_admin_user_locks: Dict[int, asyncio.Lock] = {}

def _get_admin_user_lock(user_id: int) -> asyncio.Lock:
    lock = _admin_user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _admin_user_locks[user_id] = lock
    return lock

async def setfoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_html("⛔ <b>Acesso negado</b>")
        return

    # Rate limit por admin
    ok = await anti_spam(user_id, key="cmd:/setfoto", window=3)
    if not ok:
        return

    from database import set_global_character_image

    # Trava por admin (evita 2 lotes simultâneos do mesmo admin)
    user_lock = _get_admin_user_lock(user_id)
    async with user_lock:
        # MODO 1: /setfoto ID LINK
        if len(context.args) == 2 and context.args[0].isdigit():
            char_id = int(context.args[0])
            url = context.args[1].strip()

            if not _is_direct_image_url(url):
                await update.message.reply_html(
                    "❌ Link inválido. Precisa terminar em <code>.jpg</code>, <code>.png</code> ou <code>.webp</code>."
                )
                return

            # Trava global curta (evita dois admins alterarem ao mesmo tempo em lote)
            async with _admin_ops_lock:
                try:
                    set_global_character_image(char_id, url, updated_by=user_id)
                except Exception:
                    # não muda textos; só evita crash
                    return

            await update.message.reply_html(
                "✅ <b>Foto global aplicada!</b>\n\n"
                f"🧧 Personagem: <code>{char_id}</code>\n"
                "🎴 Agora o <code>/card</code> vai usar essa foto pra todo mundo."
            )
            return

        # MODO 2: lote via reply
        if len(context.args) == 0 and update.message.reply_to_message:
            base_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
            items, errs = _parse_setfoto_lines(base_text)

            if not items and errs:
                await update.message.reply_html(
                    "❌ Não consegui ler nenhuma linha válida.\n\n"
                    "Use linhas assim:\n"
                    "<code>12345 - https://site.com/img.jpg</code>\n"
                    "<code>12345 https://site.com/img.png</code>\n\n"
                    "Erros:\n" + "\n".join(f"• {e}" for e in errs[:15])
                )
                return

            if not items:
                await update.message.reply_html(
                    "🛠️ <b>Setar foto (lote)</b>\n\n"
                    "Responda uma mensagem com linhas no formato:\n"
                    "<code>ID - LINK</code>\n\n"
                    "Exemplo:\n"
                    "<code>123 - https://site.com/a.jpg</code>\n"
                    "<code>456 - https://site.com/b.png</code>"
                )
                return

            # segurança: evita travar se mandar 500 linhas
            MAX_LOTE = 50
            items = items[:MAX_LOTE]

            ok_count = 0

            # Trava global enquanto aplica (garante consistência)
            async with _admin_ops_lock:
                for (cid, url) in items:
                    try:
                        set_global_character_image(cid, url, updated_by=user_id)
                        ok_count += 1
                    except Exception:
                        # ignora falha individual (mantém robusto)
                        continue

            msg = (
                "✅ <b>Lote aplicado!</b>\n\n"
                f"📌 Atualizados: <b>{ok_count}</b>\n"
            )
            if errs:
                msg += "\n⚠️ Linhas ignoradas:\n" + "\n".join(f"• {e}" for e in errs[:15])

            await update.message.reply_html(msg)
            return

        # ajuda
        await update.message.reply_html(
            "🛠️ <b>Admin — setar foto global</b>\n\n"
            "1) Um personagem:\n"
            "<code>/setfoto ID LINK</code>\n"
            "Ex:\n"
            "<code>/setfoto 12345 https://site.com/imagem.jpg</code>\n\n"
            "2) Vários de uma vez:\n"
            "Responda (reply) uma mensagem com várias linhas:\n"
            "<code>123 - https://site.com/a.jpg</code>\n"
            "<code>456 - https://site.com/b.png</code>\n"
            "e envie apenas:\n"
            "<code>/setfoto</code>"
        )


# ==================================================
# ADMIN: /delfoto ID  (remove foto global)
# ==================================================
async def delfoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_html("⛔ <b>Acesso negado</b>")
        return

    ok = await anti_spam(user_id, key="cmd:/delfoto", window=3)
    if not ok:
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_html(
            "🗑️ <b>Remover foto global</b>\n\n"
            "Use:\n"
            "<code>/delfoto ID</code>\n\n"
            "Ex:\n"
            "<code>/delfoto 12345</code>"
        )
        return

    char_id = int(context.args[0])

    from database import delete_global_character_image

    async with _admin_ops_lock:
        try:
            delete_global_character_image(char_id)
        except Exception:
            return

    await update.message.reply_html(
        "✅ <b>Foto global removida!</b>\n\n"
        f"🧧 Personagem: <code>{char_id}</code>\n"
        "🎴 O <code>/card</code> volta a usar a foto do AniList."
    )


# ==================================================
# ADMIN: /banchar ID [motivo]  (remove de cards/card/etc)
#       /unbanchar ID
# ==================================================
async def banchar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_html("⛔ <b>Acesso negado</b>")
        return

    ok = await anti_spam(user_id, key="cmd:/banchar", window=3)
    if not ok:
        return

    if len(context.args) < 1 or not context.args[0].isdigit():
        await update.message.reply_html(
            "🚫 <b>Banir personagem</b>\n\n"
            "Use:\n"
            "<code>/banchar ID motivo(opcional)</code>\n\n"
            "Ex:\n"
            "<code>/banchar 12345 foto errada</code>"
        )
        return

    char_id = int(context.args[0])
    motivo = " ".join(context.args[1:]).strip() or None

    from database import ban_character

    async with _admin_ops_lock:
        try:
            ban_character(char_id, reason=motivo, created_by=user_id)
        except Exception:
            return

    await update.message.reply_html(
        "✅ <b>Personagem removido do bot!</b>\n\n"
        f"🧧 ID: <code>{char_id}</code>\n"
        "📌 Ele não vai mais aparecer em <code>/cards</code>, <code>/card</code> e comandos relacionados."
    )


async def unbanchar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_html("⛔ <b>Acesso negado</b>")
        return

    ok = await anti_spam(user_id, key="cmd:/unbanchar", window=3)
    if not ok:
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_html(
            "✅ <b>Desbanir personagem</b>\n\n"
            "Use:\n"
            "<code>/unbanchar ID</code>"
        )
        return

    char_id = int(context.args[0])

    from database import unban_character

    async with _admin_ops_lock:
        try:
            unban_character(char_id)
        except Exception:
            return

    await update.message.reply_html(
        "✅ <b>Personagem voltou!</b>\n\n"
        f"🧧 ID: <code>{char_id}</code>"
    )

# ==================================================
# /dado + callbacks — SOMENTE DADO (01/04/07/10/13/16/19/22) cap 24
# ==================================================

SP_TZ = ZoneInfo("America/Sao_Paulo")

# 8 recargas/dia, acumulativo até 24 (3 dias)
DADO_MAX_BALANCE = 24
DADO_NEW_USER_START = 4
DADO_EXPIRE_SECONDS = 5 * 60

DADO_HOURS = [1, 4, 7, 10, 13, 16, 19, 22]  # horários SP

CMD_ANTIFLOOD_SECONDS = 3
BTN_ANTIFLOOD_SECONDS = 2

DADO_PICK_IMAGE = "https://photo.chelpbot.me/AgACAgEAAxkBZqAk02mfJAxu6F0SV9i2MqA5qQ6fDy3PAAKhC2sbjP74RFhnKn29pt05AQADAgADeQADOgQ/photo.jpg"
DADO_FALLBACK_IMAGE = "https://photo.chelpbot.me/AgACAgEAAxkBZqnFu2mfsGZK0p1QU7Az5i2pp9C07ahKAALQC2sbS__4RF78U7yIQqiiAQADAgADeQADOgQ/photo.jpg"

_REFRESH_LOCK = asyncio.Lock()

_dado_roll_locks: dict[int, asyncio.Lock] = {}
_user_dado_locks: dict[int, asyncio.Lock] = {}

def _get_roll_lock(roll_id: int) -> asyncio.Lock:
    lock = _dado_roll_locks.get(roll_id)
    if lock is None:
        lock = asyncio.Lock()
        _dado_roll_locks[roll_id] = lock
    return lock

def _get_user_dado_lock(user_id: int) -> asyncio.Lock:
    lock = _user_dado_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_dado_locks[user_id] = lock
    return lock

def _format_time_sp() -> str:
    return datetime.now(tz=SP_TZ).strftime("%H:%M")

def _now_dado_slot_sp(ts: float | None = None) -> int:
    """
    Slot do DADO baseado em SP: 01/04/07/10/13/16/19/22 (8 slots/dia)
    Retorna (dia*8 + idx), crescente.
    """
    if ts is None:
        ts = time.time()

    now_sp = datetime.fromtimestamp(ts, tz=SP_TZ)
    day_id = now_sp.date().toordinal()
    h = now_sp.hour
    m = now_sp.minute

    idx = -1
    for i, hh in enumerate(DADO_HOURS):
        if (h > hh) or (h == hh and m >= 0):
            idx = i

    if idx < 0:
        # antes de 01:00 -> conta como último slot do dia anterior
        return (day_id - 1) * 8 + 7

    return day_id * 8 + idx

def _refresh_user_dado_balance(user_id: int) -> int:
    """
    Atualiza saldo baseado nos slots 01/04/07/10/13/16/19/22, cap 24.
    IMPORTANTE: detecta slot antigo (4h epoch) e só reancora sem dar refill.
    """
    st = get_dado_state(user_id)
    if not st:
        return 0

    balance = int(st["b"])
    last_slot = int(st["s"])

    cur_slot = _now_dado_slot_sp()

    # 1) usuário novo / slot vazio: só ancora
    if last_slot < 0:
        set_dado_state(user_id, min(DADO_MAX_BALANCE, balance), cur_slot)
        return min(DADO_MAX_BALANCE, balance)

    # 2) MIGRAÇÃO: slot antigo (4h) tem ordem de grandeza bem menor que o novo (dia*8).
    #    Ex.: antigo ~ 120k | novo ~ milhões. Se for antigo, NÃO refill, só atualiza slot.
    if last_slot < 1_000_000:
        set_dado_state(user_id, min(DADO_MAX_BALANCE, balance), cur_slot)
        return min(DADO_MAX_BALANCE, balance)

    # 3) normal: calcula diff e adiciona
    diff = cur_slot - last_slot
    if diff <= 0:
        return min(DADO_MAX_BALANCE, balance)

    new_balance = min(DADO_MAX_BALANCE, balance + diff)
    set_dado_state(user_id, new_balance, cur_slot)
    return new_balance

def _consume_one_die(user_id: int) -> bool:
    st = get_dado_state(user_id)
    if not st:
        return False
    b = int(st["b"])
    s = int(st["s"])
    if b <= 0:
        return False
    set_dado_state(user_id, b - 1, s)
    return True

def _refund_one_die(user_id: int):
    st = get_dado_state(user_id)
    if not st:
        return
    b = int(st["b"])
    s = int(st["s"])
    set_dado_state(user_id, min(DADO_MAX_BALANCE, b + 1), s)

def _nice_group_block_text() -> str:
    return (
        "🎲 <b>DADO</b>\n\n"
        "Esse comando funciona <b>somente no privado</b> do bot.\n"
        "👉 Abra o bot no PV e use <code>/dado</code> por lá.\n\n"
        "✨ No PV você escolhe o anime e ganha um personagem!"
    )

def _nice_pick_text(dice_value: int, balance: int) -> str:
    return (
        "🎲 <b>DADO DA SORTE</b>\n\n"
        f"🔢 Resultado: <b>{dice_value}</b>\n"
        "🎴 Agora escolha um <b>anime</b> para sortear um personagem!\n\n"
        f"🎟️ Dados disponíveis: <b>{balance}</b>\n"
        "⏳ Você tem <b>5 minutos</b> para escolher."
    )

def _anime_buttons_for_roll(roll_id: int, options: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for op in options:
        title = op.get("title") or "Anime"
        aid = int(op.get("id") or 0)
        rows.append([InlineKeyboardButton(title, callback_data=f"dado_pick:{roll_id}:{aid}")])
    return InlineKeyboardMarkup(rows)

# ===== TOP CACHE (mantém seu cache do database.py) =====
async def _fetch_top500_anime_from_anilist() -> list[dict]:
    query = """
    query ($page: Int) {
      Page(page: $page, perPage: 50) {
        media(type: ANIME, sort: POPULARITY_DESC) {
          id
          title { romaji }
        }
      }
    }
    """
    items: list[dict] = []
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        rank = 1
        for page in range(1, 11):
            async with session.post(ANILIST_API, json={"query": query, "variables": {"page": page}}) as resp:
                data = await resp.json()
            media = data.get("data", {}).get("Page", {}).get("media", []) or []
            for m in media:
                anime_id = m.get("id")
                title = (m.get("title") or {}).get("romaji") or "Anime"
                if anime_id is None:
                    continue
                items.append({"anime_id": int(anime_id), "title": title, "rank": rank})
                rank += 1
    return items[:500]

async def _ensure_top_cache_fresh():
    async with _REFRESH_LOCK:
        last = int(top_cache_last_updated() or 0)
        now = int(time.time())
        if last != 0 and (now - last) < 24 * 3600:
            return
        items = await _fetch_top500_anime_from_anilist()
        if items:
            replace_top_anime_cache(items)

def _pick_random_animes(n: int) -> list[dict]:
    all_items = get_top_anime_list(500)
    if not all_items:
        return []
    n = max(1, min(int(n), len(all_items)))
    chosen = random.sample(all_items, n)
    return [{"id": int(x["anime_id"]), "title": x["title"]} for x in chosen]

# ===== Character cache + fallback (para parar de “devolver dado” toda hora) =====
_CHAR_POOL_CACHE: dict[int, dict] = {}  # anime_id -> {"exp":ts, "title":str, "cover":str|None, "chars":[...]}

def _cache_get_pool(anime_id: int) -> dict | None:
    it = _CHAR_POOL_CACHE.get(int(anime_id))
    if not it:
        return None
    if int(it.get("exp") or 0) < int(time.time()):
        _CHAR_POOL_CACHE.pop(int(anime_id), None)
        return None
    return it

def _cache_set_pool(anime_id: int, pool: dict, ttl_seconds: int = 6 * 3600):
    pool["exp"] = int(time.time()) + int(ttl_seconds)
    _CHAR_POOL_CACHE[int(anime_id)] = pool

async def _build_char_pool_for_anime(anime_id: int, max_pages: int = 4) -> dict | None:
    q = """
    query ($id: Int, $page: Int) {
      Media(id: $id, type: ANIME) {
        title { romaji }
        coverImage { large }
        characters(page: $page, perPage: 25) {
          pageInfo { lastPage }
          edges {
            node {
              id
              name { full }
              image { large medium }
            }
          }
        }
      }
    }
    """
    timeout = aiohttp.ClientTimeout(total=20)
    chars: list[dict] = []
    anime_title = "Obra"
    cover = None

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(ANILIST_API, json={"query": q, "variables": {"id": int(anime_id), "page": 1}}) as resp:
            data = await resp.json()

        media = data.get("data", {}).get("Media")
        if not media:
            return None

        anime_title = (media.get("title") or {}).get("romaji") or "Obra"
        cover = (media.get("coverImage") or {}).get("large") or None
        last_page = int((((media.get("characters") or {}).get("pageInfo")) or {}).get("lastPage") or 1)
        last_page = max(1, last_page)

        pages = {1}
        for _ in range(max(0, int(max_pages) - 1)):
            pages.add(random.randint(1, last_page))

        for page in pages:
            async with session.post(ANILIST_API, json={"query": q, "variables": {"id": int(anime_id), "page": int(page)}}) as r2:
                d2 = await r2.json()
            m2 = d2.get("data", {}).get("Media")
            if not m2:
                continue
            edges = (((m2.get("characters") or {}).get("edges")) or [])
            for e in edges:
                node = (e.get("node") or {})
                cid = node.get("id")
                name = ((node.get("name") or {}).get("full")) or None
                img_obj = node.get("image") or {}
                img = img_obj.get("large") or img_obj.get("medium") or None
                if cid and name:
                    chars.append({"id": int(cid), "name": name, "image": img})

    seen = set()
    uniq = []
    for c in chars:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        uniq.append(c)

    return {"title": anime_title, "cover": cover, "chars": uniq}

async def _get_random_character_from_anime(anime_id: int) -> dict | None:
    """
    Quase sempre retorna algo:
    - tenta personagem com foto
    - se não achar, usa capa do anime como imagem (não precisa devolver dado)
    """
    anime_id = int(anime_id)

    pool = _cache_get_pool(anime_id)
    if pool is None:
        pool = await _build_char_pool_for_anime(anime_id, max_pages=4)
        if not pool:
            return None
        _cache_set_pool(anime_id, pool, ttl_seconds=6 * 3600)

    chars = list(pool.get("chars") or [])
    if not chars:
        return None

    random.shuffle(chars)

    for c in chars[:120]:
        img = c.get("image")
        if isinstance(img, str) and img.startswith("http"):
            return {"id": int(c["id"]), "name": c["name"], "image": img, "anime_title": pool.get("title") or "Obra"}

    cover = pool.get("cover") or DADO_FALLBACK_IMAGE
    c0 = chars[0]
    return {"id": int(c0["id"]), "name": c0["name"], "image": cover, "anime_title": pool.get("title") or "Obra"}


# ==================================================
# /dado (PV only)
# ==================================================
async def dado_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat = update.effective_chat

    ok = await anti_spam(user_id, key="cmd:/dado", window=CMD_ANTIFLOOD_SECONDS)
    if not ok:
        return

    if chat.type != "private":
        await update.message.reply_html(_nice_group_block_text())
        return

    ensure_user_row(user_id, update.effective_user.first_name, new_user_dice=DADO_NEW_USER_START)

    user_lock = _get_user_dado_lock(user_id)
    async with user_lock:
        balance = _refresh_user_dado_balance(user_id)

        if balance <= 0:
            await update.message.reply_html(
                "🎲 <b>DADO</b>\n\n"
                "Você está sem dados agora.\n\n"
                "🕒 Os dados chegam nos horários:\n"
                "<b>01h, 04h, 07h, 10h, 13h, 16h, 19h, 22h</b> (BR)\n"
                "📦 Acumula até <b>24</b>.\n\n"
                f"⏱ Agora: <b>{_format_time_sp()}</b>"
            )
            return

        try:
            await _ensure_top_cache_fresh()
        except Exception:
            pass

        if not _consume_one_die(user_id):
            await update.message.reply_html("⚠️ Não consegui consumir seu dado agora. Tente novamente.")
            return

    dice_msg = await context.bot.send_dice(chat_id=chat.id, emoji="🎲")
    await asyncio.sleep(2)
    dice_value = int(dice_msg.dice.value or 1)

    options = _pick_random_animes(dice_value)
    if not options:
        _refund_one_die(user_id)
        await update.message.reply_html("❌ Não consegui carregar a lista de animes agora. Tente novamente.")
        return

    roll_id = create_dice_roll(user_id, dice_value, json.dumps(options, ensure_ascii=False))

    balance2 = _refresh_user_dado_balance(user_id)

    await update.message.reply_photo(
        photo=DADO_PICK_IMAGE,
        caption=_nice_pick_text(dice_value, balance2),
        parse_mode="HTML",
        reply_markup=_anime_buttons_for_roll(roll_id, options),
    )


# ==================================================
# Callback: escolher anime do dado
# ==================================================
async def callback_dado_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    if not callback_dedupe(q.id):
        try:
            await q.answer()
        except Exception:
            pass
        return

    user_id = q.from_user.id

    ok = await anti_spam(user_id, key="cb:dado_pick", window=BTN_ANTIFLOOD_SECONDS)
    if not ok:
        await q.answer("Calma 🙂", show_alert=False)
        return

    try:
        _, rid_s, anime_id_s = q.data.split(":")
        roll_id = int(rid_s)
        anime_id = int(anime_id_s)
    except Exception:
        await q.answer()
        return

    roll_lock = _get_roll_lock(roll_id)
    async with roll_lock:
        roll = get_dice_roll(roll_id)
        if not roll:
            await q.answer("Esse pedido não existe mais.", show_alert=True)
            return

        if int(roll["user_id"]) != int(user_id):
            await q.answer("Só quem rolou o dado pode escolher 🙂", show_alert=True)
            return

        status = str(roll.get("status") or "")
        created_at = int(roll.get("created_at") or 0)

        if status != "pending":
            await q.answer("Esse dado já foi usado.", show_alert=True)
            return

        if int(time.time()) - created_at > DADO_EXPIRE_SECONDS:
            set_dice_roll_status(roll_id, "expired")
            _refund_one_die(user_id)
            try:
                await q.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await q.answer("Expirou! Devolvi seu dado ✅", show_alert=True)
            return

        # valida opção
        try:
            options = json.loads(roll.get("options_json") or "[]")
        except Exception:
            options = []

        valid_ids = {int(o["id"]) for o in options if "id" in o}
        if anime_id not in valid_ids:
            await q.answer("Opção inválida.", show_alert=True)
            return

        # marca processing (pra não “perder” se API falhar)
        ok_db = try_set_dice_roll_status(roll_id, expected="pending", new_status="processing")
        if not ok_db:
            await q.answer("Esse dado já foi usado.", show_alert=True)
            return

        try:
            await q.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    # tenta anime escolhido + até mais 5 opções (sem gastar outro dado)
    chosen_ids = [anime_id]
    for o in options:
        try:
            oid = int(o.get("id"))
            if oid != anime_id:
                chosen_ids.append(oid)
        except Exception:
            pass
    chosen_ids = chosen_ids[:6]

    info = None
    for aid in chosen_ids:
        try:
            info = await _get_random_character_from_anime(aid)
        except Exception:
            info = None
        if info:
            break

    if not info:
        # falhou geral -> devolve o dado e volta pending
        try:
            set_dice_roll_status(roll_id, "pending")
        except Exception:
            pass
        _refund_one_die(user_id)
        await q.message.reply_html(
            "⚠️ <b>Não retornou personagens válidos nas opções sorteadas.</b>\n"
            "✅ Devolvi seu dado. Tenta novamente 🙂"
        )
        return

    set_dice_roll_status(roll_id, "resolved")

    char_id = int(info["id"])
    name = str(info["name"])
    image = str(info.get("image") or DADO_FALLBACK_IMAGE)
    anime_title = str(info.get("anime_title") or "Obra")

    from database import user_has_character, add_coin

    if user_has_character(user_id, char_id):
        add_coin(user_id, 1)
        resultado = "🪙 Personagem repetido → <b>+1 coin</b>"
    else:
        add_character_to_collection(user_id, char_id, name, image, anime_title=anime_title)
        resultado = "📦 <b>Adicionado à sua coleção!</b>"

    await q.message.reply_photo(
        photo=image,
        caption=(
            "🎁 <b>VOCÊ GANHOU!</b>\n\n"
            f"🧧 <code>{char_id}</code>. <b>{name}</b>\n"
            f"<i>{anime_title}</i>\n\n"
            f"{resultado}"
        ),
        parse_mode="HTML",
    )

# ==================================================
# COLECAO
# ==================================================
ITENS_POR_PAGINA = 15
COLECAO_BTN_ANTIFLOOD = 1.2  # segundos

def _colecao_can_click(owner_id: int, user_id: int) -> bool:
    return int(owner_id) == int(user_id)

def _colecao_keyboard(page: int, total_pages: int, owner_id: int):
    if total_pages <= 1:
        return None

    row = []
    if page > 1:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"colecao:{owner_id}:{page-1}"))
    row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        row.append(InlineKeyboardButton("➡️", callback_data=f"colecao:{owner_id}:{page+1}"))

    return InlineKeyboardMarkup([row])

def _format_colecao_text(nome_colecao: str, total: int, page: int, total_paginas: int, itens: list[tuple[int, str]]) -> str:
    texto = (
        f"📚 <b>{nome_colecao}</b>\n\n"
        f"📦 <i>Total:</i> <b>{total}</b>\n"
        f"📖 <i>Página:</i> <b>{page}/{total_paginas}</b>\n\n"
    )
    for cid, nomep in itens:
        texto += f"🧧 <code>{cid}</code>. {nomep}\n"
    return texto

async def enviar_colecao_by_owner(owner_id: int, first_name: str, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, *, edit: bool):
    ensure_user_row(owner_id, first_name)

    nome = get_collection_name(owner_id) or "Minha Coleção"
    itens, total, total_paginas = get_collection_page(owner_id, page, ITENS_POR_PAGINA)

    target_msg = update.callback_query.message if update.callback_query else update.message

    if not itens:
        if edit and update.callback_query:
            try:
                if target_msg.photo:
                    await target_msg.edit_caption(caption="📦 <b>Sua coleção está vazia.</b>", parse_mode="HTML", reply_markup=None)
                else:
                    await target_msg.edit_text("📦 <b>Sua coleção está vazia.</b>", parse_mode="HTML", reply_markup=None)
            except Exception:
                pass
        else:
            await target_msg.reply_html("📦 <b>Sua coleção está vazia.</b>")
        return

    texto = _format_colecao_text(nome, total, page, total_paginas, itens)
    kb = _colecao_keyboard(page, total_paginas, owner_id=owner_id)

    row = get_user_row(owner_id)
    fav_image = (row.get("fav_image") if row else None) or None

    if edit and update.callback_query:
        msg = update.callback_query.message
        try:
            if msg.photo:
                await msg.edit_caption(caption=texto, parse_mode="HTML", reply_markup=kb)
            else:
                await msg.edit_text(texto, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await update.callback_query.answer("Não consegui atualizar. Envie /colecao de novo.", show_alert=True)
        return

    if fav_image:
        try:
            await update.message.reply_photo(
                photo=fav_image,
                caption=texto,
                parse_mode="HTML",
                reply_markup=kb
            )
            return
        except Exception:
            pass

    await update.message.reply_text(texto, parse_mode="HTML", reply_markup=kb)


async def colecao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    if not update.effective_user or not update.message:
        return

    ok = await anti_spam(update.effective_user.id, key="cmd:/colecao", window=2)
    if not ok:
        return

    await registrar_comando(update)
    await enviar_colecao_by_owner(update.effective_user.id, update.effective_user.first_name, update, context, 1, edit=False)


async def callback_colecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    if q.data == "noop":
        await q.answer()
        return

    # dedupe e antiflood
    if not callback_dedupe(q.id):
        try:
            await q.answer()
        except Exception:
            pass
        return

    ok = await anti_spam(q.from_user.id, key="cb:colecao", window=COLECAO_BTN_ANTIFLOOD)
    if not ok:
        await q.answer("Calma 🙂", show_alert=False)
        return

    await q.answer()

    try:
        _, owner_s, page_s = q.data.split(":")
        owner_id = int(owner_s)
        page = int(page_s)
    except Exception:
        await q.answer("Erro na coleção.", show_alert=True)
        return

    if not _colecao_can_click(owner_id, q.from_user.id):
        await q.answer("Só quem abriu a coleção pode mexer 🙂", show_alert=True)
        return

    await enviar_colecao_by_owner(owner_id, q.from_user.first_name, update, context, page, edit=True)


async def nomecolecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    ok = await anti_spam(user_id, key="cmd:/nomecolecao", window=2)
    if not ok:
        return

    ensure_user_row(user_id, update.effective_user.first_name)

    if not context.args:
        await update.message.reply_text(
            "Use: `/nomecolecao Nome da Coleção`",
            parse_mode="Markdown"
        )
        return

    nome = " ".join(context.args).strip()
    set_collection_name(user_id, nome)
    await update.message.reply_text(f"📚 Coleção renomeada para *{nome}*", parse_mode="Markdown")


# ==================================================
# TROCA (MELHORADO) — bonito + anti-falhas + nomes + ofertas + imagem
# ==================================================

TRADE_BANNER = "https://photo.chelpbot.me/AgACAgEAAxkBZpLuKGmeMDP-GReON28AAZjZyLWbT8-JQAACLQxrG4z-8EQzVM7LZb9rOwEAAwIAA3kAAzoE/photo.jpg"

_trade_locks: Dict[int, asyncio.Lock] = {}
_trade_user_locks: Dict[int, asyncio.Lock] = {}

def _get_trade_lock(trade_id: int) -> asyncio.Lock:
    lock = _trade_locks.get(trade_id)
    if lock is None:
        lock = asyncio.Lock()
        _trade_locks[trade_id] = lock
    return lock

def _get_trade_user_lock(user_id: int) -> asyncio.Lock:
    lock = _trade_user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _trade_user_locks[user_id] = lock
    return lock

def _mention_html(user) -> str:
    name = (user.full_name or user.first_name or "User").strip()
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _get_char_label(user_id: int, char_id: int) -> str:
    """
    Pega o nome do personagem no DB (se tiver), senão mostra só o ID.
    """
    try:
        from database import get_collection_character_full
        item = get_collection_character_full(user_id, int(char_id))
        if item and item.get("character_name"):
            nm = str(item["character_name"]).strip()
            if nm:
                return f"<code>{int(char_id)}</code>. <b>{nm}</b>"
    except Exception:
        pass
    return f"<code>{int(char_id)}</code>"


async def trocar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    # antiflood por comando
    ok = await anti_spam(update.effective_user.id, key="cmd:/trocar", window=3)
    if not ok:
        return

    # precisa responder alguém
    if not update.message.reply_to_message:
        await update.message.reply_html(
            "❌ <b>Troca inválida</b>\n\n"
            "Você precisa <b>responder a mensagem</b> do usuário.\n\n"
            "Exemplo:\n"
            "<code>(responder a mensagem)</code>\n"
            "<code>/trocar 10 25</code>\n\n"
            "📌 <i>10 = seu personagem | 25 = personagem dele</i>"
        )
        return

    # validar args
    if len(context.args) != 2 or (not context.args[0].isdigit()) or (not context.args[1].isdigit()):
        await update.message.reply_html(
            "❌ <b>Uso correto</b>\n\n"
            "<code>/trocar SEU_ID ID_DELE</code>\n\n"
            "Exemplo:\n"
            "<code>/trocar 10 25</code>"
        )
        return

    from_user = update.effective_user
    to_user = update.message.reply_to_message.from_user

    # evita trocar com bot ou consigo mesmo
    if not to_user or getattr(to_user, "is_bot", False):
        await update.message.reply_html("❌ Você não pode fazer troca com bot.")
        return
    if int(to_user.id) == int(from_user.id):
        await update.message.reply_html("❌ Você não pode trocar com você mesmo.")
        return

    from_char = int(context.args[0])
    to_char = int(context.args[1])

    # checa posse (pré-checagem)
    if not user_has_character(from_user.id, from_char):
        await update.message.reply_html(
            "❌ <b>Troca cancelada</b>\n\n"
            "Esse personagem <b>não é seu</b>."
        )
        return
    if not user_has_character(to_user.id, to_char):
        await update.message.reply_html(
            "❌ <b>Troca cancelada</b>\n\n"
            "O outro usuário <b>não possui</b> esse personagem."
        )
        return

    # cria trade e captura trade_id de forma segura
    trade_id = None
    try:
        # IDEAL: create_trade deve retornar o trade_id (RETURNING).
        # Se ainda não retorna, tentamos um fallback mais seguro.
        maybe_id = create_trade(from_user.id, to_user.id, from_char, to_char)
        if isinstance(maybe_id, int):
            trade_id = maybe_id
        else:
            # fallback: pega a última pendente para o to_user, mas valida dados básicos depois no callback
            t = get_latest_pending_trade_for_to_user(to_user.id)
            if t:
                trade_id = int(t[0])
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        await update.message.reply_html("⚠️ Não consegui criar a troca agora. Tente novamente.")
        return

    a_name = await _get_char_label(from_user.id, from_char)
    b_name = await _get_char_label(to_user.id, to_char)

    accept_cb = f"trade_accept:{trade_id}" if trade_id else "trade_accept"
    reject_cb = f"trade_reject:{trade_id}" if trade_id else "trade_reject"

    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aceitar", callback_data=accept_cb),
        InlineKeyboardButton("❌ Recusar", callback_data=reject_cb),
    ]])

    texto = (
        "🔁 <b>PROPOSTA DE TROCA</b>\n\n"
        f"👤 <b>De:</b> {_mention_html(from_user)}\n"
        f"👤 <b>Para:</b> {_mention_html(to_user)}\n\n"
        "🎴 <b>Oferta</b>\n"
        f"➡️ {_mention_html(from_user)} oferece: {a_name}\n"
        f"⬅️ {_mention_html(to_user)} oferece: {b_name}\n\n"
        "⚠️ <i>Apenas o usuário marcado pode aceitar/recusar.</i>"
    )

    try:
        await update.message.reply_photo(
            photo=TRADE_BANNER,
            caption=texto,
            parse_mode="HTML",
            reply_markup=teclado
        )
    except Exception:
        await update.message.reply_html(texto, reply_markup=teclado)


# ==================================================
# CALLBACKS — agora aceitam trade_id e são anti-falhas
# ==================================================
async def callback_trade_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    # dedupe (duplo clique / retry)
    if not callback_dedupe(q.id):
        try:
            await q.answer()
        except Exception:
            pass
        return

    user_id = q.from_user.id

    # antiflood por callback
    ok = await anti_spam(user_id, key="cb:trade_accept", window=2)
    if not ok:
        await q.answer("Calma 🙂", show_alert=False)
        return

    trade_id = None
    try:
        parts = (q.data or "").split(":")
        if len(parts) == 2 and parts[1].isdigit():
            trade_id = int(parts[1])
    except Exception:
        trade_id = None

    # trava por usuário (anti spam) e por trade_id (anti corrida)
    user_lock = _get_trade_user_lock(user_id)
    async with user_lock:
        trade = None
        if trade_id:
            try:
                from database import get_trade_by_id
                trade = get_trade_by_id(trade_id)
            except Exception:
                trade = None

        if trade:
            try:
                trade_id = int(trade["trade_id"])
                from_user_id = int(trade["from_user"])
                to_user_id = int(trade["to_user"])
                from_char = int(trade["from_character_id"])
                to_char = int(trade["to_character_id"])
            except Exception:
                await q.answer("Erro ao ler a troca.", show_alert=True)
                return

            if int(to_user_id) != int(user_id):
                await q.answer("Essa troca não é para você.", show_alert=True)
                return
        else:
            # fallback MUITO mais restrito: só se não tiver trade_id ou não conseguir buscar
            t = get_latest_pending_trade_for_to_user(user_id)
            if not t:
                await q.answer("Nenhuma troca pendente.", show_alert=True)
                return
            trade_id, from_user_id, from_char, to_char = t

        trade_lock = _get_trade_lock(int(trade_id)) if trade_id else asyncio.Lock()
        async with trade_lock:
            # checa posse de novo
            if (not user_has_character(int(from_user_id), int(from_char))) or (not user_has_character(int(user_id), int(to_char))):
                try:
                    mark_trade_status(int(trade_id), "falhou")
                except Exception:
                    pass
                try:
                    if q.message and q.message.caption:
                        await q.message.edit_caption(
                            caption=(q.message.caption or "") + "\n\n❌ <b>Troca falhou:</b> alguém não tem mais os personagens.",
                            parse_mode="HTML",
                            reply_markup=None
                        )
                    else:
                        await q.message.edit_text(
                            text=(q.message.text or "") + "\n\n❌ <b>Troca falhou:</b> alguém não tem mais os personagens.",
                            parse_mode="HTML",
                            reply_markup=None
                        )
                except Exception:
                    pass
                await q.answer()
                return

            # executa swap (ideal: transação atômica no DB)
            try:
                swap_trade_execute(int(trade_id), int(from_user_id), int(user_id), int(from_char), int(to_char))
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                await q.answer("⚠️ Não consegui concluir agora. Tente novamente.", show_alert=True)
                return

    # final
    try:
        if q.message and q.message.caption:
            await q.message.edit_caption(
                caption="✅ <b>Troca realizada com sucesso!</b>\n\n🎉 Boa! Os personagens foram trocados.",
                parse_mode="HTML",
                reply_markup=None
            )
        else:
            await q.message.edit_text(
                "✅ <b>Troca realizada com sucesso!</b>\n\n🎉 Boa! Os personagens foram trocados.",
                parse_mode="HTML",
                reply_markup=None
            )
    except Exception:
        pass

    await q.answer()


async def callback_trade_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    if not callback_dedupe(q.id):
        try:
            await q.answer()
        except Exception:
            pass
        return

    user_id = q.from_user.id

    ok = await anti_spam(user_id, key="cb:trade_reject", window=2)
    if not ok:
        await q.answer("Calma 🙂", show_alert=False)
        return

    trade_id = None
    try:
        parts = (q.data or "").split(":")
        if len(parts) == 2 and parts[1].isdigit():
            trade_id = int(parts[1])
    except Exception:
        trade_id = None

    if not trade_id:
        t = get_latest_pending_trade_for_to_user(user_id)
        if not t:
            await q.answer("Nenhuma troca pendente.", show_alert=True)
            return
        trade_id = int(t[0])

    try:
        mark_trade_status(int(trade_id), "recusada")
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        await q.answer("⚠️ Não consegui recusar agora.", show_alert=True)
        return

    try:
        if q.message and q.message.caption:
            await q.message.edit_caption(
                caption="❌ <b>Troca recusada.</b>\n\nTudo certo 🙂",
                parse_mode="HTML",
                reply_markup=None
            )
        else:
            await q.message.edit_text(
                "❌ <b>Troca recusada.</b>\n\nTudo certo 🙂",
                parse_mode="HTML",
                reply_markup=None
            )
    except Exception:
        pass

    await q.answer()

# ==================================================
# LOJA (PV) — VENDER pro BOT (+1 coin) / COMPRAR GIRO (-2 coins -> +1 giro)
# ==================================================

SHOP_IMAGE = "https://photo.chelpbot.me/AgACAgQAAxkBZqZjcmmff-LPn4H7y3EsyO0G_rk8AAHTWgACBw5rG0eL9VAWyQkpU35BaAEAAwIAA3kAAzoE/photo.jpg"

SHOP_SELL_GAIN = 1
SHOP_GIRO_PRICE = 2
ITENS_POR_PAGINA_SHOP = 8
SHOP_BTN_FLOOD = 1.5

_shop_user_locks: Dict[int, asyncio.Lock] = {}

def _get_shop_lock(user_id: int) -> asyncio.Lock:
    lock = _shop_user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _shop_user_locks[user_id] = lock
    return lock

def _shop_only_private_text() -> str:
    return (
        "🛒 <b>LOJA</b>\n\n"
        "Use a loja <b>somente no privado</b> do bot.\n"
        "👉 Abra o bot no PV e use <code>/loja</code>."
    )

def _shop_main_text(user_name: str, coins: int, giros: int) -> str:
    return (
        "🛒 <b>LOJA BALTIGO</b>\n"
        f"👤 <b>{user_name}</b>\n\n"
        "Escolha uma opção 👇\n\n"
        f"🪙 <b>Coins:</b> <code>{coins}</code>\n"
        f"🎡 <b>Giros:</b> <code>{giros}</code>\n\n"
        "📌 <i>Venda personagens repetidos e compre giros!</i>"
    )

def _shop_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Vender personagem (+1 coin)", callback_data="shop:sell_menu:1")],
        [InlineKeyboardButton("🎡 Comprar GIRO (2 coins)", callback_data="shop:buy_giro")],
    ])

def _sell_menu_text(page: int) -> str:
    return (
        "📦 <b>VENDER PERSONAGEM (pro BOT)</b>\n\n"
        "Escolha um personagem da sua coleção.\n"
        f"✅ Ao vender, você recebe <b>+{SHOP_SELL_GAIN} coin</b>.\n"
        "⚠️ Vende <b>1 unidade</b> (se tiver quantity > 1, só diminui 1).\n\n"
        f"📄 Página: <b>{page}</b>"
    )

def _sell_kb(items: list[tuple[int, str]], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for cid, name in items:
        rows.append([InlineKeyboardButton(f"🧧 {cid}. {name}", callback_data=f"shop:sell_pick:{cid}:{page}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"shop:sell_menu:{page-1}"))
    nav.append(InlineKeyboardButton("🏠 Voltar", callback_data="shop:home"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"shop:sell_menu:{page+1}"))
    rows.append(nav)

    return InlineKeyboardMarkup(rows)

def _confirm_sell_text(char_id: int, name: str, qty: int) -> str:
    return (
        "✅ <b>CONFIRMAR VENDA</b>\n\n"
        f"🧧 <code>{char_id}</code>. <b>{name}</b>\n"
        f"📦 Você tem: <b>{qty}</b>\n\n"
        f"Você vai vender <b>1</b> unidade pro bot e ganhar <b>+{SHOP_SELL_GAIN} coin</b>.\n"
        "Confirmar?"
    )

def _confirm_sell_kb(char_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmar venda", callback_data=f"shop:sell_confirm:{char_id}:{page}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data=f"shop:sell_menu:{page}")],
    ])

async def loja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    chat = update.effective_chat
    if chat.type != "private":
        await update.message.reply_html(_shop_only_private_text())
        return

    user_id = update.effective_user.id

    ok = await anti_spam(user_id, key="cmd:/loja", window=2)
    if not ok:
        return

    ensure_user_row(user_id, update.effective_user.first_name)

    coins = get_user_coins(user_id)
    giros = get_extra_dado(user_id)

    await update.message.reply_photo(
        photo=SHOP_IMAGE,
        caption=_shop_main_text(update.effective_user.full_name, coins, giros),
        parse_mode="HTML",
        reply_markup=_shop_main_kb()
    )

# ---------------- Shop callback router ----------------
async def callback_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    # dedupe + antiflood
    if not callback_dedupe(q.id):
        try:
            await q.answer()
        except Exception:
            pass
        return

    user_id = q.from_user.id
    ok = await anti_spam(user_id, key="cb:shop", window=SHOP_BTN_FLOOD)
    if not ok:
        await q.answer("Calma 🙂", show_alert=False)
        return

    await q.answer()

    data = q.data or ""

    # trava por usuário (compra/venda não duplica)
    lock = _get_shop_lock(user_id)
    async with lock:
        # HOME
        if data == "shop:home":
            ensure_user_row(user_id, q.from_user.first_name)
            coins = get_user_coins(user_id)
            giros = get_extra_dado(user_id)
            await q.message.edit_caption(
                caption=_shop_main_text(q.from_user.full_name, coins, giros),
                parse_mode="HTML",
                reply_markup=_shop_main_kb()
            )
            return

        # BUY GIRO
        if data == "shop:buy_giro":
            ensure_user_row(user_id, q.from_user.first_name)

            ok_spend = try_spend_coins(user_id, SHOP_GIRO_PRICE)
            if not ok_spend:
                await q.answer("Você não tem coins suficientes.", show_alert=True)
                return

            add_extra_dado(user_id, 1)

            coins = get_user_coins(user_id)
            giros = get_extra_dado(user_id)

            await q.message.edit_caption(
                caption=(
                    "🎡 <b>GIRO COMPRADO!</b>\n\n"
                    "✅ Você recebeu <b>+1 giro</b>.\n\n"
                    f"🪙 <b>Coins:</b> <code>{coins}</code>\n"
                    f"🎡 <b>Giros:</b> <code>{giros}</code>\n\n"
                    "Quer mais alguma coisa? 👇"
                ),
                parse_mode="HTML",
                reply_markup=_shop_main_kb()
            )
            return

        # SELL MENU (paginação)
        if data.startswith("shop:sell_menu:"):
            try:
                page = int(data.split(":")[2])
            except Exception:
                return

            ensure_user_row(user_id, q.from_user.first_name)

            itens, total, total_pages = get_collection_page(user_id, page, ITENS_POR_PAGINA_SHOP)
            if not itens:
                await q.answer("Sua coleção está vazia.", show_alert=True)
                return

            await q.message.edit_caption(
                caption=_sell_menu_text(page),
                parse_mode="HTML",
                reply_markup=_sell_kb(itens, page, total_pages)
            )
            return

        # SELL PICK -> confirmação
        if data.startswith("shop:sell_pick:"):
            try:
                _, _, cid_s, page_s = data.split(":")
                char_id = int(cid_s)
                page = int(page_s)
            except Exception:
                return

            item = get_collection_character_full(user_id, char_id)
            if not item:
                await q.answer("Você não tem esse personagem.", show_alert=True)
                return

            name = item["character_name"]
            qty = int(item.get("quantity") or 1)

            await q.message.edit_caption(
                caption=_confirm_sell_text(char_id, name, qty),
                parse_mode="HTML",
                reply_markup=_confirm_sell_kb(char_id, page)
            )
            return

        # SELL CONFIRM
        if data.startswith("shop:sell_confirm:"):
            try:
                _, _, cid_s, page_s = data.split(":")
                char_id = int(cid_s)
                page = int(page_s)
            except Exception:
                return

            item = get_collection_character_full(user_id, char_id)
            if not item:
                await q.answer("Você não tem mais esse personagem.", show_alert=True)
                # volta pro menu da página
                try:
                    itens, total, total_pages = get_collection_page(user_id, page, ITENS_POR_PAGINA_SHOP)
                    if itens:
                        await q.message.edit_caption(
                            caption=_sell_menu_text(page),
                            parse_mode="HTML",
                            reply_markup=_sell_kb(itens, page, total_pages)
                        )
                except Exception:
                    pass
                return

            ok_remove = remove_one_from_collection(user_id, char_id)
            if not ok_remove:
                await q.answer("Não consegui vender agora. Tente de novo.", show_alert=True)
                return

            add_coin(user_id, SHOP_SELL_GAIN)

            coins = get_user_coins(user_id)
            giros = get_extra_dado(user_id)

            await q.message.edit_caption(
                caption=(
                    "✅ <b>VENDA CONCLUÍDA!</b>\n\n"
                    f"🧧 <code>{char_id}</code>. <b>{item['character_name']}</b>\n"
                    f"🪙 Você ganhou <b>+{SHOP_SELL_GAIN} coin</b>\n\n"
                    f"🪙 <b>Coins:</b> <code>{coins}</code>\n"
                    f"🎡 <b>Giros:</b> <code>{giros}</code>\n\n"
                    "Quer fazer mais alguma coisa? 👇"
                ),
                parse_mode="HTML",
                reply_markup=_shop_main_kb()
            )
            await q.answer("Vendido! ✅")
            return

# ==================================================
# /saldo + /daily + /trocas (PV only trocas)
# ==================================================

DAILY_COINS_MIN = 1
DAILY_COINS_MAX = 3
DAILY_GIRO_CHANCE = 0.20  # 20%

_SALDO_FLOOD: dict[int, float] = {}
_DAILY_FLOOD: dict[int, float] = {}
_TROCAS_FLOOD: dict[int, float] = {}

def _cmd_flood_ok(mem: dict[int, float], user_id: int, seconds: float) -> bool:
    now = time.time()
    last = mem.get(user_id, 0.0)
    if now - last < seconds:
        return False
    mem[user_id] = now
    return True


def _next_slot_dt_sp() -> datetime:
    """
    Próximo horário de recarga do dado:
    00/04/08/12/16/20 (SP_TZ)
    """
    now = datetime.now(tz=SP_TZ)
    hour = now.hour
    slots = [0, 4, 8, 12, 16, 20]

    nxt = None
    for s in slots:
        if hour < s:
            nxt = s
            break

    if nxt is None:
        # próximo dia 00:00
        return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    return now.replace(hour=nxt, minute=0, second=0, microsecond=0)


def _daily_day_start_ts_sp() -> int:
    """
    Timestamp do começo do dia no fuso SP_TZ.
    """
    now = datetime.now(tz=SP_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp())


async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id

    if not _cmd_flood_ok(_SALDO_FLOOD, user_id, 2.0):
        await update.message.reply_html("Calma 🙂")
        return

    ensure_user_row(user_id, update.effective_user.first_name)

    # atualiza saldo por slots (pra mostrar certo)
    try:
        balance = _refresh_user_dado_balance(user_id)
    except Exception:
        st = get_dado_state(user_id)
        balance = int(st["b"]) if st else 0

    coins = get_user_coins(user_id)
    giros = get_extra_dado(user_id)

    nxt = _next_slot_dt_sp()
    nxt_txt = nxt.strftime("%H:%M")

    await update.message.reply_html(
        "💳 <b>SALDO</b>\n\n"
        f"🪙 <b>Coins:</b> <code>{coins}</code>\n"
        f"🎟️ <b>Dados:</b> <code>{balance}</code>\n"
        f"🎡 <b>Giros:</b> <code>{giros}</code>\n\n"
        "🕒 Próxima recarga do dado:\n"
        f"<b>{nxt_txt}</b> (Brasil)"
    )


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id

    if not _cmd_flood_ok(_DAILY_FLOOD, user_id, 2.0):
        await update.message.reply_html("Calma 🙂")
        return

    ensure_user_row(user_id, update.effective_user.first_name)

    day_start_ts = _daily_day_start_ts_sp()

    try:
        reward = claim_daily_reward(
            user_id,
            day_start_ts,
            coins_min=DAILY_COINS_MIN,
            coins_max=DAILY_COINS_MAX,
            giro_chance=DAILY_GIRO_CHANCE,
        )
    except Exception as e:
        print("DAILY ERROR:", e)
        await update.message.reply_html("⚠️ Não consegui resgatar agora. Tente novamente.")
        return

    if not reward:
        await update.message.reply_html(
            "📦 <b>DAILY</b>\n\n"
            "Você já resgatou hoje.\n"
            "Volte amanhã 🙂"
        )
        return

    if reward["type"] == "giro":
        await update.message.reply_html(
            "📦 <b>DAILY</b>\n\n"
            "✅ Você recebeu: <b>+1 giro</b> 🎡"
        )
    else:
        await update.message.reply_html(
            "📦 <b>DAILY</b>\n\n"
            f"✅ Você recebeu: <b>+{int(reward['amount'])} coins</b> 🪙"
        )


def _trade_kb(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aceitar", callback_data=f"trade_accept:{trade_id}"),
        InlineKeyboardButton("❌ Recusar", callback_data=f"trade_reject:{trade_id}"),
    ]])


async def trocas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    chat = update.effective_chat
    if chat.type != "private":
        await update.message.reply_html(
            "🔁 <b>TROCAS</b>\n\n"
            "Esse comando funciona <b>somente no privado</b> do bot.\n"
            "👉 Abra o bot no PV e use <code>/trocas</code> por lá."
        )
        return

    user_id = update.effective_user.id

    if not _cmd_flood_ok(_TROCAS_FLOOD, user_id, 2.0):
        await update.message.reply_html("Calma 🙂")
        return

    ensure_user_row(user_id, update.effective_user.first_name)

    trades = list_pending_trades_for_user(user_id, limit=5)
    if not trades:
        await update.message.reply_html(
            "🔁 <b>TROCAS</b>\n\n"
            "Você não tem trocas pendentes."
        )
        return

    await update.message.reply_html(
        "🔁 <b>TROCAS</b>\n\n"
        "Aqui estão suas trocas pendentes:"
    )

    for t in trades:
        tid = int(t["trade_id"])
        from_user = int(t["from_user"])
        from_char = int(t["from_character_id"])
        to_char = int(t["to_character_id"])

        # usa seu helper existente (já no seu bot)
        a_name = await _get_char_label(from_user, from_char)
        b_name = await _get_char_label(user_id, to_char)

        await update.message.reply_html(
            "🔁 <b>TROCA PENDENTE</b>\n\n"
            f"🆔 <b>ID:</b> <code>{tid}</code>\n\n"
            f"➡️ O outro usuário oferece: {a_name}\n"
            f"⬅️ Você oferece: {b_name}\n\n"
            "⚠️ Apenas você pode aceitar/recusar.",
            reply_markup=_trade_kb(tid)
        )

# ==================================================
# /ranking (TOP 10) — Níveis / Coins / Coleção (com botões)
# ==================================================

RANKING_IMAGE = "https://photo.chelpbot.me/AgACAgEAAxkBZqlp8GmfqqNQyQV05efRn6slkZYc66uOAALOC2sbS__4RP55dhAgyc7mAQADAgADeQADOgQ/photo.jpg"
_RANK_BTN_LAST: dict[int, float] = {}

def _rank_btn_ok(user_id: int, seconds: float = 1.2) -> bool:
    now = time.time()
    last = _RANK_BTN_LAST.get(user_id, 0.0)
    if now - last < seconds:
        return False
    _RANK_BTN_LAST[user_id] = now
    return True


def _ranking_kb(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🪙 Moedas", callback_data=f"rank:coins:{owner_id}"),
            InlineKeyboardButton("⭐ Níveis", callback_data=f"rank:level:{owner_id}"),
        ],
        [
            InlineKeyboardButton("📚 Coleção", callback_data=f"rank:colecao:{owner_id}"),
        ],
    ])


def _format_rank_header(metric: str) -> str:
    if metric == "level":
        return "🏆 <b>RANKING — NÍVEIS (TOP 10)</b>\n\n"
    if metric == "coins":
        return "🏆 <b>RANKING — MOEDAS (TOP 10)</b>\n\n"
    return "🏆 <b>RANKING — COLEÇÃO (TOP 10)</b>\n\n"


def _safe_nick(row: dict) -> str:
    nick = (row.get("nick") or "User").strip()
    return nick if nick else "User"


def _render_ranking(metric: str) -> str:
    if metric == "level":
        rows = get_top_by_level(10)
        text = _format_rank_header(metric)
        if not rows:
            return text + "⚠️ Sem dados no momento."
        for i, r in enumerate(rows, start=1):
            nick = _safe_nick(r)
            level = int(r.get("level") or 1)
            cmds = int(r.get("commands") or 0)
            text += f"<b>{i}.</b> {nick} — ⭐<b>{level}</b>\n"
        return text

    if metric == "coins":
        rows = get_top_by_coins(10)
        text = _format_rank_header(metric)
        if not rows:
            return text + "⚠️ Sem dados no momento."
        for i, r in enumerate(rows, start=1):
            nick = _safe_nick(r)
            coins = int(r.get("coins") or 0)
            lvl = int(r.get("level") or 1)
            text += f"<b>{i}.</b> {nick} — 🪙 <b>{coins}</b>\n"
        return text

    # colecao
    rows = get_top_by_collection(10)
    text = _format_rank_header("colecao")
    if not rows:
        return text + "⚠️ Sem dados no momento."
    for i, r in enumerate(rows, start=1):
        nick = _safe_nick(r)
        total = int(r.get("total") or 0)
        text += f"<b>{i}.</b> {nick} — 📚 <b>{total}</b>\n"
    return text


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    owner_id = update.effective_user.id
    caption = (
        "🏆 <b>RANKING</b>\n\n"
        "Selecione qual ranking você quer ver 👇"
    )

    try:
        await update.message.reply_photo(
            photo=RANKING_IMAGE,
            caption=caption,
            parse_mode="HTML",
            reply_markup=_ranking_kb(owner_id),
        )
    except Exception:
        await update.message.reply_html(caption, reply_markup=_ranking_kb(owner_id))


async def callback_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    if not _rank_btn_ok(user_id, 1.2):
        await q.answer("Calma 🙂", show_alert=False)
        return

    # rank:metric:owner
    try:
        _, metric, owner_s = (q.data or "").split(":")
        owner_id = int(owner_s)
    except Exception:
        await q.answer("Erro no ranking.", show_alert=True)
        return

    # só quem abriu o ranking pode mexer (evita spam em grupo)
    if user_id != owner_id:
        await q.answer("Apenas quem abriu o ranking pode mexer.", show_alert=True)
        return

    if metric not in ("level", "coins", "colecao"):
        await q.answer("Ranking inválido.", show_alert=True)
        return

    texto = _render_ranking(metric)

    # edita caption se tiver foto; senão edita texto
    try:
        if q.message and q.message.photo:
            await q.message.edit_caption(
                caption=texto,
                parse_mode="HTML",
                reply_markup=_ranking_kb(owner_id),
            )
        else:
            await q.message.edit_text(
                text=texto,
                parse_mode="HTML",
                reply_markup=_ranking_kb(owner_id),
            )
    except Exception:
        await q.answer("Não consegui atualizar agora.", show_alert=True)

# ==================================================
# /stats e /conquistas (BONITO + IMAGEM + TITULOS + REWARD)
# ==================================================

CONQUISTAS_IMAGE = "https://photo.chelpbot.me/AgACAgEAAxkBZqnFu2mfsGZK0p1QU7Az5i2pp9C07ahKAALQC2sbS__4RF78U7yIQqiiAQADAgADeQADOgQ/photo.jpg"

def _bar(progress: float, width: int = 12) -> str:
    progress = max(0.0, min(1.0, float(progress)))
    filled = int(round(progress * width))
    return "█" * filled + "░" * (width - filled)

def _ach_title(unlocked_count: int) -> str:
    # títulos por quantidade de conquistas
    if unlocked_count >= 12:
        return "👑 <b>LENDA SUPREMA</b>"
    if unlocked_count >= 9:
        return "🏆 <b>CAMPEÃO DA BALTIGO</b>"
    if unlocked_count >= 6:
        return "⚔️ <b>VETERANO</b>"
    if unlocked_count >= 3:
        return "🔥 <b>GUERREIRO</b>"
    return "🌱 <b>INICIANTE</b>"

def _fmt_num(n: int) -> str:
    # só pra padronizar visual
    return f"<b>{int(n)}</b>"

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

    try:
        s = get_user_stats(user_id)
    except Exception:
        await update.message.reply_html("❌ Não consegui carregar suas stats agora.")
        return

    comandos = int(s["commands"])
    nivel_atual = int(s["level"])
    base = (nivel_atual - 1) * COMANDOS_POR_NIVEL
    prox = nivel_atual * COMANDOS_POR_NIVEL
    cur_in_level = max(comandos - base, 0)
    need = max(prox - comandos, 0)
    denom = max(prox - base, 1)
    pct = cur_in_level / denom

    # dados do dado e trocas (garantindo int)
    dice = s.get("dice") or {}
    trades = s.get("trades") or {}

    texto = (
        "📊 <b>STATS</b>\n\n"
        f"👤 <b>{s['nick']}</b>\n\n"
        "━━━━━━━━━━━━━━\n"
        f"⭐ <i>Nível</i>: {_fmt_num(nivel_atual)}\n"
        f"⌨️ <i>Comandos usados</i>: {_fmt_num(comandos)}\n"
        f"📈 <i>Progresso</i>: <code>{_bar(pct, 12)}</code> {_fmt_num(int(pct*100))}%\n"
        f"⏳ <i>Faltam</i>: {_fmt_num(need)} comandos\n"
        "━━━━━━━━━━━━━━\n"
        f"🪙 <i>Coins</i>: {_fmt_num(int(s['coins']))}\n"
        f"🎟️ <i>Dados</i>: {_fmt_num(int(s['dado_balance']))}\n"
        f"🎡 <i>Giros</i>: {_fmt_num(int(s['extra_dado']))}\n"
        "━━━━━━━━━━━━━━\n"
        f"📚 <i>Coleção (únicos)</i>: {_fmt_num(int(s['collection_unique']))}\n"
        f"📦 <i>Coleção (total)</i>: {_fmt_num(int(s['collection_total_qty']))}\n"
        "━━━━━━━━━━━━━━\n"
        "🎲 <b>Dado</b>\n"
        f"• Total: {_fmt_num(int(dice.get('total') or 0))}\n"
        f"• Resgates: {_fmt_num(int(dice.get('resolved') or 0))}\n"
        f"• Expirados: {_fmt_num(int(dice.get('expired') or 0))}\n"
        "━━━━━━━━━━━━━━\n"
        "🔁 <b>Trocas</b>\n"
        f"• Total: {_fmt_num(int(trades.get('total') or 0))}\n"
        f"• Aceitas: {_fmt_num(int(trades.get('aceita') or 0))}\n"
        f"• Pendentes: {_fmt_num(int(trades.get('pendente') or 0))}\n"
        f"• Recusadas: {_fmt_num(int(trades.get('recusada') or 0))}\n"
        f"• Falhou: {_fmt_num(int(trades.get('falhou') or 0))}\n"
    )

    await update.message.reply_html(texto)


async def conquistas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

    try:
        s = get_user_stats(user_id)
    except Exception:
        await update.message.reply_html("❌ Não consegui carregar suas conquistas agora.")
        return

    # ===== Defs fixas (NÃO MUDE as keys depois) =====
    defs: list[tuple[str, bool, str]] = []

    lvl = int(s["level"])
    defs += [
        ("lvl_5",   lvl >= 5,  "Nível 5"),
        ("lvl_10",  lvl >= 10, "Nível 10"),
        ("lvl_25",  lvl >= 25, "Nível 25"),
    ]

    cu = int(s["collection_unique"])
    defs += [
        ("col_10",  cu >= 10,  "10 personagens"),
        ("col_50",  cu >= 50,  "50 personagens"),
        ("col_100", cu >= 100, "100 personagens"),
    ]

    coins = int(s["coins"])
    defs += [
        ("coin_10",  coins >= 10,  "10 coins"),
        ("coin_100", coins >= 100, "100 coins"),
        ("coin_500", coins >= 500, "500 coins"),
    ]

    dice_total = int((s.get("dice") or {}).get("total") or 0)
    dice_res   = int((s.get("dice") or {}).get("resolved") or 0)
    defs += [
        ("dice_1",   dice_total >= 1, "Primeiro dado"),
        ("dice_10",  dice_res >= 10,  "10 ganhos no dado"),
        ("dice_50",  dice_res >= 50,  "50 ganhos no dado"),
    ]

    tr_ok = int((s.get("trades") or {}).get("aceita") or 0)
    defs += [
        ("trade_1",  tr_ok >= 1,  "Primeira troca aceita"),
        ("trade_5",  tr_ok >= 5,  "5 trocas aceitas"),
        ("trade_20", tr_ok >= 20, "20 trocas aceitas"),
    ]

    # ===== owned + recompensa =====
    try:
        owned = list_user_achievement_keys(user_id)
    except Exception:
        owned = set()

    newly_unlocked_keys = [k for (k, ok, _) in defs if ok and k not in owned]

    gained = 0
    if newly_unlocked_keys:
        try:
            gained = grant_achievements_and_reward(user_id, newly_unlocked_keys, reward_extra_dado_per=1)
        except Exception:
            gained = 0

    if gained > 0:
        owned.update(newly_unlocked_keys)

    # ===== contagem / título =====
    try:
        unlocked_count = count_user_achievements(user_id)
    except Exception:
        unlocked_count = sum(1 for (k, ok, _) in defs if ok and k in owned)

    total = len(defs)
    progress = unlocked_count / max(total, 1)

    title = _ach_title(unlocked_count)

    unlocked_lines = []
    locked_lines = []
    for key, ok, label in defs:
        is_unlocked = ok and (key in owned)
        if is_unlocked:
            unlocked_lines.append(f"✅ {label}")
        else:
            locked_lines.append(f"🔒 {label}")

    texto = (
        "🏅 <b>CONQUISTAS</b>\n"
        f"{title}\n\n"
        f"📌 Progresso: <code>{_bar(progress, 12)}</code> <b>{unlocked_count}/{total}</b>\n"
    )

    if gained > 0:
        texto += (
            "\n🎁 <b>CONQUISTAS NOVAS!</b>\n"
            f"🎡 Você ganhou <b>+{gained}</b> dado(s) extra.\n"
        )

    if unlocked_lines:
        texto += "\n✨ <b>Desbloqueadas</b>\n" + "\n".join(unlocked_lines) + "\n"

    texto += "\n🧩 <b>Em progresso</b>\n"
    texto += "\n".join(locked_lines) if locked_lines else "✅ Você já desbloqueou todas."

    # manda com imagem
    try:
        await update.message.reply_photo(
            photo=CONQUISTAS_IMAGE,
            caption=texto,
            parse_mode="HTML",
        )
    except Exception:
        await update.message.reply_html(texto)

# ==================================================
# GUIA INTERATIVO (PV): /ajuda /tutorial /comandos + suporte/adm
# ==================================================

import time
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes

AJUDA_IMAGE = "https://photo.chelpbot.me/AgACAgEAAxkBZqoU22mftY3fEpQzEXtLk7F2OeeWhbDfAALUC2sbS__4RPCOq-7wqnDbAQADAgADeQADOgQ/photo.jpg"

# 👉 Configure aqui:
SUPORTE_USER = "@QGSuporteBot"     # ex: "@BaltigoSuporte"  (pode deixar vazio "")
SUPORTE_CHAT_ID = None            # ex: -1001234567890 (canal/grupo de suporte) ou None
SUPORTE_TEXTO_EXTRA = ""          # texto opcional extra (pode deixar "")

AJUDA_BTN_FLOOD = 1.2
_AJUDA_BTN_LAST: dict[int, float] = {}

def _ajuda_btn_ok(user_id: int) -> bool:
    now = time.time()
    last = _AJUDA_BTN_LAST.get(user_id, 0.0)
    if now - last < AJUDA_BTN_FLOOD:
        return False
    _AJUDA_BTN_LAST[user_id] = now
    return True

def _pv_only_text() -> str:
    return (
        "📖 <b>GUIA / AJUDA</b>\n\n"
        "Esse menu funciona <b>somente no privado</b> do bot.\n"
        "👉 Abra o bot no PV e use <code>/ajuda</code>."
    )

def _ajuda_ctx_set(context: ContextTypes.DEFAULT_TYPE, msg_id: int, owner_id: int):
    context.bot_data.setdefault("ajuda_ctx", {})[str(msg_id)] = int(owner_id)

def _ajuda_ctx_owner(context: ContextTypes.DEFAULT_TYPE, msg_id: int) -> int:
    return int((context.bot_data.get("ajuda_ctx", {}) or {}).get(str(msg_id)) or 0)

def _ajuda_title() -> str:
    return (
        "📖 <b>GUIA INTERATIVO — BALTIGO</b>\n"
        "Aqui você aprende tudo rapidinho.\n\n"
        "🧭 Escolha uma categoria 👇"
    )

def _ajuda_menu_kb(is_admin_user: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🚀 Começar (Tutorial)", callback_data="ajuda:tutorial")],
        [InlineKeyboardButton("🎌 Animes (anime/infoanime/emalta/recomenda)", callback_data="ajuda:animes")],
        [InlineKeyboardButton("📚 Mangá (manga/infomanga)", callback_data="ajuda:manga")],
        [InlineKeyboardButton("🧧 Personagens (perso/cards/card)", callback_data="ajuda:personagens")],
        [InlineKeyboardButton("📦 Coleção (colecao/nomecolecao)", callback_data="ajuda:colecao")],
        [InlineKeyboardButton("👤 Perfil (perfil/nick/nivel/privado/favorito)", callback_data="ajuda:perfil")],
        [InlineKeyboardButton("🔁 Trocas (trocar/trocas)", callback_data="ajuda:trocas")],
        [InlineKeyboardButton("🛒 Loja & Economia (loja/saldo/daily/dado)", callback_data="ajuda:loja")],
        [InlineKeyboardButton("🏆 Rankings (ranking)", callback_data="ajuda:ranking")],
        [InlineKeyboardButton("📊 Stats & Conquistas (stats/conquistas)", callback_data="ajuda:stats")],
        [InlineKeyboardButton("📌 Lista completa", callback_data="ajuda:comandos")],
        [InlineKeyboardButton("📩 Falar com suporte/adm", callback_data="ajuda:suporte")],
    ]
    if is_admin_user:
        rows.append([InlineKeyboardButton("🛠️ Admin (setfoto/delfoto/banchar/unbanchar)", callback_data="ajuda:admin")])
    return InlineKeyboardMarkup(rows)

def _ajuda_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar ao menu", callback_data="ajuda:menu")]])

def _ajuda_page_text(page: str) -> str:
    # Texto “bem bonito”, com exemplos, e cobrindo todos os comandos do seu main()
    if page == "tutorial":
        return (
            "🚀 <b>TUTORIAL — COMO USAR O BOT</b>\n\n"
            "✅ <b>Passo 1 — Comece pelo perfil</b>\n"
            "• <code>/nick seu_nick</code> (1 palavra, sem espaço)\n"
            "• <code>/perfil</code> (ver sua capa e infos)\n\n"
            "🎲 <b>Passo 2 — Ganhar personagens</b>\n"
            "• <code>/dado</code> (PV do bot) → você escolhe um anime e ganha 1 personagem\n\n"
            "📦 <b>Passo 3 — Ver sua coleção</b>\n"
            "• <code>/colecao</code>\n"
            "• <code>/nomecolecao Nome</code>\n\n"
            "❤️ <b>Passo 4 — Defina seu favorito (capa do perfil)</b>\n"
            "• <code>/favoritar ID</code>\n"
            "• <code>/desfavoritar</code>\n\n"
            "🛒 <b>Passo 5 — Economia</b>\n"
            "• <code>/saldo</code> (coins + dados + giros)\n"
            "• <code>/daily</code> (recompensa 1x por dia)\n"
            "• <code>/loja</code> (PV) vender repetidos e comprar giros\n\n"
            "🔁 <b>Passo 6 — Trocas</b>\n"
            "• Responda o usuário e use: <code>/trocar SEU_ID ID_DELE</code>\n"
            "• <code>/trocas</code> (PV) ver pendências\n\n"
            "🏆 <b>Passo 7 — Competição</b>\n"
            "• <code>/ranking</code>\n"
            "• <code>/stats</code> e <code>/conquistas</code>\n\n"
            "💡 Dica: pra ver qualquer personagem do mundo: <code>/card Nome</code> ou <code>/card ID</code>"
        )

    if page == "animes":
        return (
            "🎌 <b>ANIMES — COMANDOS</b>\n\n"
            "• <code>/anime Nome</code>\n"
            "  → busca e mostra resultado com botões.\n\n"
            "• <code>/infoanime Nome</code>\n"
            "  → informações detalhadas.\n\n"
            "• <code>/emalta</code>\n"
            "  → lista do que está em alta.\n\n"
            "• <code>/recomenda</code>\n"
            "  → recomendações (você escolhe por botões).\n\n"
            "📌 Dica: quando aparecer botão de “info”, é só clicar."
        )

    if page == "manga":
        return (
            "📚 <b>MANGÁ — COMANDOS</b>\n\n"
            "• <code>/manga Nome</code>\n"
            "  → busca mangá.\n\n"
            "• <code>/infomanga Nome</code>\n"
            "  → mostra detalhes e botões.\n\n"
            "📌 Dica: se não achar, tente um nome mais curto."
        )

    if page == "personagens":
        return (
            "🧧 <b>PERSONAGENS — /perso, /cards, /card</b>\n\n"
            "• <code>/perso Nome</code>\n"
            "  → busca personagem e mostra info.\n\n"
            "• <code>/cards Nome do Anime</code>\n"
            "  → lista personagens da obra (paginado).\n\n"
            "Filtros do /cards:\n"
            "• <code>/cards s Nome</code> → só os que você TEM ✅\n"
            "• <code>/cards f Nome</code> → só os que FALTAM ✖️\n"
            "Também aceita ID:\n"
            "• <code>/cards 15125</code>\n\n"
            "• <code>/card ID</code> ou <code>/card Nome</code>\n"
            "  → mostra card único (✅ se você tem / ✖️ se não tem)\n\n"
            "Atalho:\n"
            "• <code>.cards Nome</code> (igual /cards)"
        )

    if page == "colecao":
        return (
            "📦 <b>COLEÇÃO — COMANDOS</b>\n\n"
            "• <code>/colecao</code>\n"
            "  → sua coleção com botões de página.\n\n"
            "• <code>/nomecolecao Nome da Coleção</code>\n"
            "  → renomeia o título da sua coleção.\n\n"
            "📌 Dica: seu favorito vira a “capa” quando abrir a coleção."
        )

    if page == "perfil":
        return (
            "👤 <b>PERFIL / NÍVEL / PRIVACIDADE / FAVORITO</b>\n\n"
            "• <code>/perfil</code>\n"
            "  → mostra seu perfil.\n\n"
            "• <code>/perfil nick</code>\n"
            "  → ver perfil de outra pessoa.\n\n"
            "• <code>/nick seu_nick</code>\n"
            "  → define seu nick (único).\n\n"
            "• <code>/nivel</code>\n"
            "  → mostra seu progresso por comandos.\n\n"
            "• <code>/privado on</code> / <code>/privado off</code>\n"
            "  → esconde/mostra infos do perfil.\n\n"
            "❤️ Favorito:\n"
            "• <code>/favoritar ID</code>\n"
            "• <code>/desfavoritar</code>"
        )

    if page == "trocas":
        return (
            "🔁 <b>TROCAS — COMO FUNCIONA</b>\n\n"
            "✅ <b>1) Propor troca</b>\n"
            "Responda a mensagem do usuário e use:\n"
            "<code>/trocar SEU_ID ID_DELE</code>\n\n"
            "✅ <b>2) Aceitar/Recusar</b>\n"
            "O outro usuário recebe botões ✅/❌.\n\n"
            "✅ <b>3) Trocas pendentes (PV)</b>\n"
            "• <code>/trocas</code> → mostra suas pendências.\n\n"
            "📌 Segurança:\n"
            "• Se alguém não tiver mais o personagem na hora, a troca falha."
        )

    if page == "loja":
        return (
            "🛒 <b>LOJA & ECONOMIA</b>\n\n"
            "🎲 Dado (ganhar personagem)\n"
            "• <code>/dado</code> → <b>somente no PV</b>\n\n"
            "💰 Saldo\n"
            "• <code>/saldo</code> → coins + dados + giros + recarga\n\n"
            "🎁 Daily\n"
            "• <code>/daily</code> → resgate 1x por dia\n\n"
            "🛒 Loja (PV)\n"
            "• <code>/loja</code> → vender repetidos e comprar giros\n\n"
            "📌 Dica: “giro” = dado extra."
        )

    if page == "ranking":
        return (
            "🏆 <b>RANKING (TOP 10)</b>\n\n"
            "• <code>/ranking</code>\n"
            "  → abre um menu com botões:\n"
            "  ⭐ Top Nível\n"
            "  🪙 Top Coins\n"
            "  📚 Top Coleção\n\n"
            "📌 Dica: ranking deixa o bot competitivo e prende a galera 😈"
        )

    if page == "stats":
        return (
            "📊 <b>STATS / CONQUISTAS</b>\n\n"
            "• <code>/stats</code>\n"
            "  → mostra tudo: nível, comandos, coins, dados, giros, coleção, trocas.\n\n"
            "• <code>/conquistas</code>\n"
            "  → metas por nível/coleção/coins/dado/trocas.\n\n"
            "🎁 Recompensa:\n"
            "• A cada conquista nova: <b>+1 dado extra</b> ✅"
        )

    if page == "comandos":
        return (
            "📌 <b>LISTA COMPLETA DE COMANDOS</b>\n\n"
            "🎌 Animes:\n"
            "• <code>/anime</code> • <code>/infoanime</code> • <code>/emalta</code> • <code>/recomenda</code>\n\n"
            "📚 Mangá:\n"
            "• <code>/manga</code> • <code>/infomanga</code>\n\n"
            "🧧 Personagens:\n"
            "• <code>/perso</code> • <code>/cards</code> • <code>.cards</code> • <code>/card</code>\n\n"
            "📦 Coleção:\n"
            "• <code>/colecao</code> • <code>/nomecolecao</code>\n\n"
            "👤 Perfil:\n"
            "• <code>/perfil</code> • <code>/nick</code> • <code>/nivel</code> • <code>/privado</code>\n"
            "• <code>/favoritar</code> • <code>/desfavoritar</code>\n\n"
            "🔁 Trocas:\n"
            "• <code>/trocar</code> • <code>/trocas</code>\n\n"
            "🛒 Economia:\n"
            "• <code>/dado</code> • <code>/loja</code> • <code>/saldo</code> • <code>/daily</code>\n\n"
            "🏆 Competição:\n"
            "• <code>/ranking</code>\n\n"
            "📊 Progresso:\n"
            "• <code>/stats</code> • <code>/conquistas</code>\n\n"
            "🔑 Sistema:\n"
            "• <code>/start</code> • <code>/login</code> • <code>/pedido</code>"
        )

    if page == "suporte":
        txt = (
            "📩 <b>SUPORTE / ADM</b>\n\n"
            "✅ Formas de pedir ajuda:\n"
            "• Use <code>/pedido</code> e descreva seu problema.\n"
        )
        if SUPORTE_USER:
            txt += f"• Fale com: <b>{SUPORTE_USER}</b>\n"
        if SUPORTE_CHAT_ID:
            txt += "• Ou clique no botão abaixo para abrir o suporte.\n"
        if SUPORTE_TEXTO_EXTRA:
            txt += "\n" + SUPORTE_TEXTO_EXTRA.strip() + "\n"
        txt += "\n📌 Dica: mande print + explique o que você tentou."
        return txt

    if page == "admin":
        return (
            "🛠️ <b>COMANDOS ADMIN</b>\n\n"
            "📸 Foto global (pra todo mundo no /card):\n"
            "• <code>/setfoto ID LINK</code>\n"
            "• <code>/setfoto</code> (respondendo msg com várias linhas)\n"
            "• <code>/delfoto ID</code>\n\n"
            "🚫 Banir personagem (some do bot):\n"
            "• <code>/banchar ID motivo(opcional)</code>\n"
            "• <code>/unbanchar ID</code>"
        )

    return _ajuda_title()

def _suporte_kb() -> InlineKeyboardMarkup:
    # Se tiver um chat/canal, você pode colocar link t.me (manual) se quiser.
    # Aqui deixei só o “voltar” + (opcional) botão de user.
    rows = []
    if SUPORTE_USER:
        # Botão com URL para abrir chat do user (remove @)
        u = SUPORTE_USER.strip()
        if u.startswith("@"):
            u = u[1:]
        rows.append([InlineKeyboardButton("📩 Abrir suporte", url=f"https://t.me/{u}")])
    rows.append([InlineKeyboardButton("⬅️ Voltar ao menu", callback_data="ajuda:menu")])
    return InlineKeyboardMarkup(rows)

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # PV only
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_html(_pv_only_text())
        return

    if not await checar_canal(update, context):
        return
    await registrar_comando(update)

    user_id = update.effective_user.id
    ensure_user_row(user_id, update.effective_user.first_name)

    is_admin_user = False
    try:
        is_admin_user = bool(is_admin(user_id))
    except Exception:
        is_admin_user = False

    msg = await update.message.reply_photo(
        photo=AJUDA_IMAGE,
        caption=_ajuda_title(),
        parse_mode="HTML",
        reply_markup=_ajuda_menu_kb(is_admin_user=is_admin_user)
    )
    _ajuda_ctx_set(context, msg.message_id, user_id)

async def callback_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id

    if not _ajuda_btn_ok(user_id):
        await q.answer("Calma 🙂", show_alert=False)
        return

    await q.answer()

    if not q.message:
        return

    owner = _ajuda_ctx_owner(context, q.message.message_id)
    if owner and int(owner) != int(user_id):
        await q.answer("Esse menu não é seu 🙂", show_alert=True)
        return

    try:
        _, page = (q.data or "").split(":", 1)
    except Exception:
        return

    # recalcula menu com admin
    is_admin_user = False
    try:
        is_admin_user = bool(is_admin(user_id))
    except Exception:
        is_admin_user = False

    if page == "menu":
        try:
            if q.message.photo:
                await q.message.edit_caption(
                    caption=_ajuda_title(),
                    parse_mode="HTML",
                    reply_markup=_ajuda_menu_kb(is_admin_user=is_admin_user)
                )
            else:
                await q.message.edit_text(
                    text=_ajuda_title(),
                    parse_mode="HTML",
                    reply_markup=_ajuda_menu_kb(is_admin_user=is_admin_user)
                )
        except Exception:
            await q.answer("Não consegui atualizar. Envie /ajuda de novo.", show_alert=True)
        return

    texto = _ajuda_page_text(page)

    # suporte tem teclado próprio (com URL)
    if page == "suporte":
        kb = _suporte_kb()
    else:
        kb = _ajuda_back_kb()

    try:
        if q.message.photo:
            await q.message.edit_caption(caption=texto, parse_mode="HTML", reply_markup=kb)
        else:
            await q.message.edit_text(text=texto, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await q.answer("Não consegui atualizar. Envie /ajuda de novo.", show_alert=True)

# Atalhos (PV only)
async def tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_html(_pv_only_text())
        return
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)
    await update.message.reply_photo(
        photo=AJUDA_IMAGE,
        caption=_ajuda_page_text("tutorial"),
        parse_mode="HTML",
        reply_markup=_ajuda_back_kb()
    )

async def comandos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_html(_pv_only_text())
        return
    if not await checar_canal(update, context):
        return
    await registrar_comando(update)
    await update.message.reply_photo(
        photo=AJUDA_IMAGE,
        caption=_ajuda_page_text("comandos"),
        parse_mode="HTML",
        reply_markup=_ajuda_back_kb()
    )
        
# ==================================================
# 25) MAIN (handlers)
# ==================================================

async def _on_startup(app):
    # inicia DB e Telethon
    try:
        init_db()
    except Exception:
        # não muda texto de usuário; só evita crash
        pass

    try:
        await client.start()
    except Exception:
        # se Telethon falhar, o bot ainda pode rodar (comandos de busca vão falhar)
        pass


async def _on_shutdown(app):
    try:
        await client.disconnect()
    except Exception:
        pass


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Nunca vaza stacktrace pro usuário. Loga e segue.
    try:
        err = context.error
        print("❌ Erro:", repr(err))
    except Exception:
        pass


async def _cards_dot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Suporte a ".cards ..." em texto.
    Transforma em args e chama cards().
    """
    if not update.message or not update.message.text:
        return
    txt = update.message.text.strip()
    # ".cards" ou ".cards s One Piece"
    if not txt.lower().startswith(".cards"):
        return
    rest = txt[5:].strip()  # remove ".cards"
    if rest:
        context.args = rest.split()
    else:
        context.args = []
    await cards(update, context)


def main():
    init_db()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)  # melhora throughput em grupos/volume
        .build()
    )

    # lifecycle
    app.post_init = _on_startup
    app.post_shutdown = _on_shutdown

    # error handler global
    app.add_error_handler(_error_handler)

    # ===== HANDLERS =====
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(CommandHandler("infoanime", infoanime))

    app.add_handler(CommandHandler("dado", dado_command))
    app.add_handler(CallbackQueryHandler(callback_dado_pick, pattern=r"^dado_pick:"))
    app.add_handler(CommandHandler("colecao", colecao_command))
    app.add_handler(CallbackQueryHandler(callback_colecao, pattern=r"^colecao:"))
    app.add_handler(CommandHandler("nomecolecao", nomecolecao))

    app.add_handler(CommandHandler("infomanga", infomanga))
    app.add_handler(CallbackQueryHandler(callback_info_manga, pattern=r"^info_manga:"))

    app.add_handler(CommandHandler("perso", perso))
    app.add_handler(CommandHandler("recomenda", recomenda))
    app.add_handler(CallbackQueryHandler(callback_recomenda, pattern=r"^rec:"))

    app.add_handler(CommandHandler("emalta", emalta))
    app.add_handler(CallbackQueryHandler(callback_emalta, pattern=r"^emalta:"))

    app.add_handler(CallbackQueryHandler(callback_info_perso, pattern=r"^info_perso:"))
    app.add_handler(CallbackQueryHandler(callback_info_anime, pattern=r"^info_anime:"))

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

    # /cards + callback
    app.add_handler(CommandHandler("cards", cards))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^\s*\.cards(\s|$)"), _cards_dot_handler))
    app.add_handler(CallbackQueryHandler(callback_cards, pattern=r"^cards:"))

    # /card
    app.add_handler(CommandHandler("card", card))
    app.add_handler(CallbackQueryHandler(callback_cardfav, pattern=r"^cardfav:"))

    # admin global
    app.add_handler(CommandHandler("setfoto", setfoto))
    app.add_handler(CommandHandler("delfoto", delfoto))
    app.add_handler(CommandHandler("banchar", banchar))
    app.add_handler(CommandHandler("unbanchar", unbanchar))

    # troca (aceita com e sem :ID)
    app.add_handler(CommandHandler("trocar", trocar))
    app.add_handler(CallbackQueryHandler(callback_trade_accept, pattern=r"^trade_accept(?::\d+)?$"))
    app.add_handler(CallbackQueryHandler(callback_trade_reject, pattern=r"^trade_reject(?::\d+)?$"))

    # loja
    app.add_handler(CommandHandler("loja", loja))
    app.add_handler(CallbackQueryHandler(callback_shop, pattern=r"^shop:"))
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("trocas", trocas))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CallbackQueryHandler(callback_ranking, pattern=r"^rank:(level|coins|colecao):"))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("conquistas", conquistas))

    # guia interativo
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("tutorial", tutorial))
    app.add_handler(CommandHandler("comandos", comandos))
    app.add_handler(CallbackQueryHandler(callback_ajuda, pattern=r"^ajuda:"))

    print("✅ Bot rodando...")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,  # se quiser otimizar mais, trocamos por lista mínima
    )


if __name__ == "__main__":
    main()



















