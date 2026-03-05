import os
from telegram.ext import Application, CommandHandler

from commands.start import start
from database import create_tables

BOT_TOKEN = os.getenv("BOT_TOKEN")

def main():

    create_tables()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("Bot iniciado")

    app.run_polling()

if __name__ == "__main__":
    main()
