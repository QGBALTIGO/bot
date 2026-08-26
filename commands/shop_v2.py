import os

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry


SHOP_BANNER_URL = os.getenv(
    "SHOP_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgQAAxkBZqZjcmmff-LPn4H7y3EsyO0G_rk8AAHTWgACBw5rG0eL9VAWyQkpU35BaAEAAwIAA3kAAzoE/photo.jpg",
).strip()


async def loja(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Loja Baltigo V2",
            description=(
                "Use coins para recursos reais do Game Center e venda apenas duplicatas. "
                "Sua última cópia fica protegida."
            ),
            button="🛒 Abrir Loja",
            path="/shop-v2",
            icon="🛒",
            banner_url=SHOP_BANNER_URL,
        ),
    )
