from __future__ import annotations

from pathlib import Path


BOT = Path("bot.py")
WEBAPP = Path("webapp.py")

bot = BOT.read_text(encoding="utf-8")
webapp = WEBAPP.read_text(encoding="utf-8")

# 1) Start the strict bulk curator from the real Telegram bot process.
import_anchor = "from utils.telegram_outbox import telegram_outbox_worker\n"
import_replacement = import_anchor + "from utils.wallhaven_bulk_curator import wallhaven_bulk_curator_worker\n"
if "from utils.wallhaven_bulk_curator import wallhaven_bulk_curator_worker" not in bot:
    if import_anchor not in bot:
        raise SystemExit("bot import anchor not found")
    bot = bot.replace(import_anchor, import_replacement, 1)

outbox_task = '''        app.bot_data["telegram_outbox_worker"] = asyncio.create_task(
            telegram_outbox_worker(app),
            name="telegram-outbox",
        )
'''
curator_task = outbox_task + '''        app.bot_data["wallhaven_curator_worker"] = asyncio.create_task(
            wallhaven_bulk_curator_worker(),
            name="wallhaven-character-curator",
        )
'''
if 'app.bot_data["wallhaven_curator_worker"]' not in bot:
    if outbox_task not in bot:
        raise SystemExit("post_init outbox anchor not found")
    bot = bot.replace(outbox_task, curator_task, 1)

shutdown_anchor = '''            app.bot_data.pop("terms_channel_worker", None),
            app.bot_data.pop("telegram_outbox_worker", None),
'''
shutdown_replacement = shutdown_anchor + '''            app.bot_data.pop("wallhaven_curator_worker", None),
'''
if 'app.bot_data.pop("wallhaven_curator_worker", None)' not in bot:
    if shutdown_anchor not in bot:
        raise SystemExit("shutdown task anchor not found")
    bot = bot.replace(shutdown_anchor, shutdown_replacement, 1)

# 2) Dado must use the already-curated global image instead of querying Wallhaven on reward.
resolver_marker = "from utils.character_image_resolver import resolve_character_portrait"
if resolver_marker in webapp:
    marker_index = webapp.index(resolver_marker)
    start = webapp.rfind("\n    try:\n", 0, marker_index)
    end = webapp.find("\n    reward_caption =", marker_index)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("unable to isolate old runtime resolver block")
    replacement = '''
    try:
        from cards_service import get_character_by_id

        global_character = get_character_by_id(char_id)
        global_image = str((global_character or {}).get("image") or "").strip()
        if global_image:
            image = global_image
    except Exception as exc:
        print(f"[dado] falha ao aplicar imagem global: {type(exc).__name__}", flush=True)
'''
    webapp = webapp[:start] + replacement + webapp[end:]
elif "global_character = get_character_by_id(char_id)" not in webapp:
    raise SystemExit("neither old resolver nor new global-image block found")

BOT.write_text(bot, encoding="utf-8")
WEBAPP.write_text(webapp, encoding="utf-8")
