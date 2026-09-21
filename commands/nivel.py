import asyncio

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
from utils.runtime_guard import lock_manager


def _register_progress_sync(user_id: int, xp_gain: int):
    create_or_get_user(int(user_id))
    return add_progress_xp(int(user_id), int(xp_gain))


def _load_level_sync(user_id: int):
    create_or_get_user(int(user_id))
    row = get_progress_row(int(user_id))
    if not row:
        return None, 0
    rank_pos = get_user_level_rank(int(user_id))
    return row, rank_pos


async def register_progress(update: Update, xp_gain: int = 3):
    """
    Chame isso nos comandos que você quiser que contem para evolução.
    Não mostra para o usuário que é por comando.
    """
    user = update.effective_user
    if not user:
        return

    user_id = int(user.id)
    lock = await lock_manager.acquire(f"level-progress:{user_id}")
    try:
        data = await asyncio.to_thread(
            _register_progress_sync,
            user_id,
            int(xp_gain),
        )
    finally:
        lock.release()

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
    user_id = int(user.id)

    row, rank_pos = await asyncio.to_thread(_load_level_sync, user_id)
    if not row:
        await update.message.reply_text("❌ Não consegui carregar seu progresso.")
        return

    xp = int(row["xp"] or 0)
    level = int(row["level"] or 1)

    values = get_level_progress_values(xp)

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
