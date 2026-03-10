import asyncio

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from telegram.ext import ContextTypes

from database import (
    create_trade,
    get_trade,
    set_trade_status,
    swap_characters_atomic,
)

from commands.card import load_characters


TRADE_BANNER = "https://photo.chelpbot.me/AgACAgEAAxkBZpLuKGmeMDP-GReON28AAZjZyLWbT8-JQAACLQxrG4z-8EQzVM7LZb9rOwEAAwIAA3kAAzoE/photo.jpg"

_chars = load_characters()


def char_name(cid):

    c = _chars.get(int(cid))

    if not c:
        return f"<code>{cid}</code>"

    return f"<code>{cid}</code>. <b>{c['name']}</b>"


def mention(user):

    name = user.full_name or user.first_name or "User"

    return f'<a href="tg://user?id={user.id}">{name}</a>'


# =========================================================
# /trocar
# =========================================================

async def trocar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.message

    if not msg.reply_to_message:
        await msg.reply_html(
            "❌ <b>Troca inválida</b>\n\n"
            "Responda o usuário.\n\n"
            "<code>/trocar SEU_ID ID_DELE</code>"
        )
        return

    if len(context.args) != 2:
        return

    try:
        my_char = int(context.args[0])
        other_char = int(context.args[1])
    except:
        return

    from_user = update.effective_user
    to_user = msg.reply_to_message.from_user

    if to_user.id == from_user.id:
        return

    trade_id = create_trade(
        from_user.id,
        to_user.id,
        my_char,
        other_char
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Aceitar",
                callback_data=f"trade_accept:{trade_id}"
            ),
            InlineKeyboardButton(
                "❌ Recusar",
                callback_data=f"trade_reject:{trade_id}"
            )
        ]
    ])

    text = (
        "🔁 <b>PROPOSTA DE TROCA</b>\n\n"
        f"👤 <b>De:</b> {mention(from_user)}\n"
        f"👤 <b>Para:</b> {mention(to_user)}\n\n"
        "🎴 <b>Oferta</b>\n"
        f"➡️ {mention(from_user)} oferece: {char_name(my_char)}\n"
        f"⬅️ {mention(to_user)} oferece: {char_name(other_char)}\n\n"
        "⚠️ Apenas o usuário marcado pode aceitar."
    )

    await msg.reply_photo(
        photo=TRADE_BANNER,
        caption=text,
        parse_mode="HTML",
        reply_markup=kb
    )


# =========================================================
# ACCEPT
# =========================================================

async def trade_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    trade_id = int(q.data.split(":")[1])

    trade = get_trade(trade_id)

    if not trade:
        return

    if q.from_user.id != trade["to_user"]:
        await q.answer("Essa troca não é sua.",show_alert=True)
        return

    ok = swap_characters_atomic(trade_id)

    if not ok:
        return

    await q.message.edit_caption(
        "✅ <b>Troca realizada com sucesso!</b>",
        parse_mode="HTML"
    )


# =========================================================
# REJECT
# =========================================================

async def trade_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    trade_id = int(q.data.split(":")[1])

    trade = get_trade(trade_id)

    if not trade:
        return

    if q.from_user.id != trade["to_user"]:
        return

    set_trade_status(trade_id,"rejected")

    await q.message.edit_caption(
        "❌ <b>Troca recusada.</b>",
        parse_mode="HTML"
    )
