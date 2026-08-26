from __future__ import annotations

from typing import Any, Dict, List

from psycopg.rows import dict_row

from database import pool


DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _limit(value: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, value))


def _display_expr() -> str:
    return """
    COALESCE(
        NULLIF(BTRIM(i.nickname), ''),
        NULLIF(BTRIM(i.telegram_full_name), ''),
        CASE
            WHEN NULLIF(BTRIM(i.telegram_username), '') IS NOT NULL
            THEN '@' || BTRIM(i.telegram_username)
            ELSE 'Jogador'
        END
    )
    """


def _country_expr() -> str:
    return "COALESCE(NULLIF(BTRIM(i.country_code), ''), '')"


def _public_filter() -> str:
    # Identity rows are created lazily. Missing identity means the user has not
    # opted into private profile and can still appear with the generic fallback.
    return "COALESCE(i.private_profile, FALSE) = FALSE"


def get_general_leaderboard(limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    limit = _limit(limit)
    display = _display_expr()
    country = _country_expr()
    public_filter = _public_filter()

    sql = f"""
    WITH collection AS (
        SELECT
            user_id,
            COUNT(*) FILTER (WHERE quantity > 0)::BIGINT AS unique_cards,
            COALESCE(SUM(quantity) FILTER (WHERE quantity > 0), 0)::BIGINT AS total_copies
        FROM user_card_collection
        GROUP BY user_id
    ),
    users_union AS (
        SELECT user_id FROM user_progress
        UNION
        SELECT user_id FROM collection
    ),
    metrics AS (
        SELECT
            u.user_id,
            {display} AS display_name,
            {country} AS country_code,
            COALESCE(p.level, 1)::INTEGER AS level,
            COALESCE(p.xp, 0)::BIGINT AS xp,
            COALESCE(c.unique_cards, 0)::BIGINT AS unique_cards,
            COALESCE(c.total_copies, 0)::BIGINT AS total_copies
        FROM users_union u
        LEFT JOIN user_progress p ON p.user_id = u.user_id
        LEFT JOIN collection c ON c.user_id = u.user_id
        LEFT JOIN user_identity_v2 i ON i.user_id = u.user_id
        WHERE {public_filter}
    ),
    scored AS (
        SELECT
            *,
            PERCENT_RANK() OVER (ORDER BY level ASC, xp ASC) AS progress_pct,
            PERCENT_RANK() OVER (ORDER BY unique_cards ASC, total_copies ASC) AS collection_pct
        FROM metrics
    )
    SELECT
        user_id,
        display_name,
        country_code,
        level,
        xp,
        unique_cards,
        total_copies,
        ROUND(((progress_pct * 0.55 + collection_pct * 0.45) * 100)::NUMERIC, 2) AS score
    FROM scored
    ORDER BY score DESC, level DESC, xp DESC, unique_cards DESC, total_copies DESC, user_id ASC
    LIMIT %s
    """

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (limit,))
            return [dict(row) for row in (cur.fetchall() or [])]


def get_level_leaderboard(limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    limit = _limit(limit)
    display = _display_expr()
    country = _country_expr()
    public_filter = _public_filter()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT
                    p.user_id,
                    {display} AS display_name,
                    {country} AS country_code,
                    p.level,
                    p.xp,
                    p.total_actions
                FROM user_progress p
                LEFT JOIN user_identity_v2 i ON i.user_id = p.user_id
                WHERE {public_filter}
                ORDER BY p.level DESC, p.xp DESC, p.total_actions DESC, p.user_id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in (cur.fetchall() or [])]


def get_collection_leaderboard(limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    limit = _limit(limit)
    display = _display_expr()
    country = _country_expr()
    public_filter = _public_filter()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT
                    c.user_id,
                    {display} AS display_name,
                    {country} AS country_code,
                    COUNT(*) FILTER (WHERE c.quantity > 0)::BIGINT AS unique_cards,
                    COALESCE(SUM(c.quantity) FILTER (WHERE c.quantity > 0), 0)::BIGINT AS total_copies
                FROM user_card_collection c
                LEFT JOIN user_identity_v2 i ON i.user_id = c.user_id
                WHERE {public_filter}
                GROUP BY c.user_id, i.nickname, i.telegram_full_name, i.telegram_username, i.country_code
                HAVING COUNT(*) FILTER (WHERE c.quantity > 0) > 0
                ORDER BY unique_cards DESC, total_copies DESC, c.user_id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in (cur.fetchall() or [])]


def get_coin_leaderboard(limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    limit = _limit(limit)
    display = _display_expr()
    country = _country_expr()
    public_filter = _public_filter()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT
                    w.user_id,
                    {display} AS display_name,
                    {country} AS country_code,
                    w.coins
                FROM game_wallets w
                LEFT JOIN user_identity_v2 i ON i.user_id = w.user_id
                WHERE {public_filter}
                ORDER BY w.coins DESC, w.user_id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in (cur.fetchall() or [])]


def get_user_positions(user_id: int) -> Dict[str, int]:
    user_id = int(user_id)
    public_filter = _public_filter()

    sql = f"""
    WITH collection AS (
        SELECT
            user_id,
            COUNT(*) FILTER (WHERE quantity > 0)::BIGINT AS unique_cards,
            COALESCE(SUM(quantity) FILTER (WHERE quantity > 0), 0)::BIGINT AS total_copies
        FROM user_card_collection
        GROUP BY user_id
    ),
    public_users AS (
        SELECT u.user_id
        FROM (
            SELECT user_id FROM user_progress
            UNION
            SELECT user_id FROM collection
            UNION
            SELECT user_id FROM game_wallets
        ) u
        LEFT JOIN user_identity_v2 i ON i.user_id = u.user_id
        WHERE {public_filter}
    ),
    level_rank AS (
        SELECT
            p.user_id,
            RANK() OVER (ORDER BY p.level DESC, p.xp DESC, p.total_actions DESC, p.user_id ASC) AS pos
        FROM user_progress p
        JOIN public_users pu ON pu.user_id = p.user_id
    ),
    collection_rank AS (
        SELECT
            c.user_id,
            RANK() OVER (ORDER BY c.unique_cards DESC, c.total_copies DESC, c.user_id ASC) AS pos
        FROM collection c
        JOIN public_users pu ON pu.user_id = c.user_id
    ),
    coin_rank AS (
        SELECT
            w.user_id,
            RANK() OVER (ORDER BY w.coins DESC, w.user_id ASC) AS pos
        FROM game_wallets w
        JOIN public_users pu ON pu.user_id = w.user_id
    )
    SELECT
        COALESCE((SELECT pos FROM level_rank WHERE user_id = %s), 0)::INTEGER AS level_pos,
        COALESCE((SELECT pos FROM collection_rank WHERE user_id = %s), 0)::INTEGER AS collection_pos,
        COALESCE((SELECT pos FROM coin_rank WHERE user_id = %s), 0)::INTEGER AS coin_pos
    """

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (user_id, user_id, user_id))
            row = cur.fetchone() or {}
            return {
                "level": int(row.get("level_pos") or 0),
                "collection": int(row.get("collection_pos") or 0),
                "coins": int(row.get("coin_pos") or 0),
            }
