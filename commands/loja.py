import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes


SHOP_PREVIEW_IMAGE = (
    "https://photo.chelpbot.me/AgACAgQAAxkBZqZjcmmff-LPn4H7y3EsyO0G_rk8AAHTWgACBw5rG0eL9VAWyQkpU35BaAEAAwIAA3kAAzoE/photo.jpg"
)


async def loja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_html(
            "SHOP\n\n"
            "Use a loja somente no privado do bot.\n"
            "Abra o bot no PV e use /loja."
        )
        return

    webapp_base = (os.getenv("BASE_URL", "").strip() or os.getenv("WEBAPP_URL", "").strip()).rstrip("/")
    if not webapp_base:
        await update.message.reply_html("WEBAPP_URL/BASE_URL nao configurada.")
        return

    url = f"{webapp_base}/shop?uid={update.effective_user.id}"
    texto = (
        "<b>LOJA BALTIGO</b>\n\n"
        "Venda personagens e compre recursos direto aqui no Telegram."
    )

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Abrir Loja", web_app=WebAppInfo(url=url))]]
    )

    await update.message.reply_photo(
        photo=SHOP_PREVIEW_IMAGE,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
