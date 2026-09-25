"""Protection, opt-in wishes/discovery, and non-transferable cosmetic crafting."""

from __future__ import annotations
from database_core import run
from source_features.common import (
    FeatureError,
    transaction,
    account,
    operation,
    inventory_guard,
    remove_copies,
    cosmetic,
)

MAX_WISHES = 500
RECIPES = {
    "frame-bronze": {"label": "Moldura de bronze", "kind": "frame", "cost": 10},
    "frame-silver": {"label": "Moldura de prata", "kind": "frame", "cost": 25},
    "title-collector": {"label": "Colecionador dedicado", "kind": "title", "cost": 40},
}


def character_ids(q="") -> list[int]:
    from cards_service import build_cards_final_data

    data = build_cards_final_data()["characters_by_id"]
    needle = q.strip().casefold()
    # Exact IDs take priority over names containing that number (e.g. episode titles).
    if needle.isdecimal() and int(needle) in data:
        return [int(needle)]
    return [
        int(cid)
        for cid, c in data.items()
        if not needle
        or needle == str(cid)
        or needle in f"{c.get('name', '')} {c.get('anime', '')}".casefold()
    ]


def character(cid: int, quantity=0) -> dict:
    from cards_service import get_character_by_id
    from utils.web_image_url import web_image_url

    meta = get_character_by_id(cid)
    if not meta:
        return {
            "id": cid,
            "name": f"Personagem {cid}",
            "anime": "",
            "image": "",
            "quantity": quantity,
            "available": False,
        }
    return {
        "id": cid,
        "name": meta["name"],
        "anime": meta.get("anime", ""),
        "image": web_image_url(meta.get("image")),
        "quantity": quantity,
        "available": True,
    }


def settings(uid):
    value = run(
        "SELECT discoverable,share_inline,preserve_last,equipped_cosmetic FROM source_collecting_settings WHERE user_id=%s",
        (uid,),
        fetch="one",
    )
    return value or {
        "discoverable": False,
        "share_inline": False,
        "preserve_last": True,
        "equipped_cosmetic": None,
    }


def save_settings(uid: int, payload: dict):
    with transaction(uid) as cur:
        account(cur, uid)
        cur.execute(
            "INSERT INTO source_collecting_settings(user_id) VALUES(%s) ON CONFLICT DO NOTHING",
            (uid,),
        )
        # Fixed allowlist, never interpolate client-controlled identifiers.
        for name in ("discoverable", "share_inline", "preserve_last"):
            if name in payload:
                cur.execute(
                    f"UPDATE source_collecting_settings SET {name}=%s,updated_at=NOW() WHERE user_id=%s",
                    (bool(payload[name]), uid),
                )
    return {"ok": True, **settings(uid)}


def cards(uid: int, q="", view="owned", offset=0, limit=24):
    ids = character_ids(q) if q.strip() or view == "catalog" else None
    if view == "catalog":
        chosen = (ids or [])[offset : offset + limit + 1]
        rows = run(
            "SELECT c.character_id,c.quantity,EXISTS(SELECT 1 FROM source_card_protection p WHERE p.user_id=c.user_id AND p.character_id=c.character_id) AS protected FROM user_card_collection c WHERE c.user_id=%s AND c.character_id=ANY(%s)",
            (uid, chosen),
            fetch="all",
        )
        owned = {int(r["character_id"]): r for r in rows}
        wished = {
            int(r["character_id"])
            for r in run(
                "SELECT character_id FROM source_wishlist WHERE user_id=%s AND character_id=ANY(%s)",
                (uid, chosen),
                fetch="all",
            )
        }
        items = [
            {
                **character(cid, int(owned.get(cid, {}).get("quantity", 0))),
                "protected": bool(owned.get(cid, {}).get("protected")),
                "wished": cid in wished,
            }
            for cid in chosen[:limit]
        ]
        return {
            "items": items,
            "has_more": len(chosen) > limit,
            "offset": offset,
            "total": len(ids or []),
        }
    from_sql = (
        "source_wishlist w LEFT JOIN user_card_collection c ON c.user_id=w.user_id AND c.character_id=w.character_id"
        if view == "wishes"
        else "user_card_collection c LEFT JOIN source_wishlist w ON w.user_id=c.user_id AND w.character_id=c.character_id"
    )
    field = "w" if view == "wishes" else "c"
    conditions = [f"{field}.user_id=%s"]
    params = [uid]
    if ids is not None:
        conditions.append(f"{field}.character_id=ANY(%s)")
        params.append(ids)
    if view == "duplicates":
        conditions.append("c.quantity>1")
    if view == "protected":
        conditions.append("p.character_id IS NOT NULL")
    sql = f"""SELECT {field}.character_id,COALESCE(c.quantity,0) quantity,p.character_id IS NOT NULL AS protected,
        w.character_id IS NOT NULL AS wished,s.favorite_character_id={field}.character_id AS favorite,
        EXISTS(SELECT 1 FROM source_reservations r WHERE r.user_id={field}.user_id AND r.character_id={field}.character_id) AS reserved
        FROM {from_sql} LEFT JOIN source_card_protection p ON p.user_id={field}.user_id AND p.character_id={field}.character_id
        LEFT JOIN user_profile_settings s ON s.user_id={field}.user_id
        WHERE {" AND ".join(conditions)} ORDER BY {field}.character_id LIMIT %s OFFSET %s"""
    rows = run(sql, tuple(params + [limit + 1, offset]), fetch="all")
    return {
        "items": [
            {
                **character(int(r["character_id"]), int(r["quantity"])),
                **{
                    k: bool(r[k])
                    for k in ("protected", "wished", "favorite", "reserved")
                },
            }
            for r in rows[:limit]
        ],
        "has_more": len(rows) > limit,
        "offset": offset,
    }


def set_protection(uid: int, cid: int, enabled: bool):
    with transaction(uid) as cur:
        account(cur, uid)
        cur.execute(
            "SELECT quantity FROM user_card_collection WHERE user_id=%s AND character_id=%s FOR UPDATE",
            (uid, cid),
        )
        if enabled and not cur.fetchone():
            raise FeatureError(
                "card_missing", "Proteja apenas personagens da sua coleção."
            )
        if enabled:
            cur.execute(
                "SELECT 1 FROM source_reservations WHERE user_id=%s AND character_id=%s",
                (uid, cid),
            )
            if cur.fetchone():
                raise FeatureError(
                    "card_reserved",
                    "Encerre o anúncio antes de proteger este personagem.",
                )
            cur.execute(
                "SELECT 1 FROM card_trades WHERE status='pending' AND created_at>=NOW()-INTERVAL '24 hours' AND ((from_user=%s AND from_character_id=%s) OR (to_user=%s AND to_character_id=%s)) LIMIT 1",
                (uid, cid, uid, cid),
            )
            if cur.fetchone():
                raise FeatureError(
                    "card_reserved",
                    "Encerre a troca antes de proteger este personagem.",
                )
            cur.execute(
                "INSERT INTO source_card_protection(user_id,character_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (uid, cid),
            )
        else:
            cur.execute(
                "DELETE FROM source_card_protection WHERE user_id=%s AND character_id=%s",
                (uid, cid),
            )
    return {"ok": True, "protected": enabled}


def wishes(uid: int, ids: list[int], enabled=True, missing_only=False):
    from cards_service import get_character_by_id

    valid = sorted(set(ids))
    if (
        not valid
        or len(valid) > 1000
        or (enabled and any(not get_character_by_id(cid) for cid in valid))
    ):
        raise FeatureError(
            "invalid_character", "Escolha personagens válidos do catálogo.", 400
        )
    with transaction(uid) as cur:
        account(cur, uid)
        if not enabled:
            cur.execute(
                "DELETE FROM source_wishlist WHERE user_id=%s AND character_id=ANY(%s)",
                (uid, valid),
            )
            return {"ok": True, "removed": cur.rowcount}
        cur.execute("SELECT character_id FROM source_wishlist WHERE user_id=%s", (uid,))
        prior = {int(r["character_id"]) for r in cur.fetchall()}
        if missing_only:
            cur.execute(
                "SELECT character_id FROM user_card_collection WHERE user_id=%s AND quantity>0 AND character_id=ANY(%s)",
                (uid, valid),
            )
            owned = {int(r["character_id"]) for r in cur.fetchall()}
            valid = [cid for cid in valid if cid not in owned]
        added = [cid for cid in valid if cid not in prior]
        if len(prior) + len(added) > MAX_WISHES:
            raise FeatureError(
                "wishlist_full",
                f"Sua lista comporta {MAX_WISHES} personagens. Remova alguns antes de adicionar a obra.",
            )
        cur.executemany(
            "INSERT INTO source_wishlist(user_id,character_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
            [(uid, cid) for cid in added],
        )
    return {"ok": True, "added": len(added)}


def wish_work(uid: int, anime_id: int):
    from cards_service import build_cards_final_data

    chars = build_cards_final_data()["characters_by_anime"].get(anime_id) or []
    return wishes(
        uid, [int(c.get("id") or c["character_id"]) for c in chars], missing_only=True
    )


def matches(uid: int, offset=0):
    from database_aninexus_social import is_profile_private

    if not settings(uid)["discoverable"] or is_profile_private(uid):
        return {"items": [], "opt_in_required": True}
    rows = run(
        """WITH candidates AS (
        SELECT DISTINCT other.user_id FROM source_wishlist mine
        JOIN user_card_collection other ON other.character_id=mine.character_id AND other.quantity>1
        JOIN source_collecting_settings opt ON opt.user_id=other.user_id AND opt.discoverable
        LEFT JOIN user_profile_settings priv ON priv.user_id=other.user_id
        WHERE mine.user_id=%s AND other.user_id<>%s AND NOT COALESCE(priv.private_profile,FALSE)
    ), available AS (
        SELECT c.user_id,c.character_id FROM user_card_collection c
        LEFT JOIN source_card_protection p USING(user_id,character_id)
        LEFT JOIN source_reservations r USING(user_id,character_id)
        LEFT JOIN user_profile_settings s ON s.user_id=c.user_id
        WHERE c.quantity>1 AND (c.user_id=%s OR c.user_id IN (SELECT user_id FROM candidates))
          AND p.character_id IS NULL AND r.character_id IS NULL
          AND COALESCE(s.favorite_character_id,0)<>c.character_id
          AND NOT EXISTS(SELECT 1 FROM card_trades t WHERE t.status='pending' AND t.created_at>=NOW()-INTERVAL '24 hours' AND ((t.from_user=c.user_id AND t.from_character_id=c.character_id) OR (t.to_user=c.user_id AND t.to_character_id=c.character_id)))
    ), receiving AS (
        SELECT a.user_id,array_agg(DISTINCT a.character_id ORDER BY a.character_id) AS ids
        FROM available a JOIN source_wishlist w ON w.character_id=a.character_id AND w.user_id=%s
        WHERE a.user_id<>%s GROUP BY a.user_id
    ), giving AS (
        SELECT w.user_id,array_agg(DISTINCT a.character_id ORDER BY a.character_id) AS ids
        FROM available a JOIN source_wishlist w ON w.character_id=a.character_id
        WHERE a.user_id=%s AND w.user_id IN (SELECT user_id FROM candidates) GROUP BY w.user_id
    ) SELECT r.user_id,COALESCE(NULLIF(s.nickname,''),'Colecionador') AS name,
        r.ids[1:8] AS receive,g.ids[1:8] AS give
        FROM receiving r JOIN giving g USING(user_id)
        LEFT JOIN user_profile_settings s ON s.user_id=r.user_id
        WHERE r.ids<>g.ids OR cardinality(r.ids)>1
        ORDER BY r.user_id LIMIT 11 OFFSET %s""",
        (uid, uid, uid, uid, uid, uid, offset),
        fetch="all",
    )
    return {
        "items": [
            {
                **r,
                "receive": [character(int(cid)) for cid in r["receive"]],
                "give": [character(int(cid)) for cid in r["give"]],
            }
            for r in rows[:10]
        ],
        "has_more": len(rows) > 10,
        "opt_in_required": False,
    }


def workshop_state(uid):
    wallet = run(
        "SELECT fragments FROM source_workshop_wallet WHERE user_id=%s",
        (uid,),
        fetch="one",
    ) or {"fragments": 0}
    cosmetics = run(
        "SELECT cosmetic_id,label,kind FROM source_cosmetics WHERE user_id=%s ORDER BY created_at DESC LIMIT 100",
        (uid,),
        fetch="all",
    )
    return {
        **wallet,
        "recipes": [{"id": k, **v} for k, v in RECIPES.items()],
        "cosmetics": cosmetics,
        "equipped": settings(uid)["equipped_cosmetic"],
    }


def workshop_preview(uid: int, items: list[dict]):
    if (
        not items
        or len(items) > 20
        or len({i["character_id"] for i in items}) != len(items)
    ):
        raise FeatureError(
            "invalid_selection", "Selecione de 1 a 20 personagens distintos.", 400
        )
    with transaction(uid) as cur:
        details = []
        for item in sorted(items, key=lambda i: i["character_id"]):
            inventory_guard(
                cur, uid, item["character_id"], item["quantity"], preserve_last=True
            )
            details.append(
                {**character(item["character_id"]), "consume": item["quantity"]}
            )
    return {
        "items": details,
        "fragments": sum(i["quantity"] for i in items),
        "preserves_last_copy": True,
    }


def workshop_recycle(uid: int, items: list[dict], request_id: str):
    # Validate structure even on replay, but validate inventory only on first execution.
    if (
        not items
        or len(items) > 20
        or len({i["character_id"] for i in items}) != len(items)
    ):
        raise FeatureError("invalid_selection", "Seleção inválida.", 400)
    with transaction(uid) as cur:
        account(cur, uid)

        def execute():
            for i in sorted(items, key=lambda i: i["character_id"]):
                inventory_guard(
                    cur, uid, i["character_id"], i["quantity"], preserve_last=True
                )
            amount = sum(i["quantity"] for i in items)
            for i in items:
                remove_copies(cur, uid, i["character_id"], i["quantity"])
            cur.execute(
                "INSERT INTO source_workshop_wallet(user_id,fragments) VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET fragments=source_workshop_wallet.fragments+EXCLUDED.fragments RETURNING fragments",
                (uid, amount),
            )
            return {
                "ok": True,
                "fragments": cur.fetchone()["fragments"],
                "earned": amount,
            }

        return operation(cur, uid, request_id, "recycle", {"items": items}, execute)


def craft(uid: int, recipe: str, request_id: str):
    if recipe not in RECIPES:
        raise FeatureError("invalid_recipe", "Receita não encontrada.", 404)
    spec = RECIPES[recipe]
    with transaction(uid) as cur:
        account(cur, uid)

        def execute():
            cur.execute(
                "SELECT 1 FROM source_cosmetics WHERE user_id=%s AND cosmetic_id=%s",
                (uid, recipe),
            )
            if cur.fetchone():
                raise FeatureError("already_owned", "Você já possui esse cosmético.")
            cur.execute(
                "UPDATE source_workshop_wallet SET fragments=fragments-%s WHERE user_id=%s AND fragments>=%s RETURNING fragments",
                (spec["cost"], uid, spec["cost"]),
            )
            row = cur.fetchone()
            if not row:
                raise FeatureError("no_fragments", "Fragmentos insuficientes.")
            cosmetic(cur, uid, recipe, spec["label"], spec["kind"])
            return {"ok": True, "fragments": row["fragments"], "cosmetic_id": recipe}

        return operation(cur, uid, request_id, "craft", {"recipe": recipe}, execute)


def equip(uid: int, key: str | None):
    with transaction(uid) as cur:
        account(cur, uid)
        if key:
            cur.execute(
                "SELECT 1 FROM source_cosmetics WHERE user_id=%s AND cosmetic_id=%s",
                (uid, key),
            )
            if not cur.fetchone():
                raise FeatureError(
                    "cosmetic_missing", "Você ainda não possui esse cosmético."
                )
        cur.execute(
            "INSERT INTO source_collecting_settings(user_id,equipped_cosmetic) VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET equipped_cosmetic=EXCLUDED.equipped_cosmetic",
            (uid, key),
        )
    return {"ok": True, "equipped": key}
