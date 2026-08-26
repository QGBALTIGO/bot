from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from psycopg.rows import dict_row

from database import pool
from game_rules import today_sp
from wallet_tx import insert_ledger, lock_wallet, wallet_payload
from xcards_rules import DAILY_XCARD_SLOTS, XCARD_TIERS, is_market_eligible, tier_for_card
from xcards_service import build_xcards_data, get_xcard_by_id


class XCardError(RuntimeError):
    pass


class XCardOfferNotFound(XCardError):
    pass


class XCardAlreadyPurchased(XCardError):
    pass


class XCardInsufficientCoins(XCardError):
    pass


class XCardLevelRequired(XCardError):
    def __init__(self, level_required: int):
        self.level_required = int(level_required)
        super().__init__(f"level_required:{self.level_required}")


def create_xcard_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_xcard_collection (
                    user_id BIGINT NOT NULL,
                    card_id BIGINT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
                    first_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, card_id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS xcard_daily_offers_v2 (
                    offer_date DATE NOT NULL,
                    slot_code TEXT NOT NULL,
                    display_order INTEGER NOT NULL,
                    card_id BIGINT NOT NULL,
                    tier_code TEXT NOT NULL,
                    price INTEGER NOT NULL CHECK (price > 0),
                    level_required INTEGER NOT NULL DEFAULT 1 CHECK (level_required > 0),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (offer_date, slot_code)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS xcard_purchases_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    offer_date DATE NOT NULL,
                    slot_code TEXT NOT NULL,
                    card_id BIGINT NOT NULL,
                    price_paid INTEGER NOT NULL,
                    purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (user_id, offer_date, slot_code)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_xcard_collection_user
                ON user_xcard_collection (user_id, updated_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_xcard_purchases_user
                ON xcard_purchases_v2 (user_id, purchased_at DESC)
                """
            )
            conn.commit()


def _daily_candidates(target_date: date) -> list[dict[str, Any]]:
    data = build_xcards_data()
    cards = [dict(card) for card in data.get("cards_list") or [] if is_market_eligible(card)]
    if not cards:
        return []

    by_tier: dict[str, list[dict[str, Any]]] = {tier.code: [] for tier in XCARD_TIERS}
    for card in cards:
        by_tier[tier_for_card(card).code].append(card)

    for tier_code, items in by_tier.items():
        items.sort(
            key=lambda card: hashlib.sha256(
                f"{target_date.isoformat()}:{tier_code}:{int(card.get('id') or 0)}".encode("utf-8")
            ).hexdigest()
        )

    plan = ["rookie", "rookie", "standard", "standard", "advanced", "elite"]
    chosen: list[dict[str, Any]] = []
    used: set[int] = set()
    tier_offsets: dict[str, int] = {}

    def take(tier_code: str) -> dict[str, Any] | None:
        items = by_tier.get(tier_code) or []
        offset = tier_offsets.get(tier_code, 0)
        while offset < len(items):
            item = items[offset]
            offset += 1
            tier_offsets[tier_code] = offset
            card_id = int(item.get("id") or 0)
            if card_id and card_id not in used:
                used.add(card_id)
                return item
        return None

    for tier_code in plan:
        item = take(tier_code)
        if item:
            chosen.append(item)

    if len(chosen) < DAILY_XCARD_SLOTS:
        fallback = sorted(
            cards,
            key=lambda card: hashlib.sha256(
                f"{target_date.isoformat()}:fallback:{int(card.get('id') or 0)}".encode("utf-8")
            ).hexdigest(),
        )
        for item in fallback:
            card_id = int(item.get("id") or 0)
            if not card_id or card_id in used:
                continue
            used.add(card_id)
            chosen.append(item)
            if len(chosen) >= DAILY_XCARD_SLOTS:
                break

    return chosen[:DAILY_XCARD_SLOTS]


def ensure_daily_offers(target_date: date | None = None) -> list[dict[str, Any]]:
    target = target_date or today_sp()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT offer_date, slot_code, display_order, card_id, tier_code, price, level_required
                FROM xcard_daily_offers_v2
                WHERE offer_date = %s
                ORDER BY display_order
                """,
                (target,),
            )
            existing = [dict(row) for row in (cur.fetchall() or [])]
            if len(existing) >= DAILY_XCARD_SLOTS:
                return existing

    candidates = _daily_candidates(target)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                for index, card in enumerate(candidates, start=1):
                    tier = tier_for_card(card)
                    cur.execute(
                        """
                        INSERT INTO xcard_daily_offers_v2
                        (offer_date, slot_code, display_order, card_id, tier_code, price, level_required)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (offer_date, slot_code) DO NOTHING
                        """,
                        (
                            target,
                            f"slot-{index}",
                            index,
                            int(card.get("id") or 0),
                            tier.code,
                            tier.price,
                            tier.level_required,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT offer_date, slot_code, display_order, card_id, tier_code, price, level_required
                FROM xcard_daily_offers_v2
                WHERE offer_date = %s
                ORDER BY display_order
                """,
                (target,),
            )
            return [dict(row) for row in (cur.fetchall() or [])]


def _user_level(cur, user_id: int) -> int:
    cur.execute(
        """
        INSERT INTO user_progress (user_id, xp, level, total_actions)
        VALUES (%s, 0, 1, 0)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),),
    )
    cur.execute("SELECT level FROM user_progress WHERE user_id = %s", (int(user_id),))
    return int((cur.fetchone() or {}).get("level") or 1)


def buy_daily_offer(user_id: int, slot_code: str, target_date: date | None = None) -> dict[str, Any]:
    user_id = int(user_id)
    target = target_date or today_sp()
    normalized_slot = str(slot_code or "").strip().lower()
    ensure_daily_offers(target)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                wallet = lock_wallet(cur, user_id)
                cur.execute(
                    """
                    SELECT offer_date, slot_code, card_id, tier_code, price, level_required
                    FROM xcard_daily_offers_v2
                    WHERE offer_date = %s AND LOWER(slot_code) = %s
                    FOR UPDATE
                    """,
                    (target, normalized_slot),
                )
                offer = dict(cur.fetchone() or {})
                if not offer:
                    raise XCardOfferNotFound("offer_not_found")

                level = _user_level(cur, user_id)
                level_required = int(offer.get("level_required") or 1)
                if level < level_required:
                    raise XCardLevelRequired(level_required)

                price = int(offer.get("price") or 0)
                if int(wallet.get("coins") or 0) < price:
                    raise XCardInsufficientCoins("insufficient_coins")

                cur.execute(
                    """
                    INSERT INTO xcard_purchases_v2
                    (user_id, offer_date, slot_code, card_id, price_paid)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, offer_date, slot_code) DO NOTHING
                    RETURNING id
                    """,
                    (user_id, target, offer["slot_code"], int(offer["card_id"]), price),
                )
                purchase = cur.fetchone()
                if not purchase:
                    raise XCardAlreadyPurchased("already_purchased")

                cur.execute(
                    """
                    UPDATE game_wallets
                    SET coins = coins - %s, updated_at = NOW()
                    WHERE user_id = %s AND coins >= %s
                    RETURNING user_id, coins, dice, spins, dice_slot
                    """,
                    (price, user_id, price),
                )
                updated_wallet = dict(cur.fetchone() or {})
                if not updated_wallet:
                    raise XCardInsufficientCoins("insufficient_coins")

                card_id = int(offer["card_id"])
                cur.execute(
                    """
                    INSERT INTO user_xcard_collection
                    (user_id, card_id, quantity, first_obtained_at, updated_at)
                    VALUES (%s, %s, 1, NOW(), NOW())
                    ON CONFLICT (user_id, card_id)
                    DO UPDATE SET quantity = user_xcard_collection.quantity + 1, updated_at = NOW()
                    RETURNING quantity
                    """,
                    (user_id, card_id),
                )
                quantity = int((cur.fetchone() or {}).get("quantity") or 1)
                reference = f"xcard:{target.isoformat()}:{offer['slot_code']}"
                insert_ledger(
                    cur,
                    user_id=user_id,
                    resource="coins",
                    delta=-price,
                    reason="xcard_daily_purchase",
                    reference=reference,
                    metadata={"card_id": card_id, "tier": offer.get("tier_code")},
                )
                conn.commit()
                return {
                    "card_id": card_id,
                    "quantity": quantity,
                    "price_paid": price,
                    "wallet": wallet_payload(updated_wallet),
                }
            except (XCardOfferNotFound, XCardAlreadyPurchased, XCardInsufficientCoins, XCardLevelRequired):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def get_user_xcards(user_id: int) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT card_id, quantity, first_obtained_at, updated_at
                FROM user_xcard_collection
                WHERE user_id = %s AND quantity > 0
                ORDER BY updated_at DESC, card_id
                """,
                (int(user_id),),
            )
            rows = cur.fetchall() or []

    items: list[dict[str, Any]] = []
    for row in rows:
        card = get_xcard_by_id(int(row.get("card_id") or 0)) or {}
        if not card:
            continue
        items.append(
            {
                "card_id": int(card.get("id") or 0),
                "card_no": str(card.get("card_no") or ""),
                "name": str(card.get("name") or "XCARD"),
                "title": str(card.get("title") or "Obra desconhecida"),
                "image": str(card.get("image") or ""),
                "rarity": str(card.get("rarity") or "-"),
                "bp": int(card.get("bp_value") or 0),
                "quantity": int(row.get("quantity") or 0),
            }
        )
    return items


def xcards_state(user_id: int, target_date: date | None = None) -> dict[str, Any]:
    target = target_date or today_sp()
    offers = ensure_daily_offers(target)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            wallet = lock_wallet(cur, int(user_id))
            level = _user_level(cur, int(user_id))
            cur.execute(
                """
                SELECT slot_code FROM xcard_purchases_v2
                WHERE user_id = %s AND offer_date = %s
                """,
                (int(user_id), target),
            )
            purchased = {str(row.get("slot_code") or "") for row in (cur.fetchall() or [])}
            conn.commit()

    serialized: list[dict[str, Any]] = []
    for offer in offers:
        card = get_xcard_by_id(int(offer.get("card_id") or 0)) or {}
        serialized.append(
            {
                "slot_code": str(offer.get("slot_code") or ""),
                "card_id": int(card.get("id") or 0),
                "card_no": str(card.get("card_no") or ""),
                "name": str(card.get("name") or "XCARD"),
                "title": str(card.get("title") or "Obra desconhecida"),
                "image": str(card.get("image") or ""),
                "rarity": str(card.get("rarity") or "-"),
                "bp": int(card.get("bp_value") or 0),
                "tier": str(offer.get("tier_code") or ""),
                "price": int(offer.get("price") or 0),
                "level_required": int(offer.get("level_required") or 1),
                "purchased": str(offer.get("slot_code") or "") in purchased,
            }
        )

    collection = get_user_xcards(int(user_id))
    return {
        "date": target.isoformat(),
        "wallet": wallet_payload(wallet),
        "level": level,
        "offers": serialized,
        "collection": collection,
        "stats": {
            "unique": len(collection),
            "copies": sum(int(item.get("quantity") or 0) for item in collection),
        },
    }
