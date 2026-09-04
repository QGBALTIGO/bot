from __future__ import annotations

import pytest

import source_v2_minigames as games
from source_v2_rewards import xp_to_level


def test_wheel_probability_boundaries_match_seal_contract() -> None:
    assert games.roll_wheel_index(0.00) == 3
    assert games.roll_wheel_index(0.049) == 3
    assert games.roll_wheel_index(0.05) == 5
    assert games.roll_wheel_index(0.149) == 5
    assert games.roll_wheel_index(0.15) == 2
    assert games.roll_wheel_index(0.30) == 4
    assert games.roll_wheel_index(0.45) == 1
    assert games.roll_wheel_index(0.60) == 6
    assert games.roll_wheel_index(0.75) == 0
    assert games.roll_wheel_index(0.90) == 7


def test_cipher_reward_rejects_suspicious_perfect_run() -> None:
    with pytest.raises(ValueError, match="suspicious_activity"):
        games._cipher_reward(8, 4.99)


def test_cipher_reward_rejects_insufficient_score() -> None:
    with pytest.raises(ValueError, match="insufficient_score"):
        games._cipher_reward(3, 30.0)


def test_cipher_reward_matches_seal_formula(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter([20, 5])
    monkeypatch.setattr(games.random, "randint", lambda _a, _b: next(values))
    coins, xp = games._cipher_reward(8, 20.0)
    assert coins == (8 * 25) + 20 + 100
    assert xp == (8 * 5) + 5 + 30


def test_wheel_rewards_preserve_contract() -> None:
    assert games._wheel_reward({"type": "character"}) == (100, 25, True)
    assert games._wheel_reward({"type": "xp"}) == (50, 250, False)
    assert games._wheel_reward({"type": "shards", "amount": 200}) == (200, 25, False)


def test_cipher_session_uses_existing_source_character_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = [
        {
            "id": str(index),
            "character_id": index,
            "img_url": f"https://cdn.example/{index}.jpg",
            "name": f"Character {index}",
            "anime": "Anime",
            "rarity": "Standard",
        }
        for index in range(1, 9)
    ]
    monkeypatch.setattr(games, "_character_pool", lambda: list(pool))
    monkeypatch.setattr(games.random, "sample", lambda population, _k: list(population))

    session = games.build_game_session("cipher_match")
    assert [card["id"] for card in session["cards"]] == [str(i) for i in range(1, 9)]
    assert all(card["img_url"].startswith("https://") for card in session["cards"])


def test_source_xp_formula_is_shared_by_v2_rewards() -> None:
    assert xp_to_level(0) == 1
    assert xp_to_level(200) == 2
    assert xp_to_level(600) == 3
