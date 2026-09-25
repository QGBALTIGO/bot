from __future__ import annotations
from contextlib import contextmanager
import re
import sys
from types import SimpleNamespace

import pytest
import psycopg as psycopg_driver
import psycopg.rows as psycopg_rows
from fastapi import HTTPException
from psycopg import IntegrityError
from webapp_routes.native_webapps import change_nickname_atomic


class DatabaseDouble:
    def __init__(self, coins=10, taken=False, fail_on=None):
        self.coins = coins
        self.taken = taken
        self.fail_on = fail_on
        self.calls = []
        self.committed = False
        self.rolled_back = False

    @contextmanager
    def connection(self):
        yield self

    @contextmanager
    def transaction(self):
        try:
            yield self
            self.committed = True
        except Exception:
            self.rolled_back = True
            raise

    @contextmanager
    def cursor(self, **_kwargs):
        yield self

    def execute(self, sql, args):
        self.calls.append((sql, args))
        if self.fail_on and self.fail_on in sql:
            raise IntegrityError("synthetic constraint failure")

    def fetchone(self):
        sql = self.calls[-1][0]
        if sql.startswith("SELECT coins"):
            return {"coins": self.coins}
        if sql.startswith("SELECT user_id"):
            return {"user_id": 88} if self.taken else None
        return None


def configure(monkeypatch, **kwargs):
    db = DatabaseDouble(**kwargs)
    # Older tests replace sys.modules without restoring the driver. Keep this
    # fixture self-contained while using the real exception and row factory.
    monkeypatch.setitem(sys.modules, "psycopg", psycopg_driver)
    monkeypatch.setitem(sys.modules, "psycopg.rows", psycopg_rows)
    monkeypatch.setitem(sys.modules, "database_core", SimpleNamespace(pool=db))
    monkeypatch.setitem(
        sys.modules,
        "webapp_routes.profile_settings",
        SimpleNamespace(
            valid_menu_nickname=lambda value: bool(
                re.fullmatch(r"[A-Z][A-Za-z0-9_]{3,16}", value)
            )
        ),
    )
    return db


def test_nickname_and_coins_change_in_one_transaction(monkeypatch):
    db = configure(monkeypatch)
    result = change_nickname_atomic(77, "AkiraNovo")
    assert result == {"ok": True, "nickname": "AkiraNovo", "coins": 7}
    assert db.committed and not db.rolled_back
    sql = [row[0] for row in db.calls]
    assert "FOR UPDATE" in sql[0]
    assert any("pg_advisory_xact_lock" in statement for statement in sql)
    assert sql.index(
        next(x for x in sql if x.startswith("INSERT INTO user_profile_settings"))
    ) < sql.index(next(x for x in sql if x.startswith("UPDATE users")))
    assert sum(x.startswith("UPDATE users") for x in sql) == 1
    assert any(x.startswith("INSERT INTO shop_transactions") for x in sql)


@pytest.mark.parametrize("kwargs", [{"coins": 2}, {"taken": True}])
def test_rejected_nickname_never_debits_coins(monkeypatch, kwargs):
    db = configure(monkeypatch, **kwargs)
    with pytest.raises(HTTPException) as error:
        change_nickname_atomic(77, "AkiraNovo")
    assert error.value.status_code == 409
    assert db.rolled_back and not db.committed
    assert not any(sql.startswith("UPDATE users") for sql, _ in db.calls)


def test_failure_after_debit_rolls_back_everything(monkeypatch):
    db = configure(monkeypatch, fail_on="INSERT INTO shop_transactions")
    with pytest.raises(HTTPException):
        change_nickname_atomic(77, "AkiraNovo")
    assert db.rolled_back and not db.committed


@pytest.mark.parametrize("nickname", ["abc", "invalid", "A<>bad", "A" * 18, "A B C"])
def test_invalid_nickname_cannot_start_transaction(monkeypatch, nickname):
    db = configure(monkeypatch)
    with pytest.raises(HTTPException) as error:
        change_nickname_atomic(77, nickname)
    assert error.value.status_code == 400
    assert not db.calls
