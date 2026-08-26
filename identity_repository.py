from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional

from psycopg.rows import dict_row

from database import pool


NICKNAME_MIN = 3
NICKNAME_MAX = 24
_RESERVED_NICKNAMES = {
    "admin",
    "administrator",
    "moderador",
    "moderator",
    "source baltigo",
    "sourcebaltigo",
    "baltigo",
}


class IdentityError(ValueError):
    pass


class NicknameTakenError(IdentityError):
    pass


def create_identity_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_identity_v2 (
                        user_id BIGINT PRIMARY KEY,
                        telegram_username TEXT,
                        telegram_full_name TEXT,
                        nickname TEXT,
                        nickname_key TEXT,
                        private_profile BOOLEAN NOT NULL DEFAULT FALSE,
                        favorite_character_id BIGINT,
                        country_code TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_user_identity_v2_nickname_key
                    ON user_identity_v2 (nickname_key)
                    WHERE nickname_key IS NOT NULL AND nickname_key <> ''
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_user_identity_v2_username
                    ON user_identity_v2 (telegram_username)
                    """
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _clean_text(value: Any, max_length: int) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = " ".join(text.split())
    return text[:max_length]


def normalize_nickname(value: Any) -> tuple[str, str]:
    nickname = _clean_text(value, NICKNAME_MAX)
    if not nickname:
        return "", ""
    if len(nickname) < NICKNAME_MIN:
        raise IdentityError(f"Nickname precisa ter pelo menos {NICKNAME_MIN} caracteres.")
    if not re.fullmatch(r"[\w .-]+", nickname, flags=re.UNICODE):
        raise IdentityError("Nickname pode usar letras, números, espaço, ponto, hífen e underscore.")

    key = nickname.casefold()
    if key in _RESERVED_NICKNAMES:
        raise IdentityError("Esse nickname é reservado.")
    return nickname, key


def sync_telegram_identity(user_id: int, username: str = "", full_name: str = "") -> Dict[str, Any]:
    username = _clean_text(username, 64).lstrip("@")
    full_name = _clean_text(full_name, 128)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO user_identity_v2
                    (user_id, telegram_username, telegram_full_name, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        telegram_username = EXCLUDED.telegram_username,
                        telegram_full_name = EXCLUDED.telegram_full_name,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    (int(user_id), username or None, full_name or None),
                )
                row = cur.fetchone() or {}
                conn.commit()
                return dict(row)
            except Exception:
                conn.rollback()
                raise


def ensure_identity(user_id: int) -> Dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO user_identity_v2 (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (int(user_id),),
                )
                cur.execute(
                    "SELECT * FROM user_identity_v2 WHERE user_id = %s",
                    (int(user_id),),
                )
                row = cur.fetchone() or {}
                conn.commit()
                return dict(row)
            except Exception:
                conn.rollback()
                raise


def get_identity(user_id: int) -> Dict[str, Any]:
    return ensure_identity(int(user_id))


def find_identity_by_nickname(nickname: str) -> Optional[Dict[str, Any]]:
    _, key = normalize_nickname(nickname)
    if not key:
        return None
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM user_identity_v2 WHERE nickname_key = %s LIMIT 1",
                (key,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def update_profile_settings(
    user_id: int,
    *,
    nickname: Any = None,
    private_profile: Any = None,
    favorite_character_id: Any = None,
    country_code: Any = None,
) -> Dict[str, Any]:
    current = ensure_identity(int(user_id))

    if nickname is None:
        nickname_value = current.get("nickname")
        nickname_key = current.get("nickname_key")
    else:
        nickname_value, nickname_key = normalize_nickname(nickname)
        nickname_value = nickname_value or None
        nickname_key = nickname_key or None

    private_value = bool(current.get("private_profile")) if private_profile is None else bool(private_profile)

    if favorite_character_id is None:
        favorite_value = current.get("favorite_character_id")
    else:
        try:
            favorite_value = int(favorite_character_id or 0) or None
        except (TypeError, ValueError) as exc:
            raise IdentityError("Personagem favorito inválido.") from exc

    if country_code is None:
        country_value = current.get("country_code")
    else:
        country_value = _clean_text(country_code, 2).upper() or None
        if country_value and not re.fullmatch(r"[A-Z]{2}", country_value):
            raise IdentityError("Código de país inválido.")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    """
                    UPDATE user_identity_v2
                    SET nickname = %s,
                        nickname_key = %s,
                        private_profile = %s,
                        favorite_character_id = %s,
                        country_code = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    RETURNING *
                    """,
                    (
                        nickname_value,
                        nickname_key,
                        private_value,
                        favorite_value,
                        country_value,
                        int(user_id),
                    ),
                )
                row = cur.fetchone() or {}
                conn.commit()
                return dict(row)
            except Exception as exc:
                conn.rollback()
                if getattr(exc, "sqlstate", "") == "23505":
                    raise NicknameTakenError("Esse nickname já está em uso.") from exc
                raise


def public_display_name(identity: Dict[str, Any], user_id: int) -> str:
    nickname = str(identity.get("nickname") or "").strip()
    if nickname:
        return nickname
    full_name = str(identity.get("telegram_full_name") or "").strip()
    if full_name:
        return full_name
    username = str(identity.get("telegram_username") or "").strip()
    if username:
        return f"@{username}"
    return f"Usuário {int(user_id)}"
