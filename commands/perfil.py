from telegram import Update
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper

from database import (
    create_or_get_user,
    get_user_row,
    count_collection,
    get_progress_row,
    get_user_level_rank,
    get_friend_count,
    get_user_favorite_card_quantity,
)

from level_system import get_level_theme


def fmt_num(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def get_dup_emoji(qty: int) -> str:
    if qty >= 20:
        return " 👑"
    elif qty >= 15:
        return " 🌟"
    elif qty >= 10:
        return " ⭐"
    elif qty >= 5:
        return " 💫"
    elif qty >= 2:
        return " ✨"
    return ""


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    # ========================
    # GATEKEEPER
    # ========================
    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if msg and bloqueio:
            await msg.reply_html(bloqueio)
        return

    if not update.effective_user or not msg:
        return

    viewer = update.effective_user
    viewer_id = viewer.id

    create_or_get_user(viewer_id)


    row = get_user_row(viewer_id)
    if not row:
        await msg.reply_text("❌ Não consegui carregar o perfil agora.")
        return

    user_id = int(row["user_id"])
    nick = row.get("nick") or viewer.first_name or "User"
    coins = int(row.get("coins") or 0)

    fav_name = row.get("fav_name")
    fav_image = row.get("fav_image")

    # coleção
    total_colecao = int(count_collection(user_id) or 0)

    # progresso
    progress = get_progress_row(user_id) or {}
    level = int(progress.get("level") or 1)
    rank = int(get_user_level_rank(user_id) or 0)

    theme = get_level_theme(level)
    rank_tag = theme["tag"]

    # amizade
    amizade_total = int(get_friend_count(user_id) or 0)

    # favorito
    fav_qty = int(get_user_favorite_card_quantity(user_id) or 0)
    fav_emoji = get_dup_emoji(fav_qty)

    texto = (
        "🎴 <b>PERFIL DO USUÁRIO</b>\n\n"
        f"👤 | <b>{nick}</b>\n\n"
        f"📚 | <i>Coleção</i>: <b>{fmt_num(total_colecao)}</b>\n"
        f"🪙 | <i>Coins</i>: <b>{fmt_num(coins)}</b>\n"
        f"⭐ | <i>Nível</i>: <b>{fmt_num(level)}</b>\n"
        f"🤝 | <i>Amizades</i>: <b>{fmt_num(amizade_total)}</b>\n\n"
        "❤️ <i>Favorito</i>:\n"
    )

    if fav_name:
        texto += f"🧧 <b>{fav_name}{fav_emoji}</b>"
    else:
        texto += "— Nenhum favorito"

    if fav_image:
        await msg.reply_photo(
            photo=fav_image,
            caption=texto,
            parse_mode="HTML",
        )
    else:
        await msg.reply_html(texto)
