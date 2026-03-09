import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper
from utils.runtime_guard import rate_limiter

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado no Railway.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"

DADO_BANNER = os.getenv(
    "DADO_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzjh9mmp41BscIh8CXt94vL4xYJb_x4kAALKC2sbeI3gRIgS39Orz7ePAQADAgADeQADOgQ/photo.jpg",
).strip()

DADO_RATE_LIMIT = int(os.getenv("DADO_COMMAND_RATE_LIMIT", "2"))
DADO_RATE_WINDOW_SECONDS = float(os.getenv("DADO_COMMAND_RATE_WINDOW_SECONDS", "5"))

# enquanto o WebApp novo não fica pronto, já deixamos a rota fechada
DADO_WEBAPP_URL = f"{BASE_URL}/dado"


def _is_group(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))


async def dado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    # =========================
    # RATE LIMIT LEVE DO COMANDO
    # =========================
    allowed = await rate_limiter.allow(
        key=f"cmd:dado:{user.id}",
        limit=DADO_RATE_LIMIT,
        window_seconds=DADO_RATE_WINDOW_SECONDS,
    )
    if not allowed:
        return

    # =========================
    # GRUPO -> MANDA PRO PRIVADO
    # =========================
    if _is_group(update):
        texto = (
            "⚠️ <b>Acesso indisponível neste chat</b>\n\n"
            "O <b>Sistema de Dados</b> funciona no <b>privado</b> para proteger seu "
            "<b>saldo</b>, sua <b>coleção</b> e sua <b>rolagem</b>.\n\n"
            "🎲 <b>Toque no botão abaixo para abrir no privado:</b>"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Abrir Dados no privado", url=BOT_PRIVATE_URL)]
        ])

        await msg.reply_html(texto, reply_markup=kb)
        return

    # =========================
    # GATEKEEPER (termos + canal + progresso)
    # =========================
    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    # =========================
    # TEXTO PADRÃO DO COMANDO
    # =========================
    texto = (
        "🎲 <b>SISTEMA DE DADOS</b>\n\n"
        "Aqui você poderá usar seus <b>dados</b> para descobrir <b>animes</b> e obter "
        "<b>personagens</b> para a sua coleção.\n\n"
        "🕒 <b>Horários de recarga:</b>\n"
        "<code>01h • 04h • 07h • 10h • 13h • 16h • 19h • 22h</code>\n"
        "🇧🇷 Horário de São Paulo\n\n"
        "🎁 <b>Novos jogadores começam com 4 giros</b>\n"
        "📦 <b>Acúmulo máximo:</b> 3 dias\n\n"
        "Toque no botão abaixo para abrir a área dos dados."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Abrir Dados", web_app=WebAppInfo(url=DADO_WEBAPP_URL))]
    ])

    await msg.reply_photo(
        photo=DADO_BANNER,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
