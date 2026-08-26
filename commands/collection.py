import os

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry


COLLECTION_BANNER_URL = os.getenv(
    "COLLECTION_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZ0sajmmrHXRy1AZxkfEGC2Lx4yC6A80MAAJOC2sb1ZFYRQ5kxLI09cC2AQADAgADeQADOgQ/photo.jpg",
).strip()


async def colecao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Minha coleção",
            description=(
                "Veja todos os personagens que você conquistou, quantidade de cópias, "
                "duplicatas e seu progresso no catálogo."
            ),
            button="🎴 Abrir Coleção",
            path="/collection",
            icon="🎴",
            banner_url=COLLECTION_BANNER_URL,
        ),
    )
