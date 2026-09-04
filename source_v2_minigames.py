from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from source_v2_rewards import apply_reward_locked, grant_character_locked


MAX_ENERGY = 5
RECHARGE_MINUTES = 20
SESSION_TTL_SECONDS = 300
VALID_GAMES = {"cipher_match", "nexus_wheel"}

WHEEL_PRIZES = [
    {"type": "shards", "amount": 50, "label": "50 Coins"},
    {"type": "shards", "amount": 100, "label": "100 Coins"},
    {"type": "shards", "amount": 200, "label": "200 Coins"},
    {"type": "character", "label": "Character"},
    {"type": "shards", "amount": 150, "label": "150 Coins"},
    {"type": "shards", "amount": 500, "label": "500 Coins"},
    {"type": "shards", "amount": 80, "label": "80 Coins"},
    {"type": "xp", "amount": 0, "label": "XP Boost"},
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def roll_wheel_index(value: float | None = None) -> int:
    roll = random.random() if value is None else max(0.0, min(0.999999, float(value)))
    if roll < 0.05:
        return 3
    if roll < 0.15:
        return 5
    if roll < 0.30:
        return 2
    if roll < 0.45:
        return 4
    if roll < 0.60:
        return 1
    if roll < 0.75:
        return 6
    if roll < 0.90:
        return 0
    return 7


def _character_pool() -> list[dict[str, Any]]:
    from cards_service import build_cards_final_data

    chars = build_cards_final_data().get("characters_by_id") or {}
    pool: list[dict[str, Any]] = []
    for raw_id, meta in chars.items():
        try:
            character_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        image = str((meta or {}).get("image") or "").strip()
        if character_id <= 0 or not image:
            continue
        pool.append(
            {
                "id": str(character_id),
                "character_id": character_id,
                "img_url": image,
                "name": str((meta or {}).get("name") or f"Personagem {character_id}"),
                "anime": str((meta or {}).get("anime") or "Obra desconhecida"),
                "rarity": "Standard",
            }
        )
    return pool


def build_game_session(game_type: str) -> dict[str, Any]:
    if game_type not in VALID_GAMES:
        raise ValueError("invalid_game_type")

    session: dict[str, Any] = {"start_time": _utcnow().timestamp()}
    if game_type == "cipher_match":
        pool = _character_pool()
        if len(pool) < 8:
            raise RuntimeError("insufficient_character_pool")
        cards = random.sample(pool, 8)
        session["cards"] = [
            {"id": card["id"], "img_url": card["img_url"], "name": card["name"]}
            for card in cards
        ]
    else:
        index = roll_wheel_index()
        session["prize_index"] = index
        session["prize"] = dict(WHEEL_PRIZES[index])
    return session


def _ensure_energy_row(cur, user_id: int) -> None:
    cur.execute(
        """
        INSERT INTO source_v2_minigame_energy (user_id, energy, last_recharge_at)
        VALUES (%s, %s, NULL)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id), MAX_ENERGY),
    )


def _recharge_locked(cur, user_id: int, now: datetime) -> tuple[int, datetime | None]:
    _ensure_energy_row(cur, user_id)
    cur.execute(
        """
        SELECT energy, last_recharge_at
        FROM source_v2_minigame_energy
        WHERE user_id = %s
        FOR UPDATE
        """,
        (int(user_id),),
    )
    row = cur.fetchone() or {}
    energy = int(row.get("energy") or 0)
    last = row.get("last_recharge_at")

    if energy >= MAX_ENERGY:
        if last is not None:
            cur.execute(
                """
                UPDATE source_v2_minigame_energy
                SET energy = %s, last_recharge_at = NULL, updated_at = NOW()
                WHERE user_id = %s
                """,
                (MAX_ENERGY, int(user_id)),
            )
        return MAX_ENERGY, None

    if last is None:
        last = now
        cur.execute(
            "UPDATE source_v2_minigame_energy SET last_recharge_at = %s, updated_at = NOW() WHERE user_id = %s",
            (last, int(user_id)),
        )
        return energy, last

    elapsed_seconds = max(0.0, (now - last).total_seconds())
    gained = int(elapsed_seconds // (RECHARGE_MINUTES * 60))
    if gained <= 0:
        return energy, last

    new_energy = min(MAX_ENERGY, energy + gained)
    new_last = last + timedelta(minutes=gained * RECHARGE_MINUTES)
    if new_energy >= MAX_ENERGY:
        new_last = None
    cur.execute(
        """
        UPDATE source_v2_minigame_energy
        SET energy = %s, last_recharge_at = %s, updated_at = NOW()
        WHERE user_id = %s
        """,
        (new_energy, new_last, int(user_id)),
    )
    return new_energy, new_last


def get_minigame_state(user_id: int) -> dict[str, Any]:
    from database_core import pool

    now = _utcnow()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            energy, last = _recharge_locked(cur, int(user_id), now)
            conn.commit()
    return {
        "energy": energy,
        "max_energy": MAX_ENERGY,
        "last_energy_recharge": last.isoformat() if last else None,
    }


def start_minigame(user_id: int, game_type: str) -> dict[str, Any]:
    from database_core import pool

    game_type = str(game_type or "").strip().lower()
    if game_type not in VALID_GAMES:
        raise ValueError("invalid_game_type")

    session_payload = build_game_session(game_type)
    now = _utcnow()
    expires = now + timedelta(seconds=SESSION_TTL_SECONDS)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    UPDATE source_v2_minigame_sessions
                    SET status = 'expired'
                    WHERE user_id = %s AND game_type = %s
                      AND status = 'active' AND expires_at <= %s
                    """,
                    (int(user_id), game_type, now),
                )
                cur.execute(
                    """
                    SELECT payload, expires_at
                    FROM source_v2_minigame_sessions
                    WHERE user_id = %s AND game_type = %s AND status = 'active'
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (int(user_id), game_type),
                )
                active = cur.fetchone()
                if active and active.get("expires_at") and active["expires_at"] > now:
                    conn.commit()
                    payload = active.get("payload") or {}
                    return dict(payload) if isinstance(payload, dict) else json.loads(str(payload))

                energy, last = _recharge_locked(cur, int(user_id), now)
                if energy <= 0:
                    conn.rollback()
                    raise ValueError("not_enough_energy")

                new_energy = energy - 1
                new_last = now if energy == MAX_ENERGY or last is None else last
                cur.execute(
                    """
                    UPDATE source_v2_minigame_energy
                    SET energy = %s, last_recharge_at = %s, updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (new_energy, new_last, int(user_id)),
                )
                cur.execute(
                    """
                    INSERT INTO source_v2_minigame_sessions
                        (user_id, game_type, payload, status, created_at, expires_at)
                    VALUES (%s, %s, %s, 'active', %s, %s)
                    """,
                    (int(user_id), game_type, Jsonb(session_payload), now, expires),
                )
                conn.commit()
                return session_payload
            except ValueError:
                raise
            except Exception:
                conn.rollback()
                raise


def _cipher_reward(score: int, time_taken: float) -> tuple[int, int]:
    score = max(0, min(int(score or 0), 8))
    if score >= 8 and time_taken < 5.0:
        raise ValueError("suspicious_activity")
    if score < 4:
        raise ValueError("insufficient_score")

    coins = score * 25 + random.randint(20, 100)
    xp = score * 5 + random.randint(5, 15)
    if score == 8 and time_taken < 25:
        coins += 100
        xp += 30
    return coins, xp


def _wheel_reward(prize: dict[str, Any]) -> tuple[int, int, bool]:
    prize_type = str(prize.get("type") or "")
    if prize_type == "character":
        return 100, 25, True
    if prize_type == "xp":
        return 50, 250, False
    coins = max(0, int(prize.get("amount") or 50))
    return coins, coins // 10 + 5, False


def submit_minigame(user_id: int, game_type: str, score: int) -> dict[str, Any]:
    from database_core import pool

    game_type = str(game_type or "").strip().lower()
    if game_type not in VALID_GAMES:
        raise ValueError("invalid_game_type")
    score = int(score or 0)
    if score < 0 or score > 8:
        raise ValueError("invalid_score")

    now = _utcnow()
    character_reward: dict[str, Any] | None = None
    preselected_character: dict[str, Any] | None = None

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT id, payload, created_at, expires_at
                    FROM source_v2_minigame_sessions
                    WHERE user_id = %s AND game_type = %s AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (int(user_id), game_type),
                )
                session = cur.fetchone()
                if not session:
                    conn.rollback()
                    raise ValueError("no_active_session")

                if session["expires_at"] <= now:
                    cur.execute(
                        "UPDATE source_v2_minigame_sessions SET status = 'expired' WHERE id = %s",
                        (int(session["id"]),),
                    )
                    conn.commit()
                    raise ValueError("session_expired")

                payload = session.get("payload") or {}
                if not isinstance(payload, dict):
                    payload = json.loads(str(payload))
                time_taken = max(0.0, now.timestamp() - float(payload.get("start_time") or 0))

                cur.execute(
                    """
                    UPDATE source_v2_minigame_sessions
                    SET status = 'submitted', submitted_at = %s
                    WHERE id = %s
                    """,
                    (now, int(session["id"])),
                )

                try:
                    if game_type == "cipher_match":
                        coins, xp = _cipher_reward(score, time_taken)
                        wants_character = False
                    else:
                        prize = payload.get("prize") or {}
                        coins, xp, wants_character = _wheel_reward(prize)
                except ValueError:
                    conn.commit()
                    raise

                if wants_character:
                    pool_chars = _character_pool()
                    if pool_chars:
                        preselected_character = random.choice(pool_chars)
                        quantity_after = grant_character_locked(
                            cur,
                            int(user_id),
                            int(preselected_character["character_id"]),
                        )
                        character_reward = {
                            "id": preselected_character["id"],
                            "name": preselected_character["name"],
                            "anime": preselected_character["anime"],
                            "rarity": preselected_character["rarity"],
                            "img_url": preselected_character["img_url"],
                            "count": quantity_after,
                        }

                apply_reward_locked(cur, int(user_id), xp=xp, coins=coins)
                conn.commit()
                return {
                    "shards": coins,
                    "xp": xp,
                    "character": character_reward,
                }
            except ValueError:
                raise
            except Exception:
                conn.rollback()
                raise
