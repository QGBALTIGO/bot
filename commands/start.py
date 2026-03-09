import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from database import create_or_get_user, get_user_status, mark_welcome_sent, reset_welcome_sent
from utils.gatekeeper import TERMS_VERSION

# ====== CONFIG ======
BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZzNiyWmpfGqHBancNR9gbzHUCcN5FHTmAAKjC2sbzg9QRZjbm81ltK8VAQADAgADeQADOgQ/photo.jpg"

WELCOME_BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZzjh9mmp41BscIh8CXt94vL4xYJb_x4kAALKC2sbeI3gRIgS39Orz7ePAQADAgADeQADOgQ/photo.jpg"

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado no Railway.")

# Canal obrigatório (se vazio, não bloqueia aqui — mas o gatekeeper pode bloquear)
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourcerBaltigo").strip()
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/SourcerBaltigo").strip()

# Link do bot (pra abrir privado quando o comando vier de grupo)
BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")  # coloque o user correto
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"

# Botão adicionar ao grupo
ADD_TO_GROUP_URL = f"https://t.me/{BOT_USERNAME}?startgroup=true"

# Comunidade / QG
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id if user else 0
    name = (user.first_name or "Navegante") if user else "Navegante"
    tg_lang = _map_tg_lang(user.language_code if user else None)

    # =========================
    # /start em grupo -> mandar pro privado
    # =========================
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

    # =========================
    # Garantir usuário no DB
    # =========================
    if user_id <= 0:
        if update.message:
            await update.message.reply_text("❌ Não consegui identificar seu usuário.")
        return

    create_or_get_user(user_id)
    st = get_user_status(user_id) or {}

    terms_ok = bool(st.get("terms_accepted")) and (st.get("terms_version") == TERMS_VERSION)

    # Link do WebApp termos
    terms_url = f"{BASE_URL}/terms?uid={user_id}&lang={tg_lang}"

    # =========================
    # Caso 1: não aceitou termos (ou versão mudou)
    # =========================
    if not terms_ok:
        # se mudou versão, “zera” welcome pra mandar novamente quando aceitar
        reset_welcome_sent(user_id)

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

    # =========================
    # Caso 2: aceitou termos mas não está no canal obrigatório
    # =========================
    if REQUIRED_CHANNEL:
        ok = False
        try:
            member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
            ok = member.status in ("creator", "administrator", "member")
        except Exception:
            ok = False

        if not ok:
            reset_welcome_sent(user_id)

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

    # =========================
    # Caso 3: tudo ok -> boas-vindas (1x) ou de volta
    # =========================
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
        mark_welcome_sent(user_id)
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
            reply_markup=teclado
        )
