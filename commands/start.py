import html
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from database import create_or_get_user, get_user_status, mark_welcome_sent, reset_welcome_sent
from identity_repository import sync_telegram_identity
from utils.gatekeeper import TERMS_VERSION
from utils.public_url import require_public_base_url

BANNER_URL = os.getenv(
    "TERMS_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzNiyWmpfGqHBancNR9gbzHUCcN5FHTmAAKjC2sbzg9QRZjbm81ltK8VAQADAgADeQADOgQ/photo.jpg",
).strip()
WELCOME_BANNER_URL = os.getenv(
    "WELCOME_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzjh9mmp41BscIh8CXt94vL4xYJb_x4kAALKC2sbeI3gRIgS39Orz7ePAQADAgADeQADOgQ/photo.jpg",
).strip()
BASE_URL = require_public_base_url()
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourceBaltigo").strip()
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/SourceBaltigo").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"
ADD_TO_GROUP_URL = f"https://t.me/{BOT_USERNAME}?startgroup=true"
QG_URL = os.getenv("QG_URL", "https://t.me/QG_BALTIGO").strip()


def _is_group(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))


def _map_tg_lang(tg_lang: str | None) -> str:
    tg_lang = (tg_lang or "").lower()
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
        [InlineKeyboardButton("🏴‍☠️ Abrir Baltigo", web_app=WebAppInfo(url=f"{BASE_URL}/hub#home"))],
        [
            InlineKeyboardButton("🎮 Jogar", web_app=WebAppInfo(url=f"{BASE_URL}/game")),
            InlineKeyboardButton("🎴 Coleção", web_app=WebAppInfo(url=f"{BASE_URL}/collection")),
        ],
        [
            InlineKeyboardButton("🔎 Explorar", web_app=WebAppInfo(url=f"{BASE_URL}/hub#explore")),
            InlineKeyboardButton("👥 Social", web_app=WebAppInfo(url=f"{BASE_URL}/hub#social")),
        ],
        [
            InlineKeyboardButton("✅ Missões", web_app=WebAppInfo(url=f"{BASE_URL}/hub#missions")),
            InlineKeyboardButton("👤 Perfil", web_app=WebAppInfo(url=f"{BASE_URL}/profile")),
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
    user_id = int(user.id) if user else 0
    safe_name = html.escape((user.first_name or "Navegante") if user else "Navegante", quote=False)
    tg_lang = _map_tg_lang(user.language_code if user else None)

    if _is_group(update):
        text = (
            "🏴‍☠️ <b>Source Baltigo</b>\n\n"
            "No grupo ficam <b>capturas, trocas e duelos</b>. Sua coleção, jogos, mensagens, "
            "watchlist, missões e configurações ficam na sua área privada."
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Abrir minha área", url=BOT_PRIVATE_URL)]])
        if message:
            await message.reply_html(text, reply_markup=keyboard)
        return

    if user_id <= 0:
        if message:
            await message.reply_text("❌ Não consegui identificar seu usuário.")
        return

    create_or_get_user(user_id)
    try:
        sync_telegram_identity(user_id, username=str(user.username or ""), full_name=str(user.full_name or ""))
    except Exception:
        pass
    status = get_user_status(user_id) or {}
    terms_ok = bool(status.get("terms_accepted")) and status.get("terms_version") == TERMS_VERSION
    terms_url = f"{BASE_URL}/terms?uid={user_id}&lang={tg_lang}"

    if not terms_ok:
        reset_welcome_sent(user_id)
        caption = (
            f"👋 Olá, <b>{safe_name}</b>\n\n"
            "Antes de abrir o <b>Baltigo</b>, leia os Termos de Uso e a Política de Privacidade.\n\n"
            "Depois do aceite, o Hub libera coleção, economia, jogos, social, favoritos e progressão."
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📜 Ler e aceitar termos", web_app=WebAppInfo(url=terms_url))]])
        if message:
            await message.reply_photo(photo=BANNER_URL, caption=caption, parse_mode="HTML", reply_markup=keyboard)
        return

    if REQUIRED_CHANNEL:
        try:
            member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
            channel_ok = _member_has_access(member)
        except Exception:
            channel_ok = False
        if not channel_ok:
            reset_welcome_sent(user_id)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Entrar no canal oficial", url=REQUIRED_CHANNEL_URL)],
                [InlineKeyboardButton("📜 Rever termos", web_app=WebAppInfo(url=terms_url))],
            ])
            if message:
                await message.reply_html("📢 <b>Canal oficial obrigatório</b>\n\nEntre no canal e volte ao <code>/start</code>.", reply_markup=keyboard)
            return

    if not bool(status.get("welcome_sent")):
        text = (
            f"🏴‍☠️ <b>Bem-vindo ao Baltigo, {safe_name}.</b>\n\n"
            "Agora tudo faz parte da mesma jornada:\n\n"
            "🔎 <b>Explore</b> animes, personagens, notícias e jogadores\n"
            "⭐ <b>Acompanhe</b> favoritos e watchlist\n"
            "🎴 <b>Colecione</b> personagens e complete álbuns\n"
            "🎮 <b>Jogue</b> Daily, Dado, Giro, Memória e Termo\n"
            "👥 <b>Socialize</b> com amigos, mensagens, trocas e capturas\n"
            "⚔️ <b>Compita</b> com XCards, duelos e rankings\n"
            "🏅 <b>Evolua</b> em missões, conquistas e títulos\n\n"
            "O Hub mostra o que está disponível e de onde continuar."
        )
        mark_welcome_sent(user_id)
    else:
        text = (
            f"⚓ <b>Bem-vindo de volta, {safe_name}.</b>\n\n"
            "Abra o Hub para ver Daily, recursos, missões, notificações e o próximo passo da sua jornada."
        )

    if message:
        await message.reply_photo(photo=WELCOME_BANNER_URL, caption=text, parse_mode="HTML", reply_markup=_main_keyboard(terms_url))
