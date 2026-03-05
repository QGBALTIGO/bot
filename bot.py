import os
import threading
import uvicorn

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from commands.start import start
from database import create_tables
from handlers.global_block import global_block
from webapp import app

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

PORT = int(os.getenv("PORT", "8000"))

def run_webapp():
    from webapp import app
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

def main():
    create_tables()

    t = threading.Thread(target=run_webapp, daemon=True)
    t.start()

    app = Application.builder().token(BOT_TOKEN).build()

    # TRAVA GLOBAL: roda antes de todos os handlers
    app.add_handler(MessageHandler(filters.ALL, global_block), group=-1)

    # /start sempre existe (e ele mesmo já lida com termos/canal)
    app.add_handler(CommandHandler("start", start), group=0)

    print(f"Bot + WebApp iniciado (PORT={PORT})")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

