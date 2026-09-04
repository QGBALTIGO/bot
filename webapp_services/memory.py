from __future__ import annotations

from typing import Any, Dict

MEMORY_LEVELS = frozenset({"easy", "medium", "hard", "extreme"})
MAX_MEMORY_TIME_MS = 7_200_000
MAX_MEMORY_MOVES = 10_000


def normalize_memory_finish_input(payload: Dict[str, Any]) -> tuple[str, int, int]:
    level = str(payload.get("level") or "").strip().lower()
    time_ms = int(payload.get("time_ms") or 0)
    moves = int(payload.get("moves") or 0)

    if level not in MEMORY_LEVELS:
        raise ValueError("Nivel invalido.")
    if time_ms <= 0 or time_ms > MAX_MEMORY_TIME_MS:
        raise ValueError("Tempo invalido.")
    if moves <= 0 or moves > MAX_MEMORY_MOVES:
        raise ValueError("Quantidade de jogadas invalida.")

    return level, time_ms, moves


def build_memory_best_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    rows = payload.get("rows") or []
    summary = payload.get("summary") or {}

    by_level: Dict[str, Dict[str, int]] = {}
    for row in rows:
        level_key = str(row.get("level") or "").strip().lower()
        if not level_key:
            continue
        by_level[level_key] = {
            "time_ms": int(row.get("best_time_ms") or 0),
            "moves": int(row.get("best_moves") or 0),
            "games_played": int(row.get("games_played") or 0),
            "completed_games": int(row.get("completed_games") or 0),
        }

    return {
        "ok": True,
        "by_level": by_level,
        "summary": {
            "levels_completed": int(summary.get("levels_completed") or 0),
            "avg_best_time_ms": float(summary.get("avg_best_time_ms") or 0),
            "avg_best_moves": float(summary.get("avg_best_moves") or 0),
            "completed_games": int(summary.get("completed_games") or 0),
        },
    }


def build_memory_finish_payload(
    result: Dict[str, Any],
    *,
    level: str,
    time_ms: int,
    moves: int,
) -> Dict[str, Any]:
    best = result.get("best") or {}
    summary = result.get("summary") or {}

    return {
        "ok": True,
        "new_record": bool(result.get("new_record")),
        "best": {
            "level": str(best.get("level") or level),
            "time_ms": int(best.get("best_time_ms") or time_ms),
            "moves": int(best.get("best_moves") or moves),
            "games_played": int(best.get("games_played") or 0),
            "completed_games": int(best.get("completed_games") or 0),
        },
        "summary": {
            "levels_completed": int(summary.get("levels_completed") or 0),
            "avg_best_time_ms": float(summary.get("avg_best_time_ms") or 0),
            "avg_best_moves": float(summary.get("avg_best_moves") or 0),
            "completed_games": int(summary.get("completed_games") or 0),
        },
    }
