from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from source_v2_shop import COINS_PER_PRISM, daily_rotation_ids


def _pool(size: int = 40) -> list[dict]:
    return [
        {
            "id": index,
            "name": f"Character {index}",
            "anime": "Anime",
            "img_url": f"https://cdn.example/{index}.jpg",
        }
        for index in range(1, size + 1)
    ]


def test_shop_rotation_is_deterministic_for_same_utc_day() -> None:
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    assert daily_rotation_ids(now, pool=_pool()) == daily_rotation_ids(now, pool=_pool())
    assert len(daily_rotation_ids(now, pool=_pool())) == 18


def test_shop_rotation_keeps_existing_source_ids() -> None:
    ids = daily_rotation_ids(datetime(2026, 9, 4, tzinfo=timezone.utc), pool=_pool())
    assert all(1 <= character_id <= 40 for character_id in ids)
    assert len(ids) == len(set(ids))


def test_exchange_rate_matches_seal_contract() -> None:
    assert COINS_PER_PRISM == 10_000


def test_shop_purchase_uses_existing_collection_identity_helper() -> None:
    text = Path("source_v2_shop.py").read_text(encoding="utf-8")
    assert "grant_character_locked(cur, user_id, character_id)" in text
    assert "INSERT INTO user_card_collection" not in text
    assert "character_already_owned" in text
    assert "FOR UPDATE" in text


def test_shop_routes_use_shared_source_auth() -> None:
    text = Path("webapp_routes/source_v2_shop.py").read_text(encoding="utf-8")
    assert "from utils.source_v2_auth import resolve_source_v2_identity" in text
    assert "ALLOW_INSECURE_WEBAPP_UID_FALLBACK" not in text
    assert "shop/exchange/{direction}" in text
    assert "shop/buy/character/{character_id}" in text
