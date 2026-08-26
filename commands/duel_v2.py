from __future__ import annotations

import html
import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from duel_engine import format_team_lines, get_alive_slots
from duel_repository_v2 import (
    DuelBusy,
    DuelError,
    DuelInvalidState,
    DuelNotEnoughCards,
    DuelNotParticipant,
    DuelSelectionError,
    confirm_selection,
    create_challenge,
    get_duel,
    respond_challenge,
    set_group_message,
    submit_pick,
    toggle_selection,
)
from xcards_repository import get_user_xcards


PAGE_SIZE = 6


def _safe_name(value: str) -> str:
    return html.escape(str(value or "Jogador"), quote=False)


def _group_keyboard(duel: dict) -> InlineKeyboardMarkup | None:
    if str(duel.get("state") or "") != "pending":
        return None
    duel_id = int(duel.get("duel_id") or 0)
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Aceitar", callback_data=f"duelv2:accept:{duel_id}"),
            InlineKeyboardButton("❌ Recusar", callback_data=f"duelv2:reject:{duel_id}"),
        ]]
    )


def _team_summary(team: list[dict]) -> str:
    if not team:
        return "—"
    return "\n".join(f"• {html.escape(line, quote=False)}" for line in format_team_lines(team))


def _group_text(duel: dict) -> str:
    state = str(duel.get("state") or "pending")
    a = _safe_name(str(duel.get("challenger_name") or "Jogador A"))
    b = _safe_name(str(duel.get("challenged_name") or "Jogador B"))
    duel_id = int(duel.get("duel_id") or 0)

    if state == "pending":
        return (
            f"⚔️ <b>DUELO #{duel_id}</b>\n\n"
            f"{a} desafiou <b>{b}</b>.\n\n"
            "Modo: <b>Amigável</b>\n"
            "Cada jogador monta um trio de XCards. O maior BP vence a rodada; "
            "cada derrota reduz a vida do card até a eliminação.\n\n"
            "⏳ O desafio expira automaticamente."
        )
    if state == "selecting":
        ready_a = "✅ pronto" if duel.get("ready_a") else "🧩 escolhendo"
        ready_b = "✅ pronto" if duel.get("ready_b") else "🧩 escolhendo"
        return (
            f"⚔️ <b>DUELO #{duel_id} ACEITO</b>\n\n"
            f"{a}: {ready_a}\n"
            f"{b}: {ready_b}\n\n"
            "📩 A montagem do trio acontece no privado com o bot."
        )
    if state == "active":
        return (
            f"⚔️ <b>DUELO #{duel_id} • RODADA {int(duel.get('round_no') or 1)}</b>\n\n"
            f"<b>{a}</b>\n{_team_summary(list(duel.get('team_a') or []))}\n\n"
            f"<b>{b}</b>\n{_team_summary(list(duel.get('team_b') or []))}\n\n"
            "🎯 Cada jogador escolhe seu XCard da rodada no privado."
        )
    if state == "completed":
        winner_id = int(duel.get("winner_user_id") or 0)
        winner = a if winner_id == int(duel.get("challenger_user_id") or 0) else b
        return (
            f"🏆 <b>DUELO #{duel_id} ENCERRADO</b>\n\n"
            f"Vencedor: <b>{winner}</b>\n\n"
            f"<b>{a}</b>\n{_team_summary(list(duel.get('team_a') or []))}\n\n"
            f"<b>{b}</b>\n{_team_summary(list(duel.get('team_b') or []))}"
        )
    labels = {
        "rejected": "❌ Desafio recusado.",
        "expired": "⌛ Duelo expirado.",
        "cancelled": "🚫 Duelo cancelado.",
    }
    return f"⚔️ <b>DUELO #{duel_id}</b>\n\n{labels.get(state, 'Estado encerrado.')}"


async def _refresh_group(context: ContextTypes.DEFAULT_TYPE, duel: dict) -> None:
    chat_id = int(duel.get("group_chat_id") or 0)
    message_id = int(duel.get("group_message_id") or 0)
    if not chat_id or not message_id:
        return
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=_group_text(duel),
            parse_mode="HTML",
            reply_markup=_group_keyboard(duel),
            disable_web_page_preview=True,
        )
    except Exception:
        pass


def _selection_keyboard(duel: dict, user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    cards = sorted(
        get_user_xcards(int(user_id)),
        key=lambda item: (-int(item.get("bp") or 0), str(item.get("name") or "")),
    )
    side = "a" if int(user_id) == int(duel.get("challenger_user_id") or 0) else "b"
    selected = {int(value) for value in (duel.get(f"selection_{side}") or [])}
    pages = max(1, math.ceil(len(cards) / PAGE_SIZE))
    page = max(0, min(int(page), pages - 1))
    start = page * PAGE_SIZE
    visible = cards[start:start + PAGE_SIZE]
    rows: list[list[InlineKeyboardButton]] = []
    for card in visible:
        card_id = int(card.get("card_id") or 0)
        mark = "✅" if card_id in selected else "➕"
        label = str(card.get("name") or "XCARD")
        if len(label) > 24:
            label = label[:21] + "…"
        rows.append([
            InlineKeyboardButton(
                f"{mark} {label} • BP {int(card.get('bp') or 0)}",
                callback_data=f"duelv2:toggle:{int(duel['duel_id'])}:{card_id}:{page}",
            )
        ])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"duelv2:page:{int(duel['duel_id'])}:{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="duelv2:noop:0"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"duelv2:page:{int(duel['duel_id'])}:{page+1}"))
    rows.append(nav)
    rows.append([
        InlineKeyboardButton(
            f"✅ Confirmar trio ({len(selected)}/3)",
            callback_data=f"duelv2:confirm:{int(duel['duel_id'])}:{page}",
        )
    ])
    return InlineKeyboardMarkup(rows)


def _selection_text(duel: dict, user_id: int) -> str:
    side = "a" if int(user_id) == int(duel.get("challenger_user_id") or 0) else "b"
    selected = [int(value) for value in (duel.get(f"selection_{side}") or [])]
    return (
        f"🧩 <b>MONTE SEU TRIO • DUELO #{int(duel['duel_id'])}</b>\n\n"
        "Escolha <b>3 XCards diferentes</b>. Eles ficarão como snapshot deste duelo; "
        "BP e ordem serão preservados durante a batalha.\n\n"
        f"Selecionados: <b>{len(selected)}/3</b>"
    )


async def _send_selection_panel(context: ContextTypes.DEFAULT_TYPE, duel: dict, user_id: int, page: int = 0) -> bool:
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=_selection_text(duel, int(user_id)),
            parse_mode="HTML",
            reply_markup=_selection_keyboard(duel, int(user_id), page),
        )
        return True
    except Exception:
        return False


def _pick_keyboard(duel: dict, user_id: int) -> InlineKeyboardMarkup:
    side = "a" if int(user_id) == int(duel.get("challenger_user_id") or 0) else "b"
    team = list(duel.get(f"team_{side}") or [])
    rows: list[list[InlineKeyboardButton]] = []
    alive = set(get_alive_slots(team))
    for entry in team:
        slot = int(entry.get("slot") or 0)
        if slot not in alive:
            continue
        name = str(entry.get("name") or "XCARD")
        if len(name) > 24:
            name = name[:21] + "…"
        rows.append([
            InlineKeyboardButton(
                f"⚔️ {name} • BP {int(entry.get('bp') or 0)} • {int(entry.get('hp') or 0)}%",
                callback_data=f"duelv2:pick:{int(duel['duel_id'])}:{slot}",
            )
        ])
    return InlineKeyboardMarkup(rows)


async def _send_pick_panel(context: ContextTypes.DEFAULT_TYPE, duel: dict, user_id: int) -> bool:
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=(
                f"⚔️ <b>DUELO #{int(duel['duel_id'])} • RODADA {int(duel.get('round_no') or 1)}</b>\n\n"
                "Escolha o XCard que vai lutar nesta rodada. Sua escolha fica oculta até o adversário escolher."
            ),
            parse_mode="HTML",
            reply_markup=_pick_keyboard(duel, int(user_id)),
        )
        return True
    except Exception:
        return False


async def duelo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return

    from utils.gatekeeper import gatekeeper
    ok, blocked = await gatekeeper(update, context)
    if not ok:
        if blocked:
            await message.reply_html(blocked)
        return

    if str(chat.type) not in {"group", "supergroup"}:
        await message.reply_html("⚠️ Use <code>/duelo</code> respondendo a outro jogador dentro de um grupo.")
        return
    target = getattr(getattr(message, "reply_to_message", None), "from_user", None)
    if not target:
        await message.reply_html("⚠️ Responda a mensagem do jogador que você quer desafiar e envie <code>/duelo</code>.")
        return
    if int(target.id) == int(user.id) or bool(getattr(target, "is_bot", False)):
        await message.reply_text("⚠️ Escolha outro jogador real para o duelo.")
        return

    try:
        duel = create_challenge(
            challenger_user_id=int(user.id),
            challenged_user_id=int(target.id),
            challenger_name=str(user.full_name or user.first_name or user.username or "Jogador"),
            challenged_name=str(target.full_name or target.first_name or target.username or "Jogador"),
            group_chat_id=int(chat.id),
        )
    except DuelNotEnoughCards as exc:
        who = "Você" if exc.user_id == int(user.id) else "O jogador desafiado"
        await message.reply_html(f"⚠️ {who} precisa ter pelo menos <b>3 XCards diferentes</b> para duelar. Use <code>/xcolecao</code>.")
        return
    except DuelBusy:
        await message.reply_text("⚠️ Um dos jogadores já está em outro duelo pendente ou ativo.")
        return
    except DuelError:
        await message.reply_text("⚠️ Não foi possível criar esse duelo.")
        return

    sent = await message.reply_html(_group_text(duel), reply_markup=_group_keyboard(duel))
    set_group_message(int(duel["duel_id"]), int(sent.message_id))


async def duel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user or not query.data:
        return
    parts = str(query.data).split(":")
    if len(parts) < 2 or parts[0] != "duelv2":
        return
    action = parts[1]
    if action == "noop":
        await query.answer()
        return

    try:
        duel_id = int(parts[2])
    except Exception:
        await query.answer("Duelo inválido.", show_alert=True)
        return

    try:
        if action in {"accept", "reject"}:
            duel = respond_challenge(duel_id, int(user.id), accept=(action == "accept"))
            await _refresh_group(context, duel)
            if action == "reject":
                await query.answer("Desafio recusado.")
                return
            await query.answer("Desafio aceito. Monte seu trio no privado.")
            sent_a = await _send_selection_panel(context, duel, int(duel["challenger_user_id"]))
            sent_b = await _send_selection_panel(context, duel, int(duel["challenged_user_id"]))
            if not (sent_a and sent_b):
                try:
                    await context.bot.send_message(
                        chat_id=int(duel["group_chat_id"]),
                        text="📩 Um dos jogadores ainda não abriu uma conversa privada com o bot. Abra o bot no privado e tente interagir novamente antes da expiração.",
                    )
                except Exception:
                    pass
            return

        duel = get_duel(duel_id)
        if not duel:
            await query.answer("Duelo não encontrado.", show_alert=True)
            return

        if action == "page":
            page = int(parts[3])
            await query.answer()
            await query.edit_message_text(
                _selection_text(duel, int(user.id)),
                parse_mode="HTML",
                reply_markup=_selection_keyboard(duel, int(user.id), page),
            )
            return

        if action == "toggle":
            card_id = int(parts[3]); page = int(parts[4])
            duel = toggle_selection(duel_id, int(user.id), card_id)
            await query.answer("Trio atualizado.")
            await query.edit_message_text(
                _selection_text(duel, int(user.id)),
                parse_mode="HTML",
                reply_markup=_selection_keyboard(duel, int(user.id), page),
            )
            return

        if action == "confirm":
            duel = confirm_selection(duel_id, int(user.id))
            await query.answer("Trio confirmado.")
            await query.edit_message_text("✅ <b>Trio confirmado.</b> Aguarde o outro jogador.", parse_mode="HTML")
            await _refresh_group(context, duel)
            if duel.get("state") == "active":
                await _send_pick_panel(context, duel, int(duel["challenger_user_id"]))
                await _send_pick_panel(context, duel, int(duel["challenged_user_id"]))
            return

        if action == "pick":
            slot = int(parts[3])
            duel = submit_pick(duel_id, int(user.id), slot)
            await query.answer("Escolha registrada.")
            await query.edit_message_text("🔒 <b>Escolha registrada.</b> Aguardando o adversário.", parse_mode="HTML")
            await _refresh_group(context, duel)
            if duel.get("round_resolved"):
                result = duel.get("round_result") or {}
                note = html.escape(str(result.get("note") or "Rodada resolvida."), quote=False)
                try:
                    await context.bot.send_message(
                        chat_id=int(duel["group_chat_id"]),
                        text=f"⚔️ <b>Resultado da rodada</b>\n\n{note}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                if duel.get("state") == "active":
                    await _send_pick_panel(context, duel, int(duel["challenger_user_id"]))
                    await _send_pick_panel(context, duel, int(duel["challenged_user_id"]))
            return

        await query.answer()
    except DuelNotParticipant:
        await query.answer("Essa ação não pertence a você.", show_alert=True)
    except DuelSelectionError as exc:
        messages = {
            "team_full": "Seu trio já tem 3 XCards.",
            "team_incomplete": "Escolha exatamente 3 XCards.",
            "card_not_owned": "Você não possui mais esse XCard.",
            "invalid_combat_card": "Esse XCard não é válido para combate.",
            "choice_already_sent": "Sua escolha desta rodada já foi registrada.",
            "invalid_slot": "Esse XCard não pode lutar nesta rodada.",
        }
        await query.answer(messages.get(str(exc), "Não foi possível concluir essa escolha."), show_alert=True)
    except DuelInvalidState:
        await query.answer("Esse duelo não está mais nessa etapa ou expirou.", show_alert=True)
    except DuelError:
        await query.answer("Não foi possível atualizar o duelo.", show_alert=True)
