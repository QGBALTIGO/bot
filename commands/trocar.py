"""Telegram and MiniApp trades share the same ownership and transaction rules."""
import asyncio
from html import escape

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from database_aninexus_social import create_trade_offer, respond_trade_offer
from commands.card import load_characters

TRADE_BANNER = "https://photo.chelpbot.me/AgACAgEAAxkBZpLuKGmeMDP-GReON28AAZjZyLWbT8-JQAACLQxrG4z-8EQzVM7LZb9rOwEAAwIAA3kAAzoE/photo.jpg"
_chars = load_characters()
_ERRORS = {
    "invalid_user": "Escolha outro usuário para a troca.",
    "invalid_character": "Informe dois IDs válidos de personagens.",
    "same_character": "Escolha personagens diferentes para trocar.",
    "private_profile": "Esse usuário está com o perfil privado.",
    "receiver_not_found": "Esse usuário precisa iniciar o bot primeiro.",
    "sender_card_missing": "Você não possui o personagem oferecido.",
    "receiver_card_missing": "O outro usuário não possui esse personagem.",
    "sender_card_reserved": "Seu personagem já está reservado em outra troca.",
    "receiver_card_reserved": "O personagem do outro usuário já está reservado.",
    "forbidden": "Somente o destinatário pode responder a esta troca.",
    "trade_not_found": "Esta proposta não foi encontrada.",
    "trade_not_pending": "Esta proposta já foi respondida ou encerrada.",
    "trade_expired": "Esta proposta expirou. Envie uma nova troca.",
    "card_missing": "A troca foi cancelada: um dos personagens não está mais disponível.",
}

def char_name(cid):
    c = _chars.get(int(cid)) or {}
    return f"<code>{int(cid)}</code>. <b>{escape(str(c.get('name') or 'Personagem'))}</b>"

def mention(user):
    name = escape(str(user.full_name or user.first_name or "Usuário"))
    return f'<a href="tg://user?id={int(user.id)}">{name}</a>'

async def trocar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, sender = update.effective_message, update.effective_user
    if not msg or not sender:
        return
    usage = "Responda à mensagem do outro usuário e envie <code>/trocar SEU_ID ID_DELE</code>."
    receiver = getattr(getattr(msg, "reply_to_message", None), "from_user", None)
    if not receiver or len(context.args) != 2:
        await msg.reply_html(usage)
        return
    try:
        mine, theirs = (int(value) for value in context.args)
        if not (0 < mine < 2**63 and 0 < theirs < 2**63):
            raise ValueError
    except (TypeError, ValueError):
        await msg.reply_html("Os IDs precisam ser números.\n\n" + usage)
        return
    if receiver.is_bot:
        await msg.reply_text("Escolha uma pessoa, não um bot, para a troca.")
        return
    result = await asyncio.to_thread(create_trade_offer, sender.id, receiver.id, mine, theirs)
    if not result.get("ok"):
        await msg.reply_text(_ERRORS.get(result.get("error"), "Não foi possível criar a troca agora."))
        return
    trade_id = int(result["trade_id"])
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aceitar", callback_data=f"trade_accept:{trade_id}"),
        InlineKeyboardButton("❌ Recusar", callback_data=f"trade_reject:{trade_id}"),
    ]])
    text = ("🔁 <b>PROPOSTA DE TROCA</b>\n\n"
            f"👤 <b>De:</b> {mention(sender)}\n👤 <b>Para:</b> {mention(receiver)}\n\n"
            f"🎴 {mention(sender)} oferece: {char_name(mine)}\n"
            f"🎴 {mention(receiver)} oferece: {char_name(theirs)}\n\n"
            "Apenas o destinatário pode aceitar. A proposta vale por 24 horas.")
    try:
        await msg.reply_photo(photo=TRADE_BANNER, caption=text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramError:
        await msg.reply_html(text, reply_markup=keyboard)

async def _respond(update: Update, action: str):
    query = update.callback_query
    if not query:
        return
    try:
        prefix, raw_id = str(query.data or "").split(":", 1)
        trade_id = int(raw_id)
        if prefix != f"trade_{action}" or not 0 < trade_id < 2**63:
            raise ValueError
    except (ValueError, TypeError):
        await query.answer("Proposta inválida. Abra uma nova troca.", show_alert=True)
        return
    result = await asyncio.to_thread(respond_trade_offer, query.from_user.id, trade_id, action)
    if not result.get("ok"):
        await query.answer(_ERRORS.get(result.get("error"), "Não foi possível responder à troca."), show_alert=True)
        return
    text = "✅ Troca realizada com sucesso!" if action == "accept" else "❌ Troca recusada."
    try:
        await query.answer(text)
    except TelegramError:
        # The transaction already committed. Do not repeat it for an expired callback.
        pass
    if query.message:
        try:
            if getattr(query.message, "photo", None):
                await query.message.edit_caption(caption=text, reply_markup=None)
            else:
                await query.message.edit_text(text, reply_markup=None)
        except TelegramError:
            # Old/forwarded messages may not be editable; the terminal DB state is authoritative.
            pass

async def trade_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _respond(update, "accept")

async def trade_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _respond(update, "reject")
