from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row

from database import pool
from duel_engine import build_team_snapshot, is_team_eliminated, resolve_round
from xcards_service import get_xcard_by_id


PENDING_SECONDS = 5 * 60
SELECTION_SECONDS = 10 * 60
ROUND_SECONDS = 5 * 60
ACTIVE_STATES = ("pending", "selecting", "active")


class DuelError(RuntimeError):
    pass


class DuelBusy(DuelError):
    pass


class DuelNotEnoughCards(DuelError):
    def __init__(self, user_id: int):
        self.user_id = int(user_id)
        super().__init__(f"not_enough_xcards:{self.user_id}")


class DuelInvalidState(DuelError):
    pass


class DuelNotParticipant(DuelError):
    pass


class DuelSelectionError(DuelError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decode(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    item = dict(row)
    for key in ("selection_a", "selection_b", "team_a", "team_b"):
        value = item.get(key)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                value = [] if key.startswith("selection") else {}
        item[key] = value or ([] if key.startswith("selection") else {})
    return item


def create_duel_v2_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS duels_v2 (
                    duel_id BIGSERIAL PRIMARY KEY,
                    challenger_user_id BIGINT NOT NULL,
                    challenged_user_id BIGINT NOT NULL,
                    challenger_name TEXT NOT NULL,
                    challenged_name TEXT NOT NULL,
                    group_chat_id BIGINT NOT NULL,
                    group_message_id BIGINT,
                    state TEXT NOT NULL DEFAULT 'pending',
                    selection_a JSONB NOT NULL DEFAULT '[]'::jsonb,
                    selection_b JSONB NOT NULL DEFAULT '[]'::jsonb,
                    ready_a BOOLEAN NOT NULL DEFAULT FALSE,
                    ready_b BOOLEAN NOT NULL DEFAULT FALSE,
                    team_a JSONB NOT NULL DEFAULT '[]'::jsonb,
                    team_b JSONB NOT NULL DEFAULT '[]'::jsonb,
                    choice_a INTEGER,
                    choice_b INTEGER,
                    round_no INTEGER NOT NULL DEFAULT 1,
                    winner_user_id BIGINT,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS duel_rounds_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    duel_id BIGINT NOT NULL REFERENCES duels_v2(duel_id) ON DELETE CASCADE,
                    round_no INTEGER NOT NULL,
                    choice_a INTEGER NOT NULL,
                    choice_b INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    result_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (duel_id, round_no)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS duel_stats_v2 (
                    user_id BIGINT PRIMARY KEY,
                    total_duels BIGINT NOT NULL DEFAULT 0,
                    wins BIGINT NOT NULL DEFAULT 0,
                    losses BIGINT NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_duels_v2_state_expiry
                ON duels_v2 (state, expires_at)
                """
            )
            conn.commit()


def _lock_users(cur, *user_ids: int) -> None:
    for user_id in sorted({int(value) for value in user_ids}):
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))


def _expire_stale(cur) -> None:
    cur.execute(
        """
        UPDATE duels_v2
        SET state = 'expired', updated_at = NOW()
        WHERE state IN ('pending','selecting','active')
          AND expires_at <= NOW()
        """
    )


def _distinct_xcards(cur, user_id: int) -> int:
    cur.execute(
        """
        SELECT COUNT(*) AS total
        FROM user_xcard_collection
        WHERE user_id = %s AND quantity > 0
        """,
        (int(user_id),),
    )
    return int((cur.fetchone() or {}).get("total") or 0)


def create_challenge(
    *,
    challenger_user_id: int,
    challenged_user_id: int,
    challenger_name: str,
    challenged_name: str,
    group_chat_id: int,
) -> dict[str, Any]:
    a = int(challenger_user_id)
    b = int(challenged_user_id)
    if a == b:
        raise DuelError("self_duel")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                _lock_users(cur, a, b)
                _expire_stale(cur)
                cur.execute(
                    """
                    SELECT duel_id
                    FROM duels_v2
                    WHERE state IN ('pending','selecting','active')
                      AND (
                        challenger_user_id IN (%s,%s)
                        OR challenged_user_id IN (%s,%s)
                      )
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (a, b, a, b),
                )
                if cur.fetchone():
                    raise DuelBusy("participant_busy")
                for user_id in (a, b):
                    if _distinct_xcards(cur, user_id) < 3:
                        raise DuelNotEnoughCards(user_id)

                cur.execute(
                    """
                    INSERT INTO duels_v2
                    (challenger_user_id, challenged_user_id, challenger_name, challenged_name,
                     group_chat_id, expires_at)
                    VALUES (%s,%s,%s,%s,%s,NOW() + (%s * INTERVAL '1 second'))
                    RETURNING *
                    """,
                    (a, b, challenger_name, challenged_name, int(group_chat_id), PENDING_SECONDS),
                )
                duel = _decode(cur.fetchone()) or {}
                conn.commit()
                return duel
            except (DuelBusy, DuelNotEnoughCards, DuelError):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def set_group_message(duel_id: int, message_id: int) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE duels_v2 SET group_message_id=%s, updated_at=NOW() WHERE duel_id=%s",
                (int(message_id), int(duel_id)),
            )
            conn.commit()


def get_duel(duel_id: int) -> dict[str, Any] | None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _expire_stale(cur)
            cur.execute("SELECT * FROM duels_v2 WHERE duel_id=%s", (int(duel_id),))
            row = _decode(cur.fetchone())
            conn.commit()
            return row


def respond_challenge(duel_id: int, actor_user_id: int, accept: bool) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM duels_v2 WHERE duel_id=%s FOR UPDATE", (int(duel_id),))
                duel = _decode(cur.fetchone())
                if not duel:
                    raise DuelInvalidState("not_found")
                if int(actor_user_id) != int(duel["challenged_user_id"]):
                    raise DuelNotParticipant("only_challenged")
                if duel["state"] != "pending" or duel["expires_at"] <= _utcnow():
                    raise DuelInvalidState("not_pending")
                if not accept:
                    cur.execute("UPDATE duels_v2 SET state='rejected', updated_at=NOW() WHERE duel_id=%s", (int(duel_id),))
                else:
                    cur.execute(
                        """
                        UPDATE duels_v2
                        SET state='selecting', expires_at=NOW() + (%s * INTERVAL '1 second'), updated_at=NOW()
                        WHERE duel_id=%s
                        """,
                        (SELECTION_SECONDS, int(duel_id)),
                    )
                conn.commit()
                return get_duel(int(duel_id)) or duel
            except (DuelInvalidState, DuelNotParticipant):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def _side(duel: dict[str, Any], user_id: int) -> str:
    if int(user_id) == int(duel["challenger_user_id"]):
        return "a"
    if int(user_id) == int(duel["challenged_user_id"]):
        return "b"
    raise DuelNotParticipant("not_participant")


def toggle_selection(duel_id: int, user_id: int, card_id: int) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM duels_v2 WHERE duel_id=%s FOR UPDATE", (int(duel_id),))
                duel = _decode(cur.fetchone())
                if not duel or duel["state"] != "selecting" or duel["expires_at"] <= _utcnow():
                    raise DuelInvalidState("not_selecting")
                side = _side(duel, int(user_id))
                key = f"selection_{side}"
                selected = [int(value) for value in (duel.get(key) or [])]
                card_id = int(card_id)
                cur.execute(
                    "SELECT quantity FROM user_xcard_collection WHERE user_id=%s AND card_id=%s FOR UPDATE",
                    (int(user_id), card_id),
                )
                if int((cur.fetchone() or {}).get("quantity") or 0) <= 0:
                    raise DuelSelectionError("card_not_owned")
                if card_id in selected:
                    selected = [value for value in selected if value != card_id]
                else:
                    if len(selected) >= 3:
                        raise DuelSelectionError("team_full")
                    selected.append(card_id)
                cur.execute(
                    f"UPDATE duels_v2 SET {key}=%s::jsonb, ready_{side}=FALSE, updated_at=NOW() WHERE duel_id=%s",
                    (json.dumps(selected), int(duel_id)),
                )
                conn.commit()
                return get_duel(int(duel_id)) or duel
            except (DuelInvalidState, DuelNotParticipant, DuelSelectionError):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def _team_from_ids(card_ids: list[int]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for card_id in card_ids:
        card = get_xcard_by_id(int(card_id)) or {}
        if not card or int(card.get("bp_value") or 0) <= 0:
            raise DuelSelectionError("invalid_combat_card")
        cards.append(card)
    if len(cards) != 3:
        raise DuelSelectionError("team_incomplete")
    return build_team_snapshot(cards)


def confirm_selection(duel_id: int, user_id: int) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM duels_v2 WHERE duel_id=%s FOR UPDATE", (int(duel_id),))
                duel = _decode(cur.fetchone())
                if not duel or duel["state"] != "selecting" or duel["expires_at"] <= _utcnow():
                    raise DuelInvalidState("not_selecting")
                side = _side(duel, int(user_id))
                selection = [int(value) for value in (duel.get(f"selection_{side}") or [])]
                if len(selection) != 3 or len(set(selection)) != 3:
                    raise DuelSelectionError("team_incomplete")
                for card_id in selection:
                    cur.execute(
                        "SELECT quantity FROM user_xcard_collection WHERE user_id=%s AND card_id=%s FOR UPDATE",
                        (int(user_id), card_id),
                    )
                    if int((cur.fetchone() or {}).get("quantity") or 0) <= 0:
                        raise DuelSelectionError("card_not_owned")
                cur.execute(f"UPDATE duels_v2 SET ready_{side}=TRUE, updated_at=NOW() WHERE duel_id=%s", (int(duel_id),))
                cur.execute("SELECT * FROM duels_v2 WHERE duel_id=%s", (int(duel_id),))
                fresh = _decode(cur.fetchone()) or duel
                if bool(fresh.get("ready_a")) and bool(fresh.get("ready_b")):
                    team_a = _team_from_ids([int(v) for v in fresh.get("selection_a") or []])
                    team_b = _team_from_ids([int(v) for v in fresh.get("selection_b") or []])
                    cur.execute(
                        """
                        UPDATE duels_v2
                        SET state='active', team_a=%s::jsonb, team_b=%s::jsonb,
                            round_no=1, choice_a=NULL, choice_b=NULL,
                            expires_at=NOW() + (%s * INTERVAL '1 second'), updated_at=NOW()
                        WHERE duel_id=%s
                        """,
                        (json.dumps(team_a), json.dumps(team_b), ROUND_SECONDS, int(duel_id)),
                    )
                conn.commit()
                return get_duel(int(duel_id)) or fresh
            except (DuelInvalidState, DuelNotParticipant, DuelSelectionError):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise


def submit_pick(duel_id: int, user_id: int, slot: int) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM duels_v2 WHERE duel_id=%s FOR UPDATE", (int(duel_id),))
                duel = _decode(cur.fetchone())
                if not duel or duel["state"] != "active" or duel["expires_at"] <= _utcnow():
                    raise DuelInvalidState("not_active")
                side = _side(duel, int(user_id))
                choice_key = f"choice_{side}"
                if duel.get(choice_key) is not None:
                    raise DuelSelectionError("choice_already_sent")
                slot = int(slot)
                team = list(duel.get(f"team_{side}") or [])
                entry = next((item for item in team if int(item.get("slot") or 0) == slot), None)
                if not entry or bool(entry.get("eliminated")) or int(entry.get("hp") or 0) <= 0:
                    raise DuelSelectionError("invalid_slot")
                cur.execute(f"UPDATE duels_v2 SET {choice_key}=%s, updated_at=NOW() WHERE duel_id=%s", (slot, int(duel_id)))
                cur.execute("SELECT * FROM duels_v2 WHERE duel_id=%s", (int(duel_id),))
                fresh = _decode(cur.fetchone()) or duel
                choice_a = fresh.get("choice_a")
                choice_b = fresh.get("choice_b")
                if choice_a is None or choice_b is None:
                    conn.commit()
                    fresh["round_resolved"] = False
                    return fresh

                result = resolve_round(
                    fresh.get("team_a") or [],
                    int(choice_a),
                    int(fresh["challenger_user_id"]),
                    fresh.get("team_b") or [],
                    int(choice_b),
                    int(fresh["challenged_user_id"]),
                )
                round_no = int(fresh.get("round_no") or 1)
                cur.execute(
                    """
                    INSERT INTO duel_rounds_v2
                    (duel_id, round_no, choice_a, choice_b, outcome, result_json)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                    """,
                    (int(duel_id), round_no, int(choice_a), int(choice_b), result["outcome"], json.dumps(result)),
                )
                team_a = result["team_a"]
                team_b = result["team_b"]
                a_dead = is_team_eliminated(team_a)
                b_dead = is_team_eliminated(team_b)
                winner = None
                if a_dead and not b_dead:
                    winner = int(fresh["challenged_user_id"])
                elif b_dead and not a_dead:
                    winner = int(fresh["challenger_user_id"])

                if winner:
                    loser = int(fresh["challenged_user_id"] if winner == int(fresh["challenger_user_id"]) else fresh["challenger_user_id"])
                    cur.execute(
                        """
                        UPDATE duels_v2
                        SET state='completed', team_a=%s::jsonb, team_b=%s::jsonb,
                            winner_user_id=%s, choice_a=NULL, choice_b=NULL, updated_at=NOW()
                        WHERE duel_id=%s
                        """,
                        (json.dumps(team_a), json.dumps(team_b), winner, int(duel_id)),
                    )
                    for uid, wins, losses in ((winner, 1, 0), (loser, 0, 1)):
                        cur.execute(
                            """
                            INSERT INTO duel_stats_v2 (user_id,total_duels,wins,losses)
                            VALUES (%s,1,%s,%s)
                            ON CONFLICT (user_id) DO UPDATE SET
                                total_duels=duel_stats_v2.total_duels+1,
                                wins=duel_stats_v2.wins+EXCLUDED.wins,
                                losses=duel_stats_v2.losses+EXCLUDED.losses,
                                updated_at=NOW()
                            """,
                            (uid, wins, losses),
                        )
                else:
                    cur.execute(
                        """
                        UPDATE duels_v2
                        SET team_a=%s::jsonb, team_b=%s::jsonb,
                            round_no=round_no+1, choice_a=NULL, choice_b=NULL,
                            expires_at=NOW() + (%s * INTERVAL '1 second'), updated_at=NOW()
                        WHERE duel_id=%s
                        """,
                        (json.dumps(team_a), json.dumps(team_b), ROUND_SECONDS, int(duel_id)),
                    )
                conn.commit()
                final = get_duel(int(duel_id)) or fresh
                final["round_resolved"] = True
                final["round_result"] = result
                return final
            except (DuelInvalidState, DuelNotParticipant, DuelSelectionError):
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise
