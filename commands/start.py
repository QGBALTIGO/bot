from utils.miniapp_links import miniapp_url, miniapp_entrypoint
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from database import (
    create_or_get_user,
    get_user_status,
    mark_welcome_sent,
    reset_welcome_sent,
    set_user_referrer,
)
from utils.gatekeeper import TERMS_VERSION, check_required_channel_membership

# ====== CONFIG ======
BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZzNiyWmpfGqHBancNR9gbzHUCcN5FHTmAAKjC2sbzg9QRZjbm81ltK8VAQADAgADeQADOgQ/photo.jpg"

WELCOME_BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZzjh9mmp41BscIh8CXt94vL4xYJb_x4kAALKC2sbeI3gRIgS39Orz7ePAQADAgADeQADOgQ/photo.jpg"

BASE_URL = miniapp_entrypoint().removesuffix('/menu')
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado no Railway.")

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
    if tg_lang.startswith("pt"):
        return "pt"
    if tg_lang.startswith("es"):
        return "es"
    if tg_lang.startswith("en"):
        return "en"
    return "en"


def _referrer_from_args(args: list[str] | tuple[str, ...] | None) -> int:
    if not args:
        return 0
    raw = str(args[0] or "").strip().lower()
    if not raw.startswith("ref_"):
        return 0
    try:
        return int(raw.split("_", 1)[1])
    except (TypeError, ValueError):
        return 0


def _load_start_state(user_id: int, referrer_id: int) -> dict:
    """Load/create the user in a worker thread to keep Telegram responsive."""

    uid = int(user_id)
    create_or_get_user(uid)

    if referrer_id > 0 and referrer_id != uid:
        try:
            set_user_referrer(uid, referrer_id, ref_code=f"ref_{referrer_id}")
        except Exception:
            # Referral bookkeeping must never prevent /start.
            pass

    return dict(get_user_status(uid) or {})


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id if user else 0
    name = (user.first_name or "Navegante") if user else "Navegante"
    tg_lang = _map_tg_lang(user.language_code if user else None)

    if _is_group(update):
        texto = (
            "⚠️ <b>Acesso indisponível neste chat</b>\n\n"
            "O <b>Source Baltigo</b> funciona no <b>privado</b> para manter seu <b>perfil</b>, "
            "<b>coleção</b> e <b>progresso</b> protegidos.\n\n"
            "🎴 <b>Toque no botão abaixo para abrir o bot no privado:</b>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎴 Abrir Source Baltigo no privado", url=BOT_PRIVATE_URL)]
        ])
        if update.message:
            await update.message.reply_html(texto, reply_markup=kb)
        return

    if user_id <= 0:
        if update.message:
            await update.message.reply_text("❌ Não consegui identificar seu usuário.")
        return

    # O vínculo é write-once no banco: abrir outro link depois não troca quem
    # indicou o usuário e autoindicação é rejeitada pelo helper persistente.
    referrer_id = _referrer_from_args(getattr(context, "args", None))
    st = await asyncio.to_thread(_load_start_state, user_id, referrer_id)
    terms_ok = bool(st.get("terms_accepted")) and (st.get("terms_version") == TERMS_VERSION)
    terms_url = miniapp_url('terms', lang=tg_lang)

    if not terms_ok:
        await asyncio.to_thread(reset_welcome_sent, user_id)
        caption = (
            f"👋 Olá, <b>{name}</b>\n\n"
            "Antes de continuar sua jornada na <b>Source Baltigo</b> 🎴✨\n\n"
            "📜 Você precisa ler e aceitar nossos <b>Termos de Uso e Política de Privacidade</b>.\n"
            "Isso garante uma experiência <b>justa</b>, <b>segura</b> e <b>equilibrada</b> para todos.\n\n"
            "✅ Quando estiver pronto, toque no botão abaixo para ler e aceitar."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Ler e aceitar termos", web_app=WebAppInfo(url=terms_url))],
        ])
        if update.message:
            await update.message.reply_photo(
                photo=BANNER_URL,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
            )
        return

    if REQUIRED_CHANNEL:
        # Force a fresh check on /start so a user who just joined is recognized
        # immediately. Other commands use the short gatekeeper cache.
        ok = await check_required_channel_membership(
            context,
            user_id,
            force=True,
        )

        if not ok:
            await asyncio.to_thread(reset_welcome_sent, user_id)
            texto = (
                "📢 <b>Canal oficial obrigatório</b>\n\n"
                "Para usar o <b>Source Baltigo</b>, você precisa entrar no nosso canal oficial.\n"
                "Isso ajuda a manter a tripulação informada e o acesso organizado.\n\n"
                "✅ <b>Entre no canal</b> e depois volte aqui novamente."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Entrar no canal oficial", url=REQUIRED_CHANNEL_URL)],
                [InlineKeyboardButton("📜 Abrir termos novamente", web_app=WebAppInfo(url=terms_url))],
            ])
            if update.message:
                await update.message.reply_html(texto, reply_markup=kb)
            return

    from commands.collecting import start_feature
    if await start_feature(update, context, context.args[0] if context.args else ""):
        return

    welcome_sent = bool(st.get("welcome_sent"))

    if not welcome_sent:
        texto = (
            f"🏴‍☠️ <b>Bem-vindo, {name}!</b>\n\n"
            "<b>Source Baltigo</b>\n"
            "<i>O seu portal para o mundo dos animes.</i>\n\n"
            "Aqui você pode:\n"
            "• 🔎 Descobrir personagens\n"
            "• 📚 Explorar histórias\n"
            "• 🎬 Encontrar novos animes para assistir\n\n"
            "⚔️ <b>Entre para a tripulação</b> e comece sua jornada!"
        )
        await asyncio.to_thread(mark_welcome_sent, user_id)
    else:
        texto = (
            f"⚓ <b>Bem-vindo de volta, {name}!</b>\n\n"
            "<b>Source Baltigo</b>\n"
            "Sua jornada continua, escolha o próximo destino e siga explorando. ⚔️✨\n\n"
            "Se precisar, você pode abrir os <b>termos</b> novamente pelo botão abaixo."
        )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Adicionar ao grupo", url=ADD_TO_GROUP_URL)],
        [InlineKeyboardButton("🏴‍☠️ QG Baltigo", url=QG_URL)],
        [InlineKeyboardButton("📜 Termos e condições", web_app=WebAppInfo(url=terms_url))],
    ])

    if update.message:
        await update.message.reply_photo(
            photo=WELCOME_BANNER_URL,
            caption=texto,
            parse_mode="HTML",
            reply_markup=teclado,
        )
