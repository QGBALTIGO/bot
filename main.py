import threading
import uvicorn

from bot import main as bot_main

def run_bot():
    bot_main()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    uvicorn.run("webapp:app", host="0.0.0.0", port=8000)