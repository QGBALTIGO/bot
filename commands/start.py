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
    return "en"


def _member_has_access(member) -> bool:
    status = getattr(member, "status", "")
    if status in ("creator", "administrator", "member"):
        return True
    return status == "restricted" and bool(getattr(member, "is_member", False))


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
            "⚠️ <b>Acesso indisponível neste chat</b>\n\n"
            "O <b>Source Baltigo</b> funciona no <b>privado</b> para manter seu <b>perfil</b>, "
            "<b>coleção</b> e <b>progresso</b> protegidos.\n\n"
            "🎴 <b>Toque no botão abaixo para abrir o bot no privado:</b>"
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
            "Antes de continuar sua jornada na <b>Source Baltigo</b> 🎴✨\n\n"
            "📜 Você precisa ler e aceitar nossos <b>Termos de Uso e Política de Privacidade</b>.\n"
            "Isso garante uma experiência <b>justa</b>, <b>segura</b> e <b>equilibrada</b> para todos.\n\n"
            "✅ Quando estiver pronto, toque no botão abaixo para ler e aceitar."
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
                "Para usar o <b>Source Baltigo</b>, você precisa entrar no nosso canal oficial.\n"
                "Isso ajuda a manter a tripulação informada e o acesso organizado.\n\n"
                "✅ <b>Entre no canal</b> e depois volte aqui novamente."
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
            "<b>Source Baltigo</b>\n"
            "<i>O seu portal para o mundo dos animes.</i>\n\n"
            "Aqui você pode:\n"
            "• 🔎 Descobrir personagens\n"
            "• 📚 Explorar histórias\n"
            "• 🎬 Encontrar novos animes para assistir\n\n"
            "⚔️ <b>Entre para a tripulação</b> e comece sua jornada!"
        )
        mark_welcome_sent(user_id)
    else:
        text = (
            f"⚓ <b>Bem-vindo de volta, {safe_name}!</b>\n\n"
            "<b>Source Baltigo</b>\n"
            "Sua jornada continua, escolha o próximo destino e siga explorando. ⚔️✨\n\n"
            "Se precisar, você pode abrir os <b>termos</b> novamente pelo botão abaixo."
        )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Adicionar ao grupo", url=ADD_TO_GROUP_URL)],
        [InlineKeyboardButton("🏴‍☠️ QG Baltigo", url=QG_URL)],
        [InlineKeyboardButton("📜 Termos e condições", web_app=WebAppInfo(url=terms_url))],
    ])

    if message:
        await message.reply_photo(
            photo=WELCOME_BANNER_URL,
            caption=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
