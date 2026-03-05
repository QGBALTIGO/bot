from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import create_or_get_user

BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZzNiyWmpfGqHBancNR9gbzHUCcN5FHTmAAKjC2sbzg9QRZjbm81ltK8VAQADAgADeQADOgQ/photo.jpg"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name or "Colecionador"

    create_or_get_user(user_id)

    caption = (
        f"👋 Olá, <b>{name}</b>\n\n"
        "Antes de continuar sua jornada na <b>Source Baltigo</b> 🎴✨\n\n"
        "📜 Você precisa ler e aceitar nossos <b>Termos de Uso e Política de Privacidade</b>.\n"
        "Isso garante uma experiência justa, segura e equilibrada para todos os colecionadores.\n\n"
        "⚠️ Ao continuar, você confirma que concorda com essas regras."
    )

    keyboard = [
        [InlineKeyboardButton("📜 Ler e aceitar termos", callback_data="open_terms")],
        [InlineKeyboardButton("🌐 Idioma", callback_data="change_language")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # /start normalmente vem por mensagem
    if update.message:
        await update.message.reply_photo(
            photo=BANNER_URL,
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return

    # fallback (caso raro: start vindo de outro tipo de update)
    if update.effective_chat:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=BANNER_URL,
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
