from __future__ import annotations

from ecosystem_repository import push_notification
from system_events import emit_completed_activity, emit_event
from duel_repository_v2 import (
    DuelBusy,
    DuelError,
    DuelInvalidState,
    DuelNotEnoughCards,
    DuelNotParticipant,
    DuelSelectionError,
    confirm_selection,
    create_challenge as _create_challenge,
    get_duel,
    respond_challenge as _respond_challenge,
    set_group_message,
    submit_pick as _submit_pick,
    toggle_selection,
)


def create_challenge(**kwargs):
    duel = _create_challenge(**kwargs)
    target = int(duel.get("challenged_user_id") or 0)
    if target:
        push_notification(
            target,
            "duels",
            "⚔️ Novo desafio de duelo",
            f"{duel.get('challenger_name') or 'Um jogador'} desafiou você.",
            "/hub#social",
            {"duel_id": int(duel.get("duel_id") or 0)},
        )
    return duel


def respond_challenge(duel_id: int, actor_user_id: int, accept: bool):
    duel = _respond_challenge(int(duel_id), int(actor_user_id), bool(accept))
    if accept:
        for uid in (int(duel.get("challenger_user_id") or 0), int(duel.get("challenged_user_id") or 0)):
            if uid:
                emit_event(uid, "social_interaction", label=f"⚔️ Duelo #{duel_id} aceito", metadata={"duel_id": int(duel_id)})
    return duel


def submit_pick(duel_id: int, user_id: int, slot: int):
    duel = _submit_pick(int(duel_id), int(user_id), int(slot))
    if bool(duel.get("round_resolved")) and str(duel.get("state") or "") == "completed":
        winner = int(duel.get("winner_user_id") or 0)
        a = int(duel.get("challenger_user_id") or 0)
        b = int(duel.get("challenged_user_id") or 0)
        for uid in (a, b):
            if not uid:
                continue
            emit_event(uid, "duel_completed", label=f"⚔️ Duelo #{duel_id} concluído", metadata={"duel_id": int(duel_id), "winner_user_id": winner})
            emit_event(uid, "social_interaction", label="⚔️ Interação por duelo", metadata={"duel_id": int(duel_id)})
            emit_completed_activity(uid, label="Duelo concluído", metadata={"duel_id": int(duel_id)})
        if winner:
            emit_event(winner, "duel_won", label=f"🏆 Venceu o duelo #{duel_id}", metadata={"duel_id": int(duel_id)})
            push_notification(winner, "duels", "🏆 Vitória no duelo", f"Você venceu o duelo #{duel_id}.", "/hub#activity", {"duel_id": int(duel_id)})
    return duel


__all__ = [
    "DuelBusy", "DuelError", "DuelInvalidState", "DuelNotEnoughCards", "DuelNotParticipant", "DuelSelectionError",
    "confirm_selection", "create_challenge", "get_duel", "respond_challenge", "set_group_message", "submit_pick", "toggle_selection",
]
