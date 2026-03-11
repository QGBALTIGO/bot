import os
import threading
import traceback

import uvicorn

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

# =========================================================
# COMMANDS
# =========================================================

from commands.start import start
from commands.menu import menu
from commands.perfil import perfil
from commands.reset_users import reset_user, reset_all

from commands.anime import anime
from commands.manga import manga
from commands.avisar import avisar

from commands.cards import cards
from commands.card import card, card_stats_callback

from commands.colecao import (
    colecao,
    colecao_callback,
    colecao_s_callback,
    colecao_f_callback,
    colecao_x_callback,
)

from commands.loja import loja
from commands.daily import daily

from commands.capturar import capturar
from commands.spawn_personagem import spawn_personagem

from commands.trocar import (
    trocar,
    trade_accept,
    trade_reject,
)

from commands.ranking import ranking, callback_ranking

from commands.pedido import pedido
from commands.nivel import nivel

from commands.card_contrib import sugerircard
from commands.dado import dado
from commands.dado_admin import dadogive, dadogiveall

from commands.termo import (
    termo_cmd,
    termo_guess,
    termo_stats_cmd,
    termo_ranking_cmd,
    termo_ranking_week_cmd,
    termo_ranking_month_cmd,
    termo_treino_cmd,
    termo_treino_stats_cmd,
    termo_treino_stop_cmd,
    termo_callback,
)

from commands.cards_admin import (
    card_reload,
    card_delchar,
    card_addchar,
    card_setcharimg,
    card_setcharname,
    card_delanime,
    card_addanime,
    card_setanimebanner,
    card_setanimecover,
    card_addsubcat,
    card_delsubcat,
    card_subadd,
    card_subremove,
)

from commands.messages import (
    bloquearmsg,
    denunciarmsg,
    msg,
    msganon,
    msgconfig,
    desbloquearmsg,
)
from commands.messages_help import msgtutorial

from handlers.capture_spawn import capture_message_handler

from database import create_tables


# =========================================================
# ENV
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

PORT = int(os.getenv("PORT", "8000"))


# =========================================================
# WEBAPP
# =========================================================

def run_webapp():
    try:
        from webapp import app as web_app

        uvicorn.run(
            web_app,
            host="0.0.0.0",
            port=PORT,
            log_level="warning",
        )
    except Exception:
        print("[webapp-error]")
        traceback.print_exc()


# =========================================================
# ERROR HANDLER
# =========================================================

async def on_error(update, context):
    print("[telegram-error]", repr(context.error))
    traceback.print_exc()


# =========================================================
# COMMAND HANDLERS
# =========================================================

def register_commands(app: Application):
    # básicos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("perfil", perfil))
    app.add_handler(CommandHandler("resetuser", reset_user))
    app.add_handler(CommandHandler("resetall", reset_all))
    app.add_handler(CommandHandler("avisar", avisar))
    app.add_handler(CommandHandler("cardcontrib", sugerircard))

    # msg
    app.add_handler(CommandHandler("msg", msg))
    app.add_handler(CommandHandler("msganon", msganon))
    app.add_handler(CommandHandler("bloquearmsg", bloquearmsg))
    app.add_handler(CommandHandler("desbloquearmsg", desbloquearmsg))
    app.add_handler(CommandHandler("msgconfig", msgconfig))
    app.add_handler(CommandHandler("denunciarmsg", denunciarmsg))
    app.add_handler(CommandHandler("msgtutorial", msgtutorial))
    
    # catálogo
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(CommandHandler("manga", manga))

    # cards
    app.add_handler(CommandHandler("cards", cards))
    app.add_handler(CommandHandler("card", card))

    # coleção
    app.add_handler(CommandHandler("colecao", colecao))

    # economia
    app.add_handler(CommandHandler("loja", loja))
    app.add_handler(CommandHandler("daily", daily))

    # gacha
    app.add_handler(CommandHandler("capturar", capturar))
    app.add_handler(CommandHandler("spawnpersonagem", spawn_personagem))

    # troca
    app.add_handler(CommandHandler("trocar", trocar))

    # ranking
    app.add_handler(CommandHandler("ranking", ranking))

    # misc
    app.add_handler(CommandHandler("pedido", pedido))
    app.add_handler(CommandHandler("nivel", nivel))

    # dado
    app.add_handler(CommandHandler("dado", dado))
    app.add_handler(CommandHandler("dadogive", dadogive))
    app.add_handler(CommandHandler("dadogiveall", dadogiveall))

    # termo
    app.add_handler(CommandHandler("termo", termo_cmd))
    app.add_handler(CommandHandler("termostats", termo_stats_cmd))
    app.add_handler(CommandHandler("termoranking", termo_ranking_cmd))
    app.add_handler(CommandHandler("termorankingsemana", termo_ranking_week_cmd))
    app.add_handler(CommandHandler("termorankingmes", termo_ranking_month_cmd))
    app.add_handler(CommandHandler("termotreino", termo_treino_cmd))
    app.add_handler(CommandHandler("termotreinostats", termo_treino_stats_cmd))
    app.add_handler(CommandHandler("termotreinostop", termo_treino_stop_cmd))

    # admin cards
    app.add_handler(CommandHandler("card_reload", card_reload))
    app.add_handler(CommandHandler("card_delchar", card_delchar))
    app.add_handler(CommandHandler("card_addchar", card_addchar))
    app.add_handler(CommandHandler("card_setcharimg", card_setcharimg))
    app.add_handler(CommandHandler("card_setcharname", card_setcharname))
    app.add_handler(CommandHandler("card_delanime", card_delanime))
    app.add_handler(CommandHandler("card_addanime", card_addanime))
    app.add_handler(CommandHandler("card_setanimebanner", card_setanimebanner))
    app.add_handler(CommandHandler("card_setanimecover", card_setanimecover))
    app.add_handler(CommandHandler("card_addsubcat", card_addsubcat))
    app.add_handler(CommandHandler("card_delsubcat", card_delsubcat))
    app.add_handler(CommandHandler("card_subadd", card_subadd))
    app.add_handler(CommandHandler("card_subremove", card_subremove))


# =========================================================
# CALLBACK HANDLERS
# =========================================================

def register_callbacks(app: Application):
    # trocas
    app.add_handler(CallbackQueryHandler(trade_accept, pattern=r"^trade_accept"))
    app.add_handler(CallbackQueryHandler(trade_reject, pattern=r"^trade_reject"))

    # card
    app.add_handler(CallbackQueryHandler(card_stats_callback, pattern=r"^card_stats"))

    # coleção
    app.add_handler(CallbackQueryHandler(colecao_callback, pattern=r"^colecao:"))
    app.add_handler(CallbackQueryHandler(colecao_s_callback, pattern=r"^colecao_s:"))
    app.add_handler(CallbackQueryHandler(colecao_f_callback, pattern=r"^colecao_f:"))
    app.add_handler(CallbackQueryHandler(colecao_x_callback, pattern=r"^colecao_x:"))

    # ranking
    app.add_handler(CallbackQueryHandler(callback_ranking, pattern=r"^rank:"))

    # termo
    app.add_handler(CallbackQueryHandler(termo_callback, pattern=r"^termo:"))


# =========================================================
# MESSAGE HANDLERS
# =========================================================

def register_messages(app: Application):
    # termo primeiro para tentar consumir palavras do jogo antes do sistema de captura
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, termo_guess),
        group=1,
    )

    # captura/spawn depois
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, capture_message_handler),
        group=2,
    )


# =========================================================
# APPLICATION
# =========================================================

def build_application():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    register_commands(app)
    register_callbacks(app)
    register_messages(app)

    app.add_error_handler(on_error)

    return app


# =========================================================
# MAIN
# =========================================================

def main():
    create_tables()

    threading.Thread(
        target=run_webapp,
        daemon=True,
    ).start()

    app = build_application()

    print("Bot iniciado", flush=True)

    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
