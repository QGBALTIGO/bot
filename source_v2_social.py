from __future__ import annotations

from typing import Any

from database_core import run


REFERRER_REWARD_COINS = 500
REFERRER_REWARD_XP = 50
REFERRED_REWARD_COINS = 1_500


def list_referrals(user_id: int) -> list[dict[str, Any]]:
    rows = run(
        """
        SELECT
            r.referred_user_id,
            COALESCE(
                NULLIF(p.nickname, ''),
                NULLIF(u.full_name, ''),
                CASE WHEN NULLIF(u.username, '') IS NOT NULL THEN '@' || u.username ELSE NULL END,
                'User ' || r.referred_user_id::text
            ) AS referred_name,
            r.created_at
        FROM user_referrals r
        LEFT JOIN users u ON u.user_id = r.referred_user_id
        LEFT JOIN user_profile_settings p ON p.user_id = r.referred_user_id
        WHERE r.referrer_user_id = %s
        ORDER BY r.created_at DESC, r.referred_user_id DESC
        LIMIT 500
        """,
        (int(user_id),),
        fetch="all",
    ) or []
    return [
        {
            "referred_id": int(row.get("referred_user_id") or 0),
            "referred_name": str(row.get("referred_name") or "User"),
            # Existing Source referrals predate the v2 reward ledger. They are tracked,
            # but are not labeled as paid until the dedicated referral reward migration.
            "rewarded": False,
        }
        for row in rows
        if int(row.get("referred_user_id") or 0) > 0
    ]


def referral_stats(user_id: int) -> dict[str, Any]:
    count_row = run(
        "SELECT COUNT(*) AS total FROM user_referrals WHERE referrer_user_id = %s",
        (int(user_id),),
        fetch="one",
    ) or {}
    count = int(count_row.get("total") or 0)
    return {
        "invited_count": count,
        "tracked_count": count,
        # We deliberately do not invent historical earnings for referrals created
        # before the v2 ledger exists.
        "earned_shards": 0,
        "referrer_reward_shards": REFERRER_REWARD_COINS,
        "referrer_reward_xp": REFERRER_REWARD_XP,
        "referred_reward_shards": REFERRED_REWARD_COINS,
        "referred_reward_pet": "starter_bonus",
    }


def leaderboard(metric: str, *, limit: int = 500) -> list[dict[str, Any]]:
    metric_key = str(metric or "harem").strip().lower()
    limit = min(500, max(1, int(limit or 100)))

    visibility_join = "LEFT JOIN user_profile_settings p ON p.user_id = u.user_id"
    visibility_where = "COALESCE(p.profile_visibility, 'public') <> 'private'"

    if metric_key == "harem":
        query = f"""
            SELECT
                u.user_id AS id,
                u.full_name,
                u.username,
                COUNT(c.character_id) FILTER (WHERE c.quantity > 0) AS value
            FROM users u
            JOIN user_card_collection c ON c.user_id = u.user_id
            {visibility_join}
            WHERE {visibility_where}
            GROUP BY u.user_id, u.full_name, u.username
            HAVING COUNT(c.character_id) FILTER (WHERE c.quantity > 0) > 0
            ORDER BY value DESC, u.user_id ASC
            LIMIT %s
        """
        params = (limit,)
    elif metric_key == "shards":
        query = f"""
            SELECT u.user_id AS id, u.full_name, u.username, COALESCE(u.coins, 0) AS value
            FROM users u
            {visibility_join}
            WHERE {visibility_where} AND COALESCE(u.coins, 0) > 0
            ORDER BY value DESC, u.user_id ASC
            LIMIT %s
        """
        params = (limit,)
    elif metric_key == "level":
        query = f"""
            SELECT u.user_id AS id, u.full_name, u.username, COALESCE(up.level, 1) AS value
            FROM users u
            JOIN user_progress up ON up.user_id = u.user_id
            {visibility_join}
            WHERE {visibility_where}
            ORDER BY value DESC, up.xp DESC, u.user_id ASC
            LIMIT %s
        """
        params = (limit,)
    elif metric_key == "guesses":
        query = f"""
            SELECT u.user_id AS id, u.full_name, u.username, COALESCE(ts.wins, 0) AS value
            FROM users u
            JOIN termo_stats ts ON ts.user_id = u.user_id
            {visibility_join}
            WHERE {visibility_where} AND COALESCE(ts.wins, 0) > 0
            ORDER BY value DESC, ts.games_played ASC, u.user_id ASC
            LIMIT %s
        """
        params = (limit,)
    elif metric_key == "zenith":
        # Premium currency does not exist in the current Source economy yet.
        return []
    else:
        raise ValueError("unsupported_leaderboard_metric")

    rows = run(query, params, fetch="all") or []
    return [
        {
            "id": int(row.get("id") or 0),
            "rank": index,
            "full_name": str(row.get("full_name") or "").strip(),
            "username": str(row.get("username") or "").strip(),
            "avatar": None,
            "value": int(row.get("value") or 0),
        }
        for index, row in enumerate(rows, start=1)
        if int(row.get("id") or 0) > 0
    ]
