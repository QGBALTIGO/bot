from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database.py"
CORE = ROOT / "database_core.py"


def test_database_monolith_uses_shared_postgres_core() -> None:
    legacy = DATABASE.read_text(encoding="utf-8")

    assert "from database_core import DATABASE_URL, pool, run as _run" in legacy
    assert "ConnectionPool(" not in legacy
    assert "def _run(" not in legacy
    assert "pool = ConnectionPool(" not in legacy


def test_database_core_preserves_pool_contract() -> None:
    core = CORE.read_text(encoding="utf-8")

    assert 'DATABASE_URL = os.getenv("DATABASE_URL", "").strip()' in core
    assert 'raise RuntimeError("DATABASE_URL não encontrado nas variáveis de ambiente.")' in core
    # Pool sizes became environment-configurable before the native UI migration.
    # Assert the current contract rather than the historical hard-coded values.
    assert "min_size=DATABASE_POOL_MIN_SIZE" in core
    assert "max_size=DATABASE_POOL_MAX_SIZE" in core
    assert "timeout=DATABASE_POOL_TIMEOUT_SECONDS" in core
    assert 'os.getenv("DATABASE_POOL_MIN_SIZE", "2")' in core
    assert 'os.getenv("DATABASE_POOL_MAX_SIZE", "16")' in core
    assert 'os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "10")' in core


def test_database_core_preserves_run_transaction_semantics() -> None:
    core = CORE.read_text(encoding="utf-8")

    assert "with pool.connection() as conn:" in core
    assert "with conn.cursor(row_factory=dict_row) as cur:" in core
    assert 'if fetch == "one":' in core
    assert 'if fetch == "all":' in core
    assert "conn.commit()" in core
    assert "conn.rollback()" in core
    assert "raise" in core


def test_database_keeps_direct_pool_compatibility() -> None:
    legacy = DATABASE.read_text(encoding="utf-8")

    # Várias operações transacionais especializadas ainda usam o pool diretamente.
    # O primeiro corte precisa manter esse símbolo visível em database.py.
    assert "pool.connection()" in legacy
