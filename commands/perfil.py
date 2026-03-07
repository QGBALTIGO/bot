from telegram import Update
from telegram.ext import ContextTypes

from database import (
    create_or_get_user,
    get_user_row,
    count_collection,
    get_progress_row,
    get_friend_count,
    get_user_favorite_card_quantity,
)


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.effective_message
    user = update.effective_user
    user_id = user.id

    try:

        create_or_get_user(user_id)

        row = get_user_row(user_id) or {}

        coins = int(row.get("coins", 0))
        dados = int(row.get("dice", 0))

        total_colecao = int(count_collection(user_id) or 0)

        progress = get_progress_row(user_id) or {}

        xp = int(progress.get("xp", 0))
        level = int(progress.get("level", 1))

        friends = int(get_friend_count(user_id) or 0)

        fav_name = row.get("fav_name")
        fav_image = row.get("fav_image")

        fav_qty = 0

        if fav_name:
            fav_qty = int(get_user_favorite_card_quantity(user_id) or 0)

        text = (
            f"👤 <b>{user.first_name}</b>\n\n"
            f"🪙 Moedas: <b>{coins}</b>\n"
            f"🎲 Dados: <b>{dados}</b>\n\n"
            f"🎴 Coleção: <b>{total_colecao}</b>\n"
            f"⭐ Nível: <b>{level}</b>\n"
            f"✨ XP: <b>{xp}</b>\n\n"
            f"👥 Amigos: <b>{friends}</b>"
        )

        if fav_name:

            text += (
                f"\n\n💖 Favorito:\n"
                f"<b>{fav_name}</b>\n"
                f"Qtd: <b>{fav_qty}</b>"
            )

        if fav_image:

            await msg.reply_photo(
                photo=fav_image,
                caption=text,
                parse_mode="HTML",
            )

        else:

            await msg.reply_text(
                text,
                parse_mode="HTML",
            )

    except Exception as e:

        await msg.reply_text(f"❌ Erro no /perfil: {e}")
