from pathlib import Path

bot = Path("bot.py")
text = bot.read_text(encoding="utf-8")

old = "from utils.wallhaven_bulk_curator import wallhaven_bulk_curator_worker\n"
if old not in text:
    raise SystemExit("legacy worker import not found")
text = text.replace(old, "from utils.wallhaven_legacy_cleanup import cleanup_legacy_wallhaven_global_images\n", 1)

old = '''        app.bot_data["wallhaven_curator_worker"] = asyncio.create_task(\n            wallhaven_bulk_curator_worker(),\n            name="wallhaven-character-curator",\n        )\n'''
if old not in text:
    raise SystemExit("legacy worker task block not found")
text = text.replace(
    old,
    '''        removed_legacy_wallhaven = await asyncio.to_thread(cleanup_legacy_wallhaven_global_images)\n        if removed_legacy_wallhaven:\n            print(\n                f"[wallhaven] overrides legados removidos={removed_legacy_wallhaven}",\n                flush=True,\n            )\n''',
    1,
)

old = '''            app.bot_data.pop("wallhaven_curator_worker", None),\n'''
if old not in text:
    raise SystemExit("legacy worker shutdown entry not found")
text = text.replace(old, "", 1)
bot.write_text(text, encoding="utf-8")

legacy = Path("utils/wallhaven_bulk_curator.py")
text = legacy.read_text(encoding="utf-8")
old = '''ENABLED = os.getenv("WALLHAVEN_CURATOR_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}\n'''
new = '''# Retired legacy runtime curator. Kept only for historical/diagnostic use.\n# It must never start implicitly because curated portraits are now versioned\n# in data/wallhaven_character_overrides.json and validated before deployment.\nENABLED = os.getenv("WALLHAVEN_LEGACY_CURATOR_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}\n'''
if old not in text:
    raise SystemExit("legacy ENABLED declaration not found")
text = text.replace(old, new, 1)
legacy.write_text(text, encoding="utf-8")
