from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from psycopg.rows import dict_row

from database_core import pool


PET_CATALOG: list[dict[str, Any]] = [
    {
        "petid": "fluffy_fox",
        "id": "fluffy_fox",
        "name": "Raposa Fofinha 🦊",
        "rarity": "Inicial",
        "hp": 105,
        "atk": 18,
        "spd": 32,
        "luck": 0.08,
        "ability": "Aprendizado Rápido",
        "desc": "+10% de XP nos Jogos AniNexus",
        "img": "https://files.catbox.moe/2hsawz.jpg",
        "coin_price": 0,
        "req_level": 1,
    },
    {
        "petid": "blaze_fang",
        "id": "blaze_fang",
        "name": "Presa de Fogo 🐺",
        "rarity": "Incomum",
        "hp": 125,
        "atk": 34,
        "spd": 22,
        "luck": 0.10,
        "ability": "Catador",
        "desc": "15% de chance de +1 Coin nos Jogos AniNexus",
        "img": "https://i.ibb.co/fd1qPVJs/file-89.jpg",
        "coin_price": 3,
        "req_level": 2,
    },
    {
        "petid": "shadow_panther",
        "id": "shadow_panther",
        "name": "Pantera Sombria 🐆",
        "rarity": "Raro",
        "hp": 115,
        "atk": 28,
        "spd": 42,
        "luck": 0.14,
        "ability": "Reserva de Energia",
        "desc": "+1 de energia máxima nos Jogos AniNexus",
        "img": "https://i.ibb.co/8CdC5QG/file-86.jpg",
        "coin_price": 6,
        "req_level": 5,
    },
    {
        "petid": "cosmic_phoenix",
        "id": "cosmic_phoenix",
        "name": "Fênix Cósmica 🦅",
        "rarity": "Épico",
        "hp": 150,
        "atk": 24,
        "spd": 30,
        "luck": 0.18,
        "ability": "Incubação Acelerada",
        "desc": "Ovos incubam 50% mais rápido",
        "img": "https://i.ibb.co/b5CrL8rp/file-84.jpg",
        "coin_price": 10,
        "req_level": 10,
    },
    {
        "petid": "mystic_dragon",
        "id": "mystic_dragon",
        "name": "Dragão Místico 🐲",
        "rarity": "Lendário",
        "hp": 180,
        "atk": 40,
        "spd": 18,
        "luck": 0.22,
        "ability": "Guardião de Ovos",
        "desc": "10% de chance de encontrar um Ovo Comum após um jogo",
        "img": "https://files.catbox.moe/7kvcqj.jpg",
        "coin_price": 15,
        "req_level": 15,
    },
]
PET_BY_ID = {str(pet["petid"]): dict(pet) for pet in PET_CATALOG}

EGG_TIERS: dict[str, dict[str, Any]] = {
    "common": {"name": "Ovo Comum", "wait_min": 4, "rank": 0, "sell_price": 1, "keywords": ["common", "medium", "comum", "médio", "medio"]},
    "gold": {"name": "Ovo Dourado", "wait_min": 20, "rank": 1, "sell_price": 2, "keywords": ["rare", "legendary", "raro", "lendário", "lendario"]},
    "void": {"name": "Ovo do Vazio", "wait_min": 75, "rank": 2, "sell_price": 3, "keywords": ["cosmic", "immortal", "exclusive", "cósmico", "cosmico", "imortal", "exclusivo"]},
    "rare": {"name": "Ovo Raro", "wait_min": 120, "rank": 3, "sell_price": 4, "keywords": ["rare", "legendary", "cosmic", "immortal", "raro", "lendário", "lendario", "cósmico", "cosmico", "imortal"]},
    "legendary": {"name": "Ovo Lendário", "wait_min": 240, "rank": 4, "sell_price": 5, "keywords": ["exclusive", "eternal", "royal", "mythical", "exclusivo", "eterno", "real", "mítico", "mitico"]},
    "celestial": {"name": "Ovo Celestial", "wait_min": 420, "rank": 5, "sell_price": 7, "keywords": ["celestial", "divine", "astral", "prestige", "divino", "prestígio", "prestigio"]},
}
EGG_ORDER = ["common", "gold", "void", "rare", "legendary", "celestial"]

XP_PER_LEVEL = 100
MAX_AFFECTION = 100
FEED_COST = 1
FEED_COOLDOWN_HOURS = 6
TRAIN_COOLDOWN_HOURS = 8

_TABLE_LOCK = Lock()
_TABLE_READY = False


def _ensure_tables() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    with _TABLE_LOCK:
        if _TABLE_READY:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_pet_profiles (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                        initialized_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_user_pets (
                        user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        pet_id TEXT NOT NULL,
                        level INTEGER NOT NULL DEFAULT 1,
                        xp INTEGER NOT NULL DEFAULT 0,
                        affection INTEGER NOT NULL DEFAULT 50,
                        is_active BOOLEAN NOT NULL DEFAULT FALSE,
                        last_feed_at TIMESTAMPTZ,
                        last_train_at TIMESTAMPTZ,
                        owned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, pet_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_aninexus_active_pet
                    ON aninexus_user_pets (user_id)
                    WHERE is_active = TRUE
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_user_eggs (
                        egg_id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        tier TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'fresh',
                        is_corrupted BOOLEAN NOT NULL DEFAULT FALSE,
                        incubated_at TIMESTAMPTZ,
                        hatch_at TIMESTAMPTZ,
                        resolved_character_id BIGINT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_aninexus_eggs_user_status
                    ON aninexus_user_eggs (user_id, status, created_at DESC)
                    """
                )
                conn.commit()
        _TABLE_READY = True


def _ensure_user_initialized(user_id: int) -> None:
    _ensure_tables()
    user_id = int(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO aninexus_pet_profiles (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO NOTHING
                    RETURNING user_id
                    """,
                    (user_id,),
                )
                first_time = bool(cur.fetchone())
                if first_time:
                    cur.execute(
                        """
                        INSERT INTO aninexus_user_pets
                            (user_id, pet_id, level, xp, affection, is_active)
                        VALUES (%s, 'fluffy_fox', 1, 0, 50, TRUE)
                        ON CONFLICT (user_id, pet_id) DO NOTHING
                        """,
                        (user_id,),
                    )
                    cur.execute(
                        """
                        INSERT INTO aninexus_user_eggs (user_id, tier, status, is_corrupted)
                        VALUES (%s, 'common', 'fresh', FALSE)
                        """,
                        (user_id,),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _pet_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    pet_id = str(row.get("pet_id") or row.get("petid") or "fluffy_fox")
    template = dict(PET_BY_ID.get(pet_id) or PET_BY_ID["fluffy_fox"])
    level = max(1, int(row.get("level") or 1))
    xp = max(0, int(row.get("xp") or 0))
    template.update(
        {
            "petid": pet_id,
            "id": pet_id,
            "level": level,
            "xp": xp,
            "xp_needed": level * XP_PER_LEVEL,
            "affection": max(0, min(MAX_AFFECTION, int(row.get("affection") or 0))),
            "is_active": bool(row.get("is_active")),
            "zenith_price": int(template.get("coin_price") or 0),
            "coin_price": int(template.get("coin_price") or 0),
        }
    )
    return template


def get_user_pets(user_id: int) -> List[Dict[str, Any]]:
    _ensure_user_initialized(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM aninexus_user_pets
                WHERE user_id = %s
                ORDER BY is_active DESC, level DESC, owned_at ASC
                """,
                (int(user_id),),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
            conn.commit()
    return [_pet_payload(row) for row in rows]


def get_active_pet(user_id: int) -> Optional[Dict[str, Any]]:
    pets = get_user_pets(user_id)
    return next((pet for pet in pets if pet.get("is_active")), pets[0] if pets else None)


def get_pet_catalog_for_user(user_id: int) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    pets = get_user_pets(user_id)
    owned_ids = {str(pet.get("petid") or "") for pet in pets}
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COALESCE(level, 1) AS level FROM user_progress WHERE user_id = %s", (int(user_id),))
            level = max(1, int((cur.fetchone() or {}).get("level") or 1))
            conn.commit()

    catalog = []
    for item in PET_CATALOG:
        pet = dict(item)
        pet["zenith_price"] = int(pet.get("coin_price") or 0)
        pet["owned"] = str(pet["petid"]) in owned_ids
        catalog.append(pet)
    return {
        "pets": catalog,
        "owned": [str(pet.get("name") or "") for pet in pets],
        "owned_ids": sorted(owned_ids),
        "current_level": level,
    }


def buy_pet(user_id: int, pet_id: str) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    user_id = int(user_id)
    pet_id = str(pet_id or "").strip()
    template = PET_BY_ID.get(pet_id)
    if not template:
        return {"ok": False, "error": "pet_not_found"}
    price = max(0, int(template.get("coin_price") or 0))
    required_level = max(1, int(template.get("req_level") or 1))

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT 1 FROM aninexus_user_pets WHERE user_id=%s AND pet_id=%s",
                    (user_id, pet_id),
                )
                if cur.fetchone():
                    conn.rollback()
                    return {"ok": False, "error": "already_owned"}
                cur.execute("SELECT COALESCE(level,1) AS level FROM user_progress WHERE user_id=%s", (user_id,))
                level = max(1, int((cur.fetchone() or {}).get("level") or 1))
                if level < required_level:
                    conn.rollback()
                    return {"ok": False, "error": "level_required", "required_level": required_level}
                cur.execute("SELECT coins FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                coins = int((cur.fetchone() or {}).get("coins") or 0)
                if coins < price:
                    conn.rollback()
                    return {"ok": False, "error": "insufficient_coins", "price": price, "coins": coins}
                new_balance = coins - price
                if price:
                    cur.execute("UPDATE users SET coins=%s, updated_at=NOW() WHERE user_id=%s", (new_balance, user_id))
                cur.execute(
                    """
                    INSERT INTO aninexus_user_pets
                        (user_id, pet_id, level, xp, affection, is_active)
                    VALUES (%s,%s,1,0,50,FALSE)
                    """,
                    (user_id, pet_id),
                )
                if price:
                    cur.execute(
                        """
                        INSERT INTO shop_transactions
                            (user_id, type, amount, balance_after, metadata)
                        VALUES (%s,'aninexus_buy_pet',%s,%s,jsonb_build_object('pet_id',%s))
                        """,
                        (user_id, -price, new_balance, pet_id),
                    )
                conn.commit()
                return {"ok": True, "pet": _pet_payload({"pet_id": pet_id, "level": 1, "xp": 0, "affection": 50, "is_active": False}), "coins": new_balance}
            except Exception:
                conn.rollback()
                raise


def set_active_pet(user_id: int, pet_id: str) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT * FROM aninexus_user_pets WHERE user_id=%s AND pet_id=%s FOR UPDATE",
                    (int(user_id), str(pet_id)),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return {"ok": False, "error": "pet_not_owned"}
                cur.execute("UPDATE aninexus_user_pets SET is_active=FALSE, updated_at=NOW() WHERE user_id=%s", (int(user_id),))
                cur.execute(
                    "UPDATE aninexus_user_pets SET is_active=TRUE, updated_at=NOW() WHERE user_id=%s AND pet_id=%s",
                    (int(user_id), str(pet_id)),
                )
                conn.commit()
                return {"ok": True}
            except Exception:
                conn.rollback()
                raise


def _level_up_pet(level: int, xp: int) -> tuple[int, int]:
    level = max(1, int(level))
    xp = max(0, int(xp))
    while xp >= level * XP_PER_LEVEL:
        xp -= level * XP_PER_LEVEL
        level += 1
    return level, xp


def care_for_active_pet(user_id: int, action: str) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    user_id = int(user_id)
    action = str(action or "").strip().lower()
    if action not in {"feed", "train"}:
        return {"ok": False, "error": "invalid_action"}

    now = datetime.now(timezone.utc)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT * FROM aninexus_user_pets WHERE user_id=%s AND is_active=TRUE FOR UPDATE",
                    (user_id,),
                )
                pet = dict(cur.fetchone() or {})
                if not pet:
                    conn.rollback()
                    return {"ok": False, "error": "no_active_pet"}

                if action == "feed":
                    last_at = pet.get("last_feed_at")
                    cooldown = timedelta(hours=FEED_COOLDOWN_HOURS)
                    if last_at and now < last_at + cooldown:
                        remaining = int(((last_at + cooldown) - now).total_seconds())
                        conn.rollback()
                        return {"ok": False, "error": "cooldown", "remaining_seconds": remaining}
                    cur.execute("SELECT coins FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                    coins = int((cur.fetchone() or {}).get("coins") or 0)
                    if coins < FEED_COST:
                        conn.rollback()
                        return {"ok": False, "error": "insufficient_coins"}
                    new_balance = coins - FEED_COST
                    cur.execute("UPDATE users SET coins=%s, updated_at=NOW() WHERE user_id=%s", (new_balance, user_id))
                    level, xp = _level_up_pet(int(pet.get("level") or 1), int(pet.get("xp") or 0) + 10)
                    affection = min(MAX_AFFECTION, int(pet.get("affection") or 0) + 10)
                    cur.execute(
                        """
                        UPDATE aninexus_user_pets
                        SET level=%s, xp=%s, affection=%s, last_feed_at=NOW(), updated_at=NOW()
                        WHERE user_id=%s AND pet_id=%s
                        """,
                        (level, xp, affection, user_id, str(pet.get("pet_id"))),
                    )
                    cur.execute(
                        """
                        INSERT INTO shop_transactions (user_id,type,amount,balance_after,metadata)
                        VALUES (%s,'aninexus_pet_feed',%s,%s,jsonb_build_object('pet_id',%s))
                        """,
                        (user_id, -FEED_COST, new_balance, str(pet.get("pet_id"))),
                    )
                    message = "Companheiro alimentado: +10 vínculo e +10 XP."
                else:
                    last_at = pet.get("last_train_at")
                    cooldown = timedelta(hours=TRAIN_COOLDOWN_HOURS)
                    if last_at and now < last_at + cooldown:
                        remaining = int(((last_at + cooldown) - now).total_seconds())
                        conn.rollback()
                        return {"ok": False, "error": "cooldown", "remaining_seconds": remaining}
                    level, xp = _level_up_pet(int(pet.get("level") or 1), int(pet.get("xp") or 0) + 20)
                    affection = min(MAX_AFFECTION, int(pet.get("affection") or 0) + 3)
                    cur.execute(
                        """
                        UPDATE aninexus_user_pets
                        SET level=%s, xp=%s, affection=%s, last_train_at=NOW(), updated_at=NOW()
                        WHERE user_id=%s AND pet_id=%s
                        """,
                        (level, xp, affection, user_id, str(pet.get("pet_id"))),
                    )
                    message = "Treino concluído: +20 XP e +3 vínculo."
                conn.commit()
                return {"ok": True, "message": message}
            except Exception:
                conn.rollback()
                raise


def active_pet_modifiers(user_id: int) -> Dict[str, Any]:
    pet = get_active_pet(user_id)
    pet_id = str((pet or {}).get("petid") or "")
    return {
        "pet_id": pet_id,
        "xp_multiplier": 1.10 if pet_id == "fluffy_fox" else 1.0,
        "bonus_coin_chance": 0.15 if pet_id == "blaze_fang" else 0.0,
        "energy_bonus": 1 if pet_id == "shadow_panther" else 0,
        "incubation_multiplier": 0.5 if pet_id == "cosmic_phoenix" else 1.0,
        "egg_drop_chance": 0.10 if pet_id == "mystic_dragon" else 0.0,
    }


def grant_egg(user_id: int, tier: str = "common", corrupted: bool = False) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    tier = str(tier or "common").lower()
    if tier not in EGG_TIERS:
        tier = "common"
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO aninexus_user_eggs (user_id, tier, status, is_corrupted)
                VALUES (%s,%s,'fresh',%s)
                RETURNING egg_id
                """,
                (int(user_id), tier, bool(corrupted)),
            )
            egg_id = int((cur.fetchone() or {}).get("egg_id") or 0)
            conn.commit()
    return {"ok": True, "egg_id": egg_id, "tier": tier}


def _egg_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    tier = str(row.get("tier") or "common")
    info = EGG_TIERS.get(tier, EGG_TIERS["common"])
    hatch_at = row.get("hatch_at")
    now = datetime.now(timezone.utc)
    remaining = 0
    if hatch_at:
        remaining = max(0, int(((hatch_at - now).total_seconds() + 59) // 60))
    return {
        "id": str(int(row.get("egg_id") or 0)),
        "tier": tier,
        "name": str(info["name"]),
        "status": str(row.get("status") or "fresh"),
        "is_corrupted": bool(row.get("is_corrupted")),
        "hatch_time": hatch_at.isoformat() if hasattr(hatch_at, "isoformat") else None,
        "remaining_mins": remaining,
        "base_wait_min": int(info["wait_min"]),
        "wait_min": int(info["wait_min"]),
        "incubation_pass_type": "free",
        "sell_price": int(info["sell_price"]),
    }


def get_user_eggs(user_id: int) -> List[Dict[str, Any]]:
    _ensure_user_initialized(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM aninexus_user_eggs
                WHERE user_id=%s AND status IN ('fresh','incubating')
                ORDER BY created_at ASC, egg_id ASC
                """,
                (int(user_id),),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
            conn.commit()
    return [_egg_payload(row) for row in rows]


def incubate_egg(user_id: int, egg_id: int) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    user_id = int(user_id)
    egg_id = int(egg_id)
    modifiers = active_pet_modifiers(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT * FROM aninexus_user_eggs WHERE egg_id=%s AND user_id=%s FOR UPDATE",
                    (egg_id, user_id),
                )
                egg = dict(cur.fetchone() or {})
                if not egg:
                    conn.rollback()
                    return {"ok": False, "error": "egg_not_found"}
                if str(egg.get("status")) != "fresh":
                    conn.rollback()
                    return {"ok": False, "error": "invalid_status"}
                cur.execute(
                    "SELECT COUNT(*) AS total FROM aninexus_user_eggs WHERE user_id=%s AND status='incubating'",
                    (user_id,),
                )
                if int((cur.fetchone() or {}).get("total") or 0) >= 1:
                    conn.rollback()
                    return {"ok": False, "error": "no_slot"}
                tier = str(egg.get("tier") or "common")
                base_wait = int(EGG_TIERS.get(tier, EGG_TIERS["common"])["wait_min"])
                wait_min = max(1, int(round(base_wait * float(modifiers["incubation_multiplier"]))))
                cur.execute(
                    """
                    UPDATE aninexus_user_eggs
                    SET status='incubating', incubated_at=NOW(), hatch_at=NOW()+(%s||' minutes')::interval, updated_at=NOW()
                    WHERE egg_id=%s
                    """,
                    (str(wait_min), egg_id),
                )
                conn.commit()
                return {"ok": True, "wait_min": wait_min}
            except Exception:
                conn.rollback()
                raise


def _candidate_character_ids(tier: str) -> List[int]:
    from cards_service import build_cards_final_data

    data = build_cards_final_data()
    info = EGG_TIERS.get(str(tier), EGG_TIERS["common"])
    keywords = [str(value).lower() for value in info.get("keywords") or []]
    ids: list[int] = []
    seen: set[int] = set()
    for label, characters in (data.get("subcategories") or {}).items():
        label_low = str(label or "").lower()
        if keywords and not any(keyword in label_low for keyword in keywords):
            continue
        for character in characters or []:
            cid = int((character or {}).get("id") or 0)
            if cid > 0 and cid not in seen:
                seen.add(cid)
                ids.append(cid)
    if ids:
        return ids
    return [int(cid) for cid in (data.get("characters_by_id") or {}).keys() if int(cid) > 0]


def hatch_egg(user_id: int, egg_id: int) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    user_id = int(user_id)
    egg_id = int(egg_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT * FROM aninexus_user_eggs WHERE egg_id=%s AND user_id=%s FOR UPDATE",
                    (egg_id, user_id),
                )
                egg = dict(cur.fetchone() or {})
                if not egg:
                    conn.rollback()
                    return {"ok": False, "error": "egg_not_found"}
                if str(egg.get("status")) != "incubating":
                    conn.rollback()
                    return {"ok": False, "error": "not_incubating"}
                hatch_at = egg.get("hatch_at")
                now = datetime.now(timezone.utc)
                if hatch_at and hatch_at > now:
                    remaining = max(1, int(((hatch_at - now).total_seconds() + 59) // 60))
                    conn.rollback()
                    return {"ok": False, "error": "not_ready", "remaining_mins": remaining}

                tier = str(egg.get("tier") or "common")
                candidates = _candidate_character_ids(tier)
                if not candidates:
                    conn.rollback()
                    return {"ok": False, "error": "catalog_empty"}
                character_id = random.SystemRandom().choice(candidates)
                cur.execute(
                    """
                    INSERT INTO user_card_collection (user_id,character_id,quantity,first_obtained_at,updated_at)
                    VALUES (%s,%s,1,NOW(),NOW())
                    ON CONFLICT (user_id,character_id) DO UPDATE
                    SET quantity=user_card_collection.quantity+1, updated_at=NOW()
                    """,
                    (user_id, character_id),
                )
                cur.execute(
                    """
                    UPDATE aninexus_user_eggs
                    SET status='hatched', resolved_character_id=%s, updated_at=NOW()
                    WHERE egg_id=%s
                    """,
                    (character_id, egg_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    from cards_service import get_character_by_id
    from utils.web_image_url import web_image_url

    meta = dict(get_character_by_id(character_id) or {})
    return {
        "ok": True,
        "character": {
            "id": str(character_id),
            "name": str(meta.get("name") or f"Personagem {character_id}"),
            "anime": str(meta.get("anime") or ""),
            "rarity": str(meta.get("subcategory") or "Personagem"),
            "img_url": web_image_url(meta.get("image")),
            "owned": True,
            "count": 1,
            "zenith_price": 0,
        },
    }


def sell_egg(user_id: int, egg_id: int) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT * FROM aninexus_user_eggs WHERE egg_id=%s AND user_id=%s FOR UPDATE",
                    (int(egg_id), int(user_id)),
                )
                egg = dict(cur.fetchone() or {})
                if not egg or str(egg.get("status")) != "fresh":
                    conn.rollback()
                    return {"ok": False, "error": "egg_unavailable"}
                tier = str(egg.get("tier") or "common")
                price = int(EGG_TIERS.get(tier, EGG_TIERS["common"])["sell_price"])
                cur.execute(
                    "UPDATE users SET coins=COALESCE(coins,0)+%s,updated_at=NOW() WHERE user_id=%s RETURNING coins",
                    (price, int(user_id)),
                )
                balance = int((cur.fetchone() or {}).get("coins") or 0)
                cur.execute("UPDATE aninexus_user_eggs SET status='sold',updated_at=NOW() WHERE egg_id=%s", (int(egg_id),))
                cur.execute(
                    """
                    INSERT INTO shop_transactions(user_id,type,amount,balance_after,reference_id,metadata)
                    VALUES (%s,'aninexus_sell_egg',%s,%s,%s,jsonb_build_object('tier',%s))
                    """,
                    (int(user_id), price, balance, int(egg_id), tier),
                )
                conn.commit()
                return {"ok": True, "message": f"Ovo vendido por {price} Coin{'s' if price != 1 else ''}.", "coins": balance}
            except Exception:
                conn.rollback()
                raise


def purify_egg(user_id: int, egg_id: int) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT * FROM aninexus_user_eggs WHERE egg_id=%s AND user_id=%s FOR UPDATE",
                    (int(egg_id), int(user_id)),
                )
                egg = dict(cur.fetchone() or {})
                if not egg or str(egg.get("status")) != "fresh" or not bool(egg.get("is_corrupted")):
                    conn.rollback()
                    return {"ok": False, "error": "egg_not_corrupted"}
                cur.execute("SELECT coins FROM users WHERE user_id=%s FOR UPDATE", (int(user_id),))
                coins = int((cur.fetchone() or {}).get("coins") or 0)
                if coins < 1:
                    conn.rollback()
                    return {"ok": False, "error": "insufficient_coins"}
                cur.execute("UPDATE users SET coins=coins-1,updated_at=NOW() WHERE user_id=%s RETURNING coins", (int(user_id),))
                balance = int((cur.fetchone() or {}).get("coins") or 0)
                cur.execute("UPDATE aninexus_user_eggs SET is_corrupted=FALSE,updated_at=NOW() WHERE egg_id=%s", (int(egg_id),))
                cur.execute(
                    "INSERT INTO shop_transactions(user_id,type,amount,balance_after,reference_id) VALUES (%s,'aninexus_purify_egg',-1,%s,%s)",
                    (int(user_id), balance, int(egg_id)),
                )
                conn.commit()
                return {"ok": True, "message": "Ovo purificado."}
            except Exception:
                conn.rollback()
                raise


def fuse_eggs(user_id: int, tier: str) -> Dict[str, Any]:
    _ensure_user_initialized(user_id)
    tier = str(tier or "").lower()
    if tier not in EGG_ORDER or tier == EGG_ORDER[-1]:
        return {"ok": False, "error": "invalid_tier"}
    next_tier = EGG_ORDER[EGG_ORDER.index(tier) + 1]
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT egg_id FROM aninexus_user_eggs
                    WHERE user_id=%s AND tier=%s AND status='fresh'
                    ORDER BY egg_id ASC
                    LIMIT 3
                    FOR UPDATE
                    """,
                    (int(user_id), tier),
                )
                ids = [int(row.get("egg_id") or 0) for row in (cur.fetchall() or [])]
                if len(ids) < 3:
                    conn.rollback()
                    return {"ok": False, "error": "not_enough_eggs"}
                cur.execute("UPDATE aninexus_user_eggs SET status='fused',updated_at=NOW() WHERE egg_id=ANY(%s)", (ids,))
                cur.execute(
                    """
                    INSERT INTO aninexus_user_eggs(user_id,tier,status,is_corrupted)
                    VALUES (%s,%s,'fresh',FALSE)
                    RETURNING egg_id
                    """,
                    (int(user_id), next_tier),
                )
                new_id = int((cur.fetchone() or {}).get("egg_id") or 0)
                conn.commit()
                return {"ok": True, "message": f"Fusão concluída: {EGG_TIERS[next_tier]['name']} criado.", "egg_id": new_id}
            except Exception:
                conn.rollback()
                raise
