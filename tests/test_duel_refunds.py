from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def load_repository_module():
    psycopg = types.ModuleType("psycopg")
    psycopg.sql = types.SimpleNamespace(SQL=lambda value: value, Identifier=lambda value: value)
    psycopg_rows = types.ModuleType("psycopg.rows")
    psycopg_rows.dict_row = object()
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = psycopg_rows

    database = types.ModuleType("database")
    database.create_or_get_user = lambda *args, **kwargs: None
    database.pool = object()
    database.touch_user_identity = lambda *args, **kwargs: None

    engine = types.ModuleType("duel_engine")
    engine.TEAM_SIZE = 3
    for name in (
        "build_team_snapshot",
        "choose_reward_card",
        "find_team_entry",
        "format_team_lines",
        "get_alive_slots",
        "is_team_eliminated",
        "resolve_round",
        "validate_team_selection",
    ):
        setattr(engine, name, lambda *args, **kwargs: None)

    sys.modules["database"] = database
    sys.modules["duel_engine"] = engine

    path = Path(__file__).resolve().parents[1] / "duel_repository.py"
    spec = importlib.util.spec_from_file_location("duel_repository_refund_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self):
        self.executions = []
        self._row = None

    def execute(self, query, params=()):
        query_text = str(query)
        self.executions.append((query_text, tuple(params)))
        if "UPDATE users" in query_text and "RETURNING coins" in query_text:
            self._row = {"coins": 50 + int(params[0])}
        else:
            self._row = None

    def fetchone(self):
        row = self._row
        self._row = None
        return row


def test_cancelled_wager_refunds_both_players_once():
    repo = load_repository_module()
    cursor = FakeCursor()
    transactions = []
    stats = []
    duel_updates = []

    repo._record_coin_tx_locked = lambda *args, **kwargs: transactions.append((args, kwargs))
    repo._adjust_duel_stats_locked = lambda *args, **kwargs: stats.append((args, kwargs))
    repo._update_duel_row = lambda *args, **kwargs: duel_updates.append((args, kwargs))

    duel = {
        "duel_id": 77,
        "mode": "wager",
        "entry_fee": 25,
        "entry_fee_applied": True,
        "entry_fee_refunded": False,
        "challenger_user_id": 10,
        "challenged_user_id": 20,
    }

    assert repo._refund_duel_entry_fees_locked(cursor, duel) == 2
    assert [params for query, params in cursor.executions if "UPDATE users" in query] == [(25, 10), (25, 20)]
    assert len(transactions) == 2
    assert all(call[1]["reference_id"] == 77 for call in transactions)
    assert [call[1]["coins_refunded"] for call in stats] == [25, 25]
    assert duel_updates[-1][1] == {"entry_fee_refunded": True}


def test_refund_is_noop_when_already_refunded_or_not_wager():
    repo = load_repository_module()
    cursor = FakeCursor()

    assert repo._refund_duel_entry_fees_locked(
        cursor,
        {
            "duel_id": 1,
            "mode": "wager",
            "entry_fee": 25,
            "entry_fee_applied": True,
            "entry_fee_refunded": True,
        },
    ) == 0
    assert repo._refund_duel_entry_fees_locked(
        cursor,
        {
            "duel_id": 2,
            "mode": "friendly",
            "entry_fee": 25,
            "entry_fee_applied": True,
            "entry_fee_refunded": False,
        },
    ) == 0
    assert cursor.executions == []
