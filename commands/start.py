import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from database import create_or_get_user, get_user_status, mark_welcome_sent, reset_welcome_sent
from utils.gatekeeper import TERMS_VERSION

BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZzNiyWmpfGqHBancNR9gbzHUCcN5FHTmAAKjC2sbzg9QRZjbm81ltK8VAQADAgADeQADOgQ/photo.jpg"

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado no Railway.")

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()  # @canal ou -100...

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name or "Navegante"
    tg_lang = _map_tg_lang(update.effective_user.language_code)

    # /start em grupo
    if _is_group(update):
        await update.message.reply_text("⚠️ Para usar o bot, me chame no privado. Envie /start no privado.")
        return

    create_or_get_user(user_id)
    st = get_user_status(user_id) or {}
    terms_ok = bool(st.get("terms_accepted")) and (st.get("terms_version") == TERMS_VERSION)

    # Link do WebApp termos
    terms_url = f"{BASE_URL}/terms?uid={user_id}&lang={tg_lang}"

    # Caso 1: não aceitou termos (ou versão mudou)
    if not terms_ok:
        # se mudou versão, “zera” welcome pra mandar novamente quando aceitar
        reset_welcome_sent(user_id)

        caption = (
            f"👋 Olá, <b>{name}</b>\n\n"
            "Antes de continuar sua jornada na <b>Source Baltigo</b> 🎴✨\n\n"
            "📜 Você precisa ler e aceitar nossos <b>Termos de Uso e Política de Privacidade</b>.\n"
            "Isso garante uma experiência justa, segura e equilibrada para todos os colecionadores.\n\n"
            "⚠️ Ao continuar, você confirma que concorda com essas regras."
        )

        keyboard = [
            [InlineKeyboardButton("📜 Ler e aceitar termos", web_app=WebAppInfo(url=terms_url))],
        ]
        await update.message.reply_photo(
            photo=BANNER_URL,
            caption=caption,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # Caso 2: aceitou termos mas não entrou no canal obrigatório
    if REQUIRED_CHANNEL:
        try:
            member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
            ok = member.status in ("creator", "administrator", "member")
        except Exception:
            ok = False

        if not ok:
            reset_welcome_sent(user_id)
            await update.message.reply_text(
                "📢 Para continuar, é obrigatório entrar no nosso canal oficial.\n"
                "Depois volte aqui e envie /start novamente."
            )
            return

    # Caso 3: tudo ok -> mensagem de boas-vindas (1x) ou de volta
    welcome_sent = bool(st.get("welcome_sent"))

    nome = update.effective_user.first_name if update.effective_user else ""

    texto = (
        f"🏴‍☠️ <b>Bem-vindo, {nome}!</b>\n\n"

        "<b>Source Baltigo</b>\n"
        "<i>O seu portal para o mundo dos animes.</i>\n\n"

        "Aqui você pode descobrir personagens, explorar histórias "
        "e encontrar novos animes para assistir.\n\n"

        "Entre para a tripulação e comece sua jornada. ⚔️✨"
    )

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Adicionar ao grupo",
                url="https://t.me/SourceBaltigo_bot?startgroup=true"
            )
        ],
        [
            InlineKeyboardButton("🏴‍☠️ QG Baltigo", url="https://t.me/QG_BALTIGO")
        ]
    ])

    if update.message:
        await update.message.reply_photo(
            photo="https://photo.chelpbot.me/AgACAgEAAxkBZpDL8mmeFx3it__n9zwKhDWr-EiaijwiAAIdDGsbjP7wRDMvEtZUPvYtAQADAgADeQADOgQ/photo.jpg",
            caption=texto,
            parse_mode="HTML",
            reply_markup=teclado
        )
