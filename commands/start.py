import html
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from database import (
    create_or_get_user,
    get_user_status,
    mark_welcome_sent,
    reset_welcome_sent,
)
from utils.gatekeeper import TERMS_VERSION

BANNER_URL = os.getenv(
    "TERMS_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzNiyWmpfGqHBancNR9gbzHUCcN5FHTmAAKjC2sbzg9QRZjbm81ltK8VAQADAgADeQADOgQ/photo.jpg",
).strip()

WELCOME_BANNER_URL = os.getenv(
    "WELCOME_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzjh9mmp41BscIh8CXt94vL4xYJb_x4kAALKC2sbeI3gRIgS39Orz7ePAQADAgADeQADOgQ/photo.jpg",
).strip()

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado.")

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourceBaltigo").strip()
REQUIRED_CHANNEL_URL = os.getenv(
    "REQUIRED_CHANNEL_URL",
    "https://t.me/SourceBaltigo",
).strip()

BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"
ADD_TO_GROUP_URL = f"https://t.me/{BOT_USERNAME}?startgroup=true"
QG_URL = os.getenv("QG_URL", "https://t.me/QG_BALTIGO").strip()


def _is_group(update: Update) -> bool:
    return bool(
        update.effective_chat
        and update.effective_chat.type in ("group", "supergroup")
    )


def _map_tg_lang(tg_lang: str | None) -> str:
    tg_lang = (tg_lang or "").lower()
    if tg_lang.startswith("pt"):
        return "pt"
    if tg_lang.startswith("es"):
        return "es"
    if tg_lang.startswith("en"):
        return "en"
    return "pt"


def _member_has_access(member) -> bool:
    status = getattr(member, "status", "")
    if status in ("creator", "administrator", "member"):
        return True
    return status == "restricted" and bool(getattr(member, "is_member", False))


def _main_keyboard(terms_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎮 Game Center", web_app=WebAppInfo(url=f"{BASE_URL}/game")),
            InlineKeyboardButton("🎴 Minha coleção", web_app=WebAppInfo(url=f"{BASE_URL}/collection")),
        ],
        [
            InlineKeyboardButton("📚 Catálogo", web_app=WebAppInfo(url=f"{BASE_URL}/catalogo")),
            InlineKeyboardButton("📝 Pedidos", web_app=WebAppInfo(url=f"{BASE_URL}/pedido")),
        ],
        [InlineKeyboardButton("➕ Adicionar ao grupo", url=ADD_TO_GROUP_URL)],
        [
            InlineKeyboardButton("🏴‍☠️ QG Baltigo", url=QG_URL),
            InlineKeyboardButton("📜 Termos", web_app=WebAppInfo(url=terms_url)),
        ],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    user_id = user.id if user else 0
    safe_name = html.escape(
        (user.first_name or "Navegante") if user else "Navegante",
        quote=False,
    )
    tg_lang = _map_tg_lang(user.language_code if user else None)

    if _is_group(update):
        text = (
            "⚠️ <b>Abra a sua área no privado</b>\n\n"
            "Game Center, coleção e configurações usam recursos ligados à sua conta. "
            "No grupo ficam as experiências coletivas; sua área pessoal abre no privado."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎴 Abrir Source Baltigo no privado", url=BOT_PRIVATE_URL)]
        ])
        if message:
            await message.reply_html(text, reply_markup=keyboard)
        return

    if user_id <= 0:
        if message:
            await message.reply_text("❌ Não consegui identificar seu usuário.")
        return

    create_or_get_user(user_id)
    status = get_user_status(user_id) or {}
    terms_ok = bool(status.get("terms_accepted")) and (
        status.get("terms_version") == TERMS_VERSION
    )

    terms_url = f"{BASE_URL}/terms?uid={user_id}&lang={tg_lang}"

    if not terms_ok:
        reset_welcome_sent(user_id)
        caption = (
            f"👋 Olá, <b>{safe_name}</b>\n\n"
            "Antes de abrir sua conta na <b>Source Baltigo</b>, leia os Termos de Uso e a Política de Privacidade.\n\n"
            "Depois do aceite, sua jornada, recursos e coleção ficam disponíveis."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Ler e aceitar termos", web_app=WebAppInfo(url=terms_url))]
        ])
        if message:
            await message.reply_photo(
                photo=BANNER_URL,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        return

    if REQUIRED_CHANNEL:
        channel_ok = False
        try:
            member = await context.bot.get_chat_member(
                chat_id=REQUIRED_CHANNEL,
                user_id=user_id,
            )
            channel_ok = _member_has_access(member)
        except Exception:
            channel_ok = False

        if not channel_ok:
            reset_welcome_sent(user_id)
            text = (
                "📢 <b>Canal oficial obrigatório</b>\n\n"
                "Para usar a Source Baltigo, entre no canal oficial e depois volte ao /start."
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Entrar no canal oficial", url=REQUIRED_CHANNEL_URL)],
                [InlineKeyboardButton("📜 Abrir termos novamente", web_app=WebAppInfo(url=terms_url))],
            ])
            if message:
                await message.reply_html(text, reply_markup=keyboard)
            return

    welcome_sent = bool(status.get("welcome_sent"))

    if not welcome_sent:
        text = (
            f"🏴‍☠️ <b>Bem-vindo, {safe_name}!</b>\n\n"
            "A Source Baltigo está entrando na sua <b>V2</b>: os sistemas agora começam a conversar entre si.\n\n"
            "🎁 <b>Daily</b> → entrega coins, dados e giros reais\n"
            "🎲 <b>Dado</b> → descobre obras e entrega personagem\n"
            "🎡 <b>Giro</b> → usa giros e credita recompensas reais\n"
            "🎴 <b>Coleção</b> → reúne o que você conquistou\n"
            "⭐ <b>Nível</b> → acompanha seu progresso\n"
            "📚 <b>Catálogo</b> → explora animes, mangás e cards\n\n"
            "Use os atalhos abaixo ou os comandos /jogar, /daily, /dado, /giro e /colecao."
        )
        mark_welcome_sent(user_id)
    else:
        text = (
            f"⚓ <b>Bem-vindo de volta, {safe_name}!</b>\n\n"
            "Sua conta está pronta. Continue pelo <b>Game Center</b>, confira sua <b>coleção</b> "
            "ou explore o <b>catálogo</b>."
        )

    if message:
        await message.reply_photo(
            photo=WELCOME_BANNER_URL,
            caption=text,
            parse_mode="HTML",
            reply_markup=_main_keyboard(terms_url),
        )
