import os

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper

BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
if not BOT_USERNAME:
    raise RuntimeError("BOT_USERNAME não configurado.")

DADO_BANNER_URL = os.getenv(
    "DADO_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzjh9mmp41BscIh8CXt94vL4xYJb_x4kAALKC2sbeI3gRIgS39Orz7ePAQADAgADeQADOgQ/photo.jpg",
).strip()

DADO_WEBAPP_URL = f"{BASE_URL}/dado"
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def dado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    # =========================
    # BLOQUEIO EM GRUPO
    # =========================
    if _is_group(update):
        texto = (
            "🎲 <b>SISTEMA DE DADOS</b>\n\n"
            "Esse comando funciona apenas no <b>privado</b> do bot.\n\n"
            "Abra no privado para acessar seus <b>giros</b>, sua <b>rolagem</b> "
            "e sua futura <b>coleção</b> com segurança."
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔒 Abrir no privado", url=BOT_PRIVATE_URL)]
        ])

        await msg.reply_html(texto, reply_markup=kb)
        return

    # =========================
    # GATEKEEPER
    # - termos
    # - canal obrigatório
    # - regras padrão do bot
    # =========================
    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    # =========================
    # MENSAGEM PRINCIPAL
    # =========================
    texto = (
        "🎲 <b>SISTEMA DE DADOS</b>\n\n"
        "Aqui você poderá usar seus <b>dados</b> para descobrir <b>animes</b> e obter "
        "<b>personagens</b> para a sua coleção.\n\n"
        "🕒 <b>Recargas fixas:</b>\n"
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
        photo=DADO_BANNER_URL,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
