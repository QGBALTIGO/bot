from __future__ import annotations

from collections import Counter
from typing import Any

from cards_service import build_cards_final_data, search_characters
from collection_service import get_collection_state
from database import get_progress_row, pool
from ecosystem_repository import (
    EcosystemError,
    achievements_state,
    claim_mission,
    equip_title,
    friend_request,
    friend_respond,
    friends_state,
    library_remove,
    library_state,
    library_upsert,
    mark_notification_read,
    missions_state,
    news_state,
    notification_state,
    recent_activity,
    titles_state,
    update_notification_preferences,
)
from game_service import get_state as get_game_state
from identity_repository import find_identity_by_nickname, get_identity, public_display_name


def _safe_message_summary(user_id: int) -> dict[str, int]:
    try:
        from messages_repository import message_center_state
        state = message_center_state(int(user_id), limit=20)
        return {
            "received": len(state.get("inbox") or []),
            "sent": len(state.get("sent") or []),
        }
    except Exception:
        return {"received": 0, "sent": 0}


def _collection_recommendations(user_id: int, limit: int = 8) -> list[dict[str, Any]]:
    catalog = build_cards_final_data()
    owned = get_collection_state(int(user_id)).get("items") or []
    counts: Counter[int] = Counter()
    for item in owned:
        anime_id = int(item.get("anime_id") or 0)
        if anime_id > 0:
            counts[anime_id] += 1
    candidates=[]
    for anime_id, owned_unique in counts.most_common():
        anime=(catalog.get("animes_by_id") or {}).get(anime_id) or {}
        total=int(anime.get("characters_count") or 0)
        if total <= 0 or owned_unique >= total:
            continue
        candidates.append({
            "anime_id":anime_id,
            "title":str(anime.get("anime") or "Obra"),
            "cover":str(anime.get("cover_image") or anime.get("banner_image") or ""),
            "owned":owned_unique,
            "total":total,
            "completion":round((owned_unique/total)*100,1),
            "reason":"Você já começou este álbum",
        })
        if len(candidates)>=limit:
            break
    return candidates


def _continue_cards(user_id: int) -> list[dict[str, Any]]:
    items=[]
    try:
        game=get_game_state(int(user_id))
        if not bool((game.get("daily") or {}).get("claimed_today")):
            items.append({"code":"daily","icon":"🎁","title":"Daily disponível","copy":"Resgate sua recompensa de hoje.","path":"/game#daily","priority":100})
        wallet=game.get("wallet") or {}
        if int(wallet.get("dice") or 0)>0:
            items.append({"code":"dice","icon":"🎲","title":f"{int(wallet.get('dice') or 0)} dados disponíveis","copy":"Descubra uma obra e ganhe um personagem.","path":"/game#dice","priority":75})
        if int(wallet.get("spins") or 0)>0:
            items.append({"code":"spin","icon":"🎡","title":f"{int(wallet.get('spins') or 0)} giros disponíveis","copy":"A roleta está pronta.","path":"/game#spin","priority":65})
    except Exception:
        pass
    missions=missions_state(int(user_id))
    ready=sum(1 for m in missions if m.get("completed") and not m.get("claimed"))
    if ready:
        items.append({"code":"missions","icon":"✅","title":f"{ready} missão{'ões' if ready!=1 else ''} para resgatar","copy":"Recompensas de XP e coins esperando.","path":"/hub#missions","priority":90})
    notifications=notification_state(int(user_id),limit=20)
    if int(notifications.get("unread") or 0):
        items.append({"code":"notifications","icon":"🔔","title":f"{notifications['unread']} notificações novas","copy":"Veja o que mudou desde sua última visita.","path":"/hub#notifications","priority":80})
    return sorted(items,key=lambda item:-int(item.get("priority") or 0))[:5]


def dashboard_state(user_id: int) -> dict[str, Any]:
    uid=int(user_id)
    identity=get_identity(uid)
    progress=get_progress_row(uid) or {}
    collection=get_collection_state(uid)
    game=get_game_state(uid)
    notifications=notification_state(uid,limit=30)
    library=library_state(uid)
    friends=friends_state(uid)
    achievements=achievements_state(uid)
    titles=titles_state(uid)
    missions=missions_state(uid)
    messages=_safe_message_summary(uid)
    return {
        "display_name": public_display_name(identity,uid),
        "equipped_title": titles.get("equipped") or "",
        "wallet": game.get("wallet") or {},
        "daily": game.get("daily") or {},
        "progress": {"level":int(progress.get("level") or 1),"xp":int(progress.get("xp") or 0),"actions":int(progress.get("total_actions") or 0)},
        "collection": collection.get("stats") or {},
        "library": {"total":len(library),"favorites":sum(1 for x in library if x.get("is_favorite")),"watching":sum(1 for x in library if x.get("status")=="watching"),"planned":sum(1 for x in library if x.get("status")=="planned")},
        "social": {"friends":len(friends.get("friends") or []),"friend_requests":len(friends.get("incoming") or []),**messages},
        "missions": {"items":missions,"ready":sum(1 for x in missions if x.get("completed") and not x.get("claimed"))},
        "achievements": {"unlocked":sum(1 for x in achievements if x.get("unlocked")),"total":len(achievements)},
        "notifications": {"unread":int(notifications.get("unread") or 0)},
        "continue": _continue_cards(uid),
        "recommendations": _collection_recommendations(uid),
    }


def library_payload(user_id: int) -> dict[str, Any]:
    items=library_state(int(user_id))
    return {"items":items,"stats":{"total":len(items),"favorites":sum(1 for x in items if x.get("is_favorite")),"planned":sum(1 for x in items if x.get("status")=="planned"),"watching":sum(1 for x in items if x.get("status")=="watching"),"completed":sum(1 for x in items if x.get("status")=="completed")}}


def save_library_item(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    return library_upsert(
        int(user_id),
        media_type=str(payload.get("media_type") or "anime"),
        media_id=int(payload.get("media_id") or 0),
        title=str(payload.get("title") or ""),
        cover_url=str(payload.get("cover_url") or ""),
        status=str(payload.get("status") or "planned"),
        favorite=payload.get("favorite") if "favorite" in payload else None,
        progress=payload.get("progress") if "progress" in payload else None,
    )


def universal_search(user_id: int, query: str, limit: int = 24) -> dict[str, Any]:
    q=" ".join(str(query or "").split()).strip()
    if len(q)<2:
        return {"characters":[],"animes":[],"people":[]}
    catalog=build_cards_final_data()
    qn=q.casefold()
    animes=[]
    for anime in catalog.get("animes_list") or []:
        if qn in str(anime.get("anime") or "").casefold():
            animes.append({"anime_id":int(anime.get("anime_id") or 0),"title":str(anime.get("anime") or ""),"cover":str(anime.get("cover_image") or anime.get("banner_image") or "")})
            if len(animes)>=limit: break
    characters=[{"id":int(c.get("id") or 0),"name":str(c.get("name") or ""),"anime":str(c.get("anime") or ""),"image":str(c.get("image") or "")} for c in search_characters(q,limit=limit)]
    people=[]
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict) as cur:
            cur.execute("""SELECT user_id,nickname,telegram_full_name,telegram_username FROM user_identity_v2
                WHERE private_profile=FALSE AND (nickname ILIKE %s OR telegram_full_name ILIKE %s OR telegram_username ILIKE %s)
                ORDER BY CASE WHEN LOWER(nickname)=LOWER(%s) THEN 0 ELSE 1 END,updated_at DESC LIMIT %s""",(f"%{q}%",f"%{q}%",f"%{q}%",q,max(1,min(20,limit))))
            for row in cur.fetchall() or []:
                people.append({"user_id":int(row.get("user_id") or 0),"display_name":str(row.get("nickname") or row.get("telegram_full_name") or ("@"+str(row.get("telegram_username") or "")) or "Jogador")})
    return {"characters":characters,"animes":animes,"people":people}


def ecosystem_state(user_id: int) -> dict[str, Any]:
    uid=int(user_id)
    return {
        "dashboard":dashboard_state(uid),
        "library":library_payload(uid),
        "missions":missions_state(uid),
        "achievements":achievements_state(uid),
        "titles":titles_state(uid),
        "notifications":notification_state(uid),
        "friends":friends_state(uid),
        "activity":recent_activity(uid),
        "news":news_state(uid),
        "recommendations":_collection_recommendations(uid),
    }


__all__=[
    "EcosystemError","dashboard_state","ecosystem_state","library_payload","save_library_item","library_remove",
    "claim_mission","equip_title","notification_state","update_notification_preferences","mark_notification_read",
    "friend_request","friend_respond","friends_state","universal_search",
]
