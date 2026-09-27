"""Rewarded Monetag ads for the Source Telegram MiniApp.

Rewards are granted only from a server-side Monetag postback. The browser only
starts the ad and polls the immutable session ledger.
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row

from database import DADO_MAX_BALANCE, get_dado_state
from database_core import pool
from utils.runtime_guard import rate_limiter
from webapp_routes.aninexus_compat import API_PREFIX, _require_user

PROVIDER = "monetag"
PLACEMENT = "source_dado_reward"
REWARD_DADOS = 1
DAILY_LIMIT = 3
COOLDOWN_MINUTES = 60
SESSION_TTL_MINUTES = 10


def _sdk_url() -> str:
    return str(os.getenv("MONETAG_SDK_URL") or "").strip()


def _zone_id() -> str:
    return str(os.getenv("MONETAG_ZONE_ID") or "").strip()


def _postback_secret() -> str:
    return str(os.getenv("MONETAG_POSTBACK_SECRET") or "").strip()


def monetag_enabled() -> bool:
    sdk = _sdk_url()
    zone = _zone_id()
    secret = _postback_secret()
    return sdk.startswith("https://") and bool(zone) and len(secret) >= 20


def _sdk_function() -> str:
    zone = "".join(ch for ch in _zone_id() if ch.isalnum() or ch == "_")
    return f"show_{zone}" if zone else ""


def _iso(value):
    return value.isoformat() if value else None


async def _actor(request: Request, authorization: str = Header(default="")) -> int:
    try:
        uid = int(_require_user(authorization).get("id") or 0)
        if uid <= 0:
            raise PermissionError()
    except (PermissionError, ValueError) as exc:
        raise HTTPException(401, "Sessão expirada. Reabra a MiniApp.") from exc
    if not await rate_limiter.allow(f"rewarded-ad-user:{uid}", 20, 60):
        raise HTTPException(429, "Muitas tentativas. Aguarde um momento.")
    return uid


def _expire_pending_locked(cur, user_id: int) -> None:
    cur.execute(
        """
        UPDATE source_rewarded_ad_sessions
        SET status='expired'
        WHERE user_id=%s AND status='pending' AND expires_at<=NOW()
        """,
        (int(user_id),),
    )


def _daily_rewarded_count_locked(cur, user_id: int) -> int:
    cur.execute(
        """
        SELECT COUNT(*) AS total
        FROM source_rewarded_ad_sessions
        WHERE user_id=%s
          AND status='rewarded'
          AND (rewarded_at AT TIME ZONE 'America/Sao_Paulo')::date =
              (NOW() AT TIME ZONE 'America/Sao_Paulo')::date
        """,
        (int(user_id),),
    )
    return int((cur.fetchone() or {}).get("total") or 0)


def _last_rewarded_at_locked(cur, user_id: int):
    cur.execute(
        """
        SELECT rewarded_at
        FROM source_rewarded_ad_sessions
        WHERE user_id=%s AND status='rewarded'
        ORDER BY rewarded_at DESC
        LIMIT 1
        """,
        (int(user_id),),
    )
    row = cur.fetchone() or {}
    return row.get("rewarded_at")


def rewarded_status(user_id: int) -> dict:
    uid = int(user_id)
    dado = get_dado_state(uid) or {}
    now = datetime.now(timezone.utc)
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        if not cur.fetchone():
            raise HTTPException(404, "Conta Source não encontrada.")
        _expire_pending_locked(cur, uid)
        daily = _daily_rewarded_count_locked(cur, uid)
        last = _last_rewarded_at_locked(cur, uid)
        cur.execute(
            """
            SELECT id,created_at,expires_at
            FROM source_rewarded_ad_sessions
            WHERE user_id=%s AND status='pending'
            ORDER BY created_at DESC LIMIT 1
            """,
            (uid,),
        )
        pending = cur.fetchone()
    cooldown_until = last + timedelta(minutes=COOLDOWN_MINUTES) if last else None
    balance = int(dado.get("balance") or 0)
    can_start = (
        monetag_enabled()
        and daily < DAILY_LIMIT
        and balance < DADO_MAX_BALANCE
        and (cooldown_until is None or cooldown_until <= now)
        and not pending
    )
    return {
        "enabled": monetag_enabled(),
        "provider": PROVIDER,
        "rewardDados": REWARD_DADOS,
        "dailyLimit": DAILY_LIMIT,
        "rewardedToday": daily,
        "remainingToday": max(0, DAILY_LIMIT - daily),
        "cooldownMinutes": COOLDOWN_MINUTES,
        "cooldownUntil": _iso(cooldown_until),
        "dadoBalance": balance,
        "dadoMax": int(DADO_MAX_BALANCE),
        "canStart": bool(can_start),
        "pending": {
            "id": str(pending["id"]),
            "expiresAt": _iso(pending["expires_at"]),
        } if pending else None,
    }


def start_rewarded_session(user_id: int) -> dict:
    uid = int(user_id)
    if not monetag_enabled():
        raise HTTPException(503, "Os anúncios recompensados ainda não estão configurados.")
    dado = get_dado_state(uid) or {}
    if int(dado.get("balance") or 0) >= DADO_MAX_BALANCE:
        raise HTTPException(409, "Seu saldo de Dados já está cheio.")

    now = datetime.now(timezone.utc)
    session_id = uuid4()
    expires = now + timedelta(minutes=SESSION_TTL_MINUTES)
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        if not cur.fetchone():
            raise HTTPException(404, "Conta Source não encontrada.")
        _expire_pending_locked(cur, uid)
        cur.execute(
            """
            SELECT id,expires_at
            FROM source_rewarded_ad_sessions
            WHERE user_id=%s AND status='pending'
            ORDER BY created_at DESC LIMIT 1
            """,
            (uid,),
        )
        pending = cur.fetchone()
        if pending:
            return {
                "id": str(pending["id"]),
                "ymid": str(pending["id"]),
                "expiresAt": _iso(pending["expires_at"]),
                "sdkUrl": _sdk_url(),
                "zoneId": _zone_id(),
                "sdkFunction": _sdk_function(),
                "requestVar": PLACEMENT,
                "reused": True,
            }

        daily = _daily_rewarded_count_locked(cur, uid)
        if daily >= DAILY_LIMIT:
            raise HTTPException(429, "Você já atingiu o limite de anúncios recompensados de hoje.")
        last = _last_rewarded_at_locked(cur, uid)
        if last and last + timedelta(minutes=COOLDOWN_MINUTES) > now:
            raise HTTPException(429, "Aguarde o intervalo antes de assistir outro anúncio.")

        cur.execute(
            """
            INSERT INTO source_rewarded_ad_sessions
                (id,user_id,provider,placement,status,reward_dados,zone_id,created_at,expires_at)
            VALUES (%s,%s,%s,%s,'pending',%s,%s,NOW(),%s)
            """,
            (session_id, uid, PROVIDER, PLACEMENT, REWARD_DADOS, _zone_id(), expires),
        )

    return {
        "id": str(session_id),
        "ymid": str(session_id),
        "expiresAt": expires.isoformat(),
        "sdkUrl": _sdk_url(),
        "zoneId": _zone_id(),
        "sdkFunction": _sdk_function(),
        "requestVar": PLACEMENT,
        "reused": False,
    }


def session_status(user_id: int, session_id: UUID) -> dict:
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        _expire_pending_locked(cur, int(user_id))
        cur.execute(
            """
            SELECT id,status,rewarded_dados,created_at,expires_at,confirmed_at,rewarded_at,
                   reward_event_type,event_type,estimated_price
            FROM source_rewarded_ad_sessions
            WHERE id=%s AND user_id=%s
            """,
            (session_id, int(user_id)),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Sessão de anúncio não encontrada.")
    return {
        "id": str(row["id"]),
        "status": str(row["status"]),
        "rewardedDados": int(row.get("rewarded_dados") or 0),
        "createdAt": _iso(row.get("created_at")),
        "expiresAt": _iso(row.get("expires_at")),
        "confirmedAt": _iso(row.get("confirmed_at")),
        "rewardedAt": _iso(row.get("rewarded_at")),
        "eventType": row.get("event_type"),
        "rewardEventType": row.get("reward_event_type"),
        "estimatedPrice": str(row.get("estimated_price") or "0"),
    }


def process_postback(
    *,
    secret: str,
    ymid: str,
    event_type: str,
    reward_event_type: str,
    zone_id: str,
    sub_zone_id: str | None,
    request_var: str,
    estimated_price: str | None,
    telegram_id: str | None,
) -> dict:
    expected = _postback_secret()
    if not expected or not hmac.compare_digest(str(secret or ""), expected):
        raise HTTPException(403, "Postback inválido.")
    try:
        session_id = UUID(str(ymid))
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "ymid inválido.") from exc

    event = str(event_type or "").strip().lower()
    value = str(reward_event_type or "").strip().lower()
    source = str(request_var or "").strip()
    zone = str(zone_id or "").strip()
    if zone != _zone_id() or source != PLACEMENT:
        raise HTTPException(400, "Postback não corresponde a esta integração.")
    if event not in {"impression", "click"}:
        raise HTTPException(400, "Evento Monetag desconhecido.")

    try:
        price = Decimal(str(estimated_price or "0"))
    except (InvalidOperation, ValueError):
        price = Decimal("0")

    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id,user_id,status,expires_at,reward_dados
            FROM source_rewarded_ad_sessions
            WHERE id=%s
            FOR UPDATE
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Sessão de anúncio não encontrada.")

        status = str(row.get("status") or "")
        if status == "rewarded":
            return {"ok": True, "duplicate": True, "rewarded": True}
        if status in {"expired", "cancelled"}:
            return {"ok": True, "duplicate": True, "rewarded": False}
        if row.get("expires_at") and row["expires_at"] <= datetime.now(timezone.utc):
            cur.execute(
                "UPDATE source_rewarded_ad_sessions SET status='expired' WHERE id=%s",
                (session_id,),
            )
            return {"ok": True, "rewarded": False, "expired": True}

        common = (
            zone,
            str(sub_zone_id or "")[:80] or None,
            event,
            value,
            price,
            str(telegram_id or "")[:80] or None,
            session_id,
        )
        if value != "valued" or event != "impression":
            cur.execute(
                """
                UPDATE source_rewarded_ad_sessions
                SET zone_id=%s,sub_zone_id=%s,event_type=%s,reward_event_type=%s,
                    estimated_price=%s,telegram_id=%s,confirmed_at=NOW(),
                    status=CASE WHEN %s='non_valued' THEN 'non_valued' ELSE status END
                WHERE id=%s
                """,
                (*common[:-1], value, session_id),
            )
            return {"ok": True, "rewarded": False}

        uid = int(row["user_id"])
        cur.execute("SELECT dado_balance FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(404, "Conta Source não encontrada.")
        old_balance = max(0, int(user.get("dado_balance") or 0))
        new_balance = min(DADO_MAX_BALANCE, old_balance + int(row.get("reward_dados") or REWARD_DADOS))
        applied = max(0, new_balance - old_balance)
        cur.execute(
            "UPDATE users SET dado_balance=%s,updated_at=NOW() WHERE user_id=%s",
            (new_balance, uid),
        )
        cur.execute(
            """
            UPDATE source_rewarded_ad_sessions
            SET status='rewarded',rewarded_dados=%s,zone_id=%s,sub_zone_id=%s,
                event_type=%s,reward_event_type=%s,estimated_price=%s,telegram_id=%s,
                confirmed_at=NOW(),rewarded_at=NOW()
            WHERE id=%s
            """,
            (applied, *common),
        )
        return {
            "ok": True,
            "rewarded": True,
            "rewardedDados": applied,
            "dadoBalance": new_balance,
        }


def build_monetization_router() -> APIRouter:
    router = APIRouter(tags=["source-monetization"])

    @router.get(API_PREFIX + "/monetization/rewarded/status")
    def status(uid: int = Depends(_actor)):
        return JSONResponse(rewarded_status(uid), headers={"Cache-Control": "no-store"})

    @router.post(API_PREFIX + "/monetization/rewarded/start")
    def start(uid: int = Depends(_actor)):
        return JSONResponse(start_rewarded_session(uid), headers={"Cache-Control": "no-store"})

    @router.get(API_PREFIX + "/monetization/rewarded/{session_id}")
    def result(session_id: UUID, uid: int = Depends(_actor)):
        return JSONResponse(session_status(uid, session_id), headers={"Cache-Control": "no-store"})

    @router.get("/api/monetization/monetag/postback")
    async def postback(
        request: Request,
        secret: str = Query(default=""),
        ymid: str = Query(default=""),
        event: str = Query(default=""),
        value: str = Query(default=""),
        zone: str = Query(default=""),
        sub: str = Query(default=""),
        price: str = Query(default="0"),
        source: str = Query(default=""),
        telegram_id: str = Query(default=""),
    ):
        host = str(request.client.host if request.client else "unknown")
        if not await rate_limiter.allow(f"monetag-postback:{host}", 900, 60):
            raise HTTPException(429, "Muitas tentativas.")
        return process_postback(
            secret=secret,
            ymid=ymid,
            event_type=event,
            reward_event_type=value,
            zone_id=zone,
            sub_zone_id=sub,
            request_var=source,
            estimated_price=price,
            telegram_id=telegram_id,
        )

    return router
