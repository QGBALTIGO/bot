import os
import threading
import uvicorn
import asyncio
import time
import httpx

from telegram.ext import Application, CommandHandler

from commands.start import start
from commands.anime import anime
from commands.manga import manga
from commands.cards import cards
from commands.pedido import pedido

# from commands.anime import anime  # quando você criar

from database import create_tables

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

PORT = int(os.getenv("PORT", "8000"))

def run_webapp():
    from webapp import app as web_app
    uvicorn.run(web_app, host="0.0.0.0", port=PORT, log_level="info")

def main():
    create_tables()

    t = threading.Thread(target=run_webapp, daemon=True)
    t.start()

    tg_app = Application.builder().token(BOT_TOKEN).build()

    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("anime", anime)) 
    tg_app.add_handler(CommandHandler("manga", manga)) 
    tg_app.add_handler(CommandHandler("cards", cards))
    tg_app.add_handler(CommandHandler("pedido", pedido))
    
    
    print("Bot + WebApp iniciado")
    tg_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()









