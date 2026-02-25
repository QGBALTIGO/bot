import threading
import os
import uvicorn

from bot import main as bot_main

def run_bot():
    bot_main()

if __name__ == "__main__":
    # roda o bot em background
    threading.Thread(target=run_bot, daemon=True).start()

    # roda o servidor web (Railway usa a porta do env PORT)
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("webapp:app", host="0.0.0.0", port=port)
