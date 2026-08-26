from __future__ import annotations

import logging
from typing import Any

from ecosystem_repository import record_event
from ecosystem_rules import event_category

logger = logging.getLogger(__name__)


def emit_event(
    user_id: int,
    event_code: str,
    *,
    amount: int = 1,
    absolute: bool = False,
    label: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Best-effort bridge from a completed domain action into the Baltigo ecosystem.

    Core game/economy/social actions must never be rolled back merely because a
    secondary activity/mission/achievement write failed. Domain repositories
    commit first; this bridge runs immediately after success and logs failures.
    """
    try:
        return record_event(
            int(user_id),
            str(event_code),
            amount=max(0, int(amount)),
            absolute=bool(absolute),
            category=event_category(event_code),
            label=str(label or ""),
            metadata=metadata or {},
        )
    except Exception:
        logger.exception("Falha ao registrar evento V2 user_id=%s event=%s", user_id, event_code)
        return None


def emit_completed_activity(user_id: int, *, label: str, metadata: dict[str, Any] | None = None) -> None:
    emit_event(user_id, "activity_completed", label=label, metadata=metadata)
