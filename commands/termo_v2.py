from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry


async def termo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Termo Anime",
            description=(
                "Descubra a palavra de 6 letras em até 6 tentativas. "
                "A palavra diária vale coins, XP e sequência; o modo treino é livre."
            ),
            button="🎌 Abrir Termo Anime",
            path="/termo",
            icon="🎌",
        ),
    )
