from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any


WORDS_FILE = os.getenv("TERMO_WORDS_FILE", "data/anime_words_365.json").strip()
WORD_LENGTH = 6
MAX_ATTEMPTS = 6
TIME_LIMIT_SECONDS = 300
XP_REWARD = 10
HINT_COST_COINS = 12


def normalize_word(raw: Any) -> str:
    return str(raw or "").strip().lower()


def valid_format(word: str) -> bool:
    return bool(re.fullmatch(r"[a-záàâãéèêíìîóòôõúùûç]{6}", normalize_word(word)))


@lru_cache(maxsize=1)
def load_words() -> tuple[dict[str, Any], ...]:
    with open(WORDS_FILE, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        word = normalize_word(item.get("word"))
        if not valid_format(word) or word in seen:
            continue
        seen.add(word)
        items.append(
            {
                "word": word,
                "category": str(item.get("category") or "Desconhecido").strip(),
                "source": str(item.get("source") or "Anime").strip(),
                "difficulty": max(1, min(3, int(item.get("difficulty") or 1))),
                "hint": str(item.get("hint") or "").strip(),
            }
        )
    if not items:
        raise RuntimeError("termo_word_list_empty")
    return tuple(items)


@lru_cache(maxsize=1)
def word_index() -> dict[str, dict[str, Any]]:
    return {item["word"]: dict(item) for item in load_words()}


def is_valid_guess(word: str) -> bool:
    return normalize_word(word) in word_index()


def evaluate_guess(secret: str, guess: str) -> list[str]:
    secret = normalize_word(secret)
    guess = normalize_word(guess)
    if len(secret) != WORD_LENGTH or len(guess) != WORD_LENGTH:
        raise ValueError("word_length")

    result = ["absent"] * WORD_LENGTH
    remaining: dict[str, int] = {}
    for index in range(WORD_LENGTH):
        if guess[index] == secret[index]:
            result[index] = "correct"
        else:
            remaining[secret[index]] = remaining.get(secret[index], 0) + 1

    for index in range(WORD_LENGTH):
        if result[index] == "correct":
            continue
        char = guess[index]
        if remaining.get(char, 0) > 0:
            result[index] = "present"
            remaining[char] -= 1
    return result


def daily_coin_reward(attempts: int) -> int:
    attempts = max(1, min(MAX_ATTEMPTS, int(attempts)))
    return max(12 - (attempts - 1) * 2, 2)


def streak_bonus(streak: int) -> int:
    streak = max(0, int(streak))
    if streak and streak % 30 == 0:
        return 50
    if streak and streak % 7 == 0:
        return 15
    if streak and streak % 3 == 0:
        return 5
    return 0
