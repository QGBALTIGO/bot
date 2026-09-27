"""Rewarded Monetag ads for the Source Telegram MiniApp.

The browser can start an ad and display progress, but it never grants currency.
Rewards are credited only after a Monetag server-side postback confirms a
monetized (valued) impression. Each ad action uses a unique ymid/session UUID.
"""

from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from psycopg.rows import dict_row

from database import DADO_MAX_BALANCE, get_dado_state
from database_core import pool
from utils.runtime_guard import rate_limiter
from webapp_routes.aninexus_compat import API_PREFIX, _require_user

PROVIDER = "monetag"
PLACEMENT = "source_rewarded_bonus"
DEFAULT_SDK_URL = "https://libtl.com/sdk.js"
SESSION_TTL_MINUTES = 10


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _sdk_url() -> str:
    raw = str(os.getenv("MONETAG_SDK_URL") or DEFAULT_SDK_URL).strip()
    return raw if raw.startswith("https://") else ""


def _zone_id() -> str:
    raw = str(os.getenv("MONETAG_ZONE_ID") or "").strip()
    return raw if raw.isdigit() and int(raw) > 0 else ""


def _postback_secret() -> str:
    return str(os.getenv("MONETAG_POSTBACK_SECRET") or "").strip()


def daily_limit() -> int:
    return _bounded_int("MONETAG_DAILY_REWARD_LIMIT", 3, 1, 10)


def cooldown_minutes() -> int:
    return _bounded_int("MONETAG_REWARD_COOLDOWN_MINUTES", 15, 0, 360)


def coin_reward() -> int:
    return _bounded_int("MONETAG_REWARD_COINS", 2, 1, 500)


def dado_reward() -> int:
    return _bounded_int("MONETAG_REWARD_DADOS", 1, 1, 3)


def monetag_enabled() -> bool:
    return bool(_sdk_url() and _zone_id() and len(_postback_secret()) >= 20)


def _sdk_function() -> str:
    return f"show_{_zone_id()}" if _zone_id() else ""


def _iso(value):
    return value.isoformat() if value else None


class RewardStartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rewardType: str = "dado"


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


def _normalize_reward_type(value: str) -> str:
    reward_type = str(value or "").strip().lower()
    if reward_type not in {"dado", "coins"}:
        raise HTTPException(422, "Escolha uma recompensa válida.")
    return reward_type


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


def _pending_locked(cur, user_id: int):
    cur.execute(
        """
        SELECT id,reward_type,reward_amount,created_at,expires_at
        FROM source_rewarded_ad_sessions
        WHERE user_id=%s AND status='pending'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (int(user_id),),
    )
    return cur.fetchone()


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
        pending = _pending_locked(cur, uid)

    cooldown_until = (
        last + timedelta(minutes=cooldown_minutes())
        if last and cooldown_minutes() > 0
        else None
    )
    balance = int(dado.get("balance") or 0)
    base_available = (
        monetag_enabled()
        and daily < daily_limit()
        and (cooldown_until is None or cooldown_until <= now)
        and not pending
    )
    return {
        "enabled": monetag_enabled(),
        "provider": PROVIDER,
        "sdkUrl": _sdk_url() if monetag_enabled() else None,
        "zoneId": _zone_id() if monetag_enabled() else None,
        "sdkFunction": _sdk_function() if monetag_enabled() else None,
        "requestVar": PLACEMENT,
        "rewards": {"coins": coin_reward(), "dado": dado_reward()},
        "dailyLimit": daily_limit(),
        "rewardedToday": daily,
        "remainingToday": max(0, daily_limit() - daily),
        "cooldownMinutes": cooldown_minutes(),
        "cooldownUntil": _iso(cooldown_until),
        "dadoBalance": balance,
        "dadoMax": int(DADO_MAX_BALANCE),
        "canStart": bool(base_available),
        "canStartCoins": bool(base_available),
        "canStartDado": bool(base_available and balance < DADO_MAX_BALANCE),
        "pending": {
            "id": str(pending["id"]),
            "rewardType": str(pending["reward_type"]),
            "rewardAmount": int(pending["reward_amount"]),
            "expiresAt": _iso(pending["expires_at"]),
        } if pending else None,
    }


def start_rewarded_session(user_id: int, reward_type: str) -> dict:
    uid = int(user_id)
    reward_type = _normalize_reward_type(reward_type)
    if not monetag_enabled():
        raise HTTPException(503, "Os anúncios recompensados ainda não estão configurados.")

    dado = get_dado_state(uid) or {}
    if reward_type == "dado" and int(dado.get("balance") or 0) >= DADO_MAX_BALANCE:
        raise HTTPException(
            409,
            "Seu saldo de Dados está cheio. Escolha Coins para não desperdiçar o anúncio.",
        )

    now = datetime.now(timezone.utc)
    session_id = uuid4()
    expires = now + timedelta(minutes=SESSION_TTL_MINUTES)
    intended_amount = dado_reward() if reward_type == "dado" else coin_reward()

    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        if not cur.fetchone():
            raise HTTPException(404, "Conta Source não encontrada.")

        _expire_pending_locked(cur, uid)
        pending = _pending_locked(cur, uid)
        if pending:
            return {
                "id": str(pending["id"]),
                "ymid": str(pending["id"]),
                "expiresAt": _iso(pending["expires_at"]),
                "sdkUrl": _sdk_url(),
                "zoneId": _zone_id(),
                "sdkFunction": _sdk_function(),
                "requestVar": PLACEMENT,
                "rewardType": str(pending["reward_type"]),
                "rewardAmount": int(pending["reward_amount"]),
                "reused": True,
            }

        daily = _daily_rewarded_count_locked(cur, uid)
        if daily >= daily_limit():
            raise HTTPException(429, "Você já atingiu o limite de anúncios recompensados de hoje.")

        last = _last_rewarded_at_locked(cur, uid)
        if (
            last
            and cooldown_minutes() > 0
            and last + timedelta(minutes=cooldown_minutes()) > now
        ):
            raise HTTPException(429, "Aguarde o intervalo antes de assistir outro anúncio.")

        cur.execute(
            """
            INSERT INTO source_rewarded_ad_sessions
                (id,user_id,provider,placement,status,reward_type,reward_amount,
                 reward_dados,reward_coins,zone_id,created_at,expires_at)
            VALUES (%s,%s,%s,%s,'pending',%s,%s,%s,%s,%s,NOW(),%s)
            """,
            (
                session_id,
                uid,
                PROVIDER,
                PLACEMENT,
                reward_type,
                intended_amount,
                intended_amount if reward_type == "dado" else 0,
                intended_amount if reward_type == "coins" else 0,
                _zone_id(),
                expires,
            ),
        )

    return {
        "id": str(session_id),
        "ymid": str(session_id),
        "expiresAt": expires.isoformat(),
        "sdkUrl": _sdk_url(),
        "zoneId": _zone_id(),
        "sdkFunction": _sdk_function(),
        "requestVar": PLACEMENT,
        "rewardType": reward_type,
        "rewardAmount": intended_amount,
        "reused": False,
    }


def session_status(user_id: int, session_id: UUID) -> dict:
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        _expire_pending_locked(cur, int(user_id))
        cur.execute(
            """
            SELECT id,status,reward_type,reward_amount,rewarded_dados,rewarded_coins,
                   created_at,expires_at,confirmed_at,rewarded_at,reward_event_type,
                   event_type,estimated_price
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
        "rewardType": str(row.get("reward_type") or "dado"),
        "rewardAmount": int(row.get("reward_amount") or 0),
        "rewardedDados": int(row.get("rewarded_dados") or 0),
        "rewardedCoins": int(row.get("rewarded_coins") or 0),
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
        price = max(Decimal("0"), Decimal(str(estimated_price or "0")))
    except (InvalidOperation, ValueError):
        price = Decimal("0")

    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id,user_id,status,expires_at,reward_type,reward_amount
            FROM source_rewarded_ad_sessions
            WHERE id=%s
            FOR UPDATE
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Sessão de anúncio não encontrada.")

        uid = int(row["user_id"])
        telegram = str(telegram_id or "").strip()
        if telegram and (not telegram.isdigit() or int(telegram) != uid):
            raise HTTPException(403, "Telegram ID do postback não corresponde à sessão.")

        status = str(row.get("status") or "")
        if status == "rewarded":
            return {"ok": True, "duplicate": True, "rewarded": True}
        if status in {"expired", "cancelled", "non_valued"}:
            return {"ok": True, "duplicate": True, "rewarded": False}
        if row.get("expires_at") and row["expires_at"] <= datetime.now(timezone.utc):
            cur.execute(
                "UPDATE source_rewarded_ad_sessions SET status='expired' WHERE id=%s",
                (session_id,),
            )
            return {"ok": True, "rewarded": False, "expired": True}

        if value != "valued" or event != "impression":
            cur.execute(
                """
                UPDATE source_rewarded_ad_sessions
                SET zone_id=%s,sub_zone_id=%s,event_type=%s,reward_event_type=%s,
                    estimated_price=%s,telegram_id=%s,confirmed_at=NOW(),
                    status=CASE WHEN %s='non_valued' THEN 'non_valued' ELSE status END
                WHERE id=%s
                """,
                (
                    zone,
                    str(sub_zone_id or "")[:80] or None,
                    event,
                    value,
                    price,
                    str(telegram_id or "")[:80] or None,
                    value,
                    session_id,
                ),
            )
            return {"ok": True, "rewarded": False}

        cur.execute("SELECT coins,dado_balance FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(404, "Conta Source não encontrada.")

        intended_type = str(row.get("reward_type") or "dado")
        intended_amount = max(1, int(row.get("reward_amount") or 1))
        rewarded_dados = 0
        rewarded_coins = 0
        actual_type = intended_type

        if intended_type == "coins":
            rewarded_coins = intended_amount
        else:
            old_dado = max(0, int(user.get("dado_balance") or 0))
            new_dado = min(DADO_MAX_BALANCE, old_dado + intended_amount)
            rewarded_dados = max(0, new_dado - old_dado)
            if rewarded_dados <= 0:
                actual_type = "coins"
                rewarded_coins = coin_reward()

        new_coin_balance = int(user.get("coins") or 0) + rewarded_coins
        old_dado_balance = max(0, int(user.get("dado_balance") or 0))
        new_dado_balance = min(DADO_MAX_BALANCE, old_dado_balance + rewarded_dados)
        cur.execute(
            """
            UPDATE users
            SET coins=%s,dado_balance=%s,updated_at=NOW()
            WHERE user_id=%s
            """,
            (new_coin_balance, new_dado_balance, uid),
        )

        if rewarded_coins:
            cur.execute(
                """
                INSERT INTO shop_transactions
                    (user_id,type,amount,balance_after,reference_id,metadata)
                VALUES (%s,'monetag_rewarded_ad',%s,%s,NULL,%s::jsonb)
                """,
                (
                    uid,
                    rewarded_coins,
                    new_coin_balance,
                    json.dumps(
                        {
                            "provider": PROVIDER,
                            "session_id": str(session_id),
                            "intended_reward": intended_type,
                            "actual_reward": actual_type,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )

        cur.execute(
            """
            UPDATE source_rewarded_ad_sessions
            SET status='rewarded',rewarded_dados=%s,rewarded_coins=%s,
                zone_id=%s,sub_zone_id=%s,event_type=%s,reward_event_type=%s,
                estimated_price=%s,telegram_id=%s,confirmed_at=NOW(),rewarded_at=NOW()
            WHERE id=%s
            """,
            (
                rewarded_dados,
                rewarded_coins,
                zone,
                str(sub_zone_id or "")[:80] or None,
                event,
                value,
                price,
                str(telegram_id or "")[:80] or None,
                session_id,
            ),
        )
        return {
            "ok": True,
            "rewarded": True,
            "rewardType": actual_type,
            "rewardedDados": rewarded_dados,
            "rewardedCoins": rewarded_coins,
            "dadoBalance": new_dado_balance,
            "coinBalance": new_coin_balance,
        }


def build_monetization_router() -> APIRouter:
    router = APIRouter(tags=["source-monetization"])

    @router.get(API_PREFIX + "/monetization/rewarded/status")
    def status(uid: int = Depends(_actor)):
        return JSONResponse(rewarded_status(uid), headers={"Cache-Control": "no-store"})

    @router.post(API_PREFIX + "/monetization/rewarded/start")
    def start(payload: RewardStartBody, uid: int = Depends(_actor)):
        return JSONResponse(
            start_rewarded_session(uid, payload.rewardType),
            headers={"Cache-Control": "no-store"},
        )

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
