"""Behavioral regressions for the native-profile performance repair.

Load individual functions without the production database bootstrap. Assertions
exercise the real function bodies with deterministic database/identity doubles.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]


def load_function(path, name, **dependencies):
    tree = ast.parse((ROOT / path).read_text())
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    # Future annotations preserve production signatures without importing the runtime.
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
    namespace = dict(dependencies)
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), namespace)
    return namespace[name]


def test_profile_join_reads_existing_account_only_once(monkeypatch):
    calls, creations = [], []
    row = dict(user_id=77, nickname='Akira', coins=4, level=6, notifications_enabled=None)
    def run(sql, params, fetch):
        calls.append((sql, params, fetch))
        return row
    monkeypatch.setitem(sys.modules, 'database_core', SimpleNamespace(run=run))
    monkeypatch.setitem(sys.modules, 'database', SimpleNamespace(create_or_get_user=creations.append))
    fn = load_function('webapp_services/profile_overview.py', 'load_menu_user_rows')
    user, progress, settings = fn(77)
    assert len(calls) == 1 and not creations
    assert 'LEFT JOIN user_progress' in calls[0][0]
    assert 'LEFT JOIN user_profile_settings' in calls[0][0]
    assert calls[0][1] == (77,)
    assert user['coins'] == 4 and progress['level'] == 6
    assert settings['notifications_enabled'] is True


def test_missing_account_still_initialized(monkeypatch):
    rows = iter([None, {'user_id': 77}])
    created = []
    monkeypatch.setitem(sys.modules, 'database_core', SimpleNamespace(run=lambda *a, **k: next(rows)))
    monkeypatch.setitem(sys.modules, 'database', SimpleNamespace(create_or_get_user=created.append))
    fn = load_function('webapp_services/profile_overview.py', 'load_menu_user_rows')
    assert fn(77)[0]['user_id'] == 77
    assert created == [77]


def favorite_handler(monkeypatch, owned=True, resolver=None):
    writes, reads = [], []
    def run(sql, args, fetch):
        reads.append((sql, args, fetch))
        return {'owned': 1} if owned else None
    monkeypatch.setitem(sys.modules, 'database_core', SimpleNamespace(run=run))
    monkeypatch.setitem(sys.modules, 'cards_service', SimpleNamespace(get_character_by_id=lambda cid: {'name': 'Akira', 'anime': 'Teste', 'image': 'https://example.com/a.jpg'}))
    fn = load_function('webapp_routes/profile_collection.py', 'api_menu_favorite',
        Body=lambda *a, **k: None, Header=lambda *a, **k: '', JSONResponse=JSONResponse,
        _resolve_webapp_user=resolver or (lambda **kwargs: {'user_id': 77}),
        set_profile_favorite=lambda uid, cid: writes.append((uid, cid)))
    return fn, reads, writes


def test_favorite_uses_verified_owner_and_returns_profile_contract(monkeypatch):
    fn, reads, writes = favorite_handler(monkeypatch)
    result = fn({'character_id': 23}, 'signed', '')
    assert writes == [(77, 23)]
    assert len(reads) == 1 and reads[0][1] == (77, 23)
    assert 'quantity>0' in reads[0][0]
    assert result['favorite']['id'] == 23 and result['favorite']['name'] == 'Akira'


def test_unowned_character_rejected_without_write(monkeypatch):
    fn, reads, writes = favorite_handler(monkeypatch, owned=False)
    response = fn({'character_id': 23}, 'signed', '')
    assert response.status_code == 403 and not writes and len(reads) == 1


@pytest.mark.parametrize('payload', [{}, {'character_id': 0}, {'character_id': -1}, {'character_id': 'invalid'}])
def test_bad_favorite_id_never_clears_or_writes(monkeypatch, payload):
    fn, reads, writes = favorite_handler(monkeypatch)
    assert fn(payload, 'signed', '').status_code == 400
    assert not reads and not writes


def test_favorite_removal_requires_explicit_null(monkeypatch):
    fn, reads, writes = favorite_handler(monkeypatch)
    assert fn({'character_id': None}, 'signed', '') == {'ok': True, 'favorite': None}
    assert writes == [(77, None)] and not reads


def test_favorite_authentication_precedes_reads_and_removal(monkeypatch):
    def reject(**kwargs):
        raise HTTPException(401, 'unverified')
    fn, reads, writes = favorite_handler(monkeypatch, resolver=reject)
    with pytest.raises(HTTPException):
        fn({'character_id': None}, '', '')
    assert not reads and not writes


def test_profile_settings_read_does_not_write_existing_rows():
    calls = []
    fn = load_function('database_profile.py', 'get_profile_settings', _run=lambda *a, **k: {'nickname': 'Akira'}, ensure_profile_settings_row=calls.append)
    assert fn(77)['nickname'] == 'Akira' and not calls


def test_gatekeeper_read_does_not_reinsert_existing_user():
    created = []
    fn = load_function('utils/gatekeeper.py', '_load_user_status', get_user_status=lambda uid: {'terms_accepted': True}, create_or_get_user=created.append)
    assert fn(77)['terms_accepted'] is True and not created


def test_existing_progress_read_has_no_insert():
    calls = []
    fn = load_function('database.py', 'get_progress_row', _run=lambda *a, **k: {'xp': 8}, ensure_progress_row=calls.append)
    assert fn(77)['xp'] == 8 and not calls


def test_identity_upsert_keeps_wallet_out_of_conflict_update():
    calls = []
    fn = load_function('database.py', 'touch_user_identity', _run=lambda *a, **k: calls.append(a), DADO_INITIAL_BALANCE=12, _slot_number_from_dt=lambda x: 99, _now_sp=lambda: None)
    fn(77, 'user', 'Nome')
    assert len(calls) == 1
    sql, args = calls[0]
    updates = sql.split('DO UPDATE SET')[1]
    assert 'dado_balance =' not in updates and 'coins' not in updates
    assert 'IS DISTINCT FROM' in updates and args == (77, 'user', 'Nome', 12, 99)


def test_secure_init_offloads_database_io():
    source = (ROOT / 'webapp_routes/aninexus_compat.py').read_text()
    tree = ast.parse(source)
    secure_init = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'secure_init')
    assert any(isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'to_thread' for n in ast.walk(secure_init))


def test_asset_cache_only_for_fingerprinted_success(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from webapp_routes.aninexus_runtime import FingerprintedStaticFiles
    (tmp_path / 'index-Abcd1234.js').write_text('export const x=1;')
    (tmp_path / 'plain.js').write_text('export const x=2;')
    app = FastAPI()
    app.mount('/assets', FingerprintedStaticFiles(directory=str(tmp_path)))
    with TestClient(app) as client:
        assert 'immutable' in client.get('/assets/index-Abcd1234.js').headers['cache-control']
        assert 'immutable' not in client.get('/assets/plain.js').headers.get('cache-control', '')
        assert client.get('/assets/missing-Abcd1234.js').status_code == 404


@pytest.mark.asyncio
async def test_telegram_image_conversion_is_off_event_loop(monkeypatch):
    import threading
    from utils import telegram_photo
    loop_thread = threading.get_ident()
    workers = []
    async def fetch(url, **kwargs):
        return b'fake', 'image/jpeg', url
    def encode(content, **kwargs):
        workers.append(threading.get_ident())
        return b'encoded'
    async def reply(**kwargs):
        return SimpleNamespace(photo=[])
    monkeypatch.setattr(telegram_photo, 'fetch_compatible_public_image', fetch)
    monkeypatch.setattr(telegram_photo, '_jpeg_bytes', encode)
    await telegram_photo.reply_photo_from_url(SimpleNamespace(reply_photo=reply), 'https://example.com/thread-test.jpg')
    assert workers and workers[0] != loop_thread


@pytest.mark.asyncio
async def test_webapp_portrait_conversion_is_off_event_loop(monkeypatch):
    import threading
    from webapp_routes import image_proxy
    loop_thread = threading.get_ident()
    workers = []
    async def fetch(url, **kwargs):
        return b'fake', 'image/jpeg', url
    def crop(content):
        workers.append(threading.get_ident())
        return b'portrait', {}
    monkeypatch.setattr(image_proxy, 'fetch_compatible_public_image', fetch)
    monkeypatch.setattr(image_proxy, 'crop_portrait_bytes', crop)
    response = await image_proxy.api_image_proxy('https://example.com/portrait-test.jpg', 'portrait')
    assert response.body == b'portrait' and workers[0] != loop_thread


def test_companion_overview_uses_single_read_and_parses_timestamps():
    from contextlib import contextmanager
    from datetime import datetime, timezone
    calls, initializations = [], []
    row = {'pets': [{'pet_id': 'fluffy_fox'}], 'eggs': [{'hatch_at': '2026-09-25T12:00:00+00:00'}]}
    class DB:
        @contextmanager
        def connection(self):
            yield self
        @contextmanager
        def cursor(self, **kwargs):
            yield self
        def execute(self, sql, params):
            calls.append((sql, params))
        def fetchone(self):
            return row
        def commit(self):
            pass
    fn = load_function('database_aninexus_pets.py', 'get_companion_overview',
        _ensure_user_initialized=initializations.append, pool=DB(), dict_row=None,
        datetime=datetime, _pet_payload=lambda value: value, _egg_payload=lambda value: value)
    pets, eggs = fn(77)
    assert initializations == [77] and len(calls) == 1 and calls[0][1] == (77, 77)
    assert pets[0]['pet_id'] == 'fluffy_fox'
    assert eggs[0]['hatch_at'] == datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
