from __future__ import annotations

import pytest

from webapp_services.memory import (
    build_memory_best_payload,
    build_memory_finish_payload,
    normalize_memory_finish_input,
)


def test_normalize_memory_finish_input_preserves_limits_and_levels() -> None:
    assert normalize_memory_finish_input({
        "level": " HARD ",
        "time_ms": "12345",
        "moves": "48",
    }) == ("hard", 12345, 48)

    with pytest.raises(ValueError, match=r"^Nivel invalido\.$"):
        normalize_memory_finish_input({"level": "nightmare", "time_ms": 10, "moves": 1})
    with pytest.raises(ValueError, match=r"^Tempo invalido\.$"):
        normalize_memory_finish_input({"level": "easy", "time_ms": 0, "moves": 1})
    with pytest.raises(ValueError, match=r"^Tempo invalido\.$"):
        normalize_memory_finish_input({"level": "easy", "time_ms": 7_200_001, "moves": 1})
    with pytest.raises(ValueError, match=r"^Quantidade de jogadas invalida\.$"):
        normalize_memory_finish_input({"level": "easy", "time_ms": 1, "moves": 0})
    with pytest.raises(ValueError, match=r"^Quantidade de jogadas invalida\.$"):
        normalize_memory_finish_input({"level": "easy", "time_ms": 1, "moves": 10_001})


def test_memory_best_payload_preserves_level_and_summary_shape() -> None:
    payload = build_memory_best_payload({
        "rows": [
            {
                "level": "Easy",
                "best_time_ms": 1200,
                "best_moves": 14,
                "games_played": 5,
                "completed_games": 4,
            },
            {"level": "", "best_time_ms": 999},
        ],
        "summary": {
            "levels_completed": 2,
            "avg_best_time_ms": 2345.5,
            "avg_best_moves": 18.25,
            "completed_games": 9,
        },
    })

    assert payload == {
        "ok": True,
        "by_level": {
            "easy": {
                "time_ms": 1200,
                "moves": 14,
                "games_played": 5,
                "completed_games": 4,
            }
        },
        "summary": {
            "levels_completed": 2,
            "avg_best_time_ms": 2345.5,
            "avg_best_moves": 18.25,
            "completed_games": 9,
        },
    }


def test_memory_finish_payload_preserves_fallbacks_and_record_flag() -> None:
    payload = build_memory_finish_payload(
        {
            "new_record": True,
            "best": {
                "games_played": 3,
                "completed_games": 2,
            },
            "summary": {
                "levels_completed": 1,
                "avg_best_time_ms": 4567,
                "avg_best_moves": 22,
                "completed_games": 2,
            },
        },
        level="medium",
        time_ms=5000,
        moves=25,
    )

    assert payload["ok"] is True
    assert payload["new_record"] is True
    assert payload["best"] == {
        "level": "medium",
        "time_ms": 5000,
        "moves": 25,
        "games_played": 3,
        "completed_games": 2,
    }
    assert payload["summary"] == {
        "levels_completed": 1,
        "avg_best_time_ms": 4567.0,
        "avg_best_moves": 22.0,
        "completed_games": 2,
    }
