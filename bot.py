import os
import threading
import uvicorn

from telegram.ext import Application, CommandHandler
from commands.start import start
from database import create_tables

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

PORT = int(os.getenv("PORT", "8000"))

def run_webapp():
    from webapp import app
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

def main():
    # 1) garante tabela
    create_tables()

    # 2) sobe webapp
    t = threading.Thread(target=run_webapp, daemon=True)
    t.start()

    # 3) sobe bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    print(f"Bot + WebApp iniciado (PORT={PORT})")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
