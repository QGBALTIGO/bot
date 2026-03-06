import os
import threading
import uvicorn
import asyncio

from telegram.ext import Application, CommandHandler

from commands.start import start
from commands.anime import anime
from commands.manga import manga
from commands.cards import cards
from commands.pedido import pedido

from database import create_tables

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

PORT = int(os.getenv("PORT", "8000"))


# -----------------------------
# WEBAPP SERVER
# -----------------------------
def run_webapp():
    from webapp import app as web_app
    uvicorn.run(
        web_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )


# -----------------------------
# TELEGRAM BOT
# -----------------------------
async def start_bot():

    create_tables()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("anime", anime))
    application.add_handler(CommandHandler("manga", manga))
    application.add_handler(CommandHandler("cards", cards))
    application.add_handler(CommandHandler("pedido", pedido))

    # remove webhook antigo (evita conflito)
    await application.bot.delete_webhook(drop_pending_updates=True)

    print("Bot iniciado")

    await application.run_polling()


# -----------------------------
# MAIN
# -----------------------------
def main():

    # inicia webapp em thread
    t = threading.Thread(target=run_webapp, daemon=True)
    t.start()

    # inicia bot
    asyncio.run(start_bot())


if __name__ == "__main__":
    main()
