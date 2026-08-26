from __future__ import annotations

import hashlib
import json
import secrets
from datetime import date, timedelta
from random import SystemRandom
from typing import Any

from psycopg.rows import dict_row

from database import pool, xp_to_level
from game_rules import today_sp
from termo_rules import (
    HINT_COST_COINS,
    MAX_ATTEMPTS,
    TIME_LIMIT_SECONDS,
    XP_REWARD,
    daily_coin_reward,
    evaluate_guess,
    is_valid_guess,
    load_words,
    normalize_word,
    streak_bonus,
    word_index,
)
from wallet_tx import insert_ledger, lock_wallet, wallet_payload


_rng = SystemRandom()


class TermoError(RuntimeError):
    pass


class TermoInvalidState(TermoError):
    pass


class TermoInvalidGuess(TermoError):
    pass


class TermoDuplicateGuess(TermoError):
    pass


class TermoHintAlreadyUsed(TermoError):
    pass


class TermoInsufficientCoins(TermoError):
    pass


def create_termo_v2_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS termo_games_v2 (
                    game_id BIGSERIAL PRIMARY KEY,
                    session_token TEXT NOT NULL UNIQUE,
                    user_id BIGINT NOT NULL,
                    game_date DATE,
                    mode TEXT NOT NULL CHECK (mode IN ('daily','train')),
                    secret_word TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    difficulty INTEGER NOT NULL DEFAULT 1,
                    hint TEXT NOT NULL DEFAULT '',
                    hint_used BOOLEAN NOT NULL DEFAULT FALSE,
                    guesses JSONB NOT NULL DEFAULT '[]'::jsonb,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'playing',
                    reward_coins INTEGER NOT NULL DEFAULT 0,
                    reward_xp INTEGER NOT NULL DEFAULT 0,
                    streak INTEGER NOT NULL DEFAULT 0,
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
                CREATE UNIQUE INDEX IF NOT EXISTS uq_termo_daily_user_date_v2
                ON termo_games_v2 (user_id, game_date)
                WHERE mode='daily'
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_termo_games_user_created_v2
                ON termo_games_v2 (user_id, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_termo_games_ranking_v2
                ON termo_games_v2 (mode, status, game_date DESC, attempts ASC)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS termo_used_words_v2 (
                    user_id BIGINT NOT NULL,
                    word TEXT NOT NULL,
                    first_game_date DATE NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, word)
                )
                """
            )
            conn.commit()


def _decode_guesses(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _public_game(row: dict[str, Any], *, reveal_secret: bool = False) -> dict[str, Any]:
    status = str(row.get("status") or "playing")
    reveal = reveal_secret or status in {"win", "loss", "timeout"}
    return {
        "game_id": int(row.get("game_id") or 0),
        "session_token": str(row.get("session_token") or ""),
        "mode": str(row.get("mode") or "daily"),
        "game_date": row.get("game_date").isoformat() if row.get("game_date") else None,
        "category": str(row.get("category") or "Desconhecido"),
        "source": str(row.get("source") or "Anime"),
        "difficulty": int(row.get("difficulty") or 1),
        "hint_used": bool(row.get("hint_used")),
        "hint": str(row.get("hint") or "") if bool(row.get("hint_used")) else "",
        "guesses": _decode_guesses(row.get("guesses")),
        "attempts": int(row.get("attempts") or 0),
        "max_attempts": MAX_ATTEMPTS,
        "status": status,
        "reward_coins": int(row.get("reward_coins") or 0),
        "reward_xp": int(row.get("reward_xp") or 0),
        "streak": int(row.get("streak") or 0),
        "secret_word": str(row.get("secret_word") or "") if reveal else "",
        "started_at": row.get("started_at").isoformat() if row.get("started_at") else None,
        "expires_at": row.get("expires_at").isoformat() if row.get("expires_at") else None,
    }


def _expire_if_needed(cur, row: dict[str, Any]) -> dict[str, Any]:
    if str(row.get("status") or "") != "playing":
        return row
    cur.execute("SELECT NOW() >= %s AS expired", (row.get("expires_at"),))
    expired = bool((cur.fetchone() or {}).get("expired"))
    if not expired:
        return row
    cur.execute(
        """
        UPDATE termo_games_v2
        SET status='timeout', completed_at=NOW(), updated_at=NOW()
        WHERE game_id=%s
        RETURNING *
        """,
        (int(row["game_id"]),),
    )
    return dict(cur.fetchone() or row)


def _daily_word_for_user(cur, user_id: int, target_date: date) -> dict[str, Any]:
    cur.execute("SELECT word FROM termo_used_words_v2 WHERE user_id=%s", (int(user_id),))
    used = {str(row.get("word") or "") for row in (cur.fetchall() or [])}
    words = [dict(item) for item in load_words() if str(item.get("word") or "") not in used]
    if not words:
        words = [dict(item) for item in load_words()]
    words.sort(
        key=lambda item: hashlib.sha256(
            f"{int(user_id)}:{target_date.isoformat()}:{item['word']}".encode("utf-8")
        ).hexdigest()
    )
    return words[0]


def _insert_game(cur, *, user_id: int, mode: str, target_date: date | None, word: dict[str, Any]) -> dict[str, Any]:
    token = secrets.token_urlsafe(24)
    cur.execute(
        """
        INSERT INTO termo_games_v2
        (session_token,user_id,game_date,mode,secret_word,category,source,difficulty,hint,expires_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW() + (%s * INTERVAL '1 second'))
        RETURNING *
        """,
        (
            token,
            int(user_id),
            target_date,
            mode,
            str(word["word"]),
            str(word.get("category") or "Desconhecido"),
            str(word.get("source") or "Anime"),
            int(word.get("difficulty") or 1),
            str(word.get("hint") or ""),
            TIME_LIMIT_SECONDS,
        ),
    )
    return dict(cur.fetchone() or {})


def start_daily_game(user_id: int, target_date: date | None = None) -> dict[str, Any]:
    user_id = int(user_id)
    target = target_date or today_sp()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
                cur.execute(
                    "SELECT * FROM termo_games_v2 WHERE user_id=%s AND game_date=%s AND mode='daily' FOR UPDATE",
                    (user_id, target),
                )
                existing = cur.fetchone()
                if existing:
                    row = _expire_if_needed(cur, dict(existing))
                    conn.commit()
                    return _public_game(row)

                word = _daily_word_for_user(cur, user_id, target)
                row = _insert_game(cur, user_id=user_id, mode="daily", target_date=target, word=word)
                cur.execute(
                    """
                    INSERT INTO termo_used_words_v2 (user_id, word, first_game_date)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (user_id, word) DO NOTHING
                    """,
                    (user_id, str(word["word"]), target),
                )
                conn.commit()
                return _public_game(row)
            except Exception:
                conn.rollback()
                raise


def start_train_game(user_id: int) -> dict[str, Any]:
    word = dict(_rng.choice(load_words()))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "UPDATE termo_games_v2 SET status='abandoned', completed_at=NOW(), updated_at=NOW() WHERE user_id=%s AND mode='train' AND status='playing'",
                    (int(user_id),),
                )
                row = _insert_game(cur, user_id=int(user_id), mode="train", target_date=None, word=word)
                conn.commit()
                return _public_game(row)
            except Exception:
                conn.rollback()
                raise


def get_active_or_today(user_id: int) -> dict[str, Any] | None:
    target = today_sp()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM termo_games_v2
                WHERE user_id=%s AND ((mode='daily' AND game_date=%s) OR (mode='train' AND status='playing'))
                ORDER BY CASE WHEN mode='train' AND status='playing' THEN 0 ELSE 1 END, created_at DESC
                LIMIT 1
                """,
                (int(user_id), target),
            )
            raw = cur.fetchone()
            if not raw:
                return None
            row = _expire_if_needed(cur, dict(raw))
            conn.commit()
            return _public_game(row)


def _current_streak_before(cur, user_id: int, target_date: date) -> int:
    cur.execute(
        """
        SELECT game_date FROM termo_games_v2
        WHERE user_id=%s AND mode='daily' AND status='win' AND game_date < %s
        ORDER BY game_date DESC
        """,
        (int(user_id), target_date),
    )
    dates = [row.get("game_date") for row in (cur.fetchall() or []) if row.get("game_date")]
    expected = target_date - timedelta(days=1)
    streak = 0
    for won_date in dates:
        if won_date != expected:
            break
        streak += 1
        expected -= timedelta(days=1)
    return streak


def _grant_win_locked(cur, row: dict[str, Any], attempts: int) -> tuple[int, int, int, dict[str, Any]]:
    user_id = int(row["user_id"])
    target_date = row.get("game_date") or today_sp()
    streak = _current_streak_before(cur, user_id, target_date) + 1
    coins = daily_coin_reward(attempts) + streak_bonus(streak)
    wallet = lock_wallet(cur, user_id)
    cur.execute(
        """
        UPDATE game_wallets SET coins=coins+%s, updated_at=NOW()
        WHERE user_id=%s
        RETURNING user_id,coins,dice,spins,dice_slot
        """,
        (coins, user_id),
    )
    wallet = dict(cur.fetchone() or wallet)
    insert_ledger(
        cur,
        user_id=user_id,
        resource="coins",
        delta=coins,
        reason="termo_daily_win",
        reference=f"termo:{target_date.isoformat()}",
        metadata={"attempts": attempts, "streak": streak},
    )
    cur.execute(
        """
        INSERT INTO user_progress (user_id,xp,level,total_actions)
        VALUES (%s,0,1,0)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id,),
    )
    cur.execute("SELECT xp,level,total_actions FROM user_progress WHERE user_id=%s FOR UPDATE", (user_id,))
    progress = cur.fetchone() or {}
    new_xp = int(progress.get("xp") or 0) + XP_REWARD
    new_level = xp_to_level(new_xp)
    cur.execute(
        """
        UPDATE user_progress
        SET xp=%s, level=%s, total_actions=total_actions+1, updated_at=NOW()
        WHERE user_id=%s
        """,
        (new_xp, new_level, user_id),
    )
    return coins, XP_REWARD, streak, wallet_payload(wallet)


def submit_guess(user_id: int, session_token: str, guess: str) -> dict[str, Any]:
    user_id = int(user_id)
    token = str(session_token or "").strip()
    normalized = normalize_word(guess)
    if not is_valid_guess(normalized):
        raise TermoInvalidGuess("invalid_word")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT * FROM termo_games_v2 WHERE session_token=%s AND user_id=%s FOR UPDATE",
                    (token, user_id),
                )
                row = dict(cur.fetchone() or {})
                if not row:
                    raise TermoInvalidState("not_found")
                row = _expire_if_needed(cur, row)
                if str(row.get("status") or "") != "playing":
                    conn.commit()
                    raise TermoInvalidState(str(row.get("status") or "ended"))

                guesses = _decode_guesses(row.get("guesses"))
                if normalized in {normalize_word(item.get("guess")) for item in guesses}:
                    raise TermoDuplicateGuess("duplicate_guess")

                result = evaluate_guess(str(row["secret_word"]), normalized)
                guesses.append({"guess": normalized, "result": result})
                attempts = len(guesses)
                win = normalized == str(row["secret_word"])
                status = "win" if win else ("loss" if attempts >= MAX_ATTEMPTS else "playing")
                reward_coins = reward_xp = streak = 0
                wallet = None
                if win and str(row.get("mode")) == "daily":
                    reward_coins, reward_xp, streak, wallet = _grant_win_locked(cur, row, attempts)

                cur.execute(
                    """
                    UPDATE termo_games_v2
                    SET guesses=%s::jsonb, attempts=%s, status=%s,
                        reward_coins=%s, reward_xp=%s, streak=%s,
                        completed_at=CASE WHEN %s='playing' THEN completed_at ELSE NOW() END,
                        updated_at=NOW()
                    WHERE game_id=%s
                    RETURNING *
                    """,
                    (
                        json.dumps(guesses, ensure_ascii=False), attempts, status,
                        reward_coins, reward_xp, streak, status, int(row["game_id"]),
                    ),
                )
                updated = dict(cur.fetchone() or row)
                conn.commit()
                payload = _public_game(updated)
                payload["wallet"] = wallet
                return payload
            except (TermoInvalidGuess, TermoInvalidState, TermoDuplicateGuess):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def buy_hint(user_id: int, session_token: str) -> dict[str, Any]:
    user_id = int(user_id)
    token = str(session_token or "").strip()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "SELECT * FROM termo_games_v2 WHERE session_token=%s AND user_id=%s FOR UPDATE",
                    (token, user_id),
                )
                row = dict(cur.fetchone() or {})
                if not row:
                    raise TermoInvalidState("not_found")
                row = _expire_if_needed(cur, row)
                if str(row.get("status") or "") != "playing":
                    raise TermoInvalidState("not_playing")
                if bool(row.get("hint_used")):
                    raise TermoHintAlreadyUsed("hint_used")
                hint = str(row.get("hint") or "").strip()
                if not hint:
                    hint = f"Categoria: {row.get('category') or 'Desconhecido'} • Origem: {row.get('source') or 'Anime'}"

                wallet_payload_value = None
                if str(row.get("mode")) == "daily":
                    wallet = lock_wallet(cur, user_id)
                    if int(wallet.get("coins") or 0) < HINT_COST_COINS:
                        raise TermoInsufficientCoins("insufficient_coins")
                    cur.execute(
                        """
                        UPDATE game_wallets SET coins=coins-%s, updated_at=NOW()
                        WHERE user_id=%s AND coins >= %s
                        RETURNING user_id,coins,dice,spins,dice_slot
                        """,
                        (HINT_COST_COINS, user_id, HINT_COST_COINS),
                    )
                    updated_wallet = dict(cur.fetchone() or {})
                    if not updated_wallet:
                        raise TermoInsufficientCoins("insufficient_coins")
                    insert_ledger(
                        cur,
                        user_id=user_id,
                        resource="coins",
                        delta=-HINT_COST_COINS,
                        reason="termo_hint",
                        reference=f"termo:{int(row['game_id'])}",
                    )
                    wallet_payload_value = wallet_payload(updated_wallet)

                cur.execute(
                    "UPDATE termo_games_v2 SET hint_used=TRUE, updated_at=NOW() WHERE game_id=%s",
                    (int(row["game_id"]),),
                )
                conn.commit()
                return {"hint": hint, "cost": HINT_COST_COINS if str(row.get("mode")) == "daily" else 0, "wallet": wallet_payload_value}
            except (TermoInvalidState, TermoHintAlreadyUsed, TermoInsufficientCoins):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def _streaks_from_dates(win_dates: list[date]) -> tuple[int, int]:
    if not win_dates:
        return 0, 0
    unique = sorted(set(win_dates))
    best = current = 1
    for index in range(1, len(unique)):
        if unique[index] == unique[index - 1] + timedelta(days=1):
            current += 1
        else:
            current = 1
        best = max(best, current)
    today = today_sp()
    latest = unique[-1]
    if latest not in {today, today - timedelta(days=1)}:
        current_streak = 0
    else:
        current_streak = 1
        expected = latest - timedelta(days=1)
        for won_date in reversed(unique[:-1]):
            if won_date != expected:
                break
            current_streak += 1
            expected -= timedelta(days=1)
    return current_streak, best


def termo_stats(user_id: int) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT game_date,status,attempts,reward_coins
                FROM termo_games_v2
                WHERE user_id=%s AND mode='daily' AND status IN ('win','loss','timeout')
                ORDER BY game_date
                """,
                (int(user_id),),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
    wins = [row for row in rows if row.get("status") == "win"]
    current_streak, best_streak = _streaks_from_dates([row["game_date"] for row in wins if row.get("game_date")])
    distribution = {str(index): 0 for index in range(1, MAX_ATTEMPTS + 1)}
    for row in wins:
        attempts = int(row.get("attempts") or 0)
        if 1 <= attempts <= MAX_ATTEMPTS:
            distribution[str(attempts)] += 1
    return {
        "games": len(rows),
        "wins": len(wins),
        "losses": len(rows) - len(wins),
        "win_rate": round((len(wins) / len(rows) * 100), 1) if rows else 0.0,
        "current_streak": current_streak,
        "best_streak": best_streak,
        "best_attempts": min((int(row.get("attempts") or MAX_ATTEMPTS) for row in wins), default=0),
        "coins_earned": sum(int(row.get("reward_coins") or 0) for row in wins),
        "distribution": distribution,
    }


def termo_ranking(limit: int = 10) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT g.user_id,
                       COUNT(*) FILTER (WHERE g.status='win') AS wins,
                       COUNT(*) AS games,
                       AVG(g.attempts) FILTER (WHERE g.status='win') AS avg_attempts,
                       u.username,u.full_name,
                       i.nickname
                FROM termo_games_v2 g
                LEFT JOIN users u ON u.user_id=g.user_id
                LEFT JOIN user_identity_settings i ON i.user_id=g.user_id
                WHERE g.mode='daily' AND g.status IN ('win','loss','timeout')
                  AND COALESCE(i.private_profile,FALSE)=FALSE
                GROUP BY g.user_id,u.username,u.full_name,i.nickname
                ORDER BY wins DESC, avg_attempts ASC NULLS LAST, games DESC, g.user_id ASC
                LIMIT %s
                """,
                (max(1, min(int(limit), 50)),),
            )
            rows = cur.fetchall() or []
    return [
        {
            "user_id": int(row.get("user_id") or 0),
            "display_name": str(row.get("nickname") or (f"@{row.get('username')}" if row.get("username") else row.get("full_name") or "Navegante")),
            "wins": int(row.get("wins") or 0),
            "games": int(row.get("games") or 0),
            "avg_attempts": round(float(row.get("avg_attempts") or 0), 2) if row.get("avg_attempts") is not None else None,
        }
        for row in rows
    ]
