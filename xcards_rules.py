from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DAILY_XCARD_SLOTS = 6


@dataclass(frozen=True)
class XCardTier:
    code: str
    label: str
    max_bp: int | None
    price: int
    level_required: int


XCARD_TIERS: tuple[XCardTier, ...] = (
    XCardTier("rookie", "Iniciante", 2000, 4, 1),
    XCardTier("standard", "Padrão", 3000, 6, 3),
    XCardTier("advanced", "Avançada", 4000, 9, 7),
    XCardTier("elite", "Elite", None, 13, 12),
)


def parse_bp(raw: Any) -> int:
    if isinstance(raw, int):
        return max(0, raw)
    text = str(raw or "")
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits or 0)


def tier_for_card(card: dict[str, Any]) -> XCardTier:
    bp = parse_bp(card.get("bp_value") or card.get("bp"))
    for tier in XCARD_TIERS:
        if tier.max_bp is None or bp <= tier.max_bp:
            return tier
    return XCARD_TIERS[-1]


def is_market_eligible(card: dict[str, Any]) -> bool:
    card_id = int(card.get("id") or 0)
    bp = parse_bp(card.get("bp_value") or card.get("bp"))
    image = str(card.get("image") or "").strip()
    return card_id > 0 and bp > 0 and bool(image)
