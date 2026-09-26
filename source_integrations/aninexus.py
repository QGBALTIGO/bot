"""Secure Source <-> AniNexus account bridge.

The browser never receives Source credentials. A logged-in Source user creates a
short-lived, single-use token. AniNexus consumes it server-to-server and receives
an opaque link id plus a public-safe Source profile snapshot. Re-linking rotates
that opaque id, invalidating stale AniNexus links.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from psycopg.rows import dict_row

from cards_service import build_cards_final_data
from database import DADO_MAX_BALANCE, get_level_progress_values, get_progress_row
from database_core import pool
from database_profile import get_profile_settings
from utils.runtime_guard import rate_limiter
from webapp_routes.aninexus_compat import API_PREFIX, _require_user


TOKEN_TTL_MINUTES = max(3, min(30, int(os.getenv("ANINEXUS_LINK_TTL_MINUTES", "10"))))
LINK_REWARD_COINS = 50
LINK_REWARD_DADOS = 1
ANINEXUS_ORIGIN = str(os.getenv("ANINEXUS_PUBLIC_ORIGIN") or "https://aninexus.com.br").rstrip("/")
if not ANINEXUS_ORIGIN.startswith("https://"):
    raise RuntimeError("ANINEXUS_PUBLIC_ORIGIN precisa usar HTTPS.")
def _subject_key() -> bytes:
    material = str(os.getenv("ANINEXUS_LINK_SUBJECT_SECRET") or os.getenv("BOT_TOKEN") or "").encode("utf-8")
    if len(material) < 16:
        raise RuntimeError("BOT_TOKEN ou ANINEXUS_LINK_SUBJECT_SECRET precisa estar configurado.")
    return hashlib.sha256(b"source-aninexus-subject-v1:" + material).digest()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _subject(user_id: int) -> str:
    digest = hmac.new(_subject_key(), str(int(user_id)).encode("ascii"), hashlib.sha256).hexdigest()
    return "src_" + digest


def _safe_username(value) -> str | None:
    raw = str(value or "").strip().lstrip("@")
    return raw[:64] or None


def _favorite(character_id: int | None):
    if not character_id:
        return None
    try:
        characters = build_cards_final_data().get("characters_by_id") or {}
        meta = characters.get(int(character_id)) or characters.get(str(int(character_id))) or {}
    except Exception:
        meta = {}
    if not meta:
        return None
    image = str(meta.get("image") or meta.get("img_url") or "").strip()
    return {
        "id": int(character_id),
        "name": str(meta.get("name") or f"Personagem {character_id}")[:180],
        "work": str(meta.get("anime") or meta.get("subcategory") or "")[:240],
        "image": image[:2000] if image.startswith("https://") else None,
    }


def _reward_payload(row: dict | None, *, linked: bool) -> dict:
    row = row or {}
    claimed_at = row.get("reward_claimed_at")
    return {
        "coins": LINK_REWARD_COINS,
        "dados": LINK_REWARD_DADOS,
        "claimed": bool(claimed_at),
        "available": bool(linked and not claimed_at),
        "claimedAt": claimed_at.isoformat() if claimed_at else None,
        "coinsGranted": int(row.get("reward_coins") or 0),
        "dadosGranted": int(row.get("reward_dados") or 0),
    }


def _grant_link_reward_locked(cur, user_id: int) -> dict:
    uid = int(user_id)
    subject = _subject(uid)
    cur.execute(
        """
        SELECT reward_claimed_at,reward_coins,reward_dados
        FROM source_aninexus_links
        WHERE user_id=%s
        FOR UPDATE
        """,
        (uid,),
    )
    link = dict(cur.fetchone() or {})
    if not link:
        raise HTTPException(404, "Vínculo AniNexus não encontrado.")

    cur.execute(
        """
        SELECT claimed_at,reward_coins,reward_dados
        FROM source_aninexus_reward_claims
        WHERE source_subject=%s
        """,
        (subject,),
    )
    durable = dict(cur.fetchone() or {})
    if durable:
        cur.execute(
            """
            UPDATE source_aninexus_links
            SET reward_claimed_at=COALESCE(reward_claimed_at,%s),
                reward_coins=GREATEST(reward_coins,%s),
                reward_dados=GREATEST(reward_dados,%s),
                updated_at=NOW()
            WHERE user_id=%s
            RETURNING reward_claimed_at,reward_coins,reward_dados
            """,
            (
                durable["claimed_at"],
                int(durable.get("reward_coins") or 0),
                int(durable.get("reward_dados") or 0),
                uid,
            ),
        )
        restored = dict(cur.fetchone() or {})
        return {**_reward_payload(restored, linked=True), "newlyGranted": False}

    if link.get("reward_claimed_at"):
        cur.execute(
            """
            INSERT INTO source_aninexus_reward_claims
                (source_subject,reward_coins,reward_dados,claimed_at)
            VALUES(%s,%s,%s,%s)
            ON CONFLICT(source_subject) DO NOTHING
            """,
            (
                subject,
                int(link.get("reward_coins") or 0),
                int(link.get("reward_dados") or 0),
                link["reward_claimed_at"],
            ),
        )
        return {**_reward_payload(link, linked=True), "newlyGranted": False}

    cur.execute(
        "SELECT coins,dado_balance FROM users WHERE user_id=%s FOR UPDATE",
        (uid,),
    )
    user = dict(cur.fetchone() or {})
    if not user:
        raise HTTPException(404, "Conta Source não encontrada.")

    old_dado = max(0, int(user.get("dado_balance") or 0))
    new_dado = min(DADO_MAX_BALANCE, old_dado + LINK_REWARD_DADOS)
    dados_applied = max(0, new_dado - old_dado)
    cur.execute(
        """
        UPDATE users
        SET coins=COALESCE(coins,0)+%s,
            dado_balance=%s,
            updated_at=NOW()
        WHERE user_id=%s
        RETURNING coins,dado_balance
        """,
        (LINK_REWARD_COINS, new_dado, uid),
    )
    balances = dict(cur.fetchone() or {})
    cur.execute(
        """
        UPDATE source_aninexus_links
        SET reward_claimed_at=NOW(),
            reward_coins=%s,
            reward_dados=%s,
            updated_at=NOW()
        WHERE user_id=%s
        RETURNING reward_claimed_at,reward_coins,reward_dados
        """,
        (LINK_REWARD_COINS, dados_applied, uid),
    )
    rewarded = dict(cur.fetchone() or {})
    cur.execute(
        """
        INSERT INTO source_aninexus_reward_claims
            (source_subject,reward_coins,reward_dados,claimed_at)
        VALUES(%s,%s,%s,%s)
        ON CONFLICT(source_subject) DO NOTHING
        """,
        (
            subject,
            LINK_REWARD_COINS,
            dados_applied,
            rewarded["reward_claimed_at"],
        ),
    )
    cur.execute(
        """
        INSERT INTO shop_transactions
            (user_id,type,amount,balance_after,metadata)
        VALUES (%s,'aninexus_link_reward',%s,%s,%s::jsonb)
        """,
        (
            uid,
            LINK_REWARD_COINS,
            int(balances.get("coins") or 0),
            json.dumps(
                {
                    "integration": "aninexus",
                    "coins": LINK_REWARD_COINS,
                    "dados_requested": LINK_REWARD_DADOS,
                    "dados_applied": dados_applied,
                },
                ensure_ascii=False,
            ),
        ),
    )
    return {
        **_reward_payload(rewarded, linked=True),
        "newlyGranted": True,
        "balance": int(balances.get("coins") or 0),
        "dadoBalance": int(balances.get("dado_balance") or 0),
    }


def _queue_reward_notice(user_id: int, reward: dict) -> None:
    if not reward.get("newlyGranted"):
        return
    try:
        from utils.telegram_outbox import enqueue_text

        dados = int(reward.get("dadosGranted") or 0)
        dado_line = (
            f"🎲 <b>+{dados} Dado</b>"
            if dados > 0
            else f"🎲 <b>Dado:</b> seu saldo já estava no limite de {DADO_MAX_BALANCE}"
        )
        enqueue_text(
            dedupe_key=f"aninexus-link-reward:{int(user_id)}",
            chat_id=int(user_id),
            text=(
                "✅ <b>Source AniNexus conectado!</b>\n\n"
                "Sua conta Source foi vinculada com sucesso ao AniNexus.\n\n"
                "🎁 <b>Recompensa de integração</b>\n"
                f"🪙 <b>+{int(reward.get('coinsGranted') or 0)} Coins</b>\n"
                f"{dado_line}\n"
                "🏷 <b>Badge Source AniNexus liberado</b>\n\n"
                "Use /aninexus para consultar a conexão, sincronizar ou gerenciar o vínculo."
            ),
        )
    except Exception:
        # A entrega é best-effort e desacoplada da transação econômica.
        # O worker/outbox não pode desfazer uma recompensa já confirmada.
        pass


def claim_link_reward(user_id: int) -> dict:
    uid = int(user_id)
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT revoked_at FROM source_aninexus_links WHERE user_id=%s FOR UPDATE",
            (uid,),
        )
        row = cur.fetchone()
        if not row or row.get("revoked_at") is not None:
            raise HTTPException(409, "Conecte sua conta ao AniNexus antes de resgatar a recompensa.")
        reward = _grant_link_reward_locked(cur, uid)
    _queue_reward_notice(uid, reward)
    return reward


def profile_snapshot(user_id: int) -> dict:
    uid = int(user_id)
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT u.user_id,u.username,u.full_name,u.coins,
                   COALESCE(c.unique_count,0)::bigint AS unique_count,
                   COALESCE(c.total_copies,0)::bigint AS total_copies
            FROM users u
            LEFT JOIN LATERAL (
                SELECT COUNT(*) FILTER (WHERE quantity>0) AS unique_count,
                       COALESCE(SUM(quantity) FILTER (WHERE quantity>0),0) AS total_copies
                FROM user_card_collection
                WHERE user_id=u.user_id
            ) c ON TRUE
            WHERE u.user_id=%s
            """,
            (uid,),
        )
        user = cur.fetchone()
    if not user:
        raise HTTPException(404, "Conta Source não encontrada.")

    settings = get_profile_settings(uid) or {}
    progress = get_progress_row(uid) or {}
    unique_count = int(user.get("unique_count") or 0)
    total_copies = int(user.get("total_copies") or 0)
    total_available = len(build_cards_final_data().get("characters_by_id") or {})
    xp_total = int(progress.get("xp") or progress.get("total_xp") or 0)
    level_progress = get_level_progress_values(xp_total)
    nickname = str(settings.get("nickname") or "").strip()
    full_name = str(user.get("full_name") or "").strip()
    username = _safe_username(user.get("username"))
    return {
        "displayName": (nickname or full_name or (f"@{username}" if username else "Usuário Source"))[:120],
        "username": username,
        "favorite": _favorite(settings.get("favorite_character_id")),
        "stats": {
            "level": int(level_progress.get("level") or 1),
            "xp": xp_total,
            "xpCurrent": int(level_progress.get("xp_current") or 0),
            "xpNeeded": int(level_progress.get("xp_needed") or 0),
            "coins": int(user.get("coins") or 0),
            "uniqueCharacters": unique_count,
            "totalCharacters": total_copies,
            "totalAvailableCharacters": total_available,
            "collectionPercent": round((unique_count / total_available) * 100, 1) if total_available else 0.0,
        },
        "public": not bool(settings.get("private_profile")),
        "integration": link_status(uid),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def create_link_token(user_id: int) -> dict:
    uid = int(user_id)
    token = secrets.token_urlsafe(32)
    token_hash = _digest(token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)
    with pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (uid,))
        if not cur.fetchone():
            raise HTTPException(404, "Conta Source não encontrada.")
        cur.execute(
            "DELETE FROM source_aninexus_link_tokens WHERE user_id=%s AND consumed_at IS NULL",
            (uid,),
        )
        cur.execute(
            "DELETE FROM source_aninexus_link_tokens WHERE expires_at < NOW() - INTERVAL '1 day' OR consumed_at < NOW() - INTERVAL '1 day'"
        )
        cur.execute(
            "INSERT INTO source_aninexus_link_tokens(token_hash,user_id,expires_at) VALUES(%s,%s,%s)",
            (token_hash, uid, expires_at),
        )
    return {
        # Fragment is not sent in HTTP requests, so the one-time token avoids access logs/referrers.
        "url": f"{ANINEXUS_ORIGIN}/conectar-source#source_token={token}",
        "expiresAt": expires_at.isoformat(),
        "expiresInSeconds": TOKEN_TTL_MINUTES * 60,
    }


def consume_link_token(token: str) -> dict:
    token_hash = _digest(token)
    link_id = uuid4()
    revoke_token = secrets.token_urlsafe(32)
    revoke_hash = _digest(revoke_token)
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT user_id FROM source_aninexus_link_tokens
            WHERE token_hash=%s AND consumed_at IS NULL AND expires_at>NOW()
            FOR UPDATE
            """,
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(410, "Este link expirou ou já foi usado. Gere outro no Source.")
        uid = int(row["user_id"])
        cur.execute(
            "UPDATE source_aninexus_link_tokens SET consumed_at=NOW() WHERE token_hash=%s",
            (token_hash,),
        )
        # Rotating link_id invalidates any previous AniNexus account link for this Source user.
        cur.execute(
            """
            INSERT INTO source_aninexus_links(user_id,link_id,revoke_hash,linked_at,updated_at,revoked_at)
            VALUES(%s,%s,%s,NOW(),NOW(),NULL)
            ON CONFLICT(user_id) DO UPDATE SET
              link_id=EXCLUDED.link_id,revoke_hash=EXCLUDED.revoke_hash,
              linked_at=NOW(),updated_at=NOW(),revoked_at=NULL
            """,
            (uid, link_id, revoke_hash),
        )
        reward = _grant_link_reward_locked(cur, uid)
    _queue_reward_notice(uid, reward)
    return {
        "linkId": str(link_id),
        "sourceSubject": _subject(uid),
        "revokeToken": revoke_token,
        "reward": reward,
        "profile": profile_snapshot(uid),
    }


def link_status(user_id: int) -> dict:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT linked_at,updated_at,reward_claimed_at,reward_coins,reward_dados
            FROM source_aninexus_links
            WHERE user_id=%s AND revoked_at IS NULL
            """,
            (int(user_id),),
        )
        row = cur.fetchone()
    return {
        "linked": bool(row),
        "linkedAt": row["linked_at"].isoformat() if row else None,
        "updatedAt": row["updated_at"].isoformat() if row else None,
        "reward": _reward_payload(dict(row or {}), linked=bool(row)),
        "badge": "Source AniNexus" if row else None,
    }


def revoke_for_user(user_id: int) -> bool:
    uid = int(user_id)
    with pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "DELETE FROM source_aninexus_link_tokens WHERE user_id=%s AND consumed_at IS NULL",
            (uid,),
        )
        pending_removed = cur.rowcount > 0
        cur.execute(
            "UPDATE source_aninexus_links SET revoked_at=NOW(),updated_at=NOW() WHERE user_id=%s AND revoked_at IS NULL RETURNING 1",
            (uid,),
        )
        return bool(cur.fetchone()) or pending_removed


def snapshot_for_link(link_id: UUID) -> dict:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT user_id FROM source_aninexus_links WHERE link_id=%s AND revoked_at IS NULL",
            (link_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Vínculo Source não encontrado.")
    return profile_snapshot(int(row["user_id"]))


def revoke_link(link_id: UUID, revoke_token: str) -> bool:
    revoke_hash = _digest(revoke_token)
    with pool.connection() as conn, conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE source_aninexus_links
            SET revoked_at=NOW(),updated_at=NOW()
            WHERE link_id=%s AND revoke_hash=%s AND revoked_at IS NULL
            RETURNING user_id
            """,
            (link_id, revoke_hash),
        )
        row = cur.fetchone()
        if not row:
            return False
        cur.execute(
            "DELETE FROM source_aninexus_link_tokens WHERE user_id=%s AND consumed_at IS NULL",
            (int(row["user_id"]),),
        )
        return True


class ConsumeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=256)


class RevokeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    linkId: UUID
    revokeToken: str = Field(min_length=20, max_length=256)


async def _actor(request: Request, authorization: str = Header(default="")) -> int:
    try:
        uid = int(_require_user(authorization).get("id") or 0)
        if uid <= 0:
            raise PermissionError()
    except (PermissionError, ValueError) as exc:
        raise HTTPException(401, "Sessão expirada. Reabra a MiniApp.") from exc
    if not await rate_limiter.allow(f"aninexus-link-user:{uid}", 8, 60):
        raise HTTPException(429, "Aguarde um momento antes de gerar outro link.")
    return uid


async def _public_guard(request: Request, action: str, limit: int = 20):
    host = str(request.client.host if request.client else "unknown")
    if not await rate_limiter.allow(f"aninexus-bridge:{action}:{host}", limit, 60):
        raise HTTPException(429, "Muitas tentativas. Aguarde um momento.")


def build_aninexus_integration_router() -> APIRouter:
    router = APIRouter(tags=["source-aninexus"])

    @router.get(API_PREFIX + "/integrations/aninexus/status")
    def status(uid: int = Depends(_actor)):
        return JSONResponse(link_status(uid), headers={"Cache-Control": "no-store"})

    @router.post(API_PREFIX + "/integrations/aninexus/link-token")
    def link_token(uid: int = Depends(_actor)):
        return create_link_token(uid)

    @router.post(API_PREFIX + "/integrations/aninexus/reward")
    def reward(uid: int = Depends(_actor)):
        return claim_link_reward(uid)

    @router.delete(API_PREFIX + "/integrations/aninexus/link")
    def unlink(uid: int = Depends(_actor)):
        return {"ok": True, "unlinked": revoke_for_user(uid)}

    @router.post("/api/integrations/aninexus/consume")
    async def consume(payload: ConsumeBody, request: Request):
        # AniNexus is one server-side caller for many users; this IP bucket is
        # intentionally broader than the per-user Source token-generation limit.
        await _public_guard(request, "consume", 180)
        return consume_link_token(payload.token)

    @router.get("/api/integrations/aninexus/profile/{link_id}")
    async def profile(link_id: UUID, request: Request):
        await _public_guard(request, "profile", 900)
        return JSONResponse(snapshot_for_link(link_id), headers={"Cache-Control": "no-store"})

    @router.post("/api/integrations/aninexus/revoke")
    async def revoke(payload: RevokeBody, request: Request):
        await _public_guard(request, "revoke", 180)
        if not revoke_link(payload.linkId, payload.revokeToken):
            raise HTTPException(404, "Vínculo já removido ou inválido.")
        return {"ok": True}

    return router


def install(app) -> None:
    """Compatibility helper; production composes the built router explicitly."""
    app.include_router(build_aninexus_integration_router())
