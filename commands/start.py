import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from database import create_or_get_user

BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZzNiyWmpfGqHBancNR9gbzHUCcN5FHTmAAKjC2sbzg9QRZjbm81ltK8VAQADAgADeQADOgQ/photo.jpg"

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL não configurado no Railway.")

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
    name = update.effective_user.first_name or "Colecionador"
    tg_lang = _map_tg_lang(update.effective_user.language_code)

    create_or_get_user(user_id)

    caption = (
        f"👋 Olá, <b>{name}</b>\n\n"
        "Antes de continuar sua jornada na <b>Source Baltigo</b> 🎴✨\n\n"
        "📜 Você precisa ler e aceitar nossos <b>Termos de Uso e Política de Privacidade</b>.\n"
        "Isso garante uma experiência justa, segura e equilibrada para todos os colecionadores.\n\n"
        "⚠️ Ao continuar, você confirma que concorda com essas regras."
    )

    terms_url = f"{BASE_URL}/terms?uid={user_id}&lang={tg_lang}"

    keyboard = [
        [InlineKeyboardButton("📜 Ler e aceitar termos", web_app=WebAppInfo(url=terms_url))],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_photo(
        photo=BANNER_URL,
        caption=caption,
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
