import html

from telegram import Update
from telegram.ext import ContextTypes

from database import (
    create_or_get_user,
    get_level_progress_values,
    get_progress_row,
    get_user_level_rank,
)
from level_system import (
    build_progress_bar,
    format_rank_position,
    get_level_theme,
)
from progress_repository import add_progress_xp_atomic


async def register_progress(update: Update, xp_gain: int = 3):
    """Register XP for an allowed action using a PostgreSQL row lock."""

    user = update.effective_user
    if not user:
        return

    user_id = user.id
    create_or_get_user(user_id)
    data = add_progress_xp_atomic(user_id, xp_gain)

    old_level = int(data["old_level"])
    new_level = int(data["new_level"])

    if new_level > old_level and update.effective_message:
        theme = get_level_theme(new_level)
        safe_name = html.escape(user.first_name or "Navegante", quote=False)

        message = (
            "🎉 <b>EVOLUÇÃO!</b>\n\n"
            f"👤 <b>{safe_name}</b>\n"
            f"{theme['icon']} <b>{theme['tag']}</b>\n\n"
            f"⬆️ Você alcançou o <b>Nível {new_level}</b>!"
        )
        await update.effective_message.reply_html(message)


async def nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not user or not message:
        return

    # Import local avoids a circular import: gatekeeper imports register_progress.
    from utils.gatekeeper import gatekeeper

    ok, blocked_message = await gatekeeper(update, context)
    if not ok:
        if blocked_message:
            await message.reply_html(blocked_message)
        return

    user_id = user.id
    create_or_get_user(user_id)

    row = get_progress_row(user_id)
    if not row:
        await message.reply_text("❌ Não consegui carregar seu progresso.")
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
    safe_name = html.escape(user.first_name or "Navegante", quote=False)

    text = (
        "🏆 <b>SEU PROGRESSO</b>\n\n"
        f"👤 <b>{safe_name}</b>\n"
        f"{theme['icon']} <b>{theme['tag']}</b>\n\n"
        f"⭐ <b>Nível:</b> {level}\n"
        f"🏅 <b>Ranking:</b> {format_rank_position(rank_pos)}\n\n"
        f"{bar}\n"
        f"<b>{current}/{total}</b>\n"
        f"Faltam <b>{remaining}</b> para o próximo nível."
    )

    await message.reply_html(text)
