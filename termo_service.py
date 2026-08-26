from __future__ import annotations

from psycopg.rows import dict_row

from database import pool
from termo_repository import termo_stats


def get_termo_dashboard(user_id: int, limit: int = 10) -> dict:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT g.user_id,
                       COUNT(*) FILTER (WHERE g.status='win') AS wins,
                       COUNT(*) AS games,
                       AVG(g.attempts) FILTER (WHERE g.status='win') AS avg_attempts,
                       i.nickname,
                       i.telegram_username,
                       i.telegram_full_name
                FROM termo_games_v2 g
                LEFT JOIN user_identity_v2 i ON i.user_id=g.user_id
                WHERE g.mode='daily'
                  AND g.status IN ('win','loss','timeout')
                  AND COALESCE(i.private_profile,FALSE)=FALSE
                GROUP BY g.user_id,i.nickname,i.telegram_username,i.telegram_full_name
                ORDER BY wins DESC, avg_attempts ASC NULLS LAST, games DESC, g.user_id ASC
                LIMIT %s
                """,
                (max(1, min(int(limit), 50)),),
            )
            rows = cur.fetchall() or []

    ranking = []
    for position, row in enumerate(rows, start=1):
        username = str(row.get("telegram_username") or "").strip()
        display_name = (
            str(row.get("nickname") or "").strip()
            or str(row.get("telegram_full_name") or "").strip()
            or (f"@{username}" if username else "Navegante")
        )
        ranking.append(
            {
                "position": position,
                "display_name": display_name,
                "wins": int(row.get("wins") or 0),
                "games": int(row.get("games") or 0),
                "avg_attempts": round(float(row.get("avg_attempts") or 0), 2)
                if row.get("avg_attempts") is not None
                else None,
            }
        )

    return {
        "stats": termo_stats(int(user_id)),
        "ranking": ranking,
    }
