from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from psycopg.rows import dict_row

from database import create_or_get_user, pool, touch_user_identity
from duel_engine import (
    TEAM_SIZE,
    build_team_snapshot,
    choose_reward_card,
    find_team_entry,
    format_team_lines,
    get_alive_slots,
    is_team_eliminated,
    resolve_round,
    validate_team_selection,
)


PRESENCE_SCOPE = "duel"
ACTIVE_LOCK_SCOPE = "duel"
FINAL_STATES = {
    "declined",
    "expired",
    "cancelled",
    "completed",
    "completed_reward_review",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_json_dict(raw_value: Any) -> Dict[str, Any]:
    if isinstance(raw_value, dict):
        return dict(raw_value)
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _safe_json_list(raw_value: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_value, list):
        return [item for item in raw_value if isinstance(item, dict)]
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except Exception:
            return []
    return []


def _json_param(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _player_key(user_id: int) -> str:
    return str(int(user_id))


def _decode_duel_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None

    duel = dict(row)
    duel["players_state"] = _safe_json_dict(duel.get("players_state"))
    duel["teams_state"] = _safe_json_dict(duel.get("teams_state"))
    duel["config_json"] = _safe_json_dict(duel.get("config_json"))
    return duel


def _fetch_duel_rounds(cur, duel_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    cur.execute(
        """
        SELECT duel_id, round_no, choices_json, result_json, created_at
        FROM duel_rounds
        WHERE duel_id = %s
        ORDER BY round_no DESC
        LIMIT %s
        """,
        (int(duel_id), int(limit)),
    )
    rows = cur.fetchall() or []
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["choices_json"] = _safe_json_dict(item.get("choices_json"))
        item["result_json"] = _safe_json_dict(item.get("result_json"))
        out.append(item)
    return out


def _fetch_duel_bundle(cur, duel_id: int) -> Optional[Dict[str, Any]]:
    cur.execute("SELECT * FROM duels WHERE duel_id = %s", (int(duel_id),))
    duel = _decode_duel_row(cur.fetchone())
    if not duel:
        return None
    duel["rounds"] = _fetch_duel_rounds(cur, int(duel_id), limit=25)
    return duel


def _update_duel_row(cur, duel_id: int, **fields: Any) -> None:
    if not fields:
        return

    assignments: List[str] = []
    params: List[Any] = []
    for column, value in fields.items():
        assignments.append(f"{column} = %s")
        params.append(value)

    assignments.append("updated_at = NOW()")
    params.append(int(duel_id))
    cur.execute(
        f"UPDATE duels SET {', '.join(assignments)} WHERE duel_id = %s",
        tuple(params),
    )


def _insert_duel_event(cur, duel_id: int, event_type: str, actor_user_id: Optional[int] = None, payload: Any = None) -> None:
    cur.execute(
        """
        INSERT INTO duel_events (duel_id, actor_user_id, event_type, payload_json)
        VALUES (%s, %s, %s, %s::jsonb)
        """,
        (
            int(duel_id),
            int(actor_user_id) if actor_user_id is not None else None,
            str(event_type or "").strip(),
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )


def _touch_presence_state(cur, duel_id: int, state: str) -> None:
    cur.execute(
        """
        UPDATE duel_user_presence
        SET presence_state = %s,
            updated_at = NOW()
        WHERE duel_id = %s
        """,
        (str(state or "").strip(), int(duel_id)),
    )


def _release_presence(cur, duel_id: int) -> None:
    cur.execute("DELETE FROM duel_user_presence WHERE duel_id = %s", (int(duel_id),))


def _release_duel_locks(cur, duel_id: int) -> None:
    cur.execute(
        """
        UPDATE user_xcard_locks
        SET status = 'released',
            released_at = NOW()
        WHERE scope_type = %s
          AND scope_id = %s
          AND status = 'active'
        """,
        (ACTIVE_LOCK_SCOPE, int(duel_id)),
    )


def _ensure_duel_stats_row(cur, user_id: int) -> None:
    cur.execute(
        """
        INSERT INTO duel_stats (user_id)
        VALUES (%s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),),
    )


def _get_user_coins_locked(cur, user_id: int) -> int:
    cur.execute("SELECT coins FROM users WHERE user_id = %s FOR UPDATE", (int(user_id),))
    row = cur.fetchone() or {}
    return int(row.get("coins") or 0)


def _record_coin_tx_locked(
    cur,
    user_id: int,
    tx_type: str,
    amount: int,
    balance_after: int,
    reference_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    cur.execute(
        """
        INSERT INTO shop_transactions
        (user_id, type, amount, balance_after, reference_id, metadata)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            int(user_id),
            str(tx_type or "").strip(),
            int(amount),
            int(balance_after),
            int(reference_id) if reference_id else None,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )


def _adjust_duel_stats_locked(
    cur,
    user_id: int,
    *,
    wins: int = 0,
    losses: int = 0,
    friendly_wins: int = 0,
    friendly_losses: int = 0,
    wager_wins: int = 0,
    wager_losses: int = 0,
    surrendered: int = 0,
    timeouts: int = 0,
    cards_won: int = 0,
    cards_lost: int = 0,
    coins_spent: int = 0,
    coins_refunded: int = 0,
) -> None:
    _ensure_duel_stats_row(cur, user_id)
    total_delta = max(0, int(wins) + int(losses))
    cur.execute(
        """
        UPDATE duel_stats
        SET total_duels = total_duels + %s,
            wins = wins + %s,
            losses = losses + %s,
            friendly_wins = friendly_wins + %s,
            friendly_losses = friendly_losses + %s,
            wager_wins = wager_wins + %s,
            wager_losses = wager_losses + %s,
            surrendered = surrendered + %s,
            timeouts = timeouts + %s,
            cards_won = cards_won + %s,
            cards_lost = cards_lost + %s,
            coins_spent = coins_spent + %s,
            coins_refunded = coins_refunded + %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (
            int(total_delta),
            int(wins),
            int(losses),
            int(friendly_wins),
            int(friendly_losses),
            int(wager_wins),
            int(wager_losses),
            int(surrendered),
            int(timeouts),
            int(cards_won),
            int(cards_lost),
            int(coins_spent),
            int(coins_refunded),
            int(user_id),
        ),
    )


def _other_active_lock_qty(cur, user_id: int, card_id: int, duel_id: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(quantity), 0) AS total
        FROM user_xcard_locks
        WHERE user_id = %s
          AND card_id = %s
          AND status = 'active'
          AND NOT (scope_type = %s AND scope_id = %s)
        """,
        (int(user_id), int(card_id), ACTIVE_LOCK_SCOPE, int(duel_id)),
    )
    row = cur.fetchone() or {}
    return int(row.get("total") or 0)


def _active_lock_qty(cur, user_id: int, card_id: int, duel_id: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(quantity), 0) AS total
        FROM user_xcard_locks
        WHERE user_id = %s
          AND card_id = %s
          AND status = 'active'
          AND scope_type = %s
          AND scope_id = %s
        """,
        (int(user_id), int(card_id), ACTIVE_LOCK_SCOPE, int(duel_id)),
    )
    row = cur.fetchone() or {}
    return int(row.get("total") or 0)


def _lock_user_xcard_quantity(cur, user_id: int, card_id: int) -> int:
    cur.execute(
        """
        SELECT quantity
        FROM user_xcard_collection
        WHERE user_id = %s
          AND card_id = %s
        FOR UPDATE
        """,
        (int(user_id), int(card_id)),
    )
    row = cur.fetchone() or {}
    return int(row.get("quantity") or 0)


def _acquire_duel_card_locks(cur, duel_id: int, user_id: int, card_ids: Iterable[int]) -> Tuple[bool, str]:
    unique_ids = sorted({int(card_id) for card_id in card_ids if int(card_id) > 0})
    valid, reason = validate_team_selection(unique_ids)
    if not valid:
        return False, reason

    for card_id in unique_ids:
        quantity = _lock_user_xcard_quantity(cur, user_id, card_id)
        if quantity <= 0:
            return False, "sem_card"
        unavailable = _other_active_lock_qty(cur, user_id, card_id, duel_id)
        if quantity - unavailable <= 0:
            return False, "card_bloqueado"

    for card_id in unique_ids:
        cur.execute(
            """
            INSERT INTO user_xcard_locks
            (user_id, card_id, quantity, scope_type, scope_id, status)
            VALUES (%s, %s, 1, %s, %s, 'active')
            ON CONFLICT DO NOTHING
            """,
            (int(user_id), int(card_id), ACTIVE_LOCK_SCOPE, int(duel_id)),
        )

    return True, ""


def _transfer_reward_card_locked(
    cur,
    duel_id: int,
    winner_user_id: int,
    loser_user_id: int,
    teams_state: Dict[str, Any],
) -> Dict[str, Any]:
    losing_team = list((teams_state.get(_player_key(loser_user_id)) or {}).get("cards") or [])
    reward_card = choose_reward_card(losing_team)
    candidates = sorted(
        [dict(card) for card in losing_team],
        key=lambda item: (
            int(item.get("bp") or 0),
            int(item.get("hp") or 0),
            int(item.get("slot") or 0),
            int(item.get("card_id") or 0),
        ),
    )

    for candidate in candidates:
        card_id = int(candidate.get("card_id") or 0)
        if card_id <= 0:
            continue

        quantity = _lock_user_xcard_quantity(cur, loser_user_id, card_id)
        if quantity <= 0:
            continue

        other_locked = _other_active_lock_qty(cur, loser_user_id, card_id, duel_id)
        own_duel_lock = _active_lock_qty(cur, loser_user_id, card_id, duel_id)
        if own_duel_lock <= 0:
            continue
        if quantity - other_locked <= 0:
            continue

        if quantity == 1:
            cur.execute(
                """
                DELETE FROM user_xcard_collection
                WHERE user_id = %s AND card_id = %s
                """,
                (int(loser_user_id), card_id),
            )
        else:
            cur.execute(
                """
                UPDATE user_xcard_collection
                SET quantity = quantity - 1,
                    updated_at = NOW()
                WHERE user_id = %s
                  AND card_id = %s
                """,
                (int(loser_user_id), card_id),
            )

        cur.execute(
            """
            INSERT INTO user_xcard_collection
            (user_id, card_id, quantity, first_obtained_at, updated_at)
            VALUES (%s, %s, 1, NOW(), NOW())
            ON CONFLICT (user_id, card_id)
            DO UPDATE SET
                quantity = user_xcard_collection.quantity + 1,
                updated_at = NOW()
            """,
            (int(winner_user_id), card_id),
        )

        return {
            "status": "completed",
            "card_id": card_id,
            "card_name": str(candidate.get("name") or "").strip(),
            "card_slot": int(candidate.get("slot") or 0),
            "bp": int(candidate.get("bp") or 0),
            "fallback_used": bool(reward_card and int(reward_card.get("card_id") or 0) != card_id),
        }

    return {
        "status": "review",
        "card_id": int((reward_card or {}).get("card_id") or 0),
        "card_name": str((reward_card or {}).get("name") or "").strip(),
        "card_slot": int((reward_card or {}).get("slot") or 0),
        "bp": int((reward_card or {}).get("bp") or 0),
        "fallback_used": False,
    }


def _finalize_duel_locked(
    cur,
    duel: Dict[str, Any],
    players_state: Dict[str, Any],
    teams_state: Dict[str, Any],
    *,
    winner_user_id: Optional[int],
    loser_user_id: Optional[int],
    resolution_reason: str,
    event_actor_user_id: Optional[int] = None,
    timeout_loser: bool = False,
    surrender_loser: bool = False,
    cancelled: bool = False,
) -> Dict[str, Any]:
    duel_id = int(duel["duel_id"])
    mode = str(duel.get("mode") or "friendly").strip().lower() or "friendly"
    entry_fee = int(duel.get("entry_fee") or 0)
    reward_result = {"status": "none", "card_id": 0}
    final_state = "cancelled" if cancelled else "completed"

    if winner_user_id and loser_user_id and mode == "wager":
        reward_result = _transfer_reward_card_locked(
            cur,
            duel_id=duel_id,
            winner_user_id=int(winner_user_id),
            loser_user_id=int(loser_user_id),
            teams_state=teams_state,
        )
        if reward_result.get("status") == "review":
            final_state = "completed_reward_review"

    _release_duel_locks(cur, duel_id)
    _release_presence(cur, duel_id)

    if winner_user_id and loser_user_id and not cancelled:
        winner_kwargs = {
            "wins": 1,
            "friendly_wins": 1 if mode == "friendly" else 0,
            "wager_wins": 1 if mode == "wager" else 0,
            "cards_won": 1 if reward_result.get("status") == "completed" else 0,
            "coins_spent": entry_fee if mode == "wager" and bool(duel.get("entry_fee_applied")) else 0,
        }
        loser_kwargs = {
            "losses": 1,
            "friendly_losses": 1 if mode == "friendly" else 0,
            "wager_losses": 1 if mode == "wager" else 0,
            "cards_lost": 1 if reward_result.get("status") == "completed" else 0,
            "coins_spent": entry_fee if mode == "wager" and bool(duel.get("entry_fee_applied")) else 0,
            "timeouts": 1 if timeout_loser else 0,
            "surrendered": 1 if surrender_loser else 0,
        }
        _adjust_duel_stats_locked(cur, int(winner_user_id), **winner_kwargs)
        _adjust_duel_stats_locked(cur, int(loser_user_id), **loser_kwargs)

    _update_duel_row(
        cur,
        duel_id,
        state=final_state,
        winner_user_id=int(winner_user_id) if winner_user_id else None,
        loser_user_id=int(loser_user_id) if loser_user_id else None,
        resolution_reason=str(resolution_reason or "").strip(),
        reward_card_id=int(reward_result.get("card_id") or 0) if reward_result.get("card_id") else None,
        reward_transfer_status=str(reward_result.get("status") or "none"),
        players_state=_json_param(players_state),
        teams_state=_json_param(teams_state),
        finished_at=utc_now(),
    )

    _insert_duel_event(
        cur,
        duel_id,
        "duel_finished",
        actor_user_id=event_actor_user_id,
        payload={
            "winner_user_id": int(winner_user_id) if winner_user_id else None,
            "loser_user_id": int(loser_user_id) if loser_user_id else None,
            "resolution_reason": str(resolution_reason or "").strip(),
            "cancelled": bool(cancelled),
            "reward": reward_result,
        },
    )

    return {
        "winner_user_id": int(winner_user_id) if winner_user_id else None,
        "loser_user_id": int(loser_user_id) if loser_user_id else None,
        "reward": reward_result,
        "final_state": final_state,
    }


def _resolve_duel_timeout_locked(cur, duel: Dict[str, Any]) -> Dict[str, Any]:
    duel_id = int(duel["duel_id"])
    now = utc_now()
    state = str(duel.get("state") or "")
    players_state = _safe_json_dict(duel.get("players_state"))
    teams_state = _safe_json_dict(duel.get("teams_state"))
    config = _safe_json_dict(duel.get("config_json"))

    challenge_expires_at = duel.get("challenge_expires_at")
    prep_expires_at = duel.get("prep_expires_at")
    round_expires_at = duel.get("round_expires_at")

    if state == "pending_challenge" and challenge_expires_at and challenge_expires_at <= now:
        _release_presence(cur, duel_id)
        _update_duel_row(cur, duel_id, state="expired", resolution_reason="challenge_timeout", finished_at=now)
        _insert_duel_event(cur, duel_id, "challenge_expired", payload={})
        return {"ok": True, "reason": "challenge_timeout"}

    if state in {"waiting_private", "waiting_mode", "selecting_team"} and prep_expires_at and prep_expires_at <= now:
        _release_duel_locks(cur, duel_id)
        _release_presence(cur, duel_id)
        _update_duel_row(cur, duel_id, state="cancelled", resolution_reason="prep_timeout", finished_at=now)
        _insert_duel_event(cur, duel_id, "duel_cancelled", payload={"reason": "prep_timeout"})
        return {"ok": True, "reason": "prep_timeout"}

    if state == "active" and round_expires_at and round_expires_at <= now:
        challenger_id = int(duel.get("challenger_user_id") or 0)
        challenged_id = int(duel.get("challenged_user_id") or 0)
        challenger_choice = (players_state.get(_player_key(challenger_id)) or {}).get("round_choice_slot")
        challenged_choice = (players_state.get(_player_key(challenged_id)) or {}).get("round_choice_slot")

        if challenger_choice and not challenged_choice:
            finish = _finalize_duel_locked(
                cur,
                duel,
                players_state,
                teams_state,
                winner_user_id=challenger_id,
                loser_user_id=challenged_id,
                resolution_reason="round_timeout",
                event_actor_user_id=challenged_id,
                timeout_loser=True,
            )
            return {"ok": True, "reason": "round_timeout", "finish": finish}

        if challenged_choice and not challenger_choice:
            finish = _finalize_duel_locked(
                cur,
                duel,
                players_state,
                teams_state,
                winner_user_id=challenged_id,
                loser_user_id=challenger_id,
                resolution_reason="round_timeout",
                event_actor_user_id=challenger_id,
                timeout_loser=True,
            )
            return {"ok": True, "reason": "round_timeout", "finish": finish}

        finish = _finalize_duel_locked(
            cur,
            duel,
            players_state,
            teams_state,
            winner_user_id=None,
            loser_user_id=None,
            resolution_reason="double_timeout",
            cancelled=True,
        )
        return {"ok": True, "reason": "double_timeout", "finish": finish}

    return {"ok": False, "reason": "not_due"}


def get_duel_bundle(duel_id: int) -> Optional[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _fetch_duel_bundle(cur, int(duel_id))


def get_active_duel_for_user(user_id: int) -> Optional[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT d.*
                FROM duel_user_presence dup
                JOIN duels d
                  ON d.duel_id = dup.duel_id
                WHERE dup.user_id = %s
                """,
                (int(user_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return _fetch_duel_bundle(cur, int(row["duel_id"]))


def get_user_xcard_lock_map(user_id: int, *, exclude_duel_id: Optional[int] = None) -> Dict[int, int]:
    params: List[Any] = [int(user_id)]
    sql = [
        "SELECT card_id, COALESCE(SUM(quantity), 0) AS total",
        "FROM user_xcard_locks",
        "WHERE user_id = %s",
        "  AND status = 'active'",
    ]
    if exclude_duel_id:
        sql.append("  AND NOT (scope_type = %s AND scope_id = %s)")
        params.extend([ACTIVE_LOCK_SCOPE, int(exclude_duel_id)])
    sql.append("GROUP BY card_id")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("\n".join(sql), tuple(params))
            rows = cur.fetchall() or []
            return {int(row["card_id"]): int(row.get("total") or 0) for row in rows}


def get_duel_stats_row(user_id: int) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _ensure_duel_stats_row(cur, int(user_id))
            cur.execute("SELECT * FROM duel_stats WHERE user_id = %s", (int(user_id),))
            row = cur.fetchone() or {}
            conn.commit()
            return dict(row)


def list_open_duels_for_timeout_watch() -> List[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM duels
                WHERE state IN ('pending_challenge', 'waiting_private', 'waiting_mode', 'selecting_team', 'active')
                ORDER BY created_at ASC
                """
            )
            rows = cur.fetchall() or []
            out: List[Dict[str, Any]] = []
            for row in rows:
                out.append(_decode_duel_row(row) or {})
            return out


def create_duel_challenge(
    *,
    challenger_user_id: int,
    challenger_username: str,
    challenger_full_name: str,
    challenged_user_id: int,
    challenged_username: str,
    challenged_full_name: str,
    group_chat_id: int,
    group_chat_title: str,
    challenge_timeout_seconds: int,
    prepare_timeout_seconds: int,
    round_timeout_seconds: int,
    prepare_timeout_policy: str = "cancel",
    round_timeout_policy: str = "forfeit_match",
    private_timeout_policy: str = "cancel",
) -> Dict[str, Any]:
    challenger_user_id = int(challenger_user_id)
    challenged_user_id = int(challenged_user_id)
    if challenger_user_id <= 0 or challenged_user_id <= 0:
        return {"ok": False, "error": "invalid_users"}

    create_or_get_user(challenger_user_id)
    create_or_get_user(challenged_user_id)
    touch_user_identity(challenger_user_id, challenger_username or "", challenger_full_name or "")
    touch_user_identity(challenged_user_id, challenged_username or "", challenged_full_name or "")

    now = utc_now()
    challenge_expires_at = now + timedelta(seconds=max(15, int(challenge_timeout_seconds)))
    config = {
        "challenge_timeout_seconds": int(challenge_timeout_seconds),
        "prepare_timeout_seconds": int(prepare_timeout_seconds),
        "round_timeout_seconds": int(round_timeout_seconds),
        "team_size": TEAM_SIZE,
    }
    players_state = {
        _player_key(challenger_user_id): {
            "role": "challenger",
            "username": str(challenger_username or "").strip(),
            "full_name": str(challenger_full_name or "").strip(),
            "display_name": str(challenger_full_name or challenger_username or f"User {challenger_user_id}").strip(),
            "private_ready": False,
            "private_chat_id": None,
            "panel_message_id": None,
            "mode_confirmed": False,
            "selected_card_ids": [],
            "team_confirmed": False,
            "round_choice_slot": None,
            "round_choice_at": None,
            "pending_surrender": False,
        },
        _player_key(challenged_user_id): {
            "role": "challenged",
            "username": str(challenged_username or "").strip(),
            "full_name": str(challenged_full_name or "").strip(),
            "display_name": str(challenged_full_name or challenged_username or f"User {challenged_user_id}").strip(),
            "private_ready": False,
            "private_chat_id": None,
            "panel_message_id": None,
            "mode_confirmed": False,
            "selected_card_ids": [],
            "team_confirmed": False,
            "round_choice_slot": None,
            "round_choice_at": None,
            "pending_surrender": False,
        },
    }

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute(
                    """
                    INSERT INTO duels (
                        challenger_user_id,
                        challenged_user_id,
                        group_chat_id,
                        group_chat_title,
                        state,
                        challenge_expires_at,
                        timeout_policy_prepare,
                        timeout_policy_round,
                        timeout_policy_private,
                        players_state,
                        teams_state,
                        config_json
                    )
                    VALUES (%s, %s, %s, %s, 'pending_challenge', %s, %s, %s, %s, %s::jsonb, '{}'::jsonb, %s::jsonb)
                    RETURNING duel_id
                    """,
                    (
                        challenger_user_id,
                        challenged_user_id,
                        int(group_chat_id),
                        str(group_chat_title or "").strip(),
                        challenge_expires_at,
                        str(prepare_timeout_policy or "cancel"),
                        str(round_timeout_policy or "forfeit_match"),
                        str(private_timeout_policy or "cancel"),
                        json.dumps(players_state, ensure_ascii=False),
                        json.dumps(config, ensure_ascii=False),
                    ),
                )
                duel_row = cur.fetchone() or {}
                duel_id = int(duel_row.get("duel_id") or 0)
                if duel_id <= 0:
                    raise RuntimeError("duel_id_invalido")

                cur.execute(
                    """
                    INSERT INTO duel_user_presence (user_id, duel_id, presence_state)
                    VALUES
                        (%s, %s, 'pending_challenge'),
                        (%s, %s, 'pending_challenge')
                    ON CONFLICT DO NOTHING
                    RETURNING user_id
                    """,
                    (
                        challenger_user_id,
                        duel_id,
                        challenged_user_id,
                        duel_id,
                    ),
                )
                inserted = cur.fetchall() or []
                if len(inserted) != 2:
                    cur.execute(
                        """
                        SELECT user_id
                        FROM duel_user_presence
                        WHERE user_id IN (%s, %s)
                        """,
                        (challenger_user_id, challenged_user_id),
                    )
                    busy_rows = cur.fetchall() or []
                    busy_ids = {int(row.get("user_id") or 0) for row in busy_rows}
                    conn.rollback()
                    if challenger_user_id in busy_ids:
                        return {"ok": False, "error": "challenger_busy"}
                    if challenged_user_id in busy_ids:
                        return {"ok": False, "error": "challenged_busy"}
                    return {"ok": False, "error": "presence_conflict"}

                _insert_duel_event(
                    cur,
                    duel_id,
                    "challenge_created",
                    actor_user_id=challenger_user_id,
                    payload={
                        "challenger_user_id": challenger_user_id,
                        "challenged_user_id": challenged_user_id,
                        "group_chat_id": int(group_chat_id),
                    },
                )
                conn.commit()
                return {"ok": True, "duel_id": duel_id}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def set_duel_group_message(duel_id: int, message_id: int) -> Optional[Dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("BEGIN")
            duel = _fetch_duel_bundle(cur, int(duel_id))
            if not duel:
                conn.rollback()
                return None
            _update_duel_row(cur, int(duel_id), group_message_id=int(message_id))
            conn.commit()
            return get_duel_bundle(int(duel_id))


def respond_to_duel_challenge(duel_id: int, actor_user_id: int, action: str, private_timeout_seconds: int) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}

                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel
                if str(duel.get("state") or "") != "pending_challenge":
                    due = _resolve_duel_timeout_locked(cur, duel)
                    if due.get("ok"):
                        conn.commit()
                        return {"ok": False, "error": "expired", "duel": get_duel_bundle(int(duel_id))}
                    conn.rollback()
                    return {"ok": False, "error": "invalid_state", "duel": duel}

                if int(actor_user_id) != int(duel.get("challenged_user_id") or 0):
                    conn.rollback()
                    return {"ok": False, "error": "not_target"}

                now = utc_now()
                if duel.get("challenge_expires_at") and duel["challenge_expires_at"] <= now:
                    _resolve_duel_timeout_locked(cur, duel)
                    conn.commit()
                    return {"ok": False, "error": "expired", "duel": get_duel_bundle(int(duel_id))}

                if str(action or "").strip().lower() == "reject":
                    _release_presence(cur, int(duel_id))
                    _update_duel_row(
                        cur,
                        int(duel_id),
                        state="declined",
                        resolution_reason="rejected",
                        finished_at=now,
                    )
                    _insert_duel_event(cur, int(duel_id), "challenge_rejected", actor_user_id=int(actor_user_id), payload={})
                    conn.commit()
                    return {"ok": True, "duel": get_duel_bundle(int(duel_id))}

                prep_expires_at = now + timedelta(seconds=max(30, int(private_timeout_seconds)))
                _touch_presence_state(cur, int(duel_id), "waiting_private")
                _update_duel_row(
                    cur,
                    int(duel_id),
                    state="waiting_private",
                    prep_expires_at=prep_expires_at,
                )
                _insert_duel_event(cur, int(duel_id), "challenge_accepted", actor_user_id=int(actor_user_id), payload={})
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id))}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def set_private_panel_ready(duel_id: int, user_id: int, chat_id: int, message_id: int, prepare_timeout_seconds: int) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}

                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel
                if str(duel.get("state") or "") not in {"waiting_private", "waiting_mode", "selecting_team"}:
                    due = _resolve_duel_timeout_locked(cur, duel)
                    if due.get("ok"):
                        conn.commit()
                        return {"ok": False, "error": "expired", "duel": get_duel_bundle(int(duel_id))}
                    conn.rollback()
                    return {"ok": False, "error": "invalid_state", "duel": duel}

                players_state = _safe_json_dict(duel.get("players_state"))
                player = players_state.get(_player_key(user_id))
                if not isinstance(player, dict):
                    conn.rollback()
                    return {"ok": False, "error": "not_participant"}

                player["private_ready"] = True
                player["private_chat_id"] = int(chat_id)
                player["panel_message_id"] = int(message_id)
                players_state[_player_key(user_id)] = player

                next_state = str(duel.get("state") or "")
                prep_expires_at = duel.get("prep_expires_at")
                both_ready = all(bool((players_state.get(key) or {}).get("private_ready")) for key in players_state.keys())
                if next_state == "waiting_private" and both_ready:
                    next_state = "waiting_mode"
                    prep_expires_at = utc_now() + timedelta(seconds=max(45, int(prepare_timeout_seconds)))
                    _touch_presence_state(cur, int(duel_id), "waiting_mode")
                    _insert_duel_event(cur, int(duel_id), "private_ready", actor_user_id=int(user_id), payload={"both_ready": True})
                else:
                    _insert_duel_event(cur, int(duel_id), "private_ready", actor_user_id=int(user_id), payload={"both_ready": False})

                _update_duel_row(
                    cur,
                    int(duel_id),
                    state=next_state,
                    prep_expires_at=prep_expires_at,
                    players_state=_json_param(players_state),
                )
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id))}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def update_private_panel_reference(duel_id: int, user_id: int, chat_id: int, message_id: int) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}

                players_state = _safe_json_dict(duel.get("players_state"))
                player = players_state.get(_player_key(user_id))
                if not isinstance(player, dict):
                    conn.rollback()
                    return {"ok": False, "error": "not_participant"}

                player["private_chat_id"] = int(chat_id)
                player["panel_message_id"] = int(message_id)
                player["private_ready"] = True
                players_state[_player_key(user_id)] = player
                _update_duel_row(cur, int(duel_id), players_state=_json_param(players_state))
                conn.commit()
                return {"ok": True}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def propose_duel_mode(duel_id: int, user_id: int, mode: str) -> Dict[str, Any]:
    normalized_mode = "wager" if str(mode or "").strip().lower() == "wager" else "friendly"
    entry_fee = 1 if normalized_mode == "wager" else 0

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}
                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel

                if str(duel.get("state") or "") != "waiting_mode":
                    due = _resolve_duel_timeout_locked(cur, duel)
                    if due.get("ok"):
                        conn.commit()
                        return {"ok": False, "error": "expired", "duel": get_duel_bundle(int(duel_id))}
                    conn.rollback()
                    return {"ok": False, "error": "invalid_state", "duel": duel}

                if int(user_id) != int(duel.get("challenger_user_id") or 0):
                    conn.rollback()
                    return {"ok": False, "error": "only_challenger"}

                players_state = _safe_json_dict(duel.get("players_state"))
                challenger = players_state.get(_player_key(user_id)) or {}
                challenged = players_state.get(_player_key(int(duel.get("challenged_user_id") or 0))) or {}
                challenger["mode_confirmed"] = True
                challenged["mode_confirmed"] = False
                players_state[_player_key(user_id)] = challenger
                players_state[_player_key(int(duel.get("challenged_user_id") or 0))] = challenged

                _update_duel_row(
                    cur,
                    int(duel_id),
                    mode=normalized_mode,
                    entry_fee=entry_fee,
                    players_state=_json_param(players_state),
                )
                _insert_duel_event(
                    cur,
                    int(duel_id),
                    "mode_proposed",
                    actor_user_id=int(user_id),
                    payload={"mode": normalized_mode, "entry_fee": entry_fee},
                )
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id))}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def confirm_duel_mode(duel_id: int, user_id: int, selection_timeout_seconds: int) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}
                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel

                if str(duel.get("state") or "") != "waiting_mode":
                    due = _resolve_duel_timeout_locked(cur, duel)
                    if due.get("ok"):
                        conn.commit()
                        return {"ok": False, "error": "expired", "duel": get_duel_bundle(int(duel_id))}
                    conn.rollback()
                    return {"ok": False, "error": "invalid_state", "duel": duel}

                if int(user_id) != int(duel.get("challenged_user_id") or 0):
                    conn.rollback()
                    return {"ok": False, "error": "only_challenged"}

                mode = str(duel.get("mode") or "").strip().lower()
                if mode not in {"friendly", "wager"}:
                    conn.rollback()
                    return {"ok": False, "error": "mode_missing"}

                players_state = _safe_json_dict(duel.get("players_state"))
                challenged = players_state.get(_player_key(user_id)) or {}
                challenged["mode_confirmed"] = True
                players_state[_player_key(user_id)] = challenged

                if mode == "wager":
                    challenger_coins = _get_user_coins_locked(cur, int(duel.get("challenger_user_id") or 0))
                    challenged_coins = _get_user_coins_locked(cur, int(duel.get("challenged_user_id") or 0))
                    if challenger_coins < 1 or challenged_coins < 1:
                        conn.rollback()
                        return {
                            "ok": False,
                            "error": "insufficient_coins",
                            "challenger_coins": challenger_coins,
                            "challenged_coins": challenged_coins,
                        }

                prep_expires_at = utc_now() + timedelta(seconds=max(60, int(selection_timeout_seconds)))
                _touch_presence_state(cur, int(duel_id), "selecting_team")
                _update_duel_row(
                    cur,
                    int(duel_id),
                    state="selecting_team",
                    prep_expires_at=prep_expires_at,
                    players_state=_json_param(players_state),
                )
                _insert_duel_event(cur, int(duel_id), "mode_confirmed", actor_user_id=int(user_id), payload={"mode": mode})
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id))}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def save_team_draft(duel_id: int, user_id: int, card_ids: Iterable[int]) -> Dict[str, Any]:
    clean_ids = [int(card_id) for card_id in card_ids if int(card_id) > 0]
    if len(clean_ids) > TEAM_SIZE or len(set(clean_ids)) != len(clean_ids):
        return {"ok": False, "error": "draft_invalid"}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}
                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel

                if str(duel.get("state") or "") != "selecting_team":
                    due = _resolve_duel_timeout_locked(cur, duel)
                    if due.get("ok"):
                        conn.commit()
                        return {"ok": False, "error": "expired", "duel": get_duel_bundle(int(duel_id))}
                    conn.rollback()
                    return {"ok": False, "error": "invalid_state", "duel": duel}

                players_state = _safe_json_dict(duel.get("players_state"))
                player = players_state.get(_player_key(user_id))
                if not isinstance(player, dict):
                    conn.rollback()
                    return {"ok": False, "error": "not_participant"}
                if bool(player.get("team_confirmed")):
                    conn.rollback()
                    return {"ok": False, "error": "team_locked"}

                player["selected_card_ids"] = clean_ids
                players_state[_player_key(user_id)] = player
                _update_duel_row(cur, int(duel_id), players_state=_json_param(players_state))
                _insert_duel_event(cur, int(duel_id), "team_draft_updated", actor_user_id=int(user_id), payload={"card_ids": clean_ids})
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id))}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def confirm_duel_team(
    duel_id: int,
    user_id: int,
    *,
    cards_payload: List[Dict[str, Any]],
    round_timeout_seconds: int,
) -> Dict[str, Any]:
    card_ids = [int((item or {}).get("card_id") or 0) for item in cards_payload]
    valid, reason = validate_team_selection(card_ids)
    if not valid:
        return {"ok": False, "error": reason}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}
                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel

                if str(duel.get("state") or "") != "selecting_team":
                    due = _resolve_duel_timeout_locked(cur, duel)
                    if due.get("ok"):
                        conn.commit()
                        return {"ok": False, "error": "expired", "duel": get_duel_bundle(int(duel_id))}
                    conn.rollback()
                    return {"ok": False, "error": "invalid_state", "duel": duel}

                players_state = _safe_json_dict(duel.get("players_state"))
                teams_state = _safe_json_dict(duel.get("teams_state"))
                player = players_state.get(_player_key(user_id))
                if not isinstance(player, dict):
                    conn.rollback()
                    return {"ok": False, "error": "not_participant"}
                if bool(player.get("team_confirmed")):
                    conn.rollback()
                    return {"ok": False, "error": "team_locked"}

                draft_ids = [int(card_id) for card_id in list(player.get("selected_card_ids") or [])]
                if draft_ids != card_ids:
                    conn.rollback()
                    return {"ok": False, "error": "draft_mismatch"}

                lock_ok, lock_reason = _acquire_duel_card_locks(cur, int(duel_id), int(user_id), card_ids)
                if not lock_ok:
                    conn.rollback()
                    return {"ok": False, "error": lock_reason}

                snapshot = build_team_snapshot(
                    [
                        {
                            "card_id": int(item["card_id"]),
                            "card_no": str(item.get("card_no") or "").strip(),
                            "name": str(item.get("name") or "").strip(),
                            "title": str(item.get("title") or "").strip(),
                            "image": str(item.get("image") or "").strip(),
                            "rarity": str(item.get("rarity") or "").strip(),
                            "bp_value": int(item.get("bp_value") or item.get("bp") or 0),
                            "bp": str(item.get("bp_display") or item.get("bp") or "").strip(),
                            "bp_display": str(item.get("bp_display") or item.get("bp") or "").strip(),
                        }
                        for item in cards_payload
                    ]
                )
                teams_state[_player_key(user_id)] = {
                    "cards": snapshot,
                    "confirmed_at": utc_now().isoformat(),
                }
                player["team_confirmed"] = True
                player["team_confirmed_at"] = utc_now().isoformat()
                players_state[_player_key(user_id)] = player

                both_confirmed = all(bool((players_state.get(key) or {}).get("team_confirmed")) for key in players_state.keys())
                next_state = "selecting_team"
                round_expires_at = duel.get("round_expires_at")
                current_round = int(duel.get("current_round") or 0)
                started_at = duel.get("started_at")
                entry_fee_applied = bool(duel.get("entry_fee_applied"))
                duel_mode = str(duel.get("mode") or "friendly").strip().lower() or "friendly"
                entry_fee = int(duel.get("entry_fee") or 0)

                if both_confirmed:
                    if duel_mode == "wager" and not entry_fee_applied:
                        challenger_id = int(duel.get("challenger_user_id") or 0)
                        challenged_id = int(duel.get("challenged_user_id") or 0)
                        challenger_coins = _get_user_coins_locked(cur, challenger_id)
                        challenged_coins = _get_user_coins_locked(cur, challenged_id)
                        if challenger_coins < entry_fee or challenged_coins < entry_fee:
                            _release_duel_locks(cur, int(duel_id))
                            _release_presence(cur, int(duel_id))
                            _update_duel_row(
                                cur,
                                int(duel_id),
                                state="cancelled",
                                resolution_reason="entry_fee_insufficient",
                                players_state=_json_param(players_state),
                                teams_state=_json_param(teams_state),
                                finished_at=utc_now(),
                            )
                            _insert_duel_event(
                                cur,
                                int(duel_id),
                                "duel_cancelled",
                                actor_user_id=int(user_id),
                                payload={"reason": "entry_fee_insufficient"},
                            )
                            conn.commit()
                            return {"ok": False, "error": "entry_fee_insufficient", "duel": get_duel_bundle(int(duel_id))}

                        cur.execute(
                            "UPDATE users SET coins = coins - %s, updated_at = NOW() WHERE user_id = %s",
                            (entry_fee, challenger_id),
                        )
                        cur.execute(
                            "UPDATE users SET coins = coins - %s, updated_at = NOW() WHERE user_id = %s",
                            (entry_fee, challenged_id),
                        )
                        _record_coin_tx_locked(
                            cur,
                            challenger_id,
                            "duel_entry_wager",
                            -entry_fee,
                            balance_after=challenger_coins - entry_fee,
                            reference_id=int(duel_id),
                            metadata={"duel_id": int(duel_id), "mode": duel_mode},
                        )
                        _record_coin_tx_locked(
                            cur,
                            challenged_id,
                            "duel_entry_wager",
                            -entry_fee,
                            balance_after=challenged_coins - entry_fee,
                            reference_id=int(duel_id),
                            metadata={"duel_id": int(duel_id), "mode": duel_mode},
                        )
                        entry_fee_applied = True

                    next_state = "active"
                    current_round = 1
                    round_expires_at = utc_now() + timedelta(seconds=max(20, int(round_timeout_seconds)))
                    started_at = utc_now()
                    _touch_presence_state(cur, int(duel_id), "active")
                    _insert_duel_event(cur, int(duel_id), "duel_started", actor_user_id=int(user_id), payload={"round": 1})

                _update_duel_row(
                    cur,
                    int(duel_id),
                    state=next_state,
                    current_round=current_round,
                    round_expires_at=round_expires_at,
                    started_at=started_at,
                    entry_fee_applied=entry_fee_applied,
                    players_state=_json_param(players_state),
                    teams_state=_json_param(teams_state),
                )
                _insert_duel_event(
                    cur,
                    int(duel_id),
                    "team_confirmed",
                    actor_user_id=int(user_id),
                    payload={"card_ids": card_ids, "both_confirmed": both_confirmed},
                )
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id))}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def submit_round_choice(duel_id: int, user_id: int, slot_no: int, round_timeout_seconds: int) -> Dict[str, Any]:
    slot_no = int(slot_no)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}
                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel

                if str(duel.get("state") or "") != "active":
                    due = _resolve_duel_timeout_locked(cur, duel)
                    if due.get("ok"):
                        conn.commit()
                        return {"ok": False, "error": "expired", "duel": get_duel_bundle(int(duel_id))}
                    conn.rollback()
                    return {"ok": False, "error": "invalid_state", "duel": duel}

                players_state = _safe_json_dict(duel.get("players_state"))
                teams_state = _safe_json_dict(duel.get("teams_state"))
                player = players_state.get(_player_key(user_id))
                if not isinstance(player, dict):
                    conn.rollback()
                    return {"ok": False, "error": "not_participant"}

                team_state = teams_state.get(_player_key(user_id)) or {}
                team_cards = list(team_state.get("cards") or [])
                entry = find_team_entry(team_cards, slot_no)
                if not entry:
                    conn.rollback()
                    return {"ok": False, "error": "slot_invalido"}
                if bool(entry.get("eliminated")) or int(entry.get("hp") or 0) <= 0:
                    conn.rollback()
                    return {"ok": False, "error": "slot_eliminado"}

                player["round_choice_slot"] = slot_no
                player["round_choice_at"] = utc_now().isoformat()
                player["pending_surrender"] = False
                players_state[_player_key(user_id)] = player

                challenger_id = int(duel.get("challenger_user_id") or 0)
                challenged_id = int(duel.get("challenged_user_id") or 0)
                challenger_choice = (players_state.get(_player_key(challenger_id)) or {}).get("round_choice_slot")
                challenged_choice = (players_state.get(_player_key(challenged_id)) or {}).get("round_choice_slot")

                payload = {"round_resolved": False}
                if challenger_choice and challenged_choice:
                    round_no = int(duel.get("current_round") or 1)
                    challenger_team = list((teams_state.get(_player_key(challenger_id)) or {}).get("cards") or [])
                    challenged_team = list((teams_state.get(_player_key(challenged_id)) or {}).get("cards") or [])

                    resolution = resolve_round(
                        challenger_team,
                        int(challenger_choice),
                        challenger_id,
                        challenged_team,
                        int(challenged_choice),
                        challenged_id,
                    )

                    teams_state[_player_key(challenger_id)] = {"cards": resolution["team_a"]}
                    teams_state[_player_key(challenged_id)] = {"cards": resolution["team_b"]}

                    players_state[_player_key(challenger_id)]["round_choice_slot"] = None
                    players_state[_player_key(challenger_id)]["round_choice_at"] = None
                    players_state[_player_key(challenged_id)]["round_choice_slot"] = None
                    players_state[_player_key(challenged_id)]["round_choice_at"] = None

                    cur.execute(
                        """
                        INSERT INTO duel_rounds (duel_id, round_no, choices_json, result_json)
                        VALUES (%s, %s, %s::jsonb, %s::jsonb)
                        ON CONFLICT (duel_id, round_no) DO UPDATE SET
                            choices_json = EXCLUDED.choices_json,
                            result_json = EXCLUDED.result_json
                        """,
                        (
                            int(duel_id),
                            int(round_no),
                            json.dumps(
                                {
                                    "challenger_choice": int(challenger_choice),
                                    "challenged_choice": int(challenged_choice),
                                },
                                ensure_ascii=False,
                            ),
                            json.dumps(
                                {
                                    "resolution": resolution,
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    )

                    _insert_duel_event(
                        cur,
                        int(duel_id),
                        "round_resolved",
                        actor_user_id=int(user_id),
                        payload={
                            "round_no": round_no,
                            "challenger_choice": int(challenger_choice),
                            "challenged_choice": int(challenged_choice),
                            "outcome": resolution["outcome"],
                        },
                    )

                    if is_team_eliminated(resolution["team_a"]):
                        finish = _finalize_duel_locked(
                            cur,
                            duel,
                            players_state,
                            teams_state,
                            winner_user_id=challenged_id,
                            loser_user_id=challenger_id,
                            resolution_reason="all_cards_eliminated",
                            event_actor_user_id=int(user_id),
                        )
                        payload = {"round_resolved": True, "round_result": resolution, "finish": finish}
                    elif is_team_eliminated(resolution["team_b"]):
                        finish = _finalize_duel_locked(
                            cur,
                            duel,
                            players_state,
                            teams_state,
                            winner_user_id=challenger_id,
                            loser_user_id=challenged_id,
                            resolution_reason="all_cards_eliminated",
                            event_actor_user_id=int(user_id),
                        )
                        payload = {"round_resolved": True, "round_result": resolution, "finish": finish}
                    else:
                        next_round = round_no + 1
                        round_expires_at = utc_now() + timedelta(seconds=max(20, int(round_timeout_seconds)))
                        _update_duel_row(
                            cur,
                            int(duel_id),
                            current_round=next_round,
                            round_expires_at=round_expires_at,
                            players_state=_json_param(players_state),
                            teams_state=_json_param(teams_state),
                        )
                        payload = {"round_resolved": True, "round_result": resolution, "next_round": next_round}
                else:
                    _update_duel_row(
                        cur,
                        int(duel_id),
                        players_state=_json_param(players_state),
                    )

                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id)), "payload": payload}
            except ValueError as exc:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return {"ok": False, "error": str(exc)}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def set_surrender_pending(duel_id: int, user_id: int, pending: bool) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}
                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel

                if str(duel.get("state") or "") != "active":
                    conn.rollback()
                    return {"ok": False, "error": "invalid_state"}

                players_state = _safe_json_dict(duel.get("players_state"))
                player = players_state.get(_player_key(user_id))
                if not isinstance(player, dict):
                    conn.rollback()
                    return {"ok": False, "error": "not_participant"}
                player["pending_surrender"] = bool(pending)
                players_state[_player_key(user_id)] = player
                _update_duel_row(cur, int(duel_id), players_state=_json_param(players_state))
                _insert_duel_event(cur, int(duel_id), "surrender_prompt", actor_user_id=int(user_id), payload={"pending": bool(pending)})
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id))}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def confirm_surrender(duel_id: int, user_id: int) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}
                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel

                if str(duel.get("state") or "") != "active":
                    conn.rollback()
                    return {"ok": False, "error": "invalid_state"}

                challenger_id = int(duel.get("challenger_user_id") or 0)
                challenged_id = int(duel.get("challenged_user_id") or 0)
                if int(user_id) not in {challenger_id, challenged_id}:
                    conn.rollback()
                    return {"ok": False, "error": "not_participant"}

                players_state = _safe_json_dict(duel.get("players_state"))
                teams_state = _safe_json_dict(duel.get("teams_state"))
                player = players_state.get(_player_key(user_id)) or {}
                if not bool(player.get("pending_surrender")):
                    conn.rollback()
                    return {"ok": False, "error": "not_confirmed"}

                winner_user_id = challenged_id if int(user_id) == challenger_id else challenger_id
                finish = _finalize_duel_locked(
                    cur,
                    duel,
                    players_state,
                    teams_state,
                    winner_user_id=winner_user_id,
                    loser_user_id=int(user_id),
                    resolution_reason="surrender",
                    event_actor_user_id=int(user_id),
                    surrender_loser=True,
                )
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id)), "finish": finish}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def cancel_duel(duel_id: int, reason: str, actor_user_id: Optional[int] = None) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}
                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel

                state = str(duel.get("state") or "")
                if state in FINAL_STATES:
                    conn.rollback()
                    return {"ok": False, "error": "already_final"}

                players_state = _safe_json_dict(duel.get("players_state"))
                teams_state = _safe_json_dict(duel.get("teams_state"))
                _release_duel_locks(cur, int(duel_id))
                _release_presence(cur, int(duel_id))
                _update_duel_row(
                    cur,
                    int(duel_id),
                    state="cancelled",
                    resolution_reason=str(reason or "cancelled").strip(),
                    players_state=_json_param(players_state),
                    teams_state=_json_param(teams_state),
                    finished_at=utc_now(),
                )
                _insert_duel_event(
                    cur,
                    int(duel_id),
                    "duel_cancelled",
                    actor_user_id=int(actor_user_id) if actor_user_id is not None else None,
                    payload={"reason": str(reason or "cancelled").strip()},
                )
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id))}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise


def handle_duel_timeout(duel_id: int) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                cur.execute("SELECT * FROM duels WHERE duel_id = %s FOR UPDATE", (int(duel_id),))
                duel = _decode_duel_row(cur.fetchone())
                if not duel:
                    conn.rollback()
                    return {"ok": False, "error": "not_found"}

                duel = _fetch_duel_bundle(cur, int(duel_id)) or duel
                result = _resolve_duel_timeout_locked(cur, duel)
                if not result.get("ok"):
                    conn.rollback()
                    return result
                conn.commit()
                return {"ok": True, "duel": get_duel_bundle(int(duel_id)), "timeout": result}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
