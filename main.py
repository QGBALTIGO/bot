import os
import asyncio
import uvicorn

from webapp import app as web_app
from bot import build_app


async def run_all():
    tg_app = build_app()

    # inicia bot
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)

    print("✅ Bot Telegram: polling iniciado")

    # inicia web server (callback)
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(web_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)

    print(f"✅ WebApp: ouvindo na porta {port}")

    try:
        await server.serve()
    finally:
        # encerra bot corretamente
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_all())
