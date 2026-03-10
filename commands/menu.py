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

MENU_BANNER_URL = os.getenv(
    "MENU_BANNER_URL",
    "https://carder.top/imagens/1773141172659-711153369.jpg",
).strip()

MENU_WEBAPP_URL = f"{BASE_URL}/menu"
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if not msg or not user:
        return

    # =========================
    # BLOQUEIO EM GRUPO
    # =========================
    if _is_group(update):
        texto = (
            "⚙️ <b>MENU DO USUÁRIO</b>\n\n"
            "Esse comando funciona apenas no <b>privado</b> do bot.\n\n"
            "Abra no privado para configurar seu <b>perfil</b>, seu <b>favorito</b>, "
            "suas <b>preferências</b> e outras opções da sua conta."
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔒 Abrir no privado", url=BOT_PRIVATE_URL)]
        ])

        await msg.reply_html(texto, reply_markup=kb)
        return

    # =========================
    # GATEKEEPER
    # =========================
    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    # =========================
    # MINIAPP MENU
    # =========================
    url = f"{MENU_WEBAPP_URL}?uid={user.id}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Abrir Menu", web_app=WebAppInfo(url=url))]
    ])

    texto = (
        "⚙️ <b>MENU DO USUÁRIO</b>\n\n"
        "Aqui você poderá configurar sua conta, definir seu <b>nickname</b>, "
        "escolher seu <b>personagem favorito</b>, ajustar <b>idioma</b>, "
        "<b>bandeira</b>, <b>privacidade</b> e outras preferências.\n\n"
        "Toque no botão abaixo para abrir o menu."
    )

    await msg.reply_photo(
        photo=MENU_BANNER_URL,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
