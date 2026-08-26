import asyncio
import logging
import os
import threading

import uvicorn
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from admin_repository import create_admin_tables
from capture_repository import create_capture_tables
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
from commands.collection import colecao
from commands.contrib_v2 import contribuir, sugerircard
from commands.duel_v2 import duel_callback, duelo
from commands.game import dado, daily, giro, jogar
from commands.hub_v2 import (
    atividade,
    agenda,
    ajuda,
    amigos,
    configuracoes,
    conquistas,
    favoritos,
    hub,
    menu,
    missoes,
    noticias,
    notificacoes,
    recomendar,
    watchlist,
)
from commands.manga import manga
from commands.memory_v2 import memoria
from commands.messages_v2 import (
    bloquearmsg,
    denunciarmsg,
    desbloquearmsg,
    mensagens,
    msg,
    msganon,
    msgconfig,
    msgtutorial,
)
from commands.nivel import nivel
from commands.pedido import pedido
from commands.profile import perfil
from commands.ranking_v2 import ranking
from commands.shop_v2 import loja
from commands.start import start
from commands.termo_v2 import termo
from commands.trade_v2 import trade_callback, trocar
from commands.xcards_v2 import xcard, xcolecao
from contrib_repository import create_contribution_tables
from database import create_tables
from duel_repository_v2 import create_duel_v2_tables
from ecosystem_repository import create_ecosystem_tables
from game_repository import create_game_tables
from handlers.capture_v2 import capturar, capture_activity_handler, capture_buy_callback, restore_capture_runtime
from identity_repository import create_identity_tables
from memory_repository import create_memory_v2_tables
from messages_repository import create_message_tables_v2
from news_sync import start_news_worker
from shop_repository import create_shop_tables
from termo_repository import create_termo_v2_tables
from trade_repository import create_trade_tables
from utils.public_url import get_public_base_url
from xcards_repository import create_xcard_tables

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

ENABLE_MESSAGES = os.getenv("ENABLE_MESSAGES", "true").strip().lower() in {"1", "true", "yes", "on"}
_WEB_THREAD: threading.Thread | None = None


def run_webapp() -> None:
    try:
        from secure_webapp import app as web_app
        logger.info("WebApp V2 iniciando em 0.0.0.0:%s base=%s", PORT, get_public_base_url() or "<sem-url>")
        uvicorn.run(web_app, host="0.0.0.0", port=PORT, log_level="info")
    except Exception:
        logger.exception("Falha fatal ao iniciar a WebApp")
        raise


async def _watch_webapp_thread() -> None:
    while True:
        await asyncio.sleep(5)
        thread = _WEB_THREAD
        if thread is not None and not thread.is_alive():
            logger.critical("Thread da WebApp morreu; encerrando processo para o Railway reiniciar o serviço.")
            os._exit(1)


async def on_error(update, context) -> None:
    error = getattr(context, "error", None)
    if error is None:
        logger.error("Erro do Telegram sem exceção associada. update=%r", update)
        return
    logger.error("Erro não tratado no Telegram. update=%r", update, exc_info=(type(error), error, error.__traceback__))


async def on_post_init(application: Application) -> None:
    await restore_capture_runtime(application)
    start_news_worker()
    application.create_task(_watch_webapp_thread(), name="webapp-watchdog")


def _register_message_handlers(tg_app: Application) -> None:
    if not ENABLE_MESSAGES:
        logger.info("Sistema de mensagens V2 desativado por ENABLE_MESSAGES=false")
        return
    tg_app.add_handler(CommandHandler("msg", msg))
    tg_app.add_handler(CommandHandler("msganon", msganon))
    tg_app.add_handler(CommandHandler("mensagens", mensagens))
    tg_app.add_handler(CommandHandler("msgtutorial", msgtutorial))
    tg_app.add_handler(CommandHandler("bloquearmsg", bloquearmsg))
    tg_app.add_handler(CommandHandler("desbloquearmsg", desbloquearmsg))
    tg_app.add_handler(CommandHandler("msgconfig", msgconfig))
    tg_app.add_handler(CommandHandler("denunciarmsg", denunciarmsg))


def build_application() -> Application:
    tg_app = Application.builder().token(BOT_TOKEN).post_init(on_post_init).build()

    for name, handler in (
        ("start", start), ("hub", hub), ("menu", menu), ("ajuda", ajuda),
        ("configuracoes", configuracoes), ("notificacoes", notificacoes), ("atividade", atividade),
        ("favoritos", favoritos), ("watchlist", watchlist), ("agenda", agenda), ("noticias", noticias),
        ("recomendar", recomendar), ("amigos", amigos), ("missoes", missoes), ("conquistas", conquistas),
    ):
        tg_app.add_handler(CommandHandler(name, handler))

    for name, handler in (
        ("anime", anime), ("manga", manga), ("cards", cards), ("pedido", pedido),
        ("baltigoflix", baltigoflix), ("contribuir", contribuir), ("sugerircard", sugerircard),
    ):
        tg_app.add_handler(CommandHandler(name, handler))
    tg_app.add_handler(CommandHandler("card", card))
    tg_app.add_handler(CallbackQueryHandler(card_stats_callback, pattern=r"^cardstats:"))

    for name, handler in (("nivel", nivel), ("colecao", colecao), ("perfil", perfil), ("ranking", ranking), ("loja", loja)):
        tg_app.add_handler(CommandHandler(name, handler))

    for name, handler in (("jogar", jogar), ("daily", daily), ("dado", dado), ("giro", giro), ("memoria", memoria), ("termo", termo)):
        tg_app.add_handler(CommandHandler(name, handler))

    tg_app.add_handler(CommandHandler("xcard", xcard))
    tg_app.add_handler(CommandHandler("xcolecao", xcolecao))

    tg_app.add_handler(CommandHandler("trocar", trocar))
    tg_app.add_handler(CallbackQueryHandler(trade_callback, pattern=r"^tradev2:"))
    tg_app.add_handler(CommandHandler("duelo", duelo))
    tg_app.add_handler(CallbackQueryHandler(duel_callback, pattern=r"^duelv2:"))
    tg_app.add_handler(CommandHandler("capturar", capturar))
    tg_app.add_handler(CallbackQueryHandler(capture_buy_callback, pattern=r"^capbuy:"))
    tg_app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, capture_activity_handler), group=1)

    _register_message_handlers(tg_app)

    for name, handler in (
        ("card_reload", card_reload), ("card_delchar", card_delchar), ("card_addchar", card_addchar),
        ("card_setcharimg", card_setcharimg), ("card_setcharname", card_setcharname),
        ("card_delanime", card_delanime), ("card_addanime", card_addanime),
        ("card_setanimebanner", card_setanimebanner), ("card_setanimecover", card_setanimecover),
        ("card_addsubcat", card_addsubcat), ("card_delsubcat", card_delsubcat),
        ("card_subadd", card_subadd), ("card_subremove", card_subremove),
    ):
        tg_app.add_handler(CommandHandler(name, handler))

    tg_app.add_error_handler(on_error)
    return tg_app


def main() -> None:
    global _WEB_THREAD
    logger.info("Inicializando banco de dados")
    create_tables()
    create_game_tables()
    create_identity_tables()
    create_shop_tables()
    create_capture_tables()
    create_trade_tables()
    create_xcard_tables()
    create_duel_v2_tables()
    create_memory_v2_tables()
    create_termo_v2_tables()
    create_admin_tables()
    create_contribution_tables()
    create_message_tables_v2()
    create_ecosystem_tables()

    _WEB_THREAD = threading.Thread(target=run_webapp, name="source-baltigo-webapp", daemon=True)
    _WEB_THREAD.start()

    tg_app = build_application()
    logger.info("Bot + WebApp V2 iniciados base=%s", get_public_base_url() or "<sem-url>")
    tg_app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
