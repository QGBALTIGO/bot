"""Regression coverage for malformed inputs and expired Telegram callbacks."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest
from webapp_services.memory import normalize_memory_finish_input

ROOT = Path(__file__).resolve().parents[1]
INVALID = [None, True, False, [], {}, 1.5, float('inf'), '', 'not-an-integer', '1e3', '9' * 100, -1, 0]

@pytest.mark.parametrize('value', INVALID)
@pytest.mark.parametrize('field,message', [('time_ms', 'Tempo invalido.'), ('moves', 'Quantidade de jogadas invalida.')])
def test_memory_rejects_invalid_numeric_types_without_server_error(value, field, message):
    payload = {'level': 'easy', 'time_ms': 1000, 'moves': 12, field: value}
    with pytest.raises(ValueError) as exc:
        normalize_memory_finish_input(payload)
    assert str(exc.value) == message


def load_function(name, namespace):
    tree = ast.parse((ROOT / 'commands/termo.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    source = 'from __future__ import annotations\n' + ast.unparse(fn)
    exec(compile(source, 'commands/termo.py', 'exec'), namespace)
    return namespace[name]

@pytest.mark.parametrize('message', ['Query is too old and response timeout expired or query id is invalid', 'Query id is invalid'])
def test_expired_termo_callback_does_not_continue_to_mutation(message):
    touch = Mock(side_effect=AssertionError('must not touch account'))
    fn = load_function('termo_callback', {'asyncio': asyncio, 'BadRequest': BadRequest, '_touch_identity': touch})
    query = SimpleNamespace(answer=AsyncMock(side_effect=BadRequest(message)))
    asyncio.run(fn(SimpleNamespace(callback_query=query), None))
    touch.assert_not_called()


def test_unknown_telegram_error_is_not_silently_swallowed():
    fn = load_function('termo_callback', {'asyncio': asyncio, 'BadRequest': BadRequest})
    query = SimpleNamespace(answer=AsyncMock(side_effect=BadRequest('Unexpected API error')))
    with pytest.raises(BadRequest):
        asyncio.run(fn(SimpleNamespace(callback_query=query), None))


def test_hint_does_not_reveal_or_mark_used_when_balance_is_insufficient():
    charge = Mock(return_value={'ok': False, 'error': 'no_coins'})
    fn = load_function('_give_hint', {'asyncio': asyncio, 'purchase_termo_hint_atomic': charge, 'HINT_COST_COINS': 12, 'TIME_LIMIT_SECS': 300})
    msg = SimpleNamespace(reply_text=AsyncMock())
    game = {'mode': 'daily', 'id': 1, 'hint': 'SECRET HINT', 'hint_used': False}
    asyncio.run(fn(msg, game, 77))
    assert game['hint_used'] is False
    assert 'SECRET HINT' not in str(msg.reply_text.call_args)
    assert '12 Coins' in str(msg.reply_text.call_args)
