from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from psycopg.rows import dict_row

from database_core import pool


_TABLES_LOCK = Lock()
_TABLES_READY = False
INVITE_TTL_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return
    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_bonds (
                        bond_id BIGSERIAL PRIMARY KEY,
                        user_low_id BIGINT NOT NULL,
                        user_high_id BIGINT NOT NULL,
                        created_by BIGINT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        ended_at TIMESTAMPTZ,
                        CHECK (user_low_id > 0),
                        CHECK (user_high_id > 0),
                        CHECK (user_low_id < user_high_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_aninexus_bonds_active_pair
                    ON aninexus_bonds (user_low_id, user_high_id)
                    WHERE status = 'active'
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_aninexus_bonds_low_status
                    ON aninexus_bonds (user_low_id, status, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_aninexus_bonds_high_status
                    ON aninexus_bonds (user_high_id, status, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS aninexus_bond_invites (
                        invite_id BIGSERIAL PRIMARY KEY,
                        inviter_id BIGINT NOT NULL,
                        invitee_id BIGINT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        responded_at TIMESTAMPTZ,
                        CHECK (inviter_id > 0),
                        CHECK (invitee_id > 0),
                        CHECK (inviter_id <> invitee_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_aninexus_bond_invites_pending_pair
                    ON aninexus_bond_invites (
                        (LEAST(inviter_id, invitee_id)),
                        (GREATEST(inviter_id, invitee_id))
                    )
                    WHERE status = 'pending'
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_aninexus_bond_invites_inbox
                    ON aninexus_bond_invites (invitee_id, status, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_aninexus_bond_invites_outbox
                    ON aninexus_bond_invites (inviter_id, status, created_at DESC)
                    """
                )
            conn.commit()
        _TABLES_READY = True


def _lock_users(cur, *user_ids: int) -> None:
    for user_id in sorted({int(uid) for uid in user_ids if int(uid) > 0}):
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))


def _user_exists(cur, user_id: int) -> bool:
    cur.execute("SELECT 1 FROM users WHERE user_id = %s LIMIT 1", (int(user_id),))
    return bool(cur.fetchone())


def _active_bond_locked(cur, user_id: int) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT bond_id, user_low_id, user_high_id, created_by, status, created_at, ended_at
        FROM aninexus_bonds
        WHERE status = 'active'
          AND (user_low_id = %s OR user_high_id = %s)
        ORDER BY created_at DESC
        LIMIT 1
        FOR UPDATE
        """,
        (int(user_id), int(user_id)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _active_bond_unlocked(cur, user_id: int) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT bond_id, user_low_id, user_high_id, created_by, status, created_at, ended_at
        FROM aninexus_bonds
        WHERE status = 'active'
          AND (user_low_id = %s OR user_high_id = %s)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (int(user_id), int(user_id)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _other_user_id(bond: dict[str, Any], user_id: int) -> int:
    low_id = int(bond.get("user_low_id") or 0)
    high_id = int(bond.get("user_high_id") or 0)
    return high_id if low_id == int(user_id) else low_id


def get_active_bond(user_id: int) -> dict[str, Any] | None:
    _ensure_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _active_bond_unlocked(cur, int(user_id))


def list_bond_invites(user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    _ensure_tables()
    limit = max(1, min(int(limit), 100))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE aninexus_bond_invites
                SET status = 'expired', responded_at = NOW()
                WHERE status = 'pending' AND expires_at <= NOW()
                """
            )
            cur.execute(
                """
                SELECT invite_id, inviter_id, invitee_id, status,
                       created_at, expires_at, responded_at
                FROM aninexus_bond_invites
                WHERE (inviter_id = %s OR invitee_id = %s)
                  AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (int(user_id), int(user_id), limit),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
            conn.commit()
    return rows


def create_bond_invite(inviter_id: int, invitee_id: int) -> dict[str, Any]:
    _ensure_tables()
    inviter_id = int(inviter_id)
    invitee_id = int(invitee_id)
    if inviter_id <= 0 or invitee_id <= 0 or inviter_id == invitee_id:
        return {"ok": False, "error": "invalid_user"}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")
                _lock_users(cur, inviter_id, invitee_id)
                if not _user_exists(cur, invitee_id):
                    conn.rollback()
                    return {"ok": False, "error": "user_not_found"}
                if _active_bond_locked(cur, inviter_id):
                    conn.rollback()
                    return {"ok": False, "error": "inviter_already_bonded"}
                if _active_bond_locked(cur, invitee_id):
                    conn.rollback()
                    return {"ok": False, "error": "invitee_already_bonded"}

                cur.execute(
                    """
                    UPDATE aninexus_bond_invites
                    SET status = 'expired', responded_at = NOW()
                    WHERE status = 'pending' AND expires_at <= NOW()
                      AND (
                        (inviter_id = %s AND invitee_id = %s)
                        OR (inviter_id = %s AND invitee_id = %s)
                      )
                    """,
                    (inviter_id, invitee_id, invitee_id, inviter_id),
                )
                cur.execute(
                    """
                    SELECT invite_id, inviter_id, invitee_id, status, created_at, expires_at
                    FROM aninexus_bond_invites
                    WHERE status = 'pending'
                      AND (
                        (inviter_id = %s AND invitee_id = %s)
                        OR (inviter_id = %s AND invitee_id = %s)
                      )
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (inviter_id, invitee_id, invitee_id, inviter_id),
                )
                existing = cur.fetchone()
                if existing:
                    conn.commit()
                    return {"ok": True, "already_pending": True, "invite": dict(existing)}

                expires_at = _now() + timedelta(days=INVITE_TTL_DAYS)
                cur.execute(
                    """
                    INSERT INTO aninexus_bond_invites
                        (inviter_id, invitee_id, status, expires_at)
                    VALUES (%s, %s, 'pending', %s)
                    RETURNING invite_id, inviter_id, invitee_id, status, created_at, expires_at
                    """,
                    (inviter_id, invitee_id, expires_at),
                )
                row = dict(cur.fetchone() or {})
                conn.commit()
                return {"ok": True, "already_pending": False, "invite": row}
            except Exception:
                conn.rollback()
                raise


def respond_bond_invite(user_id: int, invite_id: int, action: str) -> dict[str, Any]:
    _ensure_tables()
    action = str(action or "").strip().lower()
    if action not in {"accept", "reject"}:
        return {"ok": False, "error": "invalid_action"}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("BEGIN")

                # Primeiro descobre o par sem segurar a linha do convite. Assim
                # nunca esperamos advisory locks enquanto mantemos outro convite
                # bloqueado, evitando deadlocks em aceitações simultâneas.
                cur.execute(
                    """
                    SELECT inviter_id, invitee_id
                    FROM aninexus_bond_invites
                    WHERE invite_id = %s
                    """,
                    (int(invite_id),),
                )
                preview = cur.fetchone()
                if not preview:
                    conn.rollback()
                    return {"ok": False, "error": "invite_not_found"}

                inviter_id = int(preview.get("inviter_id") or 0)
                invitee_id = int(preview.get("invitee_id") or 0)
                _lock_users(cur, inviter_id, invitee_id)

                cur.execute(
                    """
                    SELECT * FROM aninexus_bond_invites
                    WHERE invite_id = %s
                    FOR UPDATE
                    """,
                    (int(invite_id),),
                )
                invite = cur.fetchone()
                if not invite:
                    conn.rollback()
                    return {"ok": False, "error": "invite_not_found"}
                invite = dict(invite)
                if int(invite.get("invitee_id") or 0) != int(user_id):
                    conn.rollback()
                    return {"ok": False, "error": "forbidden"}
                if str(invite.get("status") or "") != "pending":
                    conn.rollback()
                    return {"ok": False, "error": "invite_not_pending"}
                expires_at = invite.get("expires_at")
                if isinstance(expires_at, datetime) and expires_at <= _now():
                    cur.execute(
                        """
                        UPDATE aninexus_bond_invites
                        SET status = 'expired', responded_at = NOW()
                        WHERE invite_id = %s
                        """,
                        (int(invite_id),),
                    )
                    conn.commit()
                    return {"ok": False, "error": "invite_expired"}

                if action == "reject":
                    cur.execute(
                        """
                        UPDATE aninexus_bond_invites
                        SET status = 'rejected', responded_at = NOW()
                        WHERE invite_id = %s
                        """,
                        (int(invite_id),),
                    )
                    conn.commit()
                    return {"ok": True, "status": "rejected"}

                if _active_bond_locked(cur, inviter_id) or _active_bond_locked(cur, invitee_id):
                    conn.rollback()
                    return {"ok": False, "error": "already_bonded"}

                low_id, high_id = sorted((inviter_id, invitee_id))
                cur.execute(
                    """
                    INSERT INTO aninexus_bonds
                        (user_low_id, user_high_id, created_by, status)
                    VALUES (%s, %s, %s, 'active')
                    RETURNING bond_id, user_low_id, user_high_id, created_by, status, created_at
                    """,
                    (low_id, high_id, inviter_id),
                )
                bond = dict(cur.fetchone() or {})
                cur.execute(
                    """
                    UPDATE aninexus_bond_invites
                    SET status = 'accepted', responded_at = NOW()
                    WHERE invite_id = %s
                    """,
                    (int(invite_id),),
                )
                cur.execute(
                    """
                    UPDATE aninexus_bond_invites
                    SET status = 'cancelled', responded_at = NOW()
                    WHERE status = 'pending'
                      AND invite_id <> %s
                      AND (
                        inviter_id IN (%s, %s)
                        OR invitee_id IN (%s, %s)
                      )
                    """,
                    (int(invite_id), inviter_id, invitee_id, inviter_id, invitee_id),
                )
                conn.commit()
                return {"ok": True, "status": "accepted", "bond": bond}
            except Exception:
                conn.rollback()
                raise


def remove_active_bond(user_id: int) -> dict[str, Any]:
    _ensure_tables()
    user_id = int(user_id)

    # O par é consultado sem lock apenas para descobrirmos os dois IDs. Depois
    # os advisory locks são sempre adquiridos em ordem crescente. Se o vínculo
    # mudar entre as duas etapas, reiniciamos em vez de quebrar a ordem de lock.
    for _attempt in range(2):
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                try:
                    cur.execute("BEGIN")
                    preview = _active_bond_unlocked(cur, user_id)
                    if not preview:
                        conn.rollback()
                        return {"ok": False, "error": "bond_not_found"}

                    preview_other_id = _other_user_id(preview, user_id)
                    _lock_users(cur, user_id, preview_other_id)

                    bond = _active_bond_locked(cur, user_id)
                    if not bond:
                        conn.rollback()
                        return {"ok": False, "error": "bond_not_found"}

                    other_id = _other_user_id(bond, user_id)
                    if other_id != preview_other_id:
                        conn.rollback()
                        continue

                    cur.execute(
                        """
                        UPDATE aninexus_bonds
                        SET status = 'ended', ended_at = NOW()
                        WHERE bond_id = %s AND status = 'active'
                        """,
                        (int(bond.get("bond_id") or 0),),
                    )
                    conn.commit()
                    return {"ok": True, "status": "ended", "partner_id": other_id}
                except Exception:
                    conn.rollback()
                    raise

    return {"ok": False, "error": "bond_changed_retry"}
