import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from database import create_or_get_user, get_dado_state, get_next_dado_recharge_info
from utils.gatekeeper import gatekeeper


BASE_URL = (os.getenv("BASE_URL", "").strip() or os.getenv("WEBAPP_URL", "").strip()).rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL nao configurado.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
if not BOT_USERNAME:
    raise RuntimeError("BOT_USERNAME nao configurado.")

DADO_BANNER_URL = os.getenv(
    "DADO_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZqAk02mfJAxu6F0SV9i2MqA5qQ6fDy3PAAKhC2sbjP74RFhnKn29pt05AQADAgADeQADOgQ/photo.jpg",
).strip()

BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def dado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    if _is_group(update):
        texto = (
            "<b>SISTEMA DE DADOS</b>\n\n"
            "Esse comando funciona apenas no privado do bot.\n\n"
            "Abra no privado para acessar seus dados, sua rolagem e sua colecao com seguranca."
        )
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Abrir no privado", url=BOT_PRIVATE_URL)]]
        )
        await msg.reply_html(texto, reply_markup=kb)
        return

    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    create_or_get_user(user.id)

    try:
        dado_state = get_dado_state(user.id)
        recharge_info = get_next_dado_recharge_info(user.id)
        saldo = int((dado_state or {}).get("balance") or 0)
        prox_hora = str((recharge_info or {}).get("next_recharge_hhmm") or "--:--")
    except Exception:
        saldo = 0
        prox_hora = "--:--"

    url = f"{BASE_URL}/dado?uid={user.id}"
    texto = (
        "<b>SISTEMA DE DADOS</b>\n\n"
        "Aqui voce podera usar seus dados para descobrir animes e obter personagens para a sua colecao.\n\n"
        f"<b>Dados disponiveis:</b> <code>{saldo}</code>\n"
        f"<b>Proximo dado:</b> <code>{prox_hora}</code>\n\n"
        "Toque no botao abaixo para abrir a area dos dados."
    )

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Abrir Dados", web_app=WebAppInfo(url=url))]]
    )

    await msg.reply_photo(
        photo=DADO_BANNER_URL,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
