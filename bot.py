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

from commands.start import start
from commands.anime import anime
from commands.manga import manga
from commands.cards import cards
from commands.card import card, card_stats_callback
from commands.colecao import (
    colecao,
    colecao_callback,
    colecao_s_callback,
    colecao_f_callback,
    colecao_x_callback,
    get_completed_anime_message,
)
from commands.pedido import pedido
from commands.nivel import nivel
from commands.dado import dado
from commands.dado_admin import dadogive, dadogiveall
from commands.termo import (
    termo_cmd,
    termo_stats_cmd,
    termo_ranking_cmd,
    termo_ranking_week_cmd,
    termo_ranking_month_cmd,
    termo_treino_cmd,
    termo_treino_stats_cmd,
    termo_treino_stop_cmd,
    termo_guess,
    termo_callback,
)
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


# =========================================================
# WEBAPP
# =========================================================

def run_webapp() -> None:
    try:
        from webapp import app as web_app

        uvicorn.run(
            web_app,
            host="0.0.0.0",
            port=PORT,
            log_level="info",
        )
    except Exception:
        print("[webapp-error] Falha ao iniciar a WebApp", flush=True)
        traceback.print_exc()


# =========================================================
# ERROR HANDLER
# =========================================================

async def on_error(update, context) -> None:
    try:
        print("[telegram-error]", repr(getattr(context, "error", None)), flush=True)
        traceback.print_exc()
    except Exception:
        pass


# =========================================================
# REGISTER HELPERS
# =========================================================

def register_main_commands(tg_app: Application) -> None:
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("anime", anime))
    tg_app.add_handler(CommandHandler("manga", manga))
    tg_app.add_handler(CommandHandler("cards", cards))
    tg_app.add_handler(CommandHandler("card", card))
    tg_app.add_handler(CommandHandler("colecao", colecao))
    tg_app.add_handler(CommandHandler("pedido", pedido))
    tg_app.add_handler(CommandHandler("nivel", nivel))
    tg_app.add_handler(CommandHandler("dado", dado))


def register_dado_admin_commands(tg_app: Application) -> None:
    tg_app.add_handler(CommandHandler("dadogive", dadogive))
    tg_app.add_handler(CommandHandler("dadogiveall", dadogiveall))


def register_termo_commands(tg_app: Application) -> None:
    tg_app.add_handler(CommandHandler("termo", termo_cmd))
    tg_app.add_handler(CommandHandler("termostats", termo_stats_cmd))
    tg_app.add_handler(CommandHandler("termoranking", termo_ranking_cmd))
    tg_app.add_handler(CommandHandler("termorankingsemana", termo_ranking_week_cmd))
    tg_app.add_handler(CommandHandler("termorankingmes", termo_ranking_month_cmd))
    tg_app.add_handler(CommandHandler("termotreino", termo_treino_cmd))
    tg_app.add_handler(CommandHandler("termotreinostats", termo_treino_stats_cmd))
    tg_app.add_handler(CommandHandler("termotreinostop", termo_treino_stop_cmd))


def register_cards_admin_commands(tg_app: Application) -> None:
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


def register_callbacks(tg_app: Application) -> None:
    # coleção por foto primeiro (mais específico)
    tg_app.add_handler(CallbackQueryHandler(colecao_x_callback, pattern=r"^colecao_x:"))
    tg_app.add_handler(CallbackQueryHandler(colecao_s_callback, pattern=r"^colecao_s:"))
    tg_app.add_handler(CallbackQueryHandler(colecao_f_callback, pattern=r"^colecao_f:"))
    tg_app.add_handler(CallbackQueryHandler(colecao_callback, pattern=r"^colecao:"))

    # card
    tg_app.add_handler(CallbackQueryHandler(card_stats_callback, pattern=r"^cardstats:"))

    # termo
    tg_app.add_handler(CallbackQueryHandler(termo_callback, pattern=r"^termo:"))


def register_message_handlers(tg_app: Application) -> None:
    # guesses do termo: texto normal, sem barra
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, termo_guess))


# =========================================================
# APP BUILDER
# =========================================================

def build_application() -> Application:
    tg_app = Application.builder().token(BOT_TOKEN).build()

    register_main_commands(tg_app)
    register_dado_admin_commands(tg_app)
    register_termo_commands(tg_app)
    register_cards_admin_commands(tg_app)
    register_callbacks(tg_app)
    register_message_handlers(tg_app)

    tg_app.add_error_handler(on_error)
    return tg_app


# =========================================================
# MAIN
# =========================================================

def main() -> None:
    create_tables()

    web_thread = threading.Thread(target=run_webapp, daemon=True)
    web_thread.start()

    tg_app = build_application()

    print("Bot + WebApp iniciado", flush=True)
    tg_app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
