import os
import asyncio
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

# =====================================================
# DATABASE (IMPORTANTE VIR ANTES DOS COMMANDS)
# =====================================================

from database import create_tables

# cria todas as tabelas antes de qualquer import de comando
create_tables()

# =====================================================
# COMMANDS
# =====================================================

from commands.start import start
from commands.menu import menu
from commands.perfil import perfil
from commands.health import health
from commands.reset_users import reset_user, reset_all
from commands.memoria import memoria

from commands.anime import anime
from commands.manga import manga
from commands.avisar import avisar
from commands.baltigoflix import baltigoflix

from commands.cards import cards
from commands.card import card, card_stats_callback
from commands.xcard import xcard, xcard_nav_callback, xcard_stats_callback

from commands.colecao import (
    colecao,
    colecao_callback,
    colecao_s_callback,
    colecao_f_callback,
    colecao_x_callback,
)
from commands.xcolecao import (
    xcolecao,
    xcolecao_callback,
    xcolecao_s_callback,
    xcolecao_f_callback,
    xcolecao_x_callback,
)
from commands.cccolecao import colec

from commands.loja import loja
from commands.daily import daily

from commands.capturar import (
    capturar,
    capture_purchase_callback,
    restore_capture_purchase_runtime,
)
from commands.spawn_personagem import spawn_personagem

from commands.trocar import (
    trocar,
    trade_accept,
    trade_reject,
)
from commands.duelo import duelo, duel_callback

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
    setfoto,
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

from handlers.capture_spawn import capture_message_handler, restore_capture_runtime
from duel_service import restore_duel_runtime
from utils.aninexus_news_publisher import aninexus_news_worker
from utils.channel_verification_bridge import channel_verification_worker
from utils.health_monitor import source_health_monitor
from utils.card_image_review import card_image_review_worker, image_review_callback, review_photos_command
from utils.telegram_outbox import telegram_outbox_worker
from utils.wallhaven_legacy_cleanup import cleanup_legacy_wallhaven_global_images
from utils.worker_supervisor import supervise_worker


# =========================================================
# ENV
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

PORT = int(os.getenv("PORT", "8000"))

try:
    CONCURRENT_UPDATES = int(os.getenv("CONCURRENT_UPDATES", "16"))
except ValueError:
    CONCURRENT_UPDATES = 16
CONCURRENT_UPDATES = max(1, min(64, CONCURRENT_UPDATES))


# =========================================================
# WEBAPP
# =========================================================

def run_webapp():
    try:
        from webapp import app as web_app
        from utils.health_routes import router as health_router

        registered_paths = {getattr(route, "path", "") for route in web_app.routes}
        if "/health" not in registered_paths:
            web_app.include_router(health_router)

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
    error = context.error
    print("[telegram-error]", repr(error), flush=True)
    if error is not None:
        traceback.print_exception(type(error), error, error.__traceback__)


# =========================================================
# COMMAND HANDLERS
# =========================================================

def register_commands(app: Application):
    # básicos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("perfil", perfil))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(CommandHandler("resetuser", reset_user))
    app.add_handler(CommandHandler("resetall", reset_all))
    app.add_handler(CommandHandler("avisar", avisar))
    app.add_handler(CommandHandler("cardcontrib", sugerircard))
    app.add_handler(CommandHandler("baltigoflix", baltigoflix))

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
    app.add_handler(CommandHandler("xcard", xcard))

    # coleção
    app.add_handler(CommandHandler("colecao", colecao))
    app.add_handler(CommandHandler("xcolecao", xcolecao))
    app.add_handler(CommandHandler("colec", colec))

    # economia
    app.add_handler(CommandHandler("loja", loja))
    app.add_handler(CommandHandler("daily", daily))

    # gacha
    app.add_handler(CommandHandler("capturar", capturar))
    app.add_handler(CommandHandler("spawnpersonagem", spawn_personagem))

    # troca
    app.add_handler(CommandHandler("trocar", trocar))
    app.add_handler(CommandHandler("duelo", duelo))

    # ranking
    app.add_handler(CommandHandler("ranking", ranking))

    # misc
    app.add_handler(CommandHandler("pedido", pedido))
    app.add_handler(CommandHandler("nivel", nivel))
    app.add_handler(CommandHandler("memoria", memoria))
    app.add_handler(CommandHandler("memory", memoria))

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
    app.add_handler(CommandHandler("setfoto", setfoto))
    app.add_handler(CommandHandler("revisarfotos", review_photos_command))


# =========================================================
# CALLBACK HANDLERS
# =========================================================

def register_callbacks(app: Application):
    app.add_handler(CallbackQueryHandler(trade_accept, pattern=r"^trade_accept"))
    app.add_handler(CallbackQueryHandler(trade_reject, pattern=r"^trade_reject"))
    app.add_handler(CallbackQueryHandler(duel_callback, pattern=r"^duel"))

    app.add_handler(CallbackQueryHandler(card_stats_callback, pattern=r"^cardstats:"))
    app.add_handler(CallbackQueryHandler(xcard_nav_callback, pattern=r"^xcardnav:"))
    app.add_handler(CallbackQueryHandler(xcard_stats_callback, pattern=r"^xcardstats:"))
    app.add_handler(CallbackQueryHandler(xcard_nav_callback, pattern=r"^xcardnoop$"))
    app.add_handler(CallbackQueryHandler(capture_purchase_callback, pattern=r"^capturebuy:"))

    app.add_handler(CallbackQueryHandler(colecao_callback, pattern=r"^colecao:"))
    app.add_handler(CallbackQueryHandler(colecao_s_callback, pattern=r"^colecao_s:"))
    app.add_handler(CallbackQueryHandler(colecao_f_callback, pattern=r"^colecao_f:"))
    app.add_handler(CallbackQueryHandler(colecao_x_callback, pattern=r"^colecao_x:"))
    app.add_handler(CallbackQueryHandler(xcolecao_callback, pattern=r"^xcolecao:"))
    app.add_handler(CallbackQueryHandler(xcolecao_s_callback, pattern=r"^xcolecao_s:"))
    app.add_handler(CallbackQueryHandler(xcolecao_f_callback, pattern=r"^xcolecao_f:"))
    app.add_handler(CallbackQueryHandler(xcolecao_x_callback, pattern=r"^xcolecao_x:"))
    app.add_handler(CallbackQueryHandler(xcolecao_callback, pattern=r"^xcolecao_noop$"))

    app.add_handler(CallbackQueryHandler(callback_ranking, pattern=r"^rank:"))

    app.add_handler(CallbackQueryHandler(termo_callback, pattern=r"^termo:"))
    app.add_handler(CallbackQueryHandler(image_review_callback, pattern=r"^imgrev:[ar]:\d+$"))


# =========================================================
# MESSAGE HANDLERS
# =========================================================

def register_messages(app: Application):
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, termo_guess),
        group=1,
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, capture_message_handler),
        group=2,
    )


# =========================================================
# APPLICATION
# =========================================================

def build_application():
    async def post_init(app: Application):
        await restore_capture_runtime(app)
        await restore_capture_purchase_runtime(app)
        await restore_duel_runtime(app)
        app.bot_data["terms_channel_worker"] = asyncio.create_task(
            supervise_worker(
                app,
                name="channel_verification",
                worker=channel_verification_worker,
            ),
            name="terms-channel-verification",
        )
        app.bot_data["telegram_outbox_worker"] = asyncio.create_task(
            supervise_worker(
                app,
                name="telegram_outbox",
                worker=telegram_outbox_worker,
            ),
            name="telegram-outbox",
        )
        app.bot_data["aninexus_news_worker"] = asyncio.create_task(
            supervise_worker(
                app,
                name="aninexus_news",
                worker=aninexus_news_worker,
            ),
            name="aninexus-news-channel",
        )
        app.bot_data["source_health_monitor"] = asyncio.create_task(
            supervise_worker(
                app,
                name="source_health",
                worker=source_health_monitor,
            ),
            name="source-health-monitor",
        )
        app.bot_data["card_image_review_worker"] = asyncio.create_task(
            supervise_worker(
                app,
                name="card_image_review",
                worker=card_image_review_worker,
            ),
            name="card-image-review",
        )
        removed_legacy_wallhaven = await asyncio.to_thread(cleanup_legacy_wallhaven_global_images)
        if removed_legacy_wallhaven:
            print(
                f"[wallhaven] overrides legados removidos={removed_legacy_wallhaven}",
                flush=True,
            )

    async def post_shutdown(app: Application):
        tasks = [
            app.bot_data.pop("terms_channel_worker", None),
            app.bot_data.pop("telegram_outbox_worker", None),
            app.bot_data.pop("aninexus_news_worker", None),
            app.bot_data.pop("source_health_monitor", None),
            app.bot_data.pop("card_image_review_worker", None),
        ]
        for task in tasks:
            if task is not None:
                task.cancel()
        for task in tasks:
            if task is None:
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(CONCURRENT_UPDATES)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
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
