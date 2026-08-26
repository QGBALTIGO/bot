import os

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry


RANKING_BANNER_URL = os.getenv(
    "RANKING_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZqlp8GmfqqNQyQV05efRn6slkZYc66uOAALOC2sbS__4RP55dhAgyc7mAQADAgADeQADOgQ/photo.jpg",
).strip()


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Ranking Baltigo",
            description=(
                "Compare progresso, coleção e fortuna. O placar geral usa somente progresso "
                "e coleção para manter a competição justa."
            ),
            button="🏆 Abrir Ranking",
            path="/ranking",
            icon="🏆",
            banner_url=RANKING_BANNER_URL,
        ),
    )
