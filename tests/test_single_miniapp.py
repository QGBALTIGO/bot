"""Canonical launch URLs and menu repair. No Telegram account or live database used."""
from __future__ import annotations
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit, parse_qs

import pytest
from telegram import MenuButtonWebApp, WebAppInfo
from utils.miniapp_links import miniapp_entrypoint, miniapp_url
from utils.miniapp_menu import synchronize_menu, MiniAppMenuSync, refresh_private_menu

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(autouse=True)
def env(monkeypatch):
    for name in ['BASE_URL','PUBLIC_BASE_URL','WEBAPP_URL','MINIAPP_URL']:
        monkeypatch.setenv(name, 'https://old-ui.invalid/shop?uid=1')
    monkeypatch.setenv('SOURCE_MINIAPP_URL', 'https://source.invalid/menu')

@pytest.mark.parametrize('tab', ['profile','shop','cards','dado','settings','album','requests','memory','subscription','terms'])
def test_all_buttons_have_one_entrypoint(tab):
    parsed = urlsplit(miniapp_url(tab, uid=42, user_id=9, token='not-exported'))
    assert (parsed.scheme, parsed.netloc, parsed.path) == ('https','source.invalid','/menu')
    assert parsed.fragment == tab and parsed.query == ''


def test_params_survive_without_identity_in_the_url():
    parsed=urlsplit(miniapp_url('cards', anime_id=21, q='One Piece & teste', uid=42))
    assert parse_qs(parsed.query)=={'anime_id':['21'], 'q':['One Piece & teste']}

@pytest.mark.parametrize('url',['http://unsafe.invalid','https://user:secret@source.invalid','javascript:evil()', '//source.invalid'])
def test_unsafe_config_fails_closed(monkeypatch,url):
    monkeypatch.setenv('SOURCE_MINIAPP_URL',url)
    with pytest.raises(ValueError): miniapp_entrypoint()


def test_single_source_falls_back_to_existing_backend(monkeypatch):
    monkeypatch.delenv('SOURCE_MINIAPP_URL')
    assert miniapp_entrypoint()=='https://old-ui.invalid/menu'

@pytest.mark.parametrize('module',['start','menu','loja','cards','dado','anime','manga','cccolecao','memoria','pedido','card_contrib','baltigoflix'])
def test_commands_use_shared_url_builder(module):
    source=(ROOT / f'commands/{module}.py').read_text()
    assert 'from utils.miniapp_links import miniapp_url' in source
    assert 'miniapp_url(' in source
    assert 'web_app=WebAppInfo(url=url)' in source or 'WebAppInfo(url=terms_url)' in source


def test_default_menu_is_repaired_and_verified():
    target=MenuButtonWebApp(text='Abrir Source',web_app=WebAppInfo(url='https://source.invalid/menu'))
    old=MenuButtonWebApp(text='Menu',web_app=WebAppInfo(url='https://old-ui.invalid'))
    bot=SimpleNamespace(get_chat_menu_button=AsyncMock(side_effect=[old,target]),set_chat_menu_button=AsyncMock())
    assert asyncio.run(synchronize_menu(bot))
    assert bot.set_chat_menu_button.await_count==1
    assert bot.get_chat_menu_button.await_count==2
    assert bot.set_chat_menu_button.call_args.kwargs['menu_button']==target


def test_matching_menu_makes_no_write():
    target=MenuButtonWebApp(text='Abrir Source',web_app=WebAppInfo(url='https://source.invalid/menu'))
    bot=SimpleNamespace(get_chat_menu_button=AsyncMock(return_value=target),set_chat_menu_button=AsyncMock())
    assert asyncio.run(synchronize_menu(bot,77))
    bot.set_chat_menu_button.assert_not_awaited()


def test_menu_failure_does_not_break_commands():
    bot=SimpleNamespace(get_chat_menu_button=AsyncMock(side_effect=TimeoutError()))
    assert asyncio.run(synchronize_menu(bot)) is False


def test_private_sync_is_deduplicated_and_groups_are_ignored(monkeypatch):
    async def scenario():
        fake=AsyncMock(return_value=True)
        monkeypatch.setattr('utils.miniapp_menu.synchronize_menu',fake)
        app=SimpleNamespace(bot=object(),bot_data={})
        sync=MiniAppMenuSync(app);app.bot_data['miniapp_menu_sync']=sync
        ctx=SimpleNamespace(application=app)
        update=SimpleNamespace(effective_chat=SimpleNamespace(type='private',id=77))
        for _ in range(20): await refresh_private_menu(update,ctx)
        assert len(sync.tasks)==1
        await asyncio.gather(*sync.tasks)
        await refresh_private_menu(update,ctx)
        await refresh_private_menu(SimpleNamespace(effective_chat=SimpleNamespace(type='group',id=-1)),ctx)
        assert fake.await_count==1
        await sync.close()
    asyncio.run(scenario())
