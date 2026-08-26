from pathlib import Path


bot_path = Path("bot.py")
bot = bot_path.read_text(encoding="utf-8")

old_import = "from utils.channel_verification_bridge import channel_verification_worker\n"
new_import = (
    "from utils.channel_verification_bridge import channel_verification_worker\n"
    "from utils.telegram_outbox import telegram_outbox_worker\n"
)
if bot.count(old_import) != 1:
    raise SystemExit("bot import marker mismatch")
bot = bot.replace(old_import, new_import, 1)

old_startup = '''        app.bot_data["terms_channel_worker"] = asyncio.create_task(
            channel_verification_worker(app),
            name="terms-channel-verification",
        )
'''
new_startup = '''        app.bot_data["terms_channel_worker"] = asyncio.create_task(
            channel_verification_worker(app),
            name="terms-channel-verification",
        )
        app.bot_data["telegram_outbox_worker"] = asyncio.create_task(
            telegram_outbox_worker(app),
            name="telegram-outbox",
        )
'''
if bot.count(old_startup) != 1:
    raise SystemExit("bot startup marker mismatch")
bot = bot.replace(old_startup, new_startup, 1)

old_shutdown = '''    async def post_shutdown(app: Application):
        task = app.bot_data.pop("terms_channel_worker", None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
'''
new_shutdown = '''    async def post_shutdown(app: Application):
        tasks = [
            app.bot_data.pop("terms_channel_worker", None),
            app.bot_data.pop("telegram_outbox_worker", None),
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
'''
if bot.count(old_shutdown) != 1:
    raise SystemExit("bot shutdown marker mismatch")
bot = bot.replace(old_shutdown, new_shutdown, 1)
bot_path.write_text(bot, encoding="utf-8")


webapp_path = Path("webapp.py")
webapp = webapp_path.read_text(encoding="utf-8")

old_delivery = '''    try:
        await _tg_send_photo(
            chat_id=user_id,
            photo=image,
            caption=(
                "🎁 <b>VOCÊ GANHOU!</b>\\n\\n"
                f"🧧 <code>{char_id}</code>. <b>{name}</b>\\n"
                f"<i>{anime_title}</i>\\n\\n"
                "📦 <b>Adicionado à sua coleção!</b>"
            ),
        )
    except Exception:
        pass
'''
new_delivery = '''    reward_caption = (
        "🎁 <b>VOCÊ GANHOU!</b>\\n\\n"
        f"🧧 <code>{char_id}</code>. <b>{name}</b>\\n"
        f"<i>{anime_title}</i>\\n\\n"
        "📦 <b>Adicionado à sua coleção!</b>"
    )

    try:
        from utils.telegram_outbox import enqueue_photo

        await asyncio.to_thread(
            enqueue_photo,
            dedupe_key=f"dado:{user_id}:{roll_id}",
            chat_id=user_id,
            photo=image,
            caption=reward_caption,
            parse_mode="HTML",
        )
    except Exception as exc:
        print(f"[dado] falha ao enfileirar entrega no chat: {type(exc).__name__}", flush=True)
        try:
            await _tg_send_photo(
                chat_id=user_id,
                photo=image,
                caption=reward_caption,
            )
        except Exception:
            pass
'''
if webapp.count(old_delivery) != 1:
    raise SystemExit("webapp Dado delivery marker mismatch")
webapp = webapp.replace(old_delivery, new_delivery, 1)
webapp_path.write_text(webapp, encoding="utf-8")

print("Dado chat delivery patch applied")
