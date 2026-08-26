from __future__ import annotations

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cards_service import build_cards_final_data
from trade_repository import TRADE_TTL_SECONDS, create_trade, get_trade, resolve_trade
from utils.runtime_guard import rate_limiter


TRADE_BANNER = "https://photo.chelpbot.me/AgACAgEAAxkBZpLuKGmeMDP-GReON28AAZjZyLWbT8-JQAACLQxrG4z-8EQzVM7LZb9rOwEAAwIAA3kAAzoE/photo.jpg"


def _character(character_id: int):
    return (build_cards_final_data().get("characters_by_id") or {}).get(int(character_id))


def _char_line(character_id: int) -> str:
    char = _character(character_id) or {}
    return (
        f"<code>{int(character_id)}</code> • "
        f"<b>{escape(str(char.get('name') or 'Personagem'))}</b> "
        f"<i>({escape(str(char.get('anime') or 'Obra desconhecida'))})</i>"
    )


def _mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={int(user_id)}">{escape(str(name or "Jogador"))}</a>'


def _keyboard(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Aceitar", callback_data=f"tradev2:accept:{trade_id}"),
                InlineKeyboardButton("❌ Recusar", callback_data=f"tradev2:reject:{trade_id}"),
            ],
            [InlineKeyboardButton("🗑 Cancelar proposta", callback_data=f"tradev2:cancel:{trade_id}")],
        ]
    )


async def trocar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    if str(chat.type) not in {"group", "supergroup"}:
        await message.reply_html("🔁 <b>Trocas são feitas em grupos.</b> Responda a mensagem de outro jogador.")
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_html(
            "🔁 <b>Como trocar</b>\n\n"
            "Responda a mensagem do outro jogador usando:\n"
            "<code>/trocar SEU_ID ID_DELE</code>"
        )
        return
    if len(context.args or []) != 2:
        await message.reply_html("⚠️ Informe exatamente duas cartas: <code>/trocar SEU_ID ID_DELE</code>")
        return

    target = message.reply_to_message.from_user
    if int(target.id) == int(user.id):
        await message.reply_text("⚠️ Você não pode trocar consigo mesmo.")
        return
    if bool(getattr(target, "is_bot", False)):
        await message.reply_text("⚠️ Bots não podem participar de trocas.")
        return
    if not await rate_limiter.allow(f"trade:create:{int(user.id)}", limit=3, window_seconds=30):
        await message.reply_text("⚠️ Muitas propostas em sequência. Espere um pouco.")
        return

    try:
        my_char = int(context.args[0])
        target_char = int(context.args[1])
    except (TypeError, ValueError):
        await message.reply_text("⚠️ Os IDs das cartas precisam ser números.")
        return
    if not _character(my_char):
        await message.reply_html(f"⚠️ A carta <code>{my_char}</code> não existe no catálogo atual.")
        return
    if not _character(target_char):
        await message.reply_html(f"⚠️ A carta <code>{target_char}</code> não existe no catálogo atual.")
        return

    result = create_trade(int(user.id), int(target.id), my_char, target_char)
    if not result.get("ok"):
        error = str(result.get("error") or "")
        messages = {
            "same_character": "Trocar a mesma carta não altera nenhuma coleção.",
            "user_busy": "Um dos jogadores já está em outra proposta pendente.",
            "from_missing_card": "Você não possui a carta que está oferecendo.",
            "to_missing_card": "O outro jogador não possui a carta solicitada.",
        }
        await message.reply_text("⚠️ " + messages.get(error, "Não foi possível criar essa troca."))
        return

    trade = result["trade"]
    from_name = str(user.full_name or user.first_name or user.username or "Jogador")
    target_name = str(target.full_name or target.first_name or target.username or "Jogador")
    text = (
        "🔁 <b>PROPOSTA DE TROCA V2</b>\n\n"
        f"{_mention(user.id, from_name)} oferece:\n➡️ {_char_line(my_char)}\n\n"
        f"{_mention(target.id, target_name)} entrega:\n⬅️ {_char_line(target_char)}\n\n"
        f"⏳ A proposta expira em <b>{TRADE_TTL_SECONDS // 60} minutos</b>.\n"
        "<i>A propriedade das duas cartas será validada novamente no aceite.</i>"
    )
    try:
        await message.reply_photo(
            photo=TRADE_BANNER,
            caption=text,
            parse_mode="HTML",
            reply_markup=_keyboard(int(trade["id"])),
        )
    except Exception:
        await message.reply_html(text, reply_markup=_keyboard(int(trade["id"])))


async def trade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user or not query.data:
        return
    try:
        _, action, raw_id = str(query.data).split(":", 2)
        trade_id = int(raw_id)
    except (ValueError, TypeError):
        await query.answer("Troca inválida.", show_alert=True)
        return

    if not await rate_limiter.allow(f"trade:action:{int(user.id)}", limit=6, window_seconds=15):
        await query.answer("Espere um instante.", show_alert=True)
        return

    result = resolve_trade(trade_id, int(user.id), action)
    if not result.get("ok"):
        error = str(result.get("error") or "")
        messages = {
            "not_found": "Essa troca não existe.",
            "not_pending": "Essa troca já foi encerrada.",
            "expired": "Essa proposta expirou.",
            "not_target": "Somente o jogador desafiado pode aceitar ou recusar.",
            "not_owner": "Somente quem criou a proposta pode cancelá-la.",
            "card_unavailable": "Uma das cartas deixou de estar disponível; a troca foi invalidada.",
        }
        await query.answer(messages.get(error, "Não foi possível concluir essa troca."), show_alert=True)
        if error in {"expired", "card_unavailable", "not_pending"} and query.message:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        return

    trade = result.get("trade") or get_trade(trade_id) or {}
    status = str(trade.get("status") or "")
    if status == "accepted":
        text = (
            "✅ <b>TROCA CONCLUÍDA</b>\n\n"
            f"➡️ {_char_line(int(trade.get('from_character_id') or 0))}\n"
            f"⬅️ {_char_line(int(trade.get('to_character_id') or 0))}\n\n"
            "As duas coleções foram atualizadas na mesma transação."
        )
        await query.answer("Troca realizada!")
    elif status == "rejected":
        text = "❌ <b>TROCA RECUSADA</b>\n\nNenhuma coleção foi alterada."
        await query.answer("Troca recusada.")
    else:
        text = "🗑 <b>PROPOSTA CANCELADA</b>\n\nNenhuma coleção foi alterada."
        await query.answer("Proposta cancelada.")

    if query.message:
        try:
            if query.message.photo:
                await query.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=None)
            else:
                await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=None)
        except Exception:
            pass
