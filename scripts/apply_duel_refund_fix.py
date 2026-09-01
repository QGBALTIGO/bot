from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / "duel_repository.py"
TEST = ROOT / "tests" / "test_duel_refunds.py"

HELPER = '''def _refund_duel_entry_fees_locked(cur, duel: Dict[str, Any]) -> int:
    """Refund wager entry fees exactly once when a duel is cancelled."""

    if str(duel.get("mode") or "").strip().lower() != "wager":
        return 0
    if not bool(duel.get("entry_fee_applied")) or bool(duel.get("entry_fee_refunded")):
        return 0

    duel_id = int(duel.get("duel_id") or 0)
    entry_fee = max(0, int(duel.get("entry_fee") or 0))
    if duel_id <= 0 or entry_fee <= 0:
        return 0

    refunded = 0
    user_ids = {
        int(duel.get("challenger_user_id") or 0),
        int(duel.get("challenged_user_id") or 0),
    }
    for user_id in sorted(uid for uid in user_ids if uid > 0):
        cur.execute(
            """
            UPDATE users
            SET coins = coins + %s,
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING coins
            """,
            (entry_fee, user_id),
        )
        row = cur.fetchone() or {}
        if not row:
            continue

        balance_after = int(row.get("coins") or 0)
        _record_coin_tx_locked(
            cur,
            user_id,
            "duel_entry_refund",
            entry_fee,
            balance_after=balance_after,
            reference_id=duel_id,
            metadata={"duel_id": duel_id, "mode": "wager", "reason": "duel_cancelled"},
        )
        _adjust_duel_stats_locked(cur, user_id, coins_refunded=entry_fee)
        refunded += 1

    _update_duel_row(cur, duel_id, entry_fee_refunded=True)
    return refunded


'''

TEST_CONTENT = '''from __future__ import annotations

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
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = REPOSITORY.read_text(encoding="utf-8")
    if "def _refund_duel_entry_fees_locked" not in text:
        text = replace_once(
            text,
            "def _adjust_duel_stats_locked(\n",
            HELPER + "def _adjust_duel_stats_locked(\n",
            "refund helper",
        )
        text = replace_once(
            text,
            '''    reward_result = {"status": "none", "card_id": 0}\n    final_state = "cancelled" if cancelled else "completed"\n\n    if winner_user_id and loser_user_id and mode == "wager":\n''',
            '''    reward_result = {"status": "none", "card_id": 0}\n    final_state = "cancelled" if cancelled else "completed"\n    refunded_entry_fees = _refund_duel_entry_fees_locked(cur, duel) if cancelled else 0\n\n    if winner_user_id and loser_user_id and mode == "wager":\n''',
            "finalize refund",
        )
        text = replace_once(
            text,
            '''            "cancelled": bool(cancelled),\n            "reward": reward_result,\n''',
            '''            "cancelled": bool(cancelled),\n            "refunded_entry_fees": refunded_entry_fees,\n            "reward": reward_result,\n''',
            "finish event",
        )
        text = replace_once(
            text,
            '''                players_state = _safe_json_dict(duel.get("players_state"))\n                teams_state = _safe_json_dict(duel.get("teams_state"))\n                _release_duel_locks(cur, int(duel_id))\n''',
            '''                players_state = _safe_json_dict(duel.get("players_state"))\n                teams_state = _safe_json_dict(duel.get("teams_state"))\n                refunded_entry_fees = _refund_duel_entry_fees_locked(cur, duel)\n                _release_duel_locks(cur, int(duel_id))\n''',
            "manual cancel refund",
        )
        text = replace_once(
            text,
            '''                    payload={"reason": str(reason or "cancelled").strip()},\n''',
            '''                    payload={\n                        "reason": str(reason or "cancelled").strip(),\n                        "refunded_entry_fees": refunded_entry_fees,\n                    },\n''',
            "cancel event",
        )
        REPOSITORY.write_text(text, encoding="utf-8")

    TEST.parent.mkdir(parents=True, exist_ok=True)
    TEST.write_text(TEST_CONTENT, encoding="utf-8")
    print("duel refund fix applied")


if __name__ == "__main__":
    main()
