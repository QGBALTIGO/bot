"""Moderated, immutable event manifests and bounded cooperative expeditions.

Rewards are cosmetic, never coins or extra copies. No code or external URLs in manifests.
"""

from __future__ import annotations
from uuid import uuid4
from psycopg.types.json import Jsonb
from database_core import run
from source_features.common import (
    transaction,
    account,
    operation,
    FeatureError,
    cosmetic,
)


def create(uid: int, spec: dict):
    from cards_service import get_character_by_id

    ids = sorted(set(spec["character_ids"]))
    if not ids or any(not get_character_by_id(cid) for cid in ids):
        raise FeatureError(
            "invalid_characters",
            "Todos os personagens do evento precisam existir no catálogo.",
            400,
        )
    if (
        spec["ends_at"] <= spec["starts_at"]
        or (spec["ends_at"] - spec["starts_at"]).total_seconds() > 30 * 86400
    ):
        raise FeatureError(
            "invalid_dates", "Defina um período válido de até 30 dias.", 400
        )
    with transaction(uid) as cur:
        account(cur, uid)

        def execute():
            key = str(uuid4())
            cur.execute(
                "INSERT INTO source_events(id,title,description,character_ids,goal,daily_limit,reward_label,starts_at,ends_at,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    key,
                    spec["title"],
                    spec["description"],
                    ids,
                    spec["goal"],
                    spec["daily_limit"],
                    spec["reward_label"],
                    spec["starts_at"],
                    spec["ends_at"],
                    uid,
                ),
            )
            return {"ok": True, "id": key, "status": "draft"}

        return operation(
            cur,
            uid,
            spec["request_id"],
            "event-create",
            {
                **spec,
                "starts_at": spec["starts_at"].isoformat(),
                "ends_at": spec["ends_at"].isoformat(),
            },
            execute,
        )


def publish(uid: int, key: str):
    with transaction() as cur:
        cur.execute(
            "SELECT *,ends_at>NOW() AS current FROM source_events WHERE id=%s FOR UPDATE",
            (key,),
        )
        event = cur.fetchone()
        if not event:
            raise FeatureError("event_missing", "Evento não encontrado.", 404)
        if event["status"] != "draft" or not event["current"]:
            raise FeatureError(
                "event_closed", "Somente um rascunho ainda válido pode ser publicado."
            )
        from cards_service import get_character_by_id

        if any(not get_character_by_id(cid) for cid in event["character_ids"]):
            raise FeatureError(
                "invalid_characters",
                "O catálogo mudou. Revise os personagens do evento.",
            )
        cur.execute(
            "UPDATE source_events SET status='active',published_by=%s WHERE id=%s",
            (uid, key),
        )
        return {"ok": True, "status": "active"}


def listing(uid: int, admin=False):
    rows = run(
        """SELECT e.*, (SELECT COUNT(*) FROM source_contributions c WHERE c.event_id=e.id) AS progress,
        (SELECT COUNT(*) FROM source_contributions c WHERE c.event_id=e.id AND c.user_id=%s) AS contribution,
        (SELECT COUNT(*) FROM source_contributions c WHERE c.event_id=e.id AND c.user_id=%s AND c.day=(NOW() AT TIME ZONE 'America/Sao_Paulo')::date) AS today,
        EXISTS(SELECT 1 FROM source_cosmetics s WHERE s.user_id=%s AND s.cosmetic_id='event-'||e.id::text) AS claimed
        FROM source_events e WHERE (e.status='active' AND e.ends_at>NOW()-INTERVAL '30 days') OR %s
        ORDER BY e.starts_at DESC LIMIT 30""",
        (uid, uid, uid, admin),
        fetch="all",
    )
    from source_features.collection import character

    return {
        "items": [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "description": r["description"],
                "status": r["status"],
                "starts_at": r["starts_at"].isoformat(),
                "ends_at": r["ends_at"].isoformat(),
                "goal": r["goal"],
                "progress": r["progress"],
                "contribution": r["contribution"],
                "today": r["today"],
                "daily_limit": r["daily_limit"],
                "reward_label": r["reward_label"],
                "claimed": r["claimed"],
                "characters": [character(cid) for cid in r["character_ids"]],
            }
            for r in rows
        ]
    }


def contribute(uid: int, key: str, cid: int, request_id: str):
    with transaction() as cur:
        cur.execute(
            "SELECT *,starts_at<=NOW() AND ends_at>NOW() AS available FROM source_events WHERE id=%s FOR UPDATE",
            (key,),
        )
        event = cur.fetchone()
        if not event:
            raise FeatureError("event_missing", "Evento não encontrado.", 404)
        from database_shop_safety import lock_inventories

        lock_inventories(cur, uid)
        account(cur, uid)

        def execute():
            if event["status"] != "active" or not event["available"]:
                raise FeatureError(
                    "event_closed", "Esse evento não está disponível agora."
                )
            if cid not in event["character_ids"]:
                raise FeatureError(
                    "invalid_character", "Escolha um dos personagens deste evento.", 400
                )
            cur.execute(
                "SELECT quantity FROM user_card_collection WHERE user_id=%s AND character_id=%s FOR UPDATE",
                (uid, cid),
            )
            if int((cur.fetchone() or {}).get("quantity") or 0) < 1:
                raise FeatureError(
                    "card_missing",
                    "Você precisa ter esse personagem na coleção para participar.",
                )
            cur.execute(
                "SELECT character_id FROM source_contributions WHERE event_id=%s AND user_id=%s AND day=(NOW() AT TIME ZONE 'America/Sao_Paulo')::date",
                (key, uid),
            )
            today = cur.fetchall()
            if cid in {int(r["character_id"]) for r in today}:
                raise FeatureError(
                    "already_contributed", "Esse personagem já contribuiu hoje."
                )
            if len(today) >= event["daily_limit"]:
                raise FeatureError(
                    "daily_limit", "Você atingiu o limite de contribuições de hoje."
                )
            cur.execute(
                "INSERT INTO source_contributions(event_id,user_id,day,slot,character_id) VALUES(%s,%s,(NOW() AT TIME ZONE 'America/Sao_Paulo')::date,%s,%s)",
                (key, uid, len(today) + 1, cid),
            )
            return {"ok": True, "added": 1, "card_consumed": False}

        return operation(
            cur,
            uid,
            request_id,
            "event-contribute",
            {"id": key, "character_id": cid},
            execute,
        )


def claim(uid: int, key: str):
    with transaction() as cur:
        cur.execute("SELECT * FROM source_events WHERE id=%s FOR UPDATE", (key,))
        event = cur.fetchone()
        if not event or event["status"] != "active":
            raise FeatureError("event_closed", "Evento indisponível.")
        account(cur, uid)
        cur.execute(
            "SELECT COUNT(*) AS total,COUNT(*) FILTER(WHERE user_id=%s) AS mine FROM source_contributions WHERE event_id=%s",
            (uid, key),
        )
        counts = cur.fetchone()
        if counts["total"] < event["goal"] or not counts["mine"]:
            raise FeatureError(
                "goal_pending",
                "Participe e ajude a comunidade a alcançar a meta antes de resgatar.",
            )
        received = cosmetic(cur, uid, "event-" + key, event["reward_label"])
        return {"ok": True, "already_claimed": not received}
