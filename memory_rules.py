from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryLevel:
    code: str
    label: str
    pairs: int
    min_seconds: int
    max_minutes: int


MEMORY_LEVELS: dict[str, MemoryLevel] = {
    "easy": MemoryLevel("easy", "Fácil", 4, 4, 10),
    "medium": MemoryLevel("medium", "Médio", 6, 7, 15),
    "hard": MemoryLevel("hard", "Difícil", 8, 10, 20),
    "extreme": MemoryLevel("extreme", "Muito difícil", 10, 13, 25),
}

ALIASES = {
    "facil": "easy",
    "fácil": "easy",
    "easy": "easy",
    "medio": "medium",
    "médio": "medium",
    "medium": "medium",
    "dificil": "hard",
    "difícil": "hard",
    "hard": "hard",
    "muito dificil": "extreme",
    "muito difícil": "extreme",
    "muitodificil": "extreme",
    "extreme": "extreme",
}


def normalize_level(raw: str) -> str:
    value = " ".join(str(raw or "").strip().lower().split())
    return ALIASES.get(value, "medium")


def level_config(raw: str) -> MemoryLevel:
    return MEMORY_LEVELS[normalize_level(raw)]
