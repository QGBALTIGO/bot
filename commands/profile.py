import os

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry


PROFILE_BANNER_URL = os.getenv(
    "PROFILE_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzjh9mmp41BscIh8CXt94vL4xYJb_x4kAALKC2sbeI3gRIgS39Orz7ePAQADAgADeQADOgQ/photo.jpg",
).strip()


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Meu perfil",
            description=(
                "Gerencie seu nickname, privacidade e personagem favorito e veja nível, rank, "
                "coleção e recursos em um só lugar."
            ),
            button="👤 Abrir Perfil",
            path="/profile",
            icon="👤",
            banner_url=PROFILE_BANNER_URL,
        ),
    )
