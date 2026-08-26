from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry
from memory_rules import level_config, normalize_level


async def memoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    requested = normalize_level(" ".join(context.args).strip()) if context.args else "medium"
    cfg = level_config(requested)
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title="Jogo da Memória",
            description=(
                f"Dificuldade {cfg.label}: {cfg.pairs} pares. "
                "O tempo e a conclusão são validados pelo servidor antes de entrar nos recordes."
            ),
            button="🧠 Abrir Memória",
            path=f"/memory?level={requested}",
            icon="🧠",
        ),
    )
