from __future__ import annotations

from database_core import run as _run


def create_profile_settings_table():
    _run("""
    CREATE TABLE IF NOT EXISTS user_profile_settings (
        user_id BIGINT PRIMARY KEY,
        nickname TEXT UNIQUE,
        favorite_character_id BIGINT,
        country_code TEXT NOT NULL DEFAULT 'BR',
        language TEXT NOT NULL DEFAULT 'pt',
        private_profile BOOLEAN NOT NULL DEFAULT FALSE,
        notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        dado_full_notified BOOLEAN NOT NULL DEFAULT FALSE,
        dado_full_notified_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS nickname TEXT;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS favorite_character_id BIGINT;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS country_code TEXT NOT NULL DEFAULT 'BR';""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'pt';""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS private_profile BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS dado_full_notified BOOLEAN NOT NULL DEFAULT FALSE;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS dado_full_notified_at TIMESTAMPTZ;""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")
    _run("""ALTER TABLE user_profile_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();""")

    _run("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_user_profile_settings_nickname
    ON user_profile_settings (nickname)
    WHERE nickname IS NOT NULL
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_profile_settings_notifications
    ON user_profile_settings (notifications_enabled, dado_full_notified)
    """)

    _run("""
    CREATE INDEX IF NOT EXISTS idx_user_profile_settings_nickname_lower
    ON user_profile_settings (LOWER(nickname))
    WHERE nickname IS NOT NULL
    """)


def ensure_profile_settings_row(user_id: int):
    _run(
        """
        INSERT INTO user_profile_settings (user_id, created_at, updated_at)
        VALUES (%s, NOW(), NOW())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id),)
    )


def get_profile_settings(user_id: int):
    ensure_profile_settings_row(user_id)
    row = _run(
        """
        SELECT
            user_id,
            nickname,
            favorite_character_id,
            country_code,
            language,
            private_profile,
            notifications_enabled,
            dado_full_notified,
            dado_full_notified_at,
            created_at,
            updated_at
        FROM user_profile_settings
        WHERE user_id = %s
        LIMIT 1
        """,
        (int(user_id),),
        fetch="one"
    )
    return row or None


def get_profile_settings_by_nickname(nickname: str):
    row = _run(
        """
        SELECT
            user_id,
            nickname,
            favorite_character_id,
            country_code,
            language,
            private_profile,
            notifications_enabled,
            dado_full_notified,
            dado_full_notified_at,
            created_at,
            updated_at
        FROM user_profile_settings
        WHERE LOWER(nickname) = LOWER(%s)
        LIMIT 1
        """,
        ((nickname or "").strip(),),
        fetch="one"
    )
    return row or None


def nickname_exists(nickname: str) -> bool:
    row = _run(
        """
        SELECT 1
        FROM user_profile_settings
        WHERE LOWER(nickname) = LOWER(%s)
        LIMIT 1
        """,
        ((nickname or "").strip(),),
        fetch="one"
    )
    return bool(row)


def set_profile_nickname(user_id: int, nickname: str) -> dict:
    ensure_profile_settings_row(user_id)

    current = get_profile_settings(user_id) or {}
    if current.get("nickname"):
        return {"ok": False, "error": "nickname_locked"}

    if nickname_exists(nickname):
        return {"ok": False, "error": "nickname_taken"}

    _run(
        """
        UPDATE user_profile_settings
        SET nickname = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        ((nickname or "").strip(), int(user_id))
    )
    return {"ok": True}


def set_profile_favorite(user_id: int, character_id: int):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET favorite_character_id = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (int(character_id), int(user_id))
    )


def set_profile_country(user_id: int, country_code: str):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET country_code = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        ((country_code or "BR").strip().upper(), int(user_id))
    )


def set_profile_language(user_id: int, language: str):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET language = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        ((language or "pt").strip().lower(), int(user_id))
    )


def set_profile_private(user_id: int, value: bool):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET private_profile = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (bool(value), int(user_id))
    )


def set_profile_notifications(user_id: int, value: bool):
    ensure_profile_settings_row(user_id)
    _run(
        """
        UPDATE user_profile_settings
        SET notifications_enabled = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (bool(value), int(user_id))
    )
