from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


def load_database_module(monkeypatch):
    psycopg = types.ModuleType("psycopg")
    psycopg_rows = types.ModuleType("psycopg.rows")
    psycopg_rows.dict_row = object()
    psycopg_errors = types.ModuleType("psycopg.errors")
    psycopg_errors.UndefinedTable = type("UndefinedTable", (Exception,), {})
    psycopg_errors.UniqueViolation = type("UniqueViolation", (Exception,), {})
    psycopg.rows = psycopg_rows
    psycopg.errors = psycopg_errors

    psycopg_pool = types.ModuleType("psycopg_pool")

    class DummyConnectionPool:
        def __init__(self, *args, **kwargs):
            pass

    psycopg_pool.ConnectionPool = DummyConnectionPool

    monkeypatch.setitem(sys.modules, "psycopg", psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", psycopg_rows)
    monkeypatch.setitem(sys.modules, "psycopg.errors", psycopg_errors)
    monkeypatch.setitem(sys.modules, "psycopg_pool", psycopg_pool)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")

    path = Path(__file__).resolve().parents[1] / "database.py"
    spec = importlib.util.spec_from_file_location("database_account_deletion_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self, *, fail_on: str = "", account_exists: bool = True):
        self.executions: list[tuple[str, tuple]] = []
        self.fail_on = fail_on
        self.account_exists = account_exists
        self._one = None
        self._all = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        query_text = " ".join(str(query).split())
        params_tuple = tuple(params)
        self.executions.append((query_text, params_tuple))

        if self.fail_on and self.fail_on in query_text:
            raise RuntimeError("injected database failure")

        self._one = None
        self._all = None

        if query_text.startswith("SELECT user_id FROM users"):
            self._one = {"user_id": 10} if self.account_exists else None
        elif "FROM duels" in query_text and query_text.endswith("FOR UPDATE"):
            self._all = [
                {
                    "duel_id": 77,
                    "challenger_user_id": 10,
                    "challenged_user_id": 20,
                    "state": "in_progress",
                    "mode": "wager",
                    "entry_fee": 25,
                    "entry_fee_applied": True,
                    "entry_fee_refunded": False,
                }
            ]
        elif "FROM user_messages" in query_text and query_text.endswith("FOR UPDATE"):
            self._all = [
                {
                    "message_id": 88,
                    "from_user_id": 30,
                    "coin_cost": 7,
                }
            ]
        elif "FROM purchase_intents" in query_text and query_text.endswith("FOR UPDATE"):
            self._all = [
                {
                    "cakto_order_id": "order-1",
                    "cakto_subscription_id": "subscription-1",
                }
            ]
        elif query_text.startswith("SELECT to_regclass"):
            relation_name = str(params_tuple[0])
            self._one = {"relation_name": relation_name}
        elif query_text.startswith("UPDATE users") and "RETURNING coins" in query_text:
            amount, target_id = params_tuple
            self._one = {"coins": 100 + int(amount) + int(target_id)}

    def fetchone(self):
        row = self._one
        self._one = None
        return row

    def fetchall(self):
        rows = self._all or []
        self._all = None
        return rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self.cursor_instance = cursor
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, **kwargs):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakePool:
    def __init__(self, connection: FakeConnection):
        self.connection_instance = connection
        self.connection_calls = 0

    def connection(self):
        self.connection_calls += 1
        return self.connection_instance


def query_texts(cursor: FakeCursor) -> list[str]:
    return [query for query, _ in cursor.executions]


def test_delete_user_account_is_atomic_comprehensive_and_refunds_others(monkeypatch):
    database = load_database_module(monkeypatch)
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    pool = FakePool(connection)
    database.pool = pool

    result = database.delete_user_account(10)

    assert result == {
        "ok": True,
        "user_id": 10,
        "account_existed": True,
        "refunded_duels": 1,
        "refunded_messages": 1,
    }
    assert pool.connection_calls == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0

    executions = cursor.executions
    assert (25, 20) in [params for query, params in executions if query.startswith("UPDATE users")]
    assert (7, 30) in [params for query, params in executions if query.startswith("UPDATE users")]

    sql = "\n".join(query_texts(cursor))
    for table in (
        "duels",
        "duel_rounds",
        "duel_events",
        "duel_user_presence",
        "user_xcard_locks",
        "card_trades",
        "user_messages",
        "user_message_reports",
        "user_message_blocks",
        "user_message_settings",
        "user_card_collection",
        "user_xcard_collection",
        "user_progress",
        "termo_games",
        "termo_stats",
        "termo_attempt_distribution",
        "termo_used_words",
        "dice_rolls",
        "media_requests",
        "webapp_reports",
        "user_collection_profile",
        "user_profile_settings",
        "shop_transactions",
        "shop_card_sales",
        "user_shop_xcard_daily_purchases",
        "daily_rewards",
        "memory_level_bests",
        "user_referrals",
        "telegram_outbox",
        "webapp_auth_requests",
        "channel_verification_requests",
        "users",
    ):
        assert table in sql

    assert "duel_entry_refund_account_deleted" in sql
    assert "message_refund_account_deleted" in sql
    assert "UPDATE purchase_intents SET telegram_user_id = 0" in sql
    assert "UPDATE affiliate_commissions" in sql
    assert "UPDATE card_image_suggestions" in sql
    assert "UPDATE card_work_requests" in sql
    assert "UPDATE capture_spawns" in sql
    assert "UPDATE global_character_images" in sql


def test_delete_user_account_rolls_back_everything_on_failure(monkeypatch):
    database = load_database_module(monkeypatch)
    cursor = FakeCursor(fail_on="DELETE FROM user_progress")
    connection = FakeConnection(cursor)
    database.pool = FakePool(connection)

    with pytest.raises(RuntimeError, match="injected database failure"):
        database.delete_user_account(10)

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert not any(query == "DELETE FROM users WHERE user_id = %s" for query in query_texts(cursor))


def test_delete_all_users_uses_one_transaction_and_clears_all_gameplay_state(monkeypatch):
    database = load_database_module(monkeypatch)
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    pool = FakePool(connection)
    database.pool = pool

    assert database.delete_all_users() == {"ok": True}
    assert pool.connection_calls == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0

    sql = "\n".join(query_texts(cursor))
    assert "TRUNCATE TABLE" in sql
    for table in (
        "duels",
        "card_trades",
        "user_messages",
        "user_card_collection",
        "user_xcard_collection",
        "daily_rewards",
        "memory_level_bests",
        "capture_spawns",
        "users",
    ):
        assert table in sql
    assert "UPDATE purchase_intents" not in sql
    assert "UPDATE affiliate_commissions" not in sql
