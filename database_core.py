from __future__ import annotations

import os
from typing import Any, Tuple

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrado nas variáveis de ambiente.")

DATABASE_POOL_MIN_SIZE = max(
    1,
    int(os.getenv("DATABASE_POOL_MIN_SIZE", "2")),
)
DATABASE_POOL_MAX_SIZE = max(
    DATABASE_POOL_MIN_SIZE,
    int(os.getenv("DATABASE_POOL_MAX_SIZE", "16")),
)
DATABASE_POOL_TIMEOUT_SECONDS = max(
    1.0,
    float(os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "10")),
)

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=DATABASE_POOL_MIN_SIZE,
    max_size=DATABASE_POOL_MAX_SIZE,
    timeout=DATABASE_POOL_TIMEOUT_SECONDS,
)


def run(sql: str, params: Tuple[Any, ...] = (), fetch: str = "none"):
    """Executa SQL no pool legado preservando commit/rollback e row_factory."""

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(sql, params)

                if fetch == "one":
                    row = cur.fetchone()
                    conn.commit()
                    return row

                if fetch == "all":
                    rows = cur.fetchall() or []
                    conn.commit()
                    return rows

                conn.commit()
                return None

            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
