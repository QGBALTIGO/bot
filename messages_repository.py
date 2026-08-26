from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from database import pool
from identity_repository import find_identity_by_nickname, get_identity, public_display_name
from wallet_tx import insert_ledger, lock_wallet, wallet_payload


MSG_MAX_LENGTH = 500


class MessageError(ValueError):
    def __init__(self, code: str, message: str, **extra: Any):
        self.code = code
        self.message = message
        self.extra = extra
        super().__init__(message)


def create_message_tables_v2() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS message_settings_v2 (
                    user_id BIGINT PRIMARY KEY,
                    allow_messages BOOLEAN NOT NULL DEFAULT TRUE,
                    allow_anonymous BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS message_blocks_v2 (
                    blocker_user_id BIGINT NOT NULL,
                    blocked_user_id BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (blocker_user_id, blocked_user_id),
                    CHECK (blocker_user_id <> blocked_user_id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_messages_v2 (
                    message_id BIGSERIAL PRIMARY KEY,
                    from_user_id BIGINT NOT NULL,
                    to_user_id BIGINT NOT NULL,
                    sender_nickname TEXT NOT NULL,
                    recipient_nickname TEXT NOT NULL,
                    message_text TEXT NOT NULL,
                    is_anonymous BOOLEAN NOT NULL DEFAULT FALSE,
                    charged_coins INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    failure_reason TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    delivered_at TIMESTAMPTZ,
                    failed_at TIMESTAMPTZ
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_messages_v2_to_created
                ON user_messages_v2 (to_user_id, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_messages_v2_from_created
                ON user_messages_v2 (from_user_id, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS message_reports_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    message_id BIGINT NOT NULL REFERENCES user_messages_v2(message_id) ON DELETE CASCADE,
                    reporter_user_id BIGINT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (message_id, reporter_user_id)
                )
                """
            )
            conn.commit()


def _ensure_settings(cur, user_id: int) -> dict[str, Any]:
    cur.execute(
        "INSERT INTO message_settings_v2 (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
        (int(user_id),),
    )
    cur.execute("SELECT * FROM message_settings_v2 WHERE user_id=%s FOR UPDATE", (int(user_id),))
    return dict(cur.fetchone() or {})


def get_message_settings(user_id: int) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            settings = _ensure_settings(cur, int(user_id))
            conn.commit()
            return {
                "allow_messages": bool(settings.get("allow_messages", True)),
                "allow_anonymous": bool(settings.get("allow_anonymous", True)),
            }


def update_message_settings(user_id: int, *, allow_messages=None, allow_anonymous=None) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            current = _ensure_settings(cur, int(user_id))
            messages = bool(current.get("allow_messages", True)) if allow_messages is None else bool(allow_messages)
            anonymous = bool(current.get("allow_anonymous", True)) if allow_anonymous is None else bool(allow_anonymous)
            cur.execute(
                """
                UPDATE message_settings_v2
                SET allow_messages=%s, allow_anonymous=%s, updated_at=NOW()
                WHERE user_id=%s RETURNING *
                """,
                (messages, anonymous, int(user_id)),
            )
            row = dict(cur.fetchone() or {})
            conn.commit()
            return {"allow_messages": bool(row.get("allow_messages")), "allow_anonymous": bool(row.get("allow_anonymous"))}


def set_message_block(blocker_user_id: int, blocked_user_id: int, blocked: bool) -> None:
    a, b = int(blocker_user_id), int(blocked_user_id)
    if a == b:
        raise MessageError("self_block", "Você não pode bloquear a si mesmo.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if blocked:
                cur.execute(
                    "INSERT INTO message_blocks_v2 (blocker_user_id,blocked_user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (a, b),
                )
            else:
                cur.execute(
                    "DELETE FROM message_blocks_v2 WHERE blocker_user_id=%s AND blocked_user_id=%s",
                    (a, b),
                )
            conn.commit()


def list_blocks(user_id: int) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT b.blocked_user_id,
                       COALESCE(NULLIF(i.nickname,''), NULLIF(i.telegram_full_name,''), '@'||NULLIF(i.telegram_username,''), 'Jogador') AS display_name
                FROM message_blocks_v2 b
                LEFT JOIN user_identity_v2 i ON i.user_id=b.blocked_user_id
                WHERE b.blocker_user_id=%s ORDER BY b.created_at DESC
                """,
                (int(user_id),),
            )
            return [dict(row) for row in (cur.fetchall() or [])]


def prepare_message(
    from_user_id: int,
    target_nickname: str,
    text: str,
    *,
    is_anonymous: bool,
    anon_cost: int,
    normal_cooldown_seconds: int,
    anonymous_cooldown_seconds: int,
) -> dict[str, Any]:
    sender_id = int(from_user_id)
    text = str(text or "").strip()
    if not text:
        raise MessageError("empty_message", "A mensagem está vazia.")
    if len(text) > MSG_MAX_LENGTH:
        raise MessageError("message_too_long", f"A mensagem pode ter no máximo {MSG_MAX_LENGTH} caracteres.")

    sender_identity = get_identity(sender_id)
    sender_nickname = str(sender_identity.get("nickname") or "").strip()
    if not sender_nickname:
        raise MessageError("sender_no_nickname", "Defina um nickname no /perfil antes de usar mensagens.")
    target = find_identity_by_nickname(str(target_nickname or ""))
    if not target:
        raise MessageError("target_not_found", "Nickname não encontrado.")
    target_id = int(target["user_id"])
    if target_id == sender_id:
        raise MessageError("cannot_message_self", "Você não pode enviar mensagem para si mesmo.")
    target_nickname_value = str(target.get("nickname") or public_display_name(target, target_id))

    cooldown = int(anonymous_cooldown_seconds if is_anonymous else normal_cooldown_seconds)
    cost = max(0, int(anon_cost if is_anonymous else 0))

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                # deterministic transaction-level locks prevent double sends/charges across replicas
                for uid in sorted({sender_id, target_id}):
                    cur.execute("SELECT pg_advisory_xact_lock(%s)", (uid,))
                target_settings = _ensure_settings(cur, target_id)
                if not bool(target_settings.get("allow_messages", True)):
                    raise MessageError("target_messages_disabled", "Esse jogador não está aceitando mensagens.")
                if is_anonymous and not bool(target_settings.get("allow_anonymous", True)):
                    raise MessageError("target_anonymous_disabled", "Esse jogador não aceita mensagens anônimas.")

                cur.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM message_blocks_v2
                        WHERE blocker_user_id=%s AND blocked_user_id=%s
                    ) AS target_blocked,
                    EXISTS(
                        SELECT 1 FROM message_blocks_v2
                        WHERE blocker_user_id=%s AND blocked_user_id=%s
                    ) AS sender_blocked
                    """,
                    (target_id, sender_id, sender_id, target_id),
                )
                blocks = dict(cur.fetchone() or {})
                if blocks.get("target_blocked"):
                    raise MessageError("blocked_by_target", "Você não pode enviar mensagens para esse jogador.")
                if blocks.get("sender_blocked"):
                    raise MessageError("you_blocked_target", "Você bloqueou esse jogador. Desbloqueie antes de enviar.")

                cur.execute(
                    """
                    SELECT EXTRACT(EPOCH FROM (NOW()-created_at))::INTEGER AS age
                    FROM user_messages_v2
                    WHERE from_user_id=%s AND is_anonymous=%s
                      AND status IN ('pending','delivered')
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (sender_id, bool(is_anonymous)),
                )
                last = cur.fetchone()
                if last and int(last.get("age") or 0) < cooldown:
                    raise MessageError("cooldown_active", "Aguarde antes de enviar outra mensagem.", remaining_seconds=cooldown-int(last.get("age") or 0))

                wallet = None
                if cost:
                    wallet = lock_wallet(cur, sender_id)
                    if int(wallet.get("coins") or 0) < cost:
                        raise MessageError("insufficient_coins", f"Você precisa de {cost} coins para uma mensagem anônima.")
                    cur.execute(
                        "UPDATE game_wallets SET coins=coins-%s, updated_at=NOW() WHERE user_id=%s AND coins>=%s RETURNING user_id,coins,dice,spins,dice_slot",
                        (cost, sender_id, cost),
                    )
                    wallet = dict(cur.fetchone() or {})
                    if not wallet:
                        raise MessageError("insufficient_coins", f"Você precisa de {cost} coins para uma mensagem anônima.")

                cur.execute(
                    """
                    INSERT INTO user_messages_v2
                    (from_user_id,to_user_id,sender_nickname,recipient_nickname,message_text,is_anonymous,charged_coins)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
                    """,
                    (sender_id,target_id,sender_nickname,target_nickname_value,text,bool(is_anonymous),cost),
                )
                row = dict(cur.fetchone() or {})
                if cost:
                    insert_ledger(cur,user_id=sender_id,resource="coins",delta=-cost,reason="anonymous_message_reserve",reference=f"message:{row['message_id']}")
                conn.commit()
                return {"message": row, "to_user_id": target_id, "to_nickname": target_nickname_value, "from_nickname": sender_nickname, "wallet": wallet_payload(wallet) if wallet else None}
            except MessageError:
                conn.rollback(); raise
            except Exception:
                conn.rollback(); raise


def mark_message_delivered(message_id: int) -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "UPDATE user_messages_v2 SET status='delivered',delivered_at=NOW() WHERE message_id=%s AND status='pending'",
                (int(message_id),),
            )
            conn.commit()


def fail_message_and_refund(message_id: int, reason: str) -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM user_messages_v2 WHERE message_id=%s FOR UPDATE", (int(message_id),))
                row = cur.fetchone()
                if not row or str(row.get("status") or "") != "pending":
                    conn.commit(); return
                cost = int(row.get("charged_coins") or 0)
                sender_id = int(row.get("from_user_id") or 0)
                if cost > 0:
                    wallet = lock_wallet(cur, sender_id)
                    cur.execute("UPDATE game_wallets SET coins=coins+%s,updated_at=NOW() WHERE user_id=%s", (cost,sender_id))
                    insert_ledger(cur,user_id=sender_id,resource="coins",delta=cost,reason="anonymous_message_refund",reference=f"message:{int(message_id)}",metadata={"reason":str(reason)[:300]})
                cur.execute(
                    "UPDATE user_messages_v2 SET status='failed',failure_reason=%s,failed_at=NOW() WHERE message_id=%s",
                    (str(reason or "delivery_failed")[:500],int(message_id)),
                )
                conn.commit()
            except Exception:
                conn.rollback(); raise


def report_message(reporter_user_id: int, message_id: int, reason: str) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT message_id FROM user_messages_v2 WHERE message_id=%s AND to_user_id=%s AND status='delivered'",
                (int(message_id),int(reporter_user_id)),
            )
            if not cur.fetchone():
                raise MessageError("message_not_found", "Essa mensagem não está na sua caixa de entrada.")
            cur.execute(
                """
                INSERT INTO message_reports_v2 (message_id,reporter_user_id,reason)
                VALUES (%s,%s,%s)
                ON CONFLICT (message_id,reporter_user_id) DO UPDATE SET reason=EXCLUDED.reason
                RETURNING *
                """,
                (int(message_id),int(reporter_user_id),str(reason or "Sem motivo informado")[:700]),
            )
            row=dict(cur.fetchone() or {}); conn.commit(); return row


def message_center_state(user_id: int, limit: int = 60) -> dict[str, Any]:
    uid=int(user_id); limit=max(1,min(100,int(limit)))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            settings=_ensure_settings(cur,uid)
            cur.execute("SELECT * FROM user_messages_v2 WHERE to_user_id=%s AND status='delivered' ORDER BY message_id DESC LIMIT %s",(uid,limit))
            inbox=[]
            for raw in cur.fetchall() or []:
                row=dict(raw)
                inbox.append({
                    "message_id":int(row["message_id"]),
                    "from": "Anônimo" if row.get("is_anonymous") else str(row.get("sender_nickname") or "Jogador"),
                    "text":str(row.get("message_text") or ""),
                    "is_anonymous":bool(row.get("is_anonymous")),
                    "created_at":row.get("created_at").isoformat() if row.get("created_at") else None,
                })
            cur.execute("SELECT * FROM user_messages_v2 WHERE from_user_id=%s ORDER BY message_id DESC LIMIT %s",(uid,limit))
            sent=[{
                "message_id":int(row["message_id"]),"to":str(row.get("recipient_nickname") or "Jogador"),
                "text":str(row.get("message_text") or ""),"is_anonymous":bool(row.get("is_anonymous")),"status":str(row.get("status") or ""),
                "created_at":row.get("created_at").isoformat() if row.get("created_at") else None,
            } for row in (cur.fetchall() or [])]
            conn.commit()
            return {"settings":{"allow_messages":bool(settings.get("allow_messages",True)),"allow_anonymous":bool(settings.get("allow_anonymous",True))},"inbox":inbox,"sent":sent,"blocks":list_blocks(uid)}
