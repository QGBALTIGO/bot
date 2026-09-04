from __future__ import annotations

import asyncio
import html
import os
import time

from telegram import Update
from telegram.ext import ContextTypes

from utils.system_health import (
    application_version,
    database_snapshot,
    uptime_seconds,
    worker_snapshot,
)


def _parse_admin_ids() -> set[int]:
    out: set[int] = set()
    for name in ("BOT_OWNER_ID", "ADMINS", "ADMIN_IDS", "CARD_ADMIN_IDS"):
        raw = str(os.getenv(name, "") or "")
        for part in raw.replace(";", ",").split(","):
            value = part.strip()
            if not value:
                continue
            try:
                user_id = int(value)
            except ValueError:
                continue
            if user_id > 0:
                out.add(user_id)
    return out


def _duration_label(total_seconds: int) -> str:
    seconds = max(0, int(total_seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _status_icon(ok: bool) -> str:
    return "🟢" if ok else "🔴"


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    if int(user.id) not in _parse_admin_ids():
        await message.reply_text("Comando disponível apenas para a administração.")
        return

    db_task = asyncio.to_thread(database_snapshot)

    telegram_started = time.perf_counter()
    try:
        bot_info = await context.bot.get_me()
        telegram_ok = bool(bot_info and bot_info.id)
        telegram_error = ""
    except Exception as exc:
        telegram_ok = False
        telegram_error = type(exc).__name__
    telegram_ms = round((time.perf_counter() - telegram_started) * 1000, 2)

    database = await db_task
    workers = worker_snapshot(context.application)

    worker_lines = []
    workers_ok = True
    for label, state in workers.items():
        ok = bool(state.get("ok"))
        workers_ok = workers_ok and ok
        worker_lines.append(
            f"{_status_icon(ok)} <code>{html.escape(label)}</code>: "
            f"{html.escape(str(state.get('status') or 'unknown'))}"
        )

    overall_ok = bool(database.get("ok")) and telegram_ok and workers_ok
    title_icon = "🟢" if overall_ok else "🟡"

    telegram_detail = f"{telegram_ms} ms"
    if telegram_error:
        telegram_detail += f" · {telegram_error}"

    text = (
        f"{title_icon} <b>SOURCE HEALTH</b>\n\n"
        f"{_status_icon(telegram_ok)} <b>Telegram:</b> <code>{html.escape(telegram_detail)}</code>\n"
        f"{_status_icon(bool(database.get('ok')))} <b>PostgreSQL:</b> "
        f"<code>{database.get('duration_ms', 0)} ms</code>\n\n"
        "<b>Workers</b>\n"
        + "\n".join(worker_lines)
        + "\n\n"
        f"⏱ <b>Uptime:</b> <code>{_duration_label(uptime_seconds())}</code>\n"
        f"🏷 <b>Versão:</b> <code>{html.escape(application_version())}</code>"
    )

    await message.reply_html(text)
