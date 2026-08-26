from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry


async def contribuir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Contribuir com os Cards",
            description=(
                "Sugira imagens melhores ou novas obras. Toda contribuição entra em uma fila "
                "de moderação antes de alterar o catálogo."
            ),
            button="✨ Abrir Central de Contribuições",
            path="/contribute",
            icon="✨",
        ),
    )


sugerircard = contribuir
