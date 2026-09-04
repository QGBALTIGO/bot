from __future__ import annotations

from dataclasses import dataclass

import pytest

from gacha_engine import (
    RarityRule,
    apply_pity_update_in_place,
    resolve_drop,
    roll_rarity,
    update_pity_counts,
)


@dataclass
class FixedRandom:
    value: float

    def random(self) -> float:
        return self.value


def _rules() -> list[RarityRule]:
    return [
        RarityRule("common", tier=1, roll_weight=70, pity_threshold=0),
        RarityRule("epic", tier=4, roll_weight=25, pity_threshold=10, duplicate_fragments=4),
        RarityRule("mythical", tier=9, roll_weight=5, pity_threshold=50, requires_fragments=True, fragments_required=3),
    ]


def test_weighted_roll_uses_normal_pool_before_pity() -> None:
    selected = roll_rarity(_rules(), {}, rng=FixedRandom(0.10))
    assert selected.slug == "common"

    selected = roll_rarity(_rules(), {}, rng=FixedRandom(0.80))
    assert selected.slug == "epic"


def test_highest_due_pity_wins_before_randomness() -> None:
    selected = roll_rarity(
        _rules(),
        {"epic": 9, "mythical": 49},
        rng=FixedRandom(0.0),
    )
    assert selected.slug == "mythical"


def test_pity_resets_reached_tiers_and_increments_higher_tiers() -> None:
    rules = _rules()
    selected = rules[1]  # epic
    updated = update_pity_counts(
        {"epic": 7, "mythical": 20},
        rules,
        selected,
    )

    assert updated["epic"] == 0
    assert updated["mythical"] == 21


def test_in_place_pity_update_preserves_previous_counts_until_computed() -> None:
    target = {"epic": 7, "mythical": 20}
    apply_pity_update_in_place(target, _rules(), _rules()[1])
    assert target == {"epic": 0, "mythical": 21}


def test_duplicate_normal_card_can_convert_to_fragments() -> None:
    resolution = resolve_drop(
        RarityRule("epic", 4, 1, duplicate_fragments=4),
        owns_character=True,
        current_fragments=6,
    )

    assert resolution.grant_card is False
    assert resolution.duplicate_converted is True
    assert resolution.fragments_awarded == 4
    assert resolution.fragments_after == 10


def test_fragment_rarity_assembles_card_at_threshold() -> None:
    rarity = RarityRule(
        "mythical",
        tier=9,
        roll_weight=1,
        requires_fragments=True,
        fragments_required=3,
    )

    before = resolve_drop(rarity, owns_character=False, current_fragments=1)
    assert before.grant_card is False
    assert before.fragments_after == 2

    final = resolve_drop(rarity, owns_character=False, current_fragments=2)
    assert final.grant_card is True
    assert final.card_assembled is True
    assert final.fragments_after == 0


def test_roll_rejects_empty_or_zero_weight_pools() -> None:
    with pytest.raises(ValueError, match="at least one rarity"):
        roll_rarity([], {})

    with pytest.raises(ValueError, match="positive value"):
        roll_rarity([RarityRule("zero", 1, 0)], {})
