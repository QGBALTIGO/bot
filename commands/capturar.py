import asyncio
import unicodedata
from typing import Dict

from telegram import Update
from telegram.ext import ContextTypes

from handlers.capture_spawn import ACTIVE_SPAWNS
from database import add_coin, add_progress_xp


_capture_locks: Dict[int, asyncio.Lock] = {}


def _get_capture_lock(chat_id: int) -> asyncio.Lock:
    lock = _capture_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _capture_locks[chat_id] = lock
    return lock


def normalize(text: str) -> str:
    text = str(text or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(text.strip().split())


async def capturar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat_id = update.effective_chat.id

    if not context.args:
        return

    lock = _get_capture_lock(chat_id)

    async with lock:
        spawn = ACTIVE_SPAWNS.get(chat_id)
        if not spawn:
            return

        character = spawn.get("character") or {}
        correct_name = normalize(character.get("name", ""))
        guess = normalize(" ".join(context.args))

        if not correct_name or guess != correct_name:
            return

        user = update.effective_user

        try:
            add_coin(user.id, 1)
        except Exception:
            pass

        try:
            add_progress_xp(user.id, 10)
        except Exception:
            pass

        text = (
            "🎉 <b>CAPTURADO!</b>\n\n"
            f"👤 <b>{character.get('name', 'Sem nome')}</b>\n"
            f"📺 {character.get('anime', 'Obra desconhecida')}\n\n"
            "💰 +1 coin\n"
            "⭐ +10 XP"
        )

        image = str(character.get("image") or "").strip()

        try:
            if image:
                await update.message.reply_photo(
                    photo=image,
                    caption=text,
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_html(text)
        finally:
            ACTIVE_SPAWNS.pop(chat_id, None)
