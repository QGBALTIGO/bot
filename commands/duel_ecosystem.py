from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

import commands.duel_v2 as duel_ui
from duel_service_v2 import create_challenge, respond_challenge, submit_pick

# The existing duel UI remains the canonical Telegram presentation while the
# domain mutations are replaced by ecosystem-aware service functions.
duel_ui.create_challenge = create_challenge
duel_ui.respond_challenge = respond_challenge
duel_ui.submit_pick = submit_pick


async def duelo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await duel_ui.duelo(update, context)


async def duel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await duel_ui.duel_callback(update, context)
