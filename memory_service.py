from __future__ import annotations

from typing import Any

from memory_repository import (
    MemoryGameError,
    MemoryProofInvalid,
    MemorySessionInvalid,
    MemoryTooFast,
    finish_memory_session as _finish,
    memory_stats,
    start_memory_session,
)
from system_events import emit_completed_activity, emit_event


def finish_memory_session(user_id: int, token: str, moves: int, proof: Any):
    result = _finish(int(user_id), token, int(moves), proof)
    emit_event(
        int(user_id),
        "memory_completed",
        label=f"🧠 Memória {result.get('level')} concluída",
        metadata={"elapsed_ms": result.get("elapsed_ms"), "moves": result.get("moves"), "new_best": result.get("new_best")},
    )
    emit_event(int(user_id), "minigame_completed", label="🧠 Jogo da Memória concluído")
    emit_completed_activity(int(user_id), label="Memória concluída")
    return result


__all__ = [
    "MemoryGameError", "MemoryProofInvalid", "MemorySessionInvalid", "MemoryTooFast",
    "finish_memory_session", "memory_stats", "start_memory_session",
]
