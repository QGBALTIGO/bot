from __future__ import annotations

import json
from datetime import date
from typing import Any

from psycopg.rows import dict_row

from database import pool, xp_to_level
from ecosystem_rules import ACHIEVEMENTS, MISSIONS, mission_period_key, normalize_library_status, normalize_media_type
from game_rules import today_sp
from wallet_tx import insert_ledger, lock_wallet, wallet_payload


class EcosystemError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def create_ecosystem_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_library_v2 (
                    user_id BIGINT NOT NULL,
                    media_type TEXT NOT NULL CHECK (media_type IN ('anime','manga')),
                    media_id BIGINT NOT NULL,
                    title TEXT NOT NULL,
                    cover_url TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'planned',
                    is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
                    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0),
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, media_type, media_id)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_library_v2_user_status ON user_library_v2 (user_id,status,updated_at DESC)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_activity_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    event_code TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'system',
                    label TEXT NOT NULL DEFAULT '',
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_activity_v2_user_created ON user_activity_v2 (user_id,created_at DESC)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_event_counters_v2 (
                    user_id BIGINT NOT NULL,
                    event_code TEXT NOT NULL,
                    total BIGINT NOT NULL DEFAULT 0 CHECK (total >= 0),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id,event_code)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_progress_v2 (
                    user_id BIGINT NOT NULL,
                    mission_code TEXT NOT NULL,
                    period_key TEXT NOT NULL,
                    progress BIGINT NOT NULL DEFAULT 0 CHECK (progress >= 0),
                    completed_at TIMESTAMPTZ,
                    claimed_at TIMESTAMPTZ,
                    PRIMARY KEY (user_id,mission_code,period_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_achievements_v2 (
                    user_id BIGINT NOT NULL,
                    achievement_code TEXT NOT NULL,
                    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id,achievement_code)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_titles_v2 (
                    user_id BIGINT NOT NULL,
                    title_code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'achievement',
                    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    equipped BOOLEAN NOT NULL DEFAULT FALSE,
                    PRIMARY KEY (user_id,title_code)
                )
                """
            )
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_user_titles_v2_equipped ON user_titles_v2 (user_id) WHERE equipped")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_preferences_v2 (
                    user_id BIGINT PRIMARY KEY,
                    daily BOOLEAN NOT NULL DEFAULT TRUE,
                    dice_full BOOLEAN NOT NULL DEFAULT TRUE,
                    messages BOOLEAN NOT NULL DEFAULT TRUE,
                    duels BOOLEAN NOT NULL DEFAULT TRUE,
                    trades BOOLEAN NOT NULL DEFAULT TRUE,
                    requests BOOLEAN NOT NULL DEFAULT TRUE,
                    news BOOLEAN NOT NULL DEFAULT TRUE,
                    airing BOOLEAN NOT NULL DEFAULT TRUE,
                    missions BOOLEAN NOT NULL DEFAULT TRUE,
                    achievements BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    action_path TEXT NOT NULL DEFAULT '',
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    read_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_v2_user_created ON notifications_v2 (user_id,created_at DESC)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS friendships_v2 (
                    user_low BIGINT NOT NULL,
                    user_high BIGINT NOT NULL,
                    requested_by BIGINT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected','blocked')),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_low,user_high),
                    CHECK (user_low < user_high)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS news_items_v2 (
                    id BIGSERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    image_url TEXT NOT NULL DEFAULT '',
                    media_type TEXT,
                    media_id BIGINT,
                    media_title TEXT NOT NULL DEFAULT '',
                    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_by BIGINT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_news_items_v2_published ON news_items_v2 (active,published_at DESC)")
            conn.commit()


def _ensure_notification_preferences(cur, user_id: int) -> dict[str, Any]:
    cur.execute("INSERT INTO notification_preferences_v2 (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (int(user_id),))
    cur.execute("SELECT * FROM notification_preferences_v2 WHERE user_id=%s", (int(user_id),))
    return dict(cur.fetchone() or {})


def push_notification(user_id: int, kind: str, title: str, body: str = "", action_path: str = "", metadata: dict[str, Any] | None = None) -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            prefs = _ensure_notification_preferences(cur, int(user_id))
            if kind in prefs and not bool(prefs.get(kind)):
                conn.commit()
                return
            cur.execute(
                """INSERT INTO notifications_v2 (user_id,kind,title,body,action_path,metadata)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
                (int(user_id), str(kind)[:40], str(title)[:180], str(body)[:700], str(action_path)[:300], json.dumps(metadata or {}, ensure_ascii=False)),
            )
            conn.commit()


def record_event(user_id: int, event_code: str, *, amount: int = 1, absolute: bool = False, category: str = "system", label: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    uid = int(user_id)
    amount = max(0, int(amount))
    code = str(event_code or "").strip()[:80]
    if not code:
        raise EcosystemError("event_invalid", "Evento inválido.")
    current_date = today_sp()
    unlocked: list[str] = []
    completed_missions: list[str] = []

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "INSERT INTO user_activity_v2 (user_id,event_code,category,label,metadata) VALUES (%s,%s,%s,%s,%s::jsonb)",
                    (uid, code, str(category or "system")[:30], str(label or "")[:240], json.dumps(metadata or {}, ensure_ascii=False)),
                )
                cur.execute(
                    """INSERT INTO user_event_counters_v2 (user_id,event_code,total) VALUES (%s,%s,%s)
                       ON CONFLICT (user_id,event_code) DO UPDATE SET total=%s,updated_at=NOW()
                       RETURNING total""" if absolute else
                    """INSERT INTO user_event_counters_v2 (user_id,event_code,total) VALUES (%s,%s,%s)
                       ON CONFLICT (user_id,event_code) DO UPDATE SET total=user_event_counters_v2.total+EXCLUDED.total,updated_at=NOW()
                       RETURNING total""",
                    (uid, code, amount, amount) if absolute else (uid, code, amount),
                )
                total = int((cur.fetchone() or {}).get("total") or 0)

                for mission in MISSIONS:
                    if mission.event_code != code:
                        continue
                    period_key = mission_period_key(mission.period, current_date)
                    cur.execute(
                        """INSERT INTO mission_progress_v2 (user_id,mission_code,period_key,progress)
                           VALUES (%s,%s,%s,%s)
                           ON CONFLICT (user_id,mission_code,period_key)
                           DO UPDATE SET progress=LEAST(%s, mission_progress_v2.progress+EXCLUDED.progress)
                           RETURNING progress,completed_at""",
                        (uid, mission.code, period_key, amount, mission.target),
                    )
                    row = dict(cur.fetchone() or {})
                    if int(row.get("progress") or 0) >= mission.target and not row.get("completed_at"):
                        cur.execute(
                            "UPDATE mission_progress_v2 SET completed_at=NOW() WHERE user_id=%s AND mission_code=%s AND period_key=%s",
                            (uid, mission.code, period_key),
                        )
                        completed_missions.append(mission.code)

                for achievement in ACHIEVEMENTS:
                    if achievement.event_code != code or total < achievement.target:
                        continue
                    cur.execute(
                        "INSERT INTO user_achievements_v2 (user_id,achievement_code) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING achievement_code",
                        (uid, achievement.code),
                    )
                    if cur.fetchone():
                        unlocked.append(achievement.code)
                        if achievement.title:
                            cur.execute(
                                "INSERT INTO user_titles_v2 (user_id,title_code,title,source) VALUES (%s,%s,%s,'achievement') ON CONFLICT DO NOTHING",
                                (uid, achievement.code, achievement.title),
                            )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    for code_unlocked in unlocked:
        definition = next((item for item in ACHIEVEMENTS if item.code == code_unlocked), None)
        if definition:
            push_notification(uid, "achievements", f"🏅 Conquista: {definition.label}", definition.description, "/hub#achievements")
    for code_completed in completed_missions:
        mission = next((item for item in MISSIONS if item.code == code_completed), None)
        if mission:
            push_notification(uid, "missions", f"✅ Missão concluída: {mission.label}", "Sua recompensa está pronta para resgate.", "/hub#missions")
    return {"event_code": code, "total": total, "unlocked": unlocked, "completed_missions": completed_missions}


def library_upsert(user_id: int, *, media_type: str, media_id: int, title: str, cover_url: str = "", status: str = "planned", favorite: bool | None = None, progress: int | None = None) -> dict[str, Any]:
    media_type = normalize_media_type(media_type)
    status = normalize_library_status(status)
    media_id = int(media_id)
    if media_id <= 0 or not str(title or "").strip():
        raise EcosystemError("media_invalid", "Obra inválida.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM user_library_v2 WHERE user_id=%s AND media_type=%s AND media_id=%s FOR UPDATE", (int(user_id), media_type, media_id))
            current = dict(cur.fetchone() or {})
            fav = bool(current.get("is_favorite")) if favorite is None else bool(favorite)
            prog = int(current.get("progress") or 0) if progress is None else max(0, int(progress))
            cur.execute(
                """INSERT INTO user_library_v2 (user_id,media_type,media_id,title,cover_url,status,is_favorite,progress)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (user_id,media_type,media_id) DO UPDATE SET
                     title=EXCLUDED.title,cover_url=EXCLUDED.cover_url,status=EXCLUDED.status,
                     is_favorite=EXCLUDED.is_favorite,progress=EXCLUDED.progress,updated_at=NOW()
                   RETURNING *""",
                (int(user_id), media_type, media_id, str(title)[:260], str(cover_url or "")[:1200], status, fav, prog),
            )
            row = dict(cur.fetchone() or {})
            conn.commit()
            return row


def library_remove(user_id: int, media_type: str, media_id: int) -> None:
    media_type = normalize_media_type(media_type)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_library_v2 WHERE user_id=%s AND media_type=%s AND media_id=%s", (int(user_id), media_type, int(media_id)))
            conn.commit()


def library_state(user_id: int) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM user_library_v2 WHERE user_id=%s ORDER BY is_favorite DESC,updated_at DESC", (int(user_id),))
            rows = []
            for raw in cur.fetchall() or []:
                row = dict(raw)
                for key in ("created_at", "updated_at"):
                    if row.get(key): row[key] = row[key].isoformat()
                rows.append(row)
            return rows


def missions_state(user_id: int, current_date: date | None = None) -> list[dict[str, Any]]:
    current = current_date or today_sp()
    rows: list[dict[str, Any]] = []
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            for mission in MISSIONS:
                key = mission_period_key(mission.period, current)
                cur.execute("SELECT progress,completed_at,claimed_at FROM mission_progress_v2 WHERE user_id=%s AND mission_code=%s AND period_key=%s", (int(user_id), mission.code, key))
                state = dict(cur.fetchone() or {})
                progress = min(mission.target, int(state.get("progress") or 0))
                rows.append({
                    "code": mission.code, "label": mission.label, "description": mission.description,
                    "period": mission.period, "target": mission.target, "progress": progress,
                    "completed": progress >= mission.target, "claimed": bool(state.get("claimed_at")),
                    "reward": {"xp": mission.xp_reward, "coins": mission.coin_reward},
                })
    return rows


def claim_mission(user_id: int, mission_code: str, current_date: date | None = None) -> dict[str, Any]:
    mission = next((item for item in MISSIONS if item.code == str(mission_code)), None)
    if not mission:
        raise EcosystemError("mission_not_found", "Missão não encontrada.")
    current = current_date or today_sp()
    key = mission_period_key(mission.period, current)
    uid = int(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM mission_progress_v2 WHERE user_id=%s AND mission_code=%s AND period_key=%s FOR UPDATE", (uid, mission.code, key))
                row = dict(cur.fetchone() or {})
                if int(row.get("progress") or 0) < mission.target:
                    raise EcosystemError("mission_incomplete", "Essa missão ainda não foi concluída.")
                if row.get("claimed_at"):
                    raise EcosystemError("mission_claimed", "Essa recompensa já foi resgatada.")
                wallet = lock_wallet(cur, uid)
                if mission.coin_reward:
                    cur.execute("UPDATE game_wallets SET coins=coins+%s,updated_at=NOW() WHERE user_id=%s RETURNING user_id,coins,dice,spins,dice_slot", (mission.coin_reward, uid))
                    wallet = dict(cur.fetchone() or wallet)
                    insert_ledger(cur,user_id=uid,resource="coins",delta=mission.coin_reward,reason="mission_reward",reference=f"mission:{mission.code}:{key}")
                cur.execute("INSERT INTO user_progress (user_id,xp,level,total_actions) VALUES (%s,0,1,0) ON CONFLICT DO NOTHING", (uid,))
                cur.execute("SELECT xp,level,total_actions FROM user_progress WHERE user_id=%s FOR UPDATE", (uid,))
                progress_row = dict(cur.fetchone() or {})
                if mission.xp_reward:
                    new_xp = int(progress_row.get("xp") or 0) + mission.xp_reward
                    cur.execute("UPDATE user_progress SET xp=%s,level=%s,total_actions=total_actions+1,updated_at=NOW() WHERE user_id=%s", (new_xp, xp_to_level(new_xp), uid))
                cur.execute("UPDATE mission_progress_v2 SET claimed_at=NOW() WHERE user_id=%s AND mission_code=%s AND period_key=%s", (uid, mission.code, key))
                conn.commit()
                return {"mission": mission.code, "reward": {"coins": mission.coin_reward, "xp": mission.xp_reward}, "wallet": wallet_payload(wallet)}
            except EcosystemError:
                conn.rollback(); raise
            except Exception:
                conn.rollback(); raise


def achievements_state(user_id: int) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT achievement_code,unlocked_at FROM user_achievements_v2 WHERE user_id=%s", (int(user_id),))
            unlocked = {str(row["achievement_code"]): row.get("unlocked_at") for row in (cur.fetchall() or [])}
            cur.execute("SELECT event_code,total FROM user_event_counters_v2 WHERE user_id=%s", (int(user_id),))
            counters = {str(row["event_code"]): int(row.get("total") or 0) for row in (cur.fetchall() or [])}
    result=[]
    for item in ACHIEVEMENTS:
        result.append({"code":item.code,"label":item.label,"description":item.description,"title":item.title,"target":item.target,"progress":min(item.target,counters.get(item.event_code,0)),"unlocked":item.code in unlocked,"unlocked_at":unlocked[item.code].isoformat() if item.code in unlocked and unlocked[item.code] else None})
    return result


def equip_title(user_id: int, title_code: str) -> str:
    uid=int(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT title FROM user_titles_v2 WHERE user_id=%s AND title_code=%s FOR UPDATE",(uid,str(title_code)))
            row=cur.fetchone()
            if not row: raise EcosystemError("title_locked","Você ainda não desbloqueou esse título.")
            cur.execute("UPDATE user_titles_v2 SET equipped=FALSE WHERE user_id=%s",(uid,))
            cur.execute("UPDATE user_titles_v2 SET equipped=TRUE WHERE user_id=%s AND title_code=%s",(uid,str(title_code)))
            conn.commit(); return str(row.get("title") or "")


def titles_state(user_id: int) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT title_code,title,source,equipped FROM user_titles_v2 WHERE user_id=%s ORDER BY unlocked_at DESC",(int(user_id),))
            rows=[dict(row) for row in (cur.fetchall() or [])]
    return {"items":rows,"equipped":next((row["title"] for row in rows if row.get("equipped")),"")}


def notification_state(user_id: int, limit: int = 60) -> dict[str, Any]:
    uid=int(user_id); limit=max(1,min(100,int(limit)))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            prefs=_ensure_notification_preferences(cur,uid)
            cur.execute("SELECT id,kind,title,body,action_path,read_at,created_at FROM notifications_v2 WHERE user_id=%s ORDER BY id DESC LIMIT %s",(uid,limit))
            items=[]
            for row in cur.fetchall() or []:
                item=dict(row); item["read"]=bool(item.pop("read_at",None)); item["created_at"]=item["created_at"].isoformat() if item.get("created_at") else None; items.append(item)
            conn.commit()
    return {"preferences":{k:bool(v) for k,v in prefs.items() if k not in {"user_id","updated_at"}},"items":items,"unread":sum(1 for x in items if not x["read"])}


def update_notification_preferences(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    allowed={"daily","dice_full","messages","duels","trades","requests","news","airing","missions","achievements"}
    updates={k:bool(v) for k,v in payload.items() if k in allowed}
    if not updates: return notification_state(int(user_id))["preferences"]
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _ensure_notification_preferences(cur,int(user_id))
            assignments=", ".join(f"{key}=%s" for key in updates)
            cur.execute(f"UPDATE notification_preferences_v2 SET {assignments},updated_at=NOW() WHERE user_id=%s RETURNING *",(*updates.values(),int(user_id)))
            row=dict(cur.fetchone() or {}); conn.commit()
    return {k:bool(v) for k,v in row.items() if k in allowed}


def mark_notification_read(user_id: int, notification_id: int) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE notifications_v2 SET read_at=COALESCE(read_at,NOW()) WHERE id=%s AND user_id=%s",(int(notification_id),int(user_id))); conn.commit()


def recent_activity(user_id: int, limit: int = 80) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id,event_code,category,label,metadata,created_at FROM user_activity_v2 WHERE user_id=%s ORDER BY id DESC LIMIT %s",(int(user_id),max(1,min(150,int(limit)))))
            rows=[]
            for raw in cur.fetchall() or []:
                row=dict(raw); row["created_at"]=row["created_at"].isoformat() if row.get("created_at") else None; rows.append(row)
            return rows


def friend_request(from_user_id: int, to_user_id: int) -> dict[str, Any]:
    a,b=int(from_user_id),int(to_user_id)
    if a==b: raise EcosystemError("friend_self","Você não pode adicionar a si mesmo.")
    low,high=sorted((a,b))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM friendships_v2 WHERE user_low=%s AND user_high=%s FOR UPDATE",(low,high)); existing=cur.fetchone()
            if existing and str(existing.get("status")) in {"pending","accepted","blocked"}: raise EcosystemError("friend_exists","Já existe uma relação ou pedido entre vocês.")
            cur.execute("""INSERT INTO friendships_v2 (user_low,user_high,requested_by,status) VALUES (%s,%s,%s,'pending')
                           ON CONFLICT (user_low,user_high) DO UPDATE SET requested_by=EXCLUDED.requested_by,status='pending',updated_at=NOW() RETURNING *""",(low,high,a))
            row=dict(cur.fetchone() or {}); conn.commit(); return row


def friend_respond(user_id: int, other_user_id: int, accept: bool) -> None:
    uid,other=int(user_id),int(other_user_id); low,high=sorted((uid,other))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM friendships_v2 WHERE user_low=%s AND user_high=%s FOR UPDATE",(low,high)); row=cur.fetchone()
            if not row or str(row.get("status"))!="pending" or int(row.get("requested_by") or 0)==uid: raise EcosystemError("friend_request_missing","Pedido de amizade não encontrado.")
            cur.execute("UPDATE friendships_v2 SET status=%s,updated_at=NOW() WHERE user_low=%s AND user_high=%s",("accepted" if accept else "rejected",low,high)); conn.commit()


def friends_state(user_id: int) -> dict[str, Any]:
    uid=int(user_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""SELECT f.*, CASE WHEN f.user_low=%s THEN f.user_high ELSE f.user_low END AS other_id,
                COALESCE(NULLIF(i.nickname,''),NULLIF(i.telegram_full_name,''),'@'||NULLIF(i.telegram_username,''),'Jogador') AS display_name
                FROM friendships_v2 f
                LEFT JOIN user_identity_v2 i ON i.user_id=CASE WHEN f.user_low=%s THEN f.user_high ELSE f.user_low END
                WHERE %s IN (f.user_low,f.user_high) AND f.status IN ('pending','accepted') ORDER BY f.updated_at DESC""",(uid,uid,uid))
            rows=[dict(row) for row in (cur.fetchall() or [])]
    return {"friends":[{"user_id":int(r["other_id"]),"display_name":r["display_name"]} for r in rows if r["status"]=="accepted"],"incoming":[{"user_id":int(r["other_id"]),"display_name":r["display_name"]} for r in rows if r["status"]=="pending" and int(r["requested_by"])!=uid],"outgoing":[{"user_id":int(r["other_id"]),"display_name":r["display_name"]} for r in rows if r["status"]=="pending" and int(r["requested_by"])==uid]}


def news_state(user_id: int, limit: int = 40) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""SELECT n.*,
                EXISTS(SELECT 1 FROM user_library_v2 l WHERE l.user_id=%s AND l.media_id=n.media_id AND l.media_type=COALESCE(n.media_type,l.media_type) AND (l.is_favorite OR l.status IN ('planned','watching'))) AS followed
                FROM news_items_v2 n WHERE n.active=TRUE ORDER BY followed DESC,n.published_at DESC LIMIT %s""",(int(user_id),max(1,min(100,int(limit)))))
            rows=[]
            for raw in cur.fetchall() or []:
                row=dict(raw); row["published_at"]=row["published_at"].isoformat() if row.get("published_at") else None; rows.append(row)
            return rows
