from __future__ import annotations

import json
import random
import secrets
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, Optional

from psycopg.rows import dict_row

from database_core import pool

MAX_ENERGY = 5
RECHARGE_MINUTES = 120
SESSION_TTL_MINUTES = 5

_TABLES_LOCK = Lock()
_TABLES_READY = False

WHEEL_PRIZES = [
    {"type": "xp", "amount": 3, "label": "+3 XP"},
    {"type": "xp", "amount": 5, "label": "+5 XP"},
    {"type": "coins", "amount": 1, "label": "+1 Coin"},
    {"type": "character", "label": "Personagem"},
    {"type": "xp", "amount": 8, "label": "+8 XP"},
    {"type": "coins", "amount": 1, "label": "+1 Coin"},
    {"type": "xp", "amount": 5, "label": "+5 XP"},
    {"type": "xp", "amount": 15, "label": "+15 XP"},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pet_modifiers(user_id: int) -> Dict[str, Any]:
    try:
        from database_aninexus_pets import active_pet_modifiers

        return dict(active_pet_modifiers(int(user_id)) or {})
    except Exception:
        return {
            "pet_id": "",
            "xp_multiplier": 1.0,
            "bonus_coin_chance": 0.0,
            "energy_bonus": 0,
            "incubation_multiplier": 1.0,
            "egg_drop_chance": 0.0,
        }


def _effective_max_energy(user_id: int) -> int:
    modifiers = _pet_modifiers(int(user_id))
    return max(1, MAX_ENERGY + max(0, int(modifiers.get("energy_bonus") or 0)))


def _ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return
    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_game_state (
                        user_id BIGINT PRIMARY KEY,
                        energy INTEGER NOT NULL DEFAULT 5,
                        last_energy_recharge TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_game_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        game_type TEXT NOT NULL,
                        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        reward JSONB,
                        status TEXT NOT NULL DEFAULT 'active',
                        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        completed_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_aninexus_game_sessions_user_active
                    ON aninexus_game_sessions (user_id, game_type, status, expires_at DESC)
                    """
                )
                conn.commit()
        _TABLES_READY = True


def _ensure_state_locked(cur, user_id: int, max_energy: int) -> Dict[str, Any]:
    max_energy = max(1, int(max_energy))
    cur.execute(
        """
        INSERT INTO aninexus_game_state (user_id, energy, last_energy_recharge)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id), max_energy),
    )
    cur.execute(
        """
        SELECT user_id, energy, last_energy_recharge
        FROM aninexus_game_state
        WHERE user_id = %s
        FOR UPDATE
        """,
        (int(user_id),),
    )
    return dict(cur.fetchone() or {})


def _refresh_energy_locked(cur, user_id: int, max_energy: int) -> Dict[str, Any]:
    max_energy = max(1, int(max_energy))
    row = _ensure_state_locked(cur, user_id, max_energy)
    raw_energy = max(0, int(row.get("energy") or 0))
    energy = min(max_energy, raw_energy)
    last = row.get("last_energy_recharge")
    now = _now()

    if raw_energy != energy:
        cur.execute(
            """
            UPDATE aninexus_game_state
            SET energy = %s, updated_at = NOW()
            WHERE user_id = %s
            """,
            (energy, int(user_id)),
        )

    if energy >= max_energy:
        return {"energy": max_energy, "last_energy_recharge": None}

    if not isinstance(last, datetime):
        last = now
        cur.execute(
            """
            UPDATE aninexus_game_state
            SET last_energy_recharge = %s, updated_at = NOW()
            WHERE user_id = %s
            """,
            (last, int(user_id)),
        )
        return {"energy": energy, "last_energy_recharge": last}

    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    elapsed = max(0.0, (now - last).total_seconds())
    gained = int(elapsed // (RECHARGE_MINUTES * 60))
    if gained <= 0:
        return {"energy": energy, "last_energy_recharge": last}

    new_energy = min(max_energy, energy + gained)
    new_last = last + timedelta(minutes=gained * RECHARGE_MINUTES)
    if new_energy >= max_energy:
        new_last = now

    cur.execute(
        """
        UPDATE aninexus_game_state
        SET energy = %s,
            last_energy_recharge = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (new_energy, new_last, int(user_id)),
    )
    return {
        "energy": new_energy,
        "last_energy_recharge": None if new_energy >= max_energy else new_last,
    }


def get_game_energy(user_id: int) -> Dict[str, Any]:
    _ensure_tables()
    max_energy = _effective_max_energy(int(user_id))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            state = _refresh_energy_locked(cur, int(user_id), max_energy)
            conn.commit()
    last = state.get("last_energy_recharge")
    return {
        "energy": int(state.get("energy") or 0),
        "max_energy": max_energy,
        "last_energy_recharge": last.isoformat() if isinstance(last, datetime) else None,
        "recharge_minutes": RECHARGE_MINUTES,
    }


def _wheel_index() -> int:
    roll = random.random()
    if roll < 0.05:
        return 3  # personagem
    if roll < 0.15:
        return 5  # coin
    if roll < 0.30:
        return 2  # coin
    if roll < 0.45:
        return 4
    if roll < 0.60:
        return 1
    if roll < 0.75:
        return 6
    if roll < 0.90:
        return 0
    return 7


def _random_character_payload() -> Optional[Dict[str, Any]]:
    try:
        from cards_service import build_cards_final_data
        from utils.web_image_url import web_image_url

        data = build_cards_final_data()
        items = [dict(item) for item in (data.get("characters_by_id") or {}).values()]
        items = [item for item in items if int(item.get("id") or 0) > 0 and str(item.get("image") or "").strip()]
        if not items:
            return None
        item = secrets.choice(items)
        return {
            "id": str(int(item.get("id") or 0)),
            "name": str(item.get("name") or "Personagem"),
            "anime": str(item.get("anime") or "Anime"),
            "rarity": str(item.get("subcategory") or "COMMON").upper(),
            "img_url": web_image_url(item.get("image")),
        }
    except Exception:
        return None


def _cipher_cards() -> list[Dict[str, Any]]:
    try:
        from cards_service import build_cards_final_data
        from utils.web_image_url import web_image_url

        data = build_cards_final_data()
        candidates = [dict(item) for item in (data.get("characters_by_id") or {}).values()]
        candidates = [
            item for item in candidates
            if int(item.get("id") or 0) > 0 and str(item.get("image") or "").strip()
        ]
        if len(candidates) < 8:
            return []
        selected = random.sample(candidates, 8)
        return [
            {
                "id": str(int(item.get("id") or 0)),
                "img_url": web_image_url(item.get("image")),
                "name": str(item.get("name") or "Personagem"),
            }
            for item in selected
        ]
    except Exception:
        return []


def _build_session_payload(game_type: str) -> Optional[Dict[str, Any]]:
    payload: Dict[str, Any] = {"start_time": _now().timestamp()}
    if game_type == "cipher_match":
        cards = _cipher_cards()
        if len(cards) != 8:
            return None
        payload["cards"] = cards
    elif game_type == "nexus_wheel":
        idx = _wheel_index()
        payload["prize_index"] = idx
        payload["prize"] = dict(WHEEL_PRIZES[idx])
    else:
        return None
    return payload


def start_game_session(user_id: int, game_type: str) -> Dict[str, Any]:
    _ensure_tables()
    game_type = str(game_type or "").strip().lower()
    if game_type not in {"cipher_match", "nexus_wheel"}:
        return {"ok": False, "error": "invalid_game"}

    max_energy = _effective_max_energy(int(user_id))
    payload = _build_session_payload(game_type)
    if not payload:
        return {"ok": False, "error": "game_data_unavailable"}

    now = _now()
    expires_at = now + timedelta(minutes=SESSION_TTL_MINUTES)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    UPDATE aninexus_game_sessions
                    SET status = 'expired', updated_at = NOW()
                    WHERE user_id = %s
                      AND game_type = %s
                      AND status = 'active'
                      AND expires_at <= NOW()
                    """,
                    (int(user_id), game_type),
                )
                cur.execute(
                    """
                    SELECT session_id, payload, expires_at
                    FROM aninexus_game_sessions
                    WHERE user_id = %s
                      AND game_type = %s
                      AND status = 'active'
                      AND expires_at > NOW()
                    ORDER BY started_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (int(user_id), game_type),
                )
                existing = cur.fetchone()
                if existing:
                    conn.commit()
                    data = dict(existing.get("payload") or {})
                    data["session_id"] = str(existing.get("session_id") or "")
                    return {"ok": True, "reused": True, "session": data}

                state = _refresh_energy_locked(cur, int(user_id), max_energy)
                energy = int(state.get("energy") or 0)
                if energy <= 0:
                    conn.rollback()
                    return {"ok": False, "error": "not_enough_energy"}

                last = state.get("last_energy_recharge")
                if energy >= max_energy or not isinstance(last, datetime):
                    last = now

                cur.execute(
                    """
                    UPDATE aninexus_game_state
                    SET energy = energy - 1,
                        last_energy_recharge = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                      AND energy >= 1
                    RETURNING energy
                    """,
                    (last, int(user_id)),
                )
                consumed = cur.fetchone()
                if not consumed:
                    conn.rollback()
                    return {"ok": False, "error": "not_enough_energy"}

                session_id = secrets.token_urlsafe(24)
                payload = dict(payload)
                payload["session_id"] = session_id
                cur.execute(
                    """
                    INSERT INTO aninexus_game_sessions
                    (session_id, user_id, game_type, payload, status, started_at, expires_at)
                    VALUES (%s, %s, %s, %s::jsonb, 'active', %s, %s)
                    """,
                    (
                        session_id,
                        int(user_id),
                        game_type,
                        json.dumps(payload, ensure_ascii=False),
                        now,
                        expires_at,
                    ),
                )
                conn.commit()
                return {"ok": True, "reused": False, "session": payload}
            except Exception:
                conn.rollback()
                raise


def _xp_level(xp: int) -> int:
    xp = max(0, int(xp))
    level = 1
    while True:
        next_level = level + 1
        required = 80 * (next_level - 1) * (next_level - 1) + 120 * (next_level - 1)
        if xp < required:
            return level
        level = next_level


def submit_game_session(user_id: int, game_type: str, session_id: str, score: int = 0) -> Dict[str, Any]:
    _ensure_tables()
    game_type = str(game_type or "").strip().lower()
    session_id = str(session_id or "").strip()
    if game_type not in {"cipher_match", "nexus_wheel"} or not session_id:
        return {"ok": False, "error": "invalid_session"}

    pet_modifiers = _pet_modifiers(int(user_id))

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT *
                    FROM aninexus_game_sessions
                    WHERE session_id = %s
                      AND user_id = %s
                      AND game_type = %s
                    FOR UPDATE
                    """,
                    (session_id, int(user_id), game_type),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return {"ok": False, "error": "session_not_found"}

                status = str(row.get("status") or "")
                if status == "completed":
                    conn.commit()
                    return {"ok": True, "already_done": True, "rewards": dict(row.get("reward") or {})}
                if status != "active":
                    conn.rollback()
                    return {"ok": False, "error": "session_not_active"}
                expires_at = row.get("expires_at")
                if isinstance(expires_at, datetime) and expires_at <= _now():
                    cur.execute(
                        "UPDATE aninexus_game_sessions SET status='expired', updated_at=NOW() WHERE session_id=%s",
                        (session_id,),
                    )
                    conn.commit()
                    return {"ok": False, "error": "session_expired"}

                payload = dict(row.get("payload") or {})
                start_time = float(payload.get("start_time") or 0.0)
                elapsed = max(0.0, _now().timestamp() - start_time)
                coins = 0
                xp = 0
                character: Optional[Dict[str, Any]] = None

                if game_type == "cipher_match":
                    score = max(0, min(int(score or 0), 8))
                    if score >= 8 and elapsed < 5.0:
                        conn.rollback()
                        return {"ok": False, "error": "suspicious_activity"}
                    if score < 4:
                        conn.rollback()
                        return {"ok": False, "error": "insufficient_score"}
                    xp = 2 + score
                    if score == 8:
                        xp += 4
                        if elapsed < 25.0:
                            xp += 3
                else:
                    prize = dict(payload.get("prize") or {})
                    prize_type = str(prize.get("type") or "")
                    if prize_type == "coins":
                        coins = max(0, min(1, int(prize.get("amount") or 0)))
                        xp = 2
                    elif prize_type == "xp":
                        xp = max(1, min(15, int(prize.get("amount") or 3)))
                    elif prize_type == "character":
                        character = _random_character_payload()
                        if not character:
                            conn.rollback()
                            return {"ok": False, "error": "character_unavailable"}
                        xp = 5
                    else:
                        conn.rollback()
                        return {"ok": False, "error": "invalid_prize"}

                xp_multiplier = max(1.0, float(pet_modifiers.get("xp_multiplier") or 1.0))
                xp = max(1, int(round(xp * xp_multiplier)))

                bonus_coin = False
                bonus_coin_chance = max(0.0, min(1.0, float(pet_modifiers.get("bonus_coin_chance") or 0.0)))
                if bonus_coin_chance > 0 and random.random() < bonus_coin_chance:
                    coins += 1
                    bonus_coin = True

                bonus_egg = False
                egg_drop_chance = max(0.0, min(1.0, float(pet_modifiers.get("egg_drop_chance") or 0.0)))
                if egg_drop_chance > 0 and random.random() < egg_drop_chance:
                    bonus_egg = True

                cur.execute(
                    """
                    INSERT INTO users (user_id, coins, created_at, updated_at)
                    VALUES (%s, 0, NOW(), NOW())
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (int(user_id),),
                )
                if coins > 0:
                    cur.execute(
                        """
                        UPDATE users
                        SET coins = COALESCE(coins, 0) + %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        RETURNING coins
                        """,
                        (coins, int(user_id)),
                    )
                    balance_after = int((cur.fetchone() or {}).get("coins") or 0)
                    cur.execute(
                        """
                        INSERT INTO shop_transactions
                            (user_id, type, amount, balance_after, metadata)
                        VALUES (
                            %s,
                            'aninexus_game_reward',
                            %s,
                            %s,
                            jsonb_build_object(
                                'game_type', %s,
                                'session_id', %s,
                                'pet_bonus_coin', %s
                            )
                        )
                        """,
                        (
                            int(user_id),
                            coins,
                            balance_after,
                            game_type,
                            session_id,
                            bonus_coin,
                        ),
                    )

                cur.execute(
                    """
                    INSERT INTO user_progress (user_id, xp, level, total_actions, updated_at)
                    VALUES (%s, 0, 1, 0, NOW())
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (int(user_id),),
                )
                cur.execute(
                    "SELECT xp, total_actions FROM user_progress WHERE user_id=%s FOR UPDATE",
                    (int(user_id),),
                )
                progress = cur.fetchone() or {}
                new_xp = int(progress.get("xp") or 0) + xp
                new_level = _xp_level(new_xp)
                cur.execute(
                    """
                    UPDATE user_progress
                    SET xp = %s,
                        level = %s,
                        total_actions = COALESCE(total_actions, 0) + 1,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (new_xp, new_level, int(user_id)),
                )

                if character:
                    character_id = int(character.get("id") or 0)
                    cur.execute(
                        """
                        INSERT INTO user_card_collection (user_id, character_id, quantity, updated_at)
                        VALUES (%s, %s, 1, NOW())
                        ON CONFLICT (user_id, character_id)
                        DO UPDATE SET quantity = user_card_collection.quantity + 1, updated_at = NOW()
                        """,
                        (int(user_id), character_id),
                    )

                if bonus_egg:
                    cur.execute(
                        """
                        INSERT INTO aninexus_user_eggs (user_id, tier, status, is_corrupted)
                        VALUES (%s, 'common', 'fresh', FALSE)
                        """,
                        (int(user_id),),
                    )

                reward = {
                    "shards": coins,
                    "xp": xp,
                    "character": character,
                    "bonus_egg": bonus_egg,
                }
                cur.execute(
                    """
                    UPDATE aninexus_game_sessions
                    SET status = 'completed',
                        reward = %s::jsonb,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE session_id = %s
                    """,
                    (json.dumps(reward, ensure_ascii=False), session_id),
                )
                conn.commit()
                return {"ok": True, "already_done": False, "rewards": reward}
            except Exception:
                conn.rollback()
                raise
