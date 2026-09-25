"""Daily progression uses the existing daily ledger and server clock, not client dates."""

from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from database_core import run
from source_features.common import transaction, account, cosmetic

TZ = ZoneInfo("America/Sao_Paulo")


def calendar(uid: int, cur=None):
    today = datetime.now(TZ).date()
    sql = """WITH days AS (
        SELECT DISTINCT (to_timestamp(day_start_ts) AT TIME ZONE 'America/Sao_Paulo')::date AS day
        FROM daily_rewards WHERE user_id=%s
    ), ordered AS (
        SELECT day,ROW_NUMBER() OVER (ORDER BY day DESC)::int AS n,MAX(day) OVER () AS latest FROM days
    ) SELECT
        COALESCE((SELECT ARRAY_AGG(day) FROM days WHERE day >= %s),ARRAY[]::date[]) AS recent,
        (SELECT COUNT(*) FROM ordered WHERE latest >= %s AND day+n-1=latest) AS streak,
        EXISTS(SELECT 1 FROM source_cosmetics WHERE user_id=%s AND cosmetic_id='badge-week') AS milestone_claimed
    """
    params = (uid, today - timedelta(days=6), today - timedelta(days=1), uid)
    if cur is None:
        row = run(sql, params, fetch="one")
    else:
        cur.execute(sql, params)
        row = cur.fetchone()
    by_day = set(row["recent"])
    streak = int(row["streak"])
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    return {
        "today": today.isoformat(),
        "claimed_today": today in by_day,
        "streak": streak,
        "days": [{"date": d.isoformat(), "claimed": d in by_day} for d in days],
        "reward_rules": "1 a 3 Coins ou 1 dado, conforme o resgate diário existente.",
        "milestone": {
            "days": 7,
            "cosmetic": "badge-week",
            "label": "Presença semanal",
            "eligible": streak >= 7,
            "claimed": row["milestone_claimed"],
        },
    }


def claim(uid: int):
    from database import claim_daily_reward, _daily_day_start_ts_sp
    from commands.daily import DAILY_COINS_MIN, DAILY_COINS_MAX, DAILY_GIRO_CHANCE

    result = claim_daily_reward(
        uid,
        _daily_day_start_ts_sp(),
        DAILY_COINS_MIN,
        DAILY_COINS_MAX,
        DAILY_GIRO_CHANCE,
    )
    return {
        "ok": True,
        "already_claimed": result is None,
        "reward": result,
        "calendar": calendar(uid),
    }


def claim_milestone(uid: int):
    from source_features.common import FeatureError

    with transaction(uid) as cur:
        account(cur, uid)
        if calendar(uid, cur)["streak"] < 7:
            raise FeatureError(
                "milestone_unavailable",
                "Complete sete dias consecutivos para receber o emblema.",
            )
        received = cosmetic(cur, uid, "badge-week", "Presença semanal")
        return {
            "ok": True,
            "already_claimed": not received,
            "cosmetic_id": "badge-week",
        }


def now(uid: int):
    # Only this screen performs the existing dice refresh; aggregate the remaining activity.
    from database import get_dado_state
    from database_aninexus_pets import _ensure_tables

    _ensure_tables()
    dice = get_dado_state(uid)
    row = run(
        """SELECT
        EXISTS(SELECT 1 FROM daily_rewards WHERE user_id=%s AND day_start_ts=EXTRACT(EPOCH FROM (date_trunc('day',NOW() AT TIME ZONE 'America/Sao_Paulo') AT TIME ZONE 'America/Sao_Paulo'))::bigint) AS daily_claimed,
        (SELECT COUNT(*) FROM card_trades WHERE ((to_user=%s AND to_confirmed IS DISTINCT FROM revision) OR (from_user=%s AND from_confirmed IS DISTINCT FROM revision)) AND status='pending' AND created_at>=NOW()-INTERVAL '24 hours') AS incoming_trades,
        (SELECT COUNT(*) FROM aninexus_user_eggs WHERE user_id=%s AND status='incubating' AND hatch_at<=NOW()) AS ready_eggs,
        (SELECT COUNT(*) FROM source_market WHERE (seller_id=%s OR bidder_id=%s) AND status='active' AND ends_at<=NOW()) AS due_market,
        (SELECT COUNT(*) FROM source_events WHERE status='active' AND starts_at<=NOW() AND ends_at>NOW()) AS active_events""",
        (uid, uid, uid, uid, uid, uid),
        fetch="one",
    )
    return {
        "items": [
            {
                "id": "daily",
                "title": "Recompensa diária",
                "description": "Já resgatada hoje"
                if row["daily_claimed"]
                else "Seu resgate está disponível",
                "ready": not row["daily_claimed"],
                "tab": "activity",
                "section": "calendar",
            },
            {
                "id": "trades",
                "title": "Trocas para confirmar",
                "description": f"{row['incoming_trades']} proposta(s) aguardando resposta",
                "ready": row["incoming_trades"] > 0,
                "tab": "trading",
            },
            {
                "id": "market",
                "title": "Anúncios encerrados",
                "description": f"{row['due_market']} anúncio(s) em conclusão",
                "ready": row["due_market"] > 0,
                "tab": "marketplace",
            },
            {
                "id": "events",
                "title": "Expedições",
                "description": f"{row['active_events']} evento(s) disponível(is)",
                "ready": row["active_events"] > 0,
                "tab": "events",
            },
            {
                "id": "dice",
                "title": "Dados e recarga",
                "description": f"{int(dice.get('balance') or 0)} dado(s) disponível(is)",
                "ready": int(dice.get("balance") or 0) > 0,
                "tab": "dado",
            },
            {
                "id": "quests",
                "title": "Missões",
                "description": "Veja progresso e recompensas",
                "ready": False,
                "tab": "quests",
            },
            {
                "id": "eggs",
                "title": "Incubadora",
                "description": f"{row['ready_eggs']} ovo(s) pronto(s) para eclodir",
                "ready": row["ready_eggs"] > 0,
                "tab": "incubation",
            },
        ]
    }
