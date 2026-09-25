"""Repair Telegram's persistent menu independently of command responses and the database."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict

from telegram import MenuButtonWebApp, WebAppInfo
from utils.miniapp_links import miniapp_entrypoint

log = logging.getLogger(__name__)


async def synchronize_menu(bot, chat_id: int | None = None) -> bool:
    try:
        target = miniapp_entrypoint()
        current = await bot.get_chat_menu_button(chat_id=chat_id, read_timeout=6, connect_timeout=4)
        old_url = getattr(getattr(current, 'web_app', None), 'url', None)
        if old_url != target or getattr(current, 'text', None) != 'Abrir Source':
            await bot.set_chat_menu_button(
                chat_id=chat_id,
                menu_button=MenuButtonWebApp(text='Abrir Source', web_app=WebAppInfo(url=target)),
                read_timeout=6, connect_timeout=4,
            )
            verified = await bot.get_chat_menu_button(chat_id=chat_id, read_timeout=6, connect_timeout=4)
            if getattr(getattr(verified, 'web_app', None), 'url', None) != target:
                raise RuntimeError('menu verification failed')
            log.warning('[miniapp-menu] synchronized scope=%s changed_url=%s target=%s',
                        'default' if chat_id is None else 'private', old_url != target, target)
        else:
            log.info('[miniapp-menu] verified scope=%s target=%s',
                     'default' if chat_id is None else 'private', target)
        return True
    except Exception as exc:
        # Exception messages may contain request URLs with credentials: do not log them.
        log.warning('[miniapp-menu] synchronization failed: %s', type(exc).__name__)
        return False


class MiniAppMenuSync:
    def __init__(self, application):
        self.application = application
        self.semaphore = asyncio.Semaphore(2)
        self.pending: set[int | None] = set()
        self.tasks: set[asyncio.Task] = set()
        self.checked: OrderedDict[int | None, float] = OrderedDict()

    def schedule(self, chat_id: int | None = None) -> None:
        now = time.monotonic()
        if chat_id in self.pending or self.checked.get(chat_id, 0) > now or len(self.pending) >= 32:
            return
        self.pending.add(chat_id)
        task = asyncio.create_task(self._run(chat_id), name='source-miniapp-menu-sync')
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, chat_id):
        try:
            async with self.semaphore:
                ok = await asyncio.wait_for(synchronize_menu(self.application.bot, chat_id), timeout=22)
            self.checked[chat_id] = time.monotonic() + (86400 if ok else 300)
            self.checked.move_to_end(chat_id)
            while len(self.checked) > 4096:
                self.checked.popitem(last=False)
        except (TimeoutError, asyncio.TimeoutError):
            self.checked[chat_id] = time.monotonic() + 300
        finally:
            self.pending.discard(chat_id)

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def start_menu_sync(application):
    sync = MiniAppMenuSync(application)
    application.bot_data['miniapp_menu_sync'] = sync
    sync.schedule()
    # Fix existing per-chat overrides for the owner too; do not enumerate/message users.
    for key in ('BOT_OWNER_ID', 'ADMIN_IDS', 'ADMINS'):
        for value in os.getenv(key, '').replace(';', ',').replace(' ', ',').split(','):
            if value.isdecimal() and int(value) > 0:
                sync.schedule(int(value))


async def refresh_private_menu(update, context):
    chat = update.effective_chat
    sync = context.application.bot_data.get('miniapp_menu_sync')
    if chat and chat.type == 'private' and sync:
        sync.schedule(chat.id)
