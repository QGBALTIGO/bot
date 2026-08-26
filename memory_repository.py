from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from random import SystemRandom
from typing import Any

from psycopg.rows import dict_row

from cards_service import build_cards_final_data
from database import pool
from memory_rules import level_config, normalize_level


_rng = SystemRandom()


class MemoryGameError(RuntimeError):
    pass


class MemorySessionInvalid(MemoryGameError):
    pass


class MemoryProofInvalid(MemoryGameError):
    pass


class MemoryTooFast(MemoryGameError):
    pass


def create_memory_v2_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_sessions_v2 (
                    session_token TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    level TEXT NOT NULL,
                    board_json JSONB NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    completed_at TIMESTAMPTZ,
                    elapsed_ms BIGINT,
                    moves INTEGER,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_bests_v2 (
                    user_id BIGINT NOT NULL,
                    level TEXT NOT NULL,
                    best_elapsed_ms BIGINT NOT NULL,
                    best_moves INTEGER NOT NULL,
                    completed_games BIGINT NOT NULL DEFAULT 1,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, level)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_sessions_user_status
                ON memory_sessions_v2 (user_id, status, expires_at)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_bests_global
                ON memory_bests_v2 (level, best_elapsed_ms ASC, best_moves ASC)
                """
            )
            conn.commit()


def _memory_pool() -> list[dict[str, Any]]:
    data = build_cards_final_data()
    out: list[dict[str, Any]] = []
    for anime in data.get("animes_list") or []:
        anime_id = int(anime.get("anime_id") or 0)
        title = str(anime.get("anime") or "").strip()
        image = str(anime.get("cover_image") or anime.get("banner_image") or "").strip()
        if anime_id > 0 and title and image:
            out.append({"anime_id": anime_id, "title": title, "image": image})
    return out


def _build_board(level: str) -> list[dict[str, Any]]:
    cfg = level_config(level)
    pool_items = _memory_pool()
    if len(pool_items) < cfg.pairs:
        raise MemoryGameError("memory_pool_too_small")
    chosen = _rng.sample(pool_items, cfg.pairs)
    board: list[dict[str, Any]] = []
    for pair_index, item in enumerate(chosen):
        for copy_index in (0, 1):
            board.append(
                {
                    "pair_key": int(item["anime_id"]),
                    "title": str(item["title"]),
                    "image": str(item["image"]),
                    "copy": copy_index,
                    "pair_index": pair_index,
                }
            )
    _rng.shuffle(board)
    for position, item in enumerate(board):
        item["position"] = position
    return board


def _public_board(board: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "position": int(item["position"]),
            "title": str(item["title"]),
            "image": str(item["image"]),
        }
        for item in board
    ]


def start_memory_session(user_id: int, level: str) -> dict[str, Any]:
    user_id = int(user_id)
    normalized = normalize_level(level)
    cfg = level_config(normalized)
    board = _build_board(normalized)
    token = secrets.token_urlsafe(24)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    UPDATE memory_sessions_v2
                    SET status='expired'
                    WHERE user_id=%s AND status='active'
                    """,
                    (user_id,),
                )
                cur.execute(
                    """
                    INSERT INTO memory_sessions_v2
                    (session_token, user_id, level, board_json, expires_at)
                    VALUES (%s,%s,%s,%s::jsonb,NOW() + (%s * INTERVAL '1 minute'))
                    RETURNING started_at, expires_at
                    """,
                    (token, user_id, normalized, json.dumps(board, ensure_ascii=False), cfg.max_minutes),
                )
                row = cur.fetchone() or {}
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return {
        "session_token": token,
        "level": normalized,
        "pairs": cfg.pairs,
        "board": _public_board(board),
        "started_at": row.get("started_at").isoformat() if row.get("started_at") else None,
        "expires_at": row.get("expires_at").isoformat() if row.get("expires_at") else None,
    }


def _decode_board(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _validate_proof(board: list[dict[str, Any]], proof: Any, expected_pairs: int) -> None:
    if not isinstance(proof, list) or len(proof) != expected_pairs:
        raise MemoryProofInvalid("proof_pair_count")
    used: set[int] = set()
    for pair in proof:
        if not isinstance(pair, list) or len(pair) != 2:
            raise MemoryProofInvalid("proof_shape")
        try:
            a, b = int(pair[0]), int(pair[1])
        except (TypeError, ValueError):
            raise MemoryProofInvalid("proof_position")
        if a == b or a < 0 or b < 0 or a >= len(board) or b >= len(board):
            raise MemoryProofInvalid("proof_position")
        if a in used or b in used:
            raise MemoryProofInvalid("proof_reused_tile")
        if int(board[a].get("pair_key") or 0) != int(board[b].get("pair_key") or 0):
            raise MemoryProofInvalid("proof_wrong_pair")
        used.update((a, b))
    if used != set(range(len(board))):
        raise MemoryProofInvalid("proof_incomplete")


def finish_memory_session(user_id: int, token: str, moves: int, proof: Any) -> dict[str, Any]:
    user_id = int(user_id)
    token = str(token or "").strip()
    moves = int(moves)
    if not token:
        raise MemorySessionInvalid("missing_token")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    SELECT * FROM memory_sessions_v2
                    WHERE session_token=%s AND user_id=%s
                    FOR UPDATE
                    """,
                    (token, user_id),
                )
                row = dict(cur.fetchone() or {})
                if not row or str(row.get("status") or "") != "active":
                    raise MemorySessionInvalid("session_not_active")
                now = datetime.now(timezone.utc)
                expires_at = row.get("expires_at")
                if expires_at and expires_at <= now:
                    cur.execute("UPDATE memory_sessions_v2 SET status='expired' WHERE session_token=%s", (token,))
                    raise MemorySessionInvalid("session_expired")

                level = normalize_level(str(row.get("level") or "medium"))
                cfg = level_config(level)
                board = _decode_board(row.get("board_json"))
                if len(board) != cfg.pairs * 2:
                    raise MemorySessionInvalid("invalid_board")
                if moves < cfg.pairs or moves > 10_000:
                    raise MemoryProofInvalid("invalid_moves")
                _validate_proof(board, proof, cfg.pairs)

                started_at = row.get("started_at")
                if not started_at:
                    raise MemorySessionInvalid("missing_started_at")
                elapsed_ms = max(0, int((now - started_at).total_seconds() * 1000))
                if elapsed_ms < cfg.min_seconds * 1000:
                    raise MemoryTooFast("implausible_time")

                cur.execute(
                    """
                    UPDATE memory_sessions_v2
                    SET status='completed', completed_at=NOW(), elapsed_ms=%s, moves=%s
                    WHERE session_token=%s
                    """,
                    (elapsed_ms, moves, token),
                )
                cur.execute(
                    """
                    INSERT INTO memory_bests_v2
                    (user_id, level, best_elapsed_ms, best_moves, completed_games)
                    VALUES (%s,%s,%s,%s,1)
                    ON CONFLICT (user_id, level) DO UPDATE SET
                        completed_games=memory_bests_v2.completed_games+1,
                        best_elapsed_ms=CASE
                            WHEN EXCLUDED.best_elapsed_ms < memory_bests_v2.best_elapsed_ms THEN EXCLUDED.best_elapsed_ms
                            WHEN EXCLUDED.best_elapsed_ms = memory_bests_v2.best_elapsed_ms
                                 AND EXCLUDED.best_moves < memory_bests_v2.best_moves THEN EXCLUDED.best_elapsed_ms
                            ELSE memory_bests_v2.best_elapsed_ms
                        END,
                        best_moves=CASE
                            WHEN EXCLUDED.best_elapsed_ms < memory_bests_v2.best_elapsed_ms THEN EXCLUDED.best_moves
                            WHEN EXCLUDED.best_elapsed_ms = memory_bests_v2.best_elapsed_ms
                                 AND EXCLUDED.best_moves < memory_bests_v2.best_moves THEN EXCLUDED.best_moves
                            ELSE memory_bests_v2.best_moves
                        END,
                        updated_at=NOW()
                    RETURNING best_elapsed_ms, best_moves, completed_games
                    """,
                    (user_id, level, elapsed_ms, moves),
                )
                best = dict(cur.fetchone() or {})
                conn.commit()
                return {
                    "level": level,
                    "elapsed_ms": elapsed_ms,
                    "moves": moves,
                    "best_elapsed_ms": int(best.get("best_elapsed_ms") or elapsed_ms),
                    "best_moves": int(best.get("best_moves") or moves),
                    "completed_games": int(best.get("completed_games") or 1),
                    "new_best": elapsed_ms == int(best.get("best_elapsed_ms") or elapsed_ms)
                    and moves == int(best.get("best_moves") or moves),
                }
            except (MemorySessionInvalid, MemoryProofInvalid, MemoryTooFast):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def memory_stats(user_id: int) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT level, best_elapsed_ms, best_moves, completed_games
                FROM memory_bests_v2
                WHERE user_id=%s
                """,
                (int(user_id),),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
    by_level = {
        str(row.get("level") or ""): {
            "best_elapsed_ms": int(row.get("best_elapsed_ms") or 0),
            "best_moves": int(row.get("best_moves") or 0),
            "completed_games": int(row.get("completed_games") or 0),
        }
        for row in rows
    }
    return {
        "levels": by_level,
        "completed_games": sum(item["completed_games"] for item in by_level.values()),
    }
