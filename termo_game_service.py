from __future__ import annotations

from termo_repository import (
    TermoDuplicateGuess,
    TermoHintAlreadyUsed,
    TermoInsufficientCoins,
    TermoInvalidGuess,
    TermoInvalidState,
    buy_hint,
    get_active_or_today,
    start_daily_game,
    start_train_game,
    submit_guess as _submit_guess,
)
from system_events import emit_completed_activity, emit_event


def submit_guess(user_id: int, session_token: str, guess: str):
    result = _submit_guess(int(user_id), session_token, guess)
    status = str(result.get("status") or "")
    mode = str(result.get("mode") or "")
    if status in {"win", "loss"}:
        if status == "win" and mode == "daily":
            emit_event(
                int(user_id),
                "termo_won",
                label=f"🎌 Termo diário vencido em {int(result.get('attempts') or 0)} tentativas",
                metadata={"attempts": result.get("attempts"), "streak": result.get("streak")},
            )
        emit_event(int(user_id), "minigame_completed", label=f"🎌 Termo {'vencido' if status == 'win' else 'concluído'}")
        emit_completed_activity(int(user_id), label="Termo concluído")
    return result


__all__ = [
    "TermoDuplicateGuess", "TermoHintAlreadyUsed", "TermoInsufficientCoins", "TermoInvalidGuess", "TermoInvalidState",
    "buy_hint", "get_active_or_today", "start_daily_game", "start_train_game", "submit_guess",
]
