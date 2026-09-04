from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Mapping, MutableMapping, Protocol


class RandomSource(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class RarityRule:
    slug: str
    tier: int
    roll_weight: float
    pity_threshold: int = 0
    base_reward: int = 0
    requires_fragments: bool = False
    fragments_required: int = 0
    duplicate_fragments: int = 0


@dataclass(frozen=True)
class DropResolution:
    grant_card: bool
    is_fragment: bool
    duplicate_converted: bool
    fragments_awarded: int
    fragments_after: int
    card_assembled: bool


def _active_rarities(rarities: Iterable[RarityRule]) -> list[RarityRule]:
    return sorted(
        [r for r in rarities if r.roll_weight >= 0 and r.tier > 0],
        key=lambda r: (r.tier, r.slug),
    )


def roll_rarity(
    rarities: Iterable[RarityRule],
    pity_counts: Mapping[str, int],
    *,
    rng: RandomSource | None = None,
) -> RarityRule:
    """Choose a rarity with hard pity, then weighted random fallback.

    Mirrors the useful part of BasteArima/GachaBot's pity semantics: the highest
    configured rarity whose threshold is about to be reached wins before normal
    randomness is evaluated.
    """

    rules = _active_rarities(rarities)
    if not rules:
        raise ValueError("at least one rarity is required")

    for rarity in reversed(rules):
        threshold = max(0, int(rarity.pity_threshold or 0))
        if threshold > 0 and int(pity_counts.get(rarity.slug, 0) or 0) >= threshold - 1:
            return rarity

    total_weight = sum(max(0.0, float(r.roll_weight)) for r in rules)
    if total_weight <= 0:
        raise ValueError("rarity roll weights must contain at least one positive value")

    source = rng or random
    target = source.random() * total_weight
    cumulative = 0.0
    for rarity in rules:
        cumulative += max(0.0, float(rarity.roll_weight))
        if target <= cumulative:
            return rarity
    return rules[-1]


def update_pity_counts(
    pity_counts: Mapping[str, int],
    rarities: Iterable[RarityRule],
    selected: RarityRule,
) -> dict[str, int]:
    """Reset pity for the rolled tier and every lower/equal guarantee; increment higher ones."""

    updated = dict(pity_counts)
    for rarity in _active_rarities(rarities):
        if rarity.pity_threshold <= 0:
            continue
        if selected.tier >= rarity.tier:
            updated[rarity.slug] = 0
        else:
            updated[rarity.slug] = max(0, int(updated.get(rarity.slug, 0) or 0)) + 1
    return updated


def resolve_drop(
    rarity: RarityRule,
    *,
    owns_character: bool,
    current_fragments: int = 0,
) -> DropResolution:
    """Resolve card-vs-fragment behavior without touching persistence.

    Fragment-only rarities follow the GachaBot assembly model. Normal duplicate
    cards may instead convert to configured fragments, which keeps duplicate rolls
    valuable without creating a second character identity.
    """

    current_fragments = max(0, int(current_fragments or 0))

    if rarity.requires_fragments:
        awarded = 1
        after = current_fragments + awarded
        needed = max(1, int(rarity.fragments_required or 0))
        assembled = after >= needed
        return DropResolution(
            grant_card=assembled,
            is_fragment=True,
            duplicate_converted=False,
            fragments_awarded=awarded,
            fragments_after=0 if assembled else after,
            card_assembled=assembled,
        )

    duplicate_fragments = max(0, int(rarity.duplicate_fragments or 0))
    if owns_character and duplicate_fragments > 0:
        after = current_fragments + duplicate_fragments
        return DropResolution(
            grant_card=False,
            is_fragment=True,
            duplicate_converted=True,
            fragments_awarded=duplicate_fragments,
            fragments_after=after,
            card_assembled=False,
        )

    return DropResolution(
        grant_card=True,
        is_fragment=False,
        duplicate_converted=False,
        fragments_awarded=0,
        fragments_after=current_fragments,
        card_assembled=False,
    )


def apply_pity_update_in_place(
    target: MutableMapping[str, int],
    rarities: Iterable[RarityRule],
    selected: RarityRule,
) -> None:
    updated = update_pity_counts(target, rarities, selected)
    target.clear()
    target.update(updated)
