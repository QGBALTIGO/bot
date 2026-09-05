from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row

from database_aninexus_bonds import (
    create_bond_invite,
    get_active_bond,
    list_bond_invites,
    remove_active_bond,
    respond_bond_invite,
)
from database_core import pool
from webapp_routes.aninexus_compat import API_PREFIX
from webapp_routes.aninexus_social import _auth, _name_for_user


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _partner_id(bond: dict[str, Any], user_id: int) -> int:
    low_id = int(bond.get("user_low_id") or 0)
    high_id = int(bond.get("user_high_id") or 0)
    return high_id if low_id == int(user_id) else low_id


def _bond_payload(user_id: int, bond: dict[str, Any] | None) -> dict[str, Any] | None:
    if not bond:
        return None
    partner_id = _partner_id(bond, int(user_id))
    return {
        "bond_id": int(bond.get("bond_id") or 0),
        "partner_id": partner_id,
        "partner_name": _name_for_user(partner_id),
        "partner_avatar": None,
        "married_at": _iso(bond.get("created_at")),
        "created_at": _iso(bond.get("created_at")),
        "status": str(bond.get("status") or "active"),
    }


def _invite_payload(user_id: int, row: dict[str, Any]) -> dict[str, Any]:
    inviter_id = int(row.get("inviter_id") or 0)
    invitee_id = int(row.get("invitee_id") or 0)
    incoming = invitee_id == int(user_id)
    other_id = inviter_id if incoming else invitee_id
    return {
        "invite_id": int(row.get("invite_id") or 0),
        "direction": "incoming" if incoming else "outgoing",
        "inviter_id": inviter_id,
        "invitee_id": invitee_id,
        "other_user_id": other_id,
        "other_user_name": _name_for_user(other_id),
        "status": str(row.get("status") or "pending"),
        "created_at": _iso(row.get("created_at")),
        "expires_at": _iso(row.get("expires_at")),
    }


def _duel_history(user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT duel_id, challenger_user_id, challenged_user_id,
                       mode, state, winner_user_id, loser_user_id,
                       resolution_reason, current_round, reward_card_id,
                       reward_transfer_status, created_at, started_at, finished_at
                FROM duels
                WHERE challenger_user_id = %s OR challenged_user_id = %s
                ORDER BY COALESCE(finished_at, started_at, created_at) DESC
                LIMIT %s
                """,
                (int(user_id), int(user_id), limit),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]

    items: list[dict[str, Any]] = []
    final_states = {"completed", "completed_reward_review", "cancelled", "declined", "expired"}
    for row in rows:
        challenger_id = int(row.get("challenger_user_id") or 0)
        challenged_id = int(row.get("challenged_user_id") or 0)
        opponent_id = challenged_id if challenger_id == int(user_id) else challenger_id
        winner_id = int(row.get("winner_user_id") or 0)
        loser_id = int(row.get("loser_user_id") or 0)
        state = str(row.get("state") or "")
        if winner_id == int(user_id):
            outcome = "win"
        elif loser_id == int(user_id):
            outcome = "loss"
        elif state in final_states:
            outcome = "draw"
        else:
            outcome = "active"
        items.append(
            {
                "duel_id": int(row.get("duel_id") or 0),
                "opponent_id": opponent_id,
                "opponent_name": _name_for_user(opponent_id),
                "mode": str(row.get("mode") or "friendly"),
                "state": state,
                "outcome": outcome,
                "winner_user_id": winner_id or None,
                "loser_user_id": loser_id or None,
                "resolution_reason": str(row.get("resolution_reason") or ""),
                "rounds": max(0, int(row.get("current_round") or 0)),
                "reward_card_id": int(row.get("reward_card_id") or 0) or None,
                "reward_transfer_status": str(row.get("reward_transfer_status") or "none"),
                "created_at": _iso(row.get("created_at")),
                "started_at": _iso(row.get("started_at")),
                "finished_at": _iso(row.get("finished_at")),
            }
        )
    return items


def build_aninexus_bonds_duels_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-bonds-duels"])

    @router.get("/social/marriage")
    @router.get("/social/bond")
    def current_bond(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        user_id = int(user.get("id") or 0)
        return JSONResponse(_bond_payload(user_id, get_active_bond(user_id)))

    @router.get("/social/bond/invites")
    def bond_invites(
        limit: int = Query(default=30, ge=1, le=100),
        authorization: str = Header(default=""),
    ):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        user_id = int(user.get("id") or 0)
        rows = list_bond_invites(user_id, limit=limit)
        return JSONResponse([_invite_payload(user_id, row) for row in rows])

    @router.post("/social/bond/invite")
    def bond_invite(
        payload: dict = Body(default={}),
        authorization: str = Header(default=""),
    ):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        try:
            target_user_id = int((payload or {}).get("target_user_id") or 0)
        except (TypeError, ValueError):
            target_user_id = 0
        result = create_bond_invite(int(user.get("id") or 0), target_user_id)
        if result.get("ok"):
            return JSONResponse(result)
        messages = {
            "invalid_user": "Usuário inválido.",
            "user_not_found": "Usuário não encontrado.",
            "inviter_already_bonded": "Você já possui um vínculo ativo.",
            "invitee_already_bonded": "Esse usuário já possui um vínculo ativo.",
        }
        code = str(result.get("error") or "bond_invite_failed")
        return JSONResponse(
            {"error": {"code": code, "message": messages.get(code, "Não foi possível enviar o convite.")}},
            status_code=409,
        )

    @router.post("/social/bond/invites/{invite_id}/respond")
    def bond_respond(
        invite_id: int,
        payload: dict = Body(default={}),
        authorization: str = Header(default=""),
    ):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        action = str((payload or {}).get("action") or "").strip().lower()
        result = respond_bond_invite(int(user.get("id") or 0), int(invite_id), action)
        if result.get("ok"):
            return JSONResponse(result)
        messages = {
            "invalid_action": "Resposta inválida.",
            "invite_not_found": "Convite não encontrado.",
            "forbidden": "Apenas quem recebeu o convite pode responder.",
            "invite_not_pending": "Este convite já foi encerrado.",
            "invite_expired": "Este convite expirou.",
            "already_bonded": "Um dos usuários já possui um vínculo ativo.",
        }
        code = str(result.get("error") or "bond_response_failed")
        return JSONResponse(
            {"error": {"code": code, "message": messages.get(code, "Não foi possível responder ao convite.")}},
            status_code=409,
        )

    @router.delete("/social/bond")
    def bond_remove(authorization: str = Header(default="")):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        result = remove_active_bond(int(user.get("id") or 0))
        if result.get("ok"):
            return JSONResponse(result)
        return JSONResponse(
            {"error": {"code": "bond_not_found", "message": "Você não possui um vínculo ativo."}},
            status_code=404,
        )

    @router.get("/duels/history")
    def duel_history(
        limit: int = Query(default=30, ge=1, le=100),
        authorization: str = Header(default=""),
    ):
        user, error = _auth(authorization)
        if error:
            return error
        assert user is not None
        return JSONResponse(_duel_history(int(user.get("id") or 0), limit=limit))

    return router
