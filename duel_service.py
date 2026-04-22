from __future__ import annotations

import asyncio
import html
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import database as db
import duel_repository as repo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import Application
from xcards_service import get_xcard_by_id


BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"

DUEL_CHALLENGE_TIMEOUT_SECONDS = int(os.getenv("DUEL_CHALLENGE_TIMEOUT_SECONDS", "120"))
DUEL_PRIVATE_TIMEOUT_SECONDS = int(os.getenv("DUEL_PRIVATE_TIMEOUT_SECONDS", "300"))
DUEL_SELECTION_TIMEOUT_SECONDS = int(os.getenv("DUEL_SELECTION_TIMEOUT_SECONDS", "420"))
DUEL_ROUND_TIMEOUT_SECONDS = int(os.getenv("DUEL_ROUND_TIMEOUT_SECONDS", "90"))

_SCHEDULED_DUEL_TASKS: set[int] = set()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def duel_constants() -> Dict[str, int]:
    return {
        "challenge_timeout_seconds": DUEL_CHALLENGE_TIMEOUT_SECONDS,
        "private_timeout_seconds": DUEL_PRIVATE_TIMEOUT_SECONDS,
        "selection_timeout_seconds": DUEL_SELECTION_TIMEOUT_SECONDS,
        "round_timeout_seconds": DUEL_ROUND_TIMEOUT_SECONDS,
    }


def user_link(user_id: int, name: str) -> str:
    safe_name = html.escape(str(name or f"User {user_id}").strip())
    return f'<a href="tg://user?id={int(user_id)}">{safe_name}</a>'


def player_state(duel: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    return dict((duel.get("players_state") or {}).get(str(int(user_id))) or {})


def player_display_name(duel: Dict[str, Any], user_id: int) -> str:
    player = player_state(duel, user_id)
    return (
        str(player.get("full_name") or "").strip()
        or str(player.get("username") or "").strip()
        or f"User {int(user_id)}"
    )


def team_state(duel: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    return dict((duel.get("teams_state") or {}).get(str(int(user_id))) or {})


def mode_label(mode: str) -> str:
    return "Apostado" if str(mode or "").strip().lower() == "wager" else "Amistoso"


def duel_status_label(state: str) -> str:
    mapping = {
        "pending_challenge": "Aguardando resposta",
        "waiting_private": "Abrindo o privado",
        "waiting_mode": "Escolha de modo",
        "selecting_team": "Montagem do trio",
        "active": "Duelo em andamento",
        "declined": "Desafio recusado",
        "expired": "Desafio expirado",
        "cancelled": "Duelo cancelado",
        "completed": "Duelo encerrado",
        "completed_reward_review": "Duelo encerrado com revisao do premio",
    }
    return mapping.get(str(state or "").strip(), "Estado desconhecido")


def resolution_label(reason: Any) -> str:
    raw = str(reason or "").strip()
    if raw.startswith("insufficient_xcards:"):
        names = raw.split(":", 1)[1].strip()
        if names:
            return f"Sem 3 XCARDs válidos para participar: {names}"
        return "Um dos jogadores não possui 3 XCARDs válidos para participar"
    mapping = {
        "rejected": "Desafio recusado",
        "challenge_timeout": "Desafio expirou",
        "prep_timeout": "Preparação expirada",
        "round_timeout": "Derrota por falta de resposta na rodada",
        "double_timeout": "Abandono duplo na rodada",
        "surrender": "Desistência",
        "all_cards_eliminated": "Todos os personagens do rival foram eliminados",
        "entry_fee_insufficient": "Saldo insuficiente para iniciar o modo apostado",
    }
    return mapping.get(raw, raw or "-")


def format_seconds_left(target_dt: Optional[datetime]) -> str:
    if not target_dt:
        return "--"
    remaining = max(int((target_dt - now_utc()).total_seconds()), 0)
    minutes, seconds = divmod(remaining, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}h {minutes:02d}m"
    return f"{minutes:02d}m {seconds:02d}s"


def duel_deadline(duel: Dict[str, Any]) -> Optional[datetime]:
    state = str(duel.get("state") or "")
    if state == "pending_challenge":
        return duel.get("challenge_expires_at")
    if state in {"waiting_private", "waiting_mode", "selecting_team"}:
        return duel.get("prep_expires_at")
    if state == "active":
        return duel.get("round_expires_at")
    return None


def _alive_count(duel: Dict[str, Any], user_id: int) -> int:
    cards = list((team_state(duel, user_id) or {}).get("cards") or [])
    total = 0
    for entry in cards:
        if not bool(entry.get("eliminated")) and int(entry.get("hp") or 0) > 0:
            total += 1
    return total


def _missing_private_users(duel: Dict[str, Any]) -> List[int]:
    missing: List[int] = []
    for user_id in (
        int(duel.get("challenger_user_id") or 0),
        int(duel.get("challenged_user_id") or 0),
    ):
        if user_id <= 0:
            continue
        if not bool(player_state(duel, user_id).get("private_ready")):
            missing.append(user_id)
    return missing


def build_group_keyboard(duel: Dict[str, Any]) -> Optional[InlineKeyboardMarkup]:
    duel_id = int(duel.get("duel_id") or 0)
    state = str(duel.get("state") or "")
    if duel_id <= 0:
        return None

    if state == "pending_challenge":
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Aceitar duelo", callback_data=f"duelacc:{duel_id}"),
                    InlineKeyboardButton("Negar duelo", callback_data=f"duelden:{duel_id}"),
                ]
            ]
        )

    if state == "waiting_private":
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Abrir bot no privado", url=BOT_PRIVATE_URL)],
                [InlineKeyboardButton("Continuar duelo", callback_data=f"duelrdy:{duel_id}")],
            ]
        )

    return None


def render_group_text(duel: Dict[str, Any]) -> str:
    challenger_id = int(duel.get("challenger_user_id") or 0)
    challenged_id = int(duel.get("challenged_user_id") or 0)
    challenger_name = player_display_name(duel, challenger_id)
    challenged_name = player_display_name(duel, challenged_id)
    state = str(duel.get("state") or "")
    mode = str(duel.get("mode") or "")

    lines = [
        "⚔️ <b>Duelo entre jogadores</b>",
        "",
        f"Desafiante: {user_link(challenger_id, challenger_name)}",
        f"Desafiado: {user_link(challenged_id, challenged_name)}",
        f"Modo: <b>{mode_label(mode) if mode else 'A definir no privado'}</b>",
        f"Status: <b>{html.escape(duel_status_label(state))}</b>",
    ]

    deadline = duel_deadline(duel)
    if deadline and state not in {"completed", "completed_reward_review", "declined", "expired", "cancelled"}:
        lines.append(f"Tempo restante: <b>{format_seconds_left(deadline)}</b>")

    if state == "pending_challenge":
        lines.extend(
            [
                "",
                "Apenas o jogador desafiado pode aceitar ou negar este desafio.",
            ]
        )
    elif state == "waiting_private":
        missing_users = _missing_private_users(duel)
        if missing_users:
            missing_names = ", ".join(
                html.escape(player_display_name(duel, user_id)) for user_id in missing_users
            )
            lines.extend(
                [
                    "",
                    f"Faltando abrir o privado com o bot: <b>{missing_names}</b>.",
                    "Abra o bot, envie <code>/start</code> e depois toque em <b>Continuar duelo</b>.",
                ]
            )
    elif state in {"waiting_mode", "selecting_team"}:
        lines.extend(
            [
                "",
                "A preparação esta acontecendo no privado com cada jogador.",
            ]
        )
    elif state == "active":
        lines.extend(
            [
                "",
                f"Rodada atual: <b>{int(duel.get('current_round') or 1)}</b>",
                f"{html.escape(challenger_name)}: <b>{_alive_count(duel, challenger_id)}/3</b> vivos",
                f"{html.escape(challenged_name)}: <b>{_alive_count(duel, challenged_id)}/3</b> vivos",
            ]
        )
    elif state in {"completed", "completed_reward_review"}:
        winner_id = int(duel.get("winner_user_id") or 0)
        loser_id = int(duel.get("loser_user_id") or 0)
        lines.extend(
            [
                "",
                f"Vencedor: {user_link(winner_id, player_display_name(duel, winner_id)) if winner_id else '<b>Sem vencedor</b>'}",
                f"Motivo final: <b>{html.escape(resolution_label(duel.get('resolution_reason')))}</b>",
            ]
        )
        reward_status = str(duel.get("reward_transfer_status") or "none")
        reward_card_id = int(duel.get("reward_card_id") or 0)
        if str(duel.get("mode") or "") == "wager":
            if reward_status == "completed" and reward_card_id > 0:
                reward_card = get_xcard_by_id(reward_card_id) or {}
                reward_name = str(reward_card.get("name") or f"Card #{reward_card_id}").strip()
                lines.append(f"Prêmio transferido: <b>{html.escape(reward_name)}</b>")
            elif reward_status == "review":
                lines.append("Prêmio: <b>em revisão manual</b> por inconsistência de inventário.")
    elif state == "declined":
        lines.extend(["", "O duelo foi recusado pelo jogador desafiado."])
    elif state == "expired":
        lines.extend(["", "O desafio expirou antes de ser aceito."])
    elif state == "cancelled":
        lines.extend(
            [
                "",
                f"Motivo: <b>{html.escape(resolution_label(duel.get('resolution_reason')))}</b>",
            ]
        )

    return "\n".join(lines)


def _team_summary_lines(duel: Dict[str, Any], user_id: int) -> List[str]:
    cards = list((team_state(duel, user_id) or {}).get("cards") or [])
    if not cards:
        return ["1. --", "2. --", "3. --"]

    lines: List[str] = []
    by_slot = {int(entry.get("slot") or 0): entry for entry in cards}
    for slot in (1, 2, 3):
        entry = by_slot.get(slot)
        if not entry:
            lines.append(f"{slot}. --")
            continue
        name = str(entry.get("name") or "XCARD").strip()
        bp = int(entry.get("bp") or 0)
        hp = int(entry.get("hp") or 0)
        marker = "☠️" if bool(entry.get("eliminated")) or hp <= 0 else "🟢"
        lines.append(f"{slot}. {html.escape(name)} | BP {bp} | Vida {hp}% {marker}")
    return lines


def _render_private_selectable_card(card: Dict[str, Any], owned_qty: int, locked_qty: int, selected: bool) -> List[str]:
    bp = int(card.get("bp_value") or 0)
    return [
        "🎴 <b>Card em destaque</b>",
        f"<b>{html.escape(str(card.get('name') or 'XCARD'))}</b>",
        html.escape(str(card.get("title") or "Obra desconhecida")),
        f"BP <b>{bp}</b> • Raridade <b>{html.escape(str(card.get('rarity') or '-'))}</b>",
        f"ID <code>{html.escape(str(card.get('card_no') or card.get('card_id') or '-'))}</code>",
        f"Na sua coleção: <b>{owned_qty}</b>",
        f"Travado em outros fluxos: <b>{locked_qty}</b>",
        f"Status neste trio: <b>{'Selecionado' if selected else 'Livre'}</b>",
    ]


def _duel_history_line(stats_row: Dict[str, Any]) -> str:
    wins = int(stats_row.get("wins") or 0)
    losses = int(stats_row.get("losses") or 0)
    wager_wins = int(stats_row.get("wager_wins") or 0)
    wager_losses = int(stats_row.get("wager_losses") or 0)
    return (
        f"Histórico geral: <b>{wins}V</b> • <b>{losses}D</b>\n"
        f"Apostados: <b>{wager_wins}V</b> • <b>{wager_losses}D</b>"
    )


def _get_selectable_xcards(user_id: int, duel_id: int) -> List[Dict[str, Any]]:
    lock_map = repo.get_user_xcard_lock_map(int(user_id), exclude_duel_id=int(duel_id))
    collection = db.get_user_xcard_collection(int(user_id)) or []
    candidates: List[Dict[str, Any]] = []

    for item in collection:
        card_id = int(item.get("card_id") or 0)
        quantity = int(item.get("quantity") or 0)
        if card_id <= 0 or quantity <= 0:
            continue
        locked_qty = int(lock_map.get(card_id) or 0)
        available_qty = quantity - locked_qty
        if available_qty <= 0:
            continue
        card = get_xcard_by_id(card_id) or {}
        if not card:
            continue
        bp_value = int(card.get("bp_value") or 0)
        candidates.append(
            {
                "card_id": card_id,
                "card_no": str(card.get("card_no") or "").strip(),
                "name": str(card.get("name") or "").strip(),
                "title": str(card.get("title") or "").strip(),
                "image": str(card.get("image") or "").strip(),
                "rarity": str(card.get("rarity") or "").strip(),
                "bp_value": bp_value,
                "bp_display": str(card.get("bp") or bp_value).strip(),
                "owned_qty": quantity,
                "locked_qty": locked_qty,
            }
        )

    candidates.sort(
        key=lambda item: (
            -int(item.get("bp_value") or 0),
            str(item.get("title") or "").lower(),
            str(item.get("name") or "").lower(),
            str(item.get("card_no") or "").lower(),
        )
    )
    return candidates


def get_selectable_xcards(user_id: int, duel_id: int) -> List[Dict[str, Any]]:
    return _get_selectable_xcards(int(user_id), int(duel_id))


def _private_title_block(duel: Dict[str, Any], user_id: int) -> List[str]:
    state = str(duel.get("state") or "")
    me = player_display_name(duel, user_id)
    opponent_id = int(duel.get("challenged_user_id") if int(duel.get("challenger_user_id") or 0) == int(user_id) else duel.get("challenger_user_id") or 0)
    opponent_name = player_display_name(duel, opponent_id)
    lines = [
        "⚔️ <b>Sala do duelo</b>",
        "",
        f"Você: <b>{html.escape(me)}</b>",
        f"Rival: <b>{html.escape(opponent_name)}</b>",
        f"Estado: <b>{html.escape(duel_status_label(state))}</b>",
        f"Modo: <b>{mode_label(str(duel.get('mode') or '')) if duel.get('mode') else 'A definir'}</b>",
    ]
    return lines


def render_private_text(duel: Dict[str, Any], user_id: int, *, focus_index: int = 0) -> str:
    state = str(duel.get("state") or "")
    lines = _private_title_block(duel, user_id)
    lines.append("")
    lines.append(_duel_history_line(repo.get_duel_stats_row(int(user_id))))

    player = player_state(duel, user_id)
    opponent_id = int(duel.get("challenged_user_id") if int(duel.get("challenger_user_id") or 0) == int(user_id) else duel.get("challenger_user_id") or 0)

    if state == "waiting_private":
        lines.extend(
            [
                "",
                "O duelo foi aceito no grupo.",
                "Estamos preparando o fluxo no privado.",
            ]
        )
    elif state == "waiting_mode":
        mode = str(duel.get("mode") or "")
        if int(user_id) == int(duel.get("challenger_user_id") or 0):
            lines.extend(
                [
                    "",
                    "Escolha agora o modo da partida.",
                    "Amistoso: sem prêmio.",
                    "Apostado: 1 coin de entrada para cada lado e o vencedor leva o XCARD de menor BP do perdedor entre os 3 usados.",
                ]
            )
        else:
            lines.extend(["", "Aguardando o desafiante escolher o modo do duelo."])
            if mode:
                lines.extend(
                    [
                        "",
                        f"Modo proposto: <b>{mode_label(mode)}</b>",
                        "Se você confirmar, a partida avança para a seleção do trio.",
                    ]
                )
    elif state == "selecting_team":
        selected_ids = [int(card_id) for card_id in list(player.get("selected_card_ids") or [])]
        selected_cards = [get_xcard_by_id(card_id) or {} for card_id in selected_ids]
        lines.extend(
            [
                "",
                "Monte o seu trio com 3 XCARDs distintos da sua coleção.",
                f"Selecionados: <b>{len(selected_ids)}/3</b>",
            ]
        )
        for slot in range(3):
            card = selected_cards[slot] if slot < len(selected_cards) else {}
            if card:
                bp_value = int(card.get("bp_value") or 0)
                lines.append(f"{slot + 1}. {html.escape(str(card.get('name') or 'XCARD'))} | BP {bp_value}")
            else:
                lines.append(f"{slot + 1}. --")

        if bool(player.get("team_confirmed")):
            lines.extend(
                [
                    "",
                    "Seu trio já foi confirmado e agora está travado até o fim do duelo.",
                ]
            )

        candidates = _get_selectable_xcards(int(user_id), int(duel.get("duel_id") or 0))
        if bool(player.get("team_confirmed")):
            pass
        elif len(candidates) < 3:
            lines.extend(
                [
                    "",
                    "Você não possui 3 XCARDs distintos livres para este duelo.",
                ]
            )
        elif candidates:
            safe_index = max(0, min(int(focus_index), len(candidates) - 1))
            card = candidates[safe_index]
            lines.extend([""] + _render_private_selectable_card(
                card,
                int(card.get("owned_qty") or 0),
                int(card.get("locked_qty") or 0),
                int(card.get("card_id") or 0) in selected_ids,
            ))
            lines.append(f"Navegação: <b>{safe_index + 1}/{len(candidates)}</b>")
    elif state == "active":
        lines.extend(
            [
                "",
                f"Rodada atual: <b>{int(duel.get('current_round') or 1)}</b>",
                f"Tempo restante da rodada: <b>{format_seconds_left(duel.get('round_expires_at'))}</b>",
                "",
                "<b>Seu time</b>",
            ]
        )
        lines.extend(_team_summary_lines(duel, user_id))
        lines.extend(["", "<b>Time rival</b>"])
        lines.extend(_team_summary_lines(duel, opponent_id))

        if player.get("round_choice_slot"):
            lines.extend(
                [
                    "",
                    f"Sua jogada desta rodada: <b>slot {int(player.get('round_choice_slot') or 0)}</b>.",
                    "Agora estamos aguardando a jogada do outro jogador.",
                ]
            )
        elif bool(player.get("pending_surrender")):
            lines.extend(
                [
                    "",
                    "Você abriu a desistência.",
                    "Confirme apenas se realmente quiser entregar a partida.",
                ]
            )
        else:
            lines.extend(["", "Escolha agora qual dos seus personagens vivos vai lutar nesta rodada."])
    elif state in {"completed", "completed_reward_review"}:
        winner_id = int(duel.get("winner_user_id") or 0)
        lines.extend(
            [
                "",
                f"Resultado final: <b>{'Vitória' if winner_id == int(user_id) else 'Derrota' if winner_id else 'Sem vencedor'}</b>",
                f"Motivo: <b>{html.escape(resolution_label(duel.get('resolution_reason')))}</b>",
            ]
        )
        reward_status = str(duel.get("reward_transfer_status") or "")
        reward_card_id = int(duel.get("reward_card_id") or 0)
        if reward_status == "completed" and reward_card_id > 0:
            reward_card = get_xcard_by_id(reward_card_id) or {}
            reward_name = str(reward_card.get("name") or f"Card #{reward_card_id}").strip()
            if winner_id == int(user_id):
                lines.append(f"Você recebeu: <b>{html.escape(reward_name)}</b>")
            else:
                lines.append(f"Você perdeu: <b>{html.escape(reward_name)}</b>")
        elif reward_status == "review":
            lines.append("O prêmio desta partida entrou em revisão manual por segurança.")
    elif state == "declined":
        lines.extend(["", "O desafio foi recusado no grupo."])
    elif state == "expired":
        lines.extend(["", "O desafio expirou sem resposta."])
    elif state == "cancelled":
        lines.extend(
            [
                "",
                f"Este duelo foi cancelado.",
                f"Motivo: <b>{html.escape(resolution_label(duel.get('resolution_reason')))}</b>",
            ]
        )

    return "\n".join(lines)


def build_private_keyboard(duel: Dict[str, Any], user_id: int, *, focus_index: int = 0) -> Optional[InlineKeyboardMarkup]:
    duel_id = int(duel.get("duel_id") or 0)
    if duel_id <= 0:
        return None

    state = str(duel.get("state") or "")
    player = player_state(duel, user_id)

    if state == "waiting_mode":
        if int(user_id) == int(duel.get("challenger_user_id") or 0):
            return InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Amistoso", callback_data=f"duelmd:{duel_id}:f"),
                        InlineKeyboardButton("Apostado", callback_data=f"duelmd:{duel_id}:w"),
                    ]
                ]
            )
        if duel.get("mode"):
            return InlineKeyboardMarkup(
                [[InlineKeyboardButton(f"Confirmar {mode_label(str(duel.get('mode') or ''))}", callback_data=f"duelmok:{duel_id}")]]
            )
        return None

    if state == "selecting_team":
        candidates = _get_selectable_xcards(int(user_id), duel_id)
        if not candidates:
            return None
        if bool(player.get("team_confirmed")):
            return None

        safe_index = max(0, min(int(focus_index), len(candidates) - 1))
        current = candidates[safe_index]
        selected_ids = [int(card_id) for card_id in list(player.get("selected_card_ids") or [])]
        selected = int(current.get("card_id") or 0) in selected_ids
        buttons: List[List[InlineKeyboardButton]] = []

        nav_row = []
        if safe_index > 0:
            nav_row.append(InlineKeyboardButton("◀️", callback_data=f"duelnv:{duel_id}:{safe_index - 1}"))
        nav_row.append(InlineKeyboardButton(f"{safe_index + 1}/{len(candidates)}", callback_data=f"duelnp:{duel_id}"))
        if safe_index < len(candidates) - 1:
            nav_row.append(InlineKeyboardButton("▶️", callback_data=f"duelnv:{duel_id}:{safe_index + 1}"))
        buttons.append(nav_row)

        if selected:
            buttons.append(
                [InlineKeyboardButton("Remover do trio", callback_data=f"duelrm:{duel_id}:{safe_index}:{int(current.get('card_id') or 0)}")]
            )
        else:
            buttons.append(
                [InlineKeyboardButton("Adicionar ao trio", callback_data=f"duelad:{duel_id}:{safe_index}:{int(current.get('card_id') or 0)}")]
            )

        if len(selected_ids) == 3:
            buttons.append([InlineKeyboardButton("Confirmar trio", callback_data=f"duelcf:{duel_id}")])

        return InlineKeyboardMarkup(buttons)

    if state == "active":
        if bool(player.get("pending_surrender")):
            return InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Confirmar desistência", callback_data=f"duelsr:{duel_id}:ok")],
                    [InlineKeyboardButton("Voltar", callback_data=f"duelsr:{duel_id}:no")],
                ]
            )

        if player.get("round_choice_slot"):
            return InlineKeyboardMarkup(
                [[InlineKeyboardButton("Desistir", callback_data=f"duelsr:{duel_id}:ask")]]
            )

        cards = list((team_state(duel, user_id) or {}).get("cards") or [])
        alive_buttons = []
        for entry in cards:
            if bool(entry.get("eliminated")) or int(entry.get("hp") or 0) <= 0:
                continue
            slot = int(entry.get("slot") or 0)
            alive_buttons.append(
                InlineKeyboardButton(
                    f"Usar {slot}",
                    callback_data=f"duelrd:{duel_id}:{slot}",
                )
            )

        rows: List[List[InlineKeyboardButton]] = []
        if alive_buttons:
            rows.append(alive_buttons[:2])
            if len(alive_buttons) > 2:
                rows.append(alive_buttons[2:])
        rows.append([InlineKeyboardButton("Desistir", callback_data=f"duelsr:{duel_id}:ask")])
        return InlineKeyboardMarkup(rows)

    return None


async def _edit_group_message(application: Application, duel: Dict[str, Any]) -> None:
    chat_id = int(duel.get("group_chat_id") or 0)
    message_id = int(duel.get("group_message_id") or 0)
    if chat_id == 0 or message_id == 0:
        return

    try:
        await application.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=render_group_text(duel),
            parse_mode=ParseMode.HTML,
            reply_markup=build_group_keyboard(duel),
            disable_web_page_preview=True,
        )
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _upsert_private_panel(application: Application, duel: Dict[str, Any], user_id: int, *, focus_index: int = 0) -> None:
    player = player_state(duel, user_id)
    chat_id = int(player.get("private_chat_id") or 0)
    message_id = int(player.get("panel_message_id") or 0)
    if chat_id <= 0:
        chat_id = int(user_id)

    text = render_private_text(duel, user_id, focus_index=focus_index)
    keyboard = build_private_keyboard(duel, user_id, focus_index=focus_index)

    if message_id > 0:
        try:
            await application.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            return
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
        except Forbidden:
            return

    try:
        sent = await application.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Forbidden:
        return

    repo.update_private_panel_reference(int(duel.get("duel_id") or 0), int(user_id), int(chat_id), int(sent.message_id))


async def refresh_duel_ui(application: Application, duel_id: int, *, focus_overrides: Optional[Dict[int, int]] = None) -> Optional[Dict[str, Any]]:
    duel = repo.get_duel_bundle(int(duel_id))
    if not duel:
        return None

    await _edit_group_message(application, duel)
    for uid in (
        int(duel.get("challenger_user_id") or 0),
        int(duel.get("challenged_user_id") or 0),
    ):
        if uid <= 0:
            continue
        player = player_state(duel, uid)
        if not bool(player.get("private_ready")) and str(duel.get("state") or "") not in {"completed", "completed_reward_review", "cancelled", "declined", "expired"}:
            continue
        focus_index = int((focus_overrides or {}).get(uid, 0))
        await _upsert_private_panel(application, duel, uid, focus_index=focus_index)
    return repo.get_duel_bundle(int(duel_id))


async def kickoff_private_setup(application: Application, duel_id: int) -> Optional[Dict[str, Any]]:
    duel = repo.get_duel_bundle(int(duel_id))
    if not duel:
        return None

    if str(duel.get("state") or "") not in {"waiting_private", "waiting_mode", "selecting_team", "active"}:
        return duel

    for uid in (
        int(duel.get("challenger_user_id") or 0),
        int(duel.get("challenged_user_id") or 0),
    ):
        if uid <= 0:
            continue
        player = player_state(duel, uid)
        if bool(player.get("private_ready")):
            continue
        try:
            sent = await application.bot.send_message(
                chat_id=uid,
                text=render_private_text(duel, uid),
                parse_mode=ParseMode.HTML,
                reply_markup=build_private_keyboard(duel, uid),
                disable_web_page_preview=True,
            )
        except Forbidden:
            continue

        result = repo.set_private_panel_ready(
            int(duel_id),
            int(uid),
            int(uid),
            int(sent.message_id),
            DUEL_SELECTION_TIMEOUT_SECONDS,
        )
        if result.get("ok"):
            duel = result.get("duel") or duel

    schedule_duel_watch(int(duel_id), application)
    return await refresh_duel_ui(application, int(duel_id))


async def cancel_duel_if_missing_xcards(application: Application, duel_id: int) -> Optional[Dict[str, Any]]:
    duel = repo.get_duel_bundle(int(duel_id))
    if not duel:
        return None
    if str(duel.get("state") or "") != "selecting_team":
        return duel

    missing: List[int] = []
    for uid in (
        int(duel.get("challenger_user_id") or 0),
        int(duel.get("challenged_user_id") or 0),
    ):
        if uid <= 0:
            continue
        if len(_get_selectable_xcards(uid, int(duel_id))) < 3:
            missing.append(uid)

    if not missing:
        return duel

    names = ", ".join(player_display_name(duel, uid) for uid in missing)
    result = repo.cancel_duel(int(duel_id), f"insufficient_xcards:{names}")
    if result.get("ok"):
        duel = result.get("duel") or duel
    await refresh_duel_ui(application, int(duel_id))
    return duel


def schedule_duel_watch(duel_id: int, application: Application) -> None:
    duel_id = int(duel_id)
    if duel_id <= 0 or duel_id in _SCHEDULED_DUEL_TASKS:
        return
    _SCHEDULED_DUEL_TASKS.add(duel_id)
    asyncio.create_task(_duel_timeout_worker(duel_id, application))


async def _duel_timeout_worker(duel_id: int, application: Application) -> None:
    try:
        while True:
            duel = repo.get_duel_bundle(int(duel_id))
            if not duel:
                return

            state = str(duel.get("state") or "")
            if state in {"declined", "expired", "cancelled", "completed", "completed_reward_review"}:
                return

            deadline = duel_deadline(duel)
            if not deadline:
                return

            delay = max((deadline - now_utc()).total_seconds(), 0.0)
            if delay > 0:
                await asyncio.sleep(delay + 0.25)

            result = repo.handle_duel_timeout(int(duel_id))
            if result.get("ok"):
                await refresh_duel_ui(application, int(duel_id))
            else:
                duel = repo.get_duel_bundle(int(duel_id))
                if not duel or duel_deadline(duel) is None:
                    return
    finally:
        _SCHEDULED_DUEL_TASKS.discard(int(duel_id))


async def restore_duel_runtime(application: Application) -> None:
    for duel in repo.list_open_duels_for_timeout_watch():
        schedule_duel_watch(int(duel.get("duel_id") or 0), application)
