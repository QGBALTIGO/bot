import os
import threading
import uvicorn

from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from commands.start import start
from commands.anime import anime
from commands.manga import manga
from commands.cards import cards
from commands.pedido import pedido
from commands.nivel import nivel
from commands.card import card
from commands.perfil import perfil

from commands.cards_admin import (
    card_addanime,
    card_addchar,
    card_addsubcat,
    card_delanime,
    card_delchar,
    card_delsubcat,
    card_reload,
    card_setanimebanner,
    card_setanimecover,
    card_setcharimg,
    card_setcharname,
    card_subadd,
    card_subremove,
)

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
    tg_app.add_handler(CommandHandler("card", card))
    tg_app.add_handler(CommandHandler("nivel", nivel))
    tg_app.add_handler(CommandHandler("perfil", perfil))

    # admin cards
    tg_app.add_handler(CommandHandler("card_reload", card_reload))
    tg_app.add_handler(CommandHandler("card_delchar", card_delchar))
    tg_app.add_handler(CommandHandler("card_addchar", card_addchar))
    tg_app.add_handler(CommandHandler("card_setcharimg", card_setcharimg))
    tg_app.add_handler(CommandHandler("card_setcharname", card_setcharname))
    tg_app.add_handler(CommandHandler("card_delanime", card_delanime))
    tg_app.add_handler(CommandHandler("card_addanime", card_addanime))
    tg_app.add_handler(CommandHandler("card_setanimebanner", card_setanimebanner))
    tg_app.add_handler(CommandHandler("card_setanimecover", card_setanimecover))
    tg_app.add_handler(CommandHandler("card_addsubcat", card_addsubcat))
    tg_app.add_handler(CommandHandler("card_delsubcat", card_delsubcat))
    tg_app.add_handler(CommandHandler("card_subadd", card_subadd))
    tg_app.add_handler(CommandHandler("card_subremove", card_subremove))

    print("Bot + WebApp iniciado")
    tg_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()







