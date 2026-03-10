import os

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, Update
from telegram.ext import ContextTypes

SHOP_PREVIEW_IMAGE = "https://photo.chelpbot.me/AgACAgQAAxkBZqZjcmmff-LPn4H7y3EsyO0G_rk8AAHTWgACBw5rG0eL9VAWyQkpU35BaAEAAwIAA3kAAzoE/photo.jpg"


async def loja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_html(
            "🛒 <b>LOJA</b>\n\n"
            "Use a loja <b>somente no privado</b> do bot.\n"
            "👉 Abra o bot no PV e use <code>/loja</code>."
        )
        return

    webapp_base = (os.getenv("BASE_URL", "").strip() or os.getenv("WEBAPP_URL", "").strip())
    if not webapp_base:
        await update.message.reply_html("⚠️ WEBAPP_URL/BASE_URL não configurada.")
        return

    texto = (
        "🛒 <b>LOJA BALTIGO</b>\n\n"
        "Venda personagens e compre recursos direto aqui no Telegram. 👇"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Abrir Loja", web_app=WebAppInfo(url=f"{webapp_base}/shop"))],
    ])

    await update.message.reply_photo(
        photo=SHOP_PREVIEW_IMAGE,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb
    )
