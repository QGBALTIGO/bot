from __future__ import annotations

import os
from functools import lru_cache


def _parse_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in str(raw or "").replace(";", ",").split(","):
        value = part.strip()
        if not value:
            continue
        try:
            user_id = int(value)
        except (TypeError, ValueError):
            continue
        if user_id > 0:
            out.add(user_id)
    return out


@lru_cache(maxsize=1)
def owner_ids() -> set[int]:
    ids: set[int] = set()
    ids.update(_parse_ids(os.getenv("BOT_OWNER_ID", "")))
    return ids


@lru_cache(maxsize=1)
def admin_ids() -> set[int]:
    ids = set(owner_ids())
    for env_name in ("ADMINS", "ADMIN_IDS", "CARD_ADMIN_IDS"):
        ids.update(_parse_ids(os.getenv(env_name, "")))
    return ids


def is_owner(user_id: int) -> bool:
    try:
        return int(user_id) in owner_ids()
    except (TypeError, ValueError):
        return False


def is_admin(user_id: int) -> bool:
    try:
        return int(user_id) in admin_ids()
    except (TypeError, ValueError):
        return False
