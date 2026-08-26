import logging
import os
import threading

import uvicorn
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from commands.anime import anime
from commands.baltigoflix import baltigoflix
from commands.card import card, card_stats_callback
from commands.cards import cards
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
from commands.manga import manga
from commands.nivel import nivel
from commands.pedido import pedido
from commands.start import start
from database import create_tables

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

try:
    PORT = int(os.getenv("PORT", "8000"))
except ValueError as exc:
    raise RuntimeError("PORT precisa ser um número inteiro.") from exc

if not 1 <= PORT <= 65535:
    raise RuntimeError("PORT precisa estar entre 1 e 65535.")

ENABLE_MESSAGES = os.getenv("ENABLE_MESSAGES", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def run_webapp() -> None:
    try:
        from webapp import app as web_app

        uvicorn.run(web_app, host="0.0.0.0", port=PORT, log_level="info")
    except Exception:
        logger.exception("Falha fatal ao iniciar a WebApp")
        raise


async def on_error(update, context) -> None:
    error = getattr(context, "error", None)
    if error is None:
        logger.error("Erro do Telegram sem exceção associada. update=%r", update)
        return

    logger.error(
        "Erro não tratado no Telegram. update=%r",
        update,
        exc_info=(type(error), error, error.__traceback__),
    )


def _register_message_handlers(tg_app: Application) -> None:
    if not ENABLE_MESSAGES:
        logger.info("Sistema de mensagens desativado (ENABLE_MESSAGES=false)")
        return

    try:
        from commands.messages import (
            bloquearmsg,
            denunciarmsg,
            msg,
            msganon,
            msgconfig,
            desbloquearmsg,
        )
    except ImportError as exc:
        raise RuntimeError(
            "ENABLE_MESSAGES=true, mas a camada de persistência do sistema de mensagens está incompleta."
        ) from exc

    tg_app.add_handler(CommandHandler("msg", msg))
    tg_app.add_handler(CommandHandler("msganon", msganon))
    tg_app.add_handler(CommandHandler("bloquearmsg", bloquearmsg))
    tg_app.add_handler(CommandHandler("desbloquearmsg", desbloquearmsg))
    tg_app.add_handler(CommandHandler("msgconfig", msgconfig))
    tg_app.add_handler(CommandHandler("denunciarmsg", denunciarmsg))


def build_application() -> Application:
    tg_app = Application.builder().token(BOT_TOKEN).build()

    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("anime", anime))
    tg_app.add_handler(CommandHandler("manga", manga))
    tg_app.add_handler(CommandHandler("cards", cards))
    tg_app.add_handler(CommandHandler("pedido", pedido))
    tg_app.add_handler(CommandHandler("card", card))
    tg_app.add_handler(CallbackQueryHandler(card_stats_callback, pattern=r"^cardstats:"))
    tg_app.add_handler(CommandHandler("nivel", nivel))
    tg_app.add_handler(CommandHandler("baltigoflix", baltigoflix))

    _register_message_handlers(tg_app)

    # administração dos cards
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

    tg_app.add_error_handler(on_error)
    return tg_app


def main() -> None:
    logger.info("Inicializando banco de dados")
    create_tables()

    web_thread = threading.Thread(
        target=run_webapp,
        name="source-baltigo-webapp",
        daemon=True,
    )
    web_thread.start()

    tg_app = build_application()

    logger.info("Bot + WebApp iniciados")
    tg_app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
