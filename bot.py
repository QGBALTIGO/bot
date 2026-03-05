import os
import threading
import uvicorn

from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from commands.start import start
from commands.language import open_language_menu, set_lang
from database import create_tables

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

PORT = int(os.getenv("PORT", "8000"))

def run_webapp():
    # Import aqui dentro pra evitar import circular
    from webapp import app
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

def main():
    create_tables()

    # Sobe o webapp em uma thread separada
    t = threading.Thread(target=run_webapp, daemon=True)
    t.start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))


    print("Bot + WebApp iniciado")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

