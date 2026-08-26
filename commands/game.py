import os

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry


GAME_BANNER_URL = os.getenv(
    "GAME_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZ0sajmmrHXRy1AZxkfEGC2Lx4yC6A80MAAJOC2sb1ZFYRQ5kxLI09cC2AQADAgADeQADOgQ/photo.jpg",
).strip()


async def jogar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Baltigo Game Center",
            description=(
                "Daily, dados e giros agora fazem parte da mesma economia. "
                "Seus recursos, recompensas e coleção ficam sincronizados em um único lugar."
            ),
            button="🎮 Abrir Game Center",
            path="/game",
            icon="🎮",
            banner_url=GAME_BANNER_URL,
        ),
    )


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Recompensa diária",
            description=(
                "Resgate coins, dados e giros reais. A sequência de 7 dias aumenta as recompensas "
                "e tudo entra direto na sua carteira."
            ),
            button="🎁 Resgatar Daily",
            path="/game#daily",
            icon="🎁",
            banner_url=GAME_BANNER_URL,
        ),
    )


async def dado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Dado de descoberta",
            description=(
                "Role um dado 3D, descubra obras e escolha uma delas para revelar um personagem "
                "que entra de verdade na sua coleção."
            ),
            button="🎲 Rolar Dado",
            path="/game#dice",
            icon="🎲",
            banner_url=GAME_BANNER_URL,
        ),
    )


async def giro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Roleta Baltigo",
            description=(
                "Use seus giros em uma roleta animada com recompensas reais de coins, dados e novos giros."
            ),
            button="🎡 Abrir Roleta",
            path="/game#spin",
            icon="🎡",
            banner_url=GAME_BANNER_URL,
        ),
    )
