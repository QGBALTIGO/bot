from __future__ import annotations

import os
import unicodedata


ACTIVITY_THRESHOLD = max(10, int(os.getenv("CAPTURE_V2_ACTIVITY_THRESHOLD", "35")))
USER_ACTIVITY_COOLDOWN_SECONDS = max(5, int(os.getenv("CAPTURE_V2_USER_COOLDOWN", "20")))
ACTIVITY_WINDOW_SECONDS = max(120, int(os.getenv("CAPTURE_V2_ACTIVITY_WINDOW", "900")))
MIN_UNIQUE_PARTICIPANTS = max(2, int(os.getenv("CAPTURE_V2_MIN_PARTICIPANTS", "3")))
GROUP_SPAWN_COOLDOWN_SECONDS = max(120, int(os.getenv("CAPTURE_V2_GROUP_COOLDOWN", "900")))
ESCAPE_SECONDS = max(30, int(os.getenv("CAPTURE_V2_ESCAPE_SECONDS", "240")))
XP_REWARD = max(1, int(os.getenv("CAPTURE_V2_XP_REWARD", "10")))
PURCHASE_PRICE = max(1, int(os.getenv("CAPTURE_V2_PURCHASE_PRICE", "5")))
PURCHASE_WINDOW_SECONDS = max(30, int(os.getenv("CAPTURE_V2_PURCHASE_WINDOW", "180")))
RECENT_CHARACTER_WINDOW = max(4, int(os.getenv("CAPTURE_V2_RECENT_CHARACTERS", "12")))


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in text)
    return " ".join(text.split())


def name_matches(character_name: str, guess: str) -> bool:
    full = normalize_name(character_name)
    probe = normalize_name(guess)
    if not full or not probe:
        return False
    if probe == full or probe.replace(" ", "") == full.replace(" ", ""):
        return True

    full_tokens = full.split()
    guess_tokens = probe.split()
    if len(guess_tokens) == 1:
        token = guess_tokens[0]
        if len(token) < 2:
            return False
        if token in full_tokens:
            return True
        return len(token) >= 3 and any(part.startswith(token) for part in full_tokens)

    if len(guess_tokens) > len(full_tokens):
        return False
    remaining = list(full_tokens)
    for token in guess_tokens:
        match_index = next(
            (
                idx
                for idx, part in enumerate(remaining)
                if token == part or (len(token) >= 3 and part.startswith(token))
            ),
            None,
        )
        if match_index is None:
            return False
        remaining.pop(match_index)
    return True


def valid_activity_text(text: str) -> bool:
    value = " ".join(str(text or "").split())
    if not value or value.startswith("/"):
        return False
    if len(value) < 3:
        return False
    # Repeated one-character spam such as "aaaaa" or punctuation-only noise
    # should not move the spawn meter.
    normalized = normalize_name(value)
    if len(normalized) < 3:
        return False
    return True
