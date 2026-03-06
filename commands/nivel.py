import asyncio
from typing import Dict

from telegram import Update
from telegram.ext import ContextTypes

from database import (
    add_progress_xp,
    create_or_get_user,
    get_progress_row,
    get_user_level_rank,
    get_level_progress_values,
)
from level_system import (
    build_progress_bar,
    format_rank_position,
    get_level_theme,
)

_level_locks: Dict[int, asyncio.Lock] = {}


def _get_level_lock(user_id: int) -> asyncio.Lock:
    lock = _level_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _level_locks[user_id] = lock
    return lock


async def register_progress(update: Update, xp_gain: int = 3):
    """
    Chame isso nos comandos que você quiser que contem para evolução.
    Não mostra para o usuário que é por comando.
    """
    user = update.effective_user
    if not user:
        return

    user_id = user.id
    create_or_get_user(user_id)

    lock = _get_level_lock(user_id)
    async with lock:
        data = add_progress_xp(user_id, xp_gain)

    old_level = int(data["old_level"])
    new_level = int(data["new_level"])

    if new_level > old_level and update.message:
        theme = get_level_theme(new_level)

        msg = (
            "🎉 <b>EVOLUÇÃO!</b>\n\n"
            f"👤 <b>{user.first_name}</b>\n"
            f"{theme['icon']} <b>{theme['tag']}</b>\n\n"
            f"⬆️ Você alcançou o <b>Nível {new_level}</b>!"
        )
        await update.message.reply_html(msg)


async def nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    user_id = user.id

    create_or_get_user(user_id)

    row = get_progress_row(user_id)
    if not row:
        await update.message.reply_text("❌ Não consegui carregar seu progresso.")
        return

    xp = int(row["xp"] or 0)
    level = int(row["level"] or 1)

    values = get_level_progress_values(xp)
    rank_pos = get_user_level_rank(user_id)

    current = int(values["xp_current"])
    total = int(values["xp_needed"])
    remaining = int(values["xp_remaining"])

    bar = build_progress_bar(current, total, size=10)
    theme = get_level_theme(level)

    msg = (
        "🏆 <b>SEU PROGRESSO</b>\n\n"
        f"👤 <b>{user.first_name}</b>\n"
        f"{theme['icon']} <b>{theme['tag']}</b>\n\n"
        f"⭐ <b>Nível:</b> {level}\n"
        f"🏅 <b>Ranking:</b> {format_rank_position(rank_pos)}\n\n"
        f"{bar}\n"
        f"<b>{current}/{total}</b>\n"
        f"Faltam <b>{remaining}</b> para o próximo nível."
    )

    await update.message.reply_html(msg)
