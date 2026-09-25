"""Adversarial input, network-boundary and cache regressions without external calls."""
import asyncio
import importlib
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from utils.api_validation import body_integer
from utils import image_proxy as images


@pytest.mark.parametrize('value', [None, True, False, 2.5, [], {}, '', '--1', '++1', '1.2', '1e3', '１２', ' 1', 2**63, -(2**63), '9'*10000])
def test_invalid_body_integers_fail_with_controlled_client_error(value):
    with pytest.raises(HTTPException) as e:
        body_integer(value)
    assert e.value.status_code == 400


@pytest.mark.parametrize('value,number', [(0,0),('123',123),(-1,-1),('-123',-123)])
def test_valid_body_integers(value,number):
    assert body_integer(value)==number


@pytest.mark.parametrize('url', ['http://127.0.0.1/a', 'http://[::1]/a', 'http://169.254.169.254/a', 'http://user:pass@example.com/a','file:///tmp/a','http://localhost/a','https://[bad/a'])
def test_proxy_blocks_private_and_malformed_destinations(url):
    async def scenario():
        with pytest.raises(images.ImageProxyError):
            await images._assert_public_destination(url)
    asyncio.run(scenario())


def test_proxy_pins_validated_ip_and_preserves_tls_hostname(monkeypatch):
    captured=[]
    async def resolve(_): return '93.184.216.34'
    def serve(request):
        captured.append(request)
        return httpx.Response(200,content=b'\x89PNG\r\n\x1a\n'+b'test')
    real_client=httpx.AsyncClient
    def client(**kw):
        assert kw['trust_env'] is False and kw['verify'] is True
        return real_client(transport=httpx.MockTransport(serve),**kw)
    monkeypatch.setattr(images,'_assert_public_destination',resolve)
    monkeypatch.setattr(images.httpx,'AsyncClient',client)
    result=asyncio.run(images.fetch_public_image('https://images.example.com/a.png'))
    req=captured[0]
    assert req.url.host=='93.184.216.34'
    assert req.headers['host']=='images.example.com'
    assert req.extensions['sni_hostname']=='images.example.com'
    assert result[1]=='image/png'


def test_redirect_is_rechecked_and_not_followed_into_private_network(monkeypatch):
    calls=[]
    async def resolve(url):
        if '127.0.0.1' in url: raise images.ImageProxyError('blocked_image_host')
        return '93.184.216.34'
    def serve(request):
        calls.append(request)
        return httpx.Response(302,headers={'location':'http://127.0.0.1/secrets'})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(images,'_assert_public_destination',resolve)
    monkeypatch.setattr(images.httpx,'AsyncClient',lambda **kw: real_client(transport=httpx.MockTransport(serve),**kw))
    with pytest.raises(images.ImageProxyError) as e:
        asyncio.run(images.fetch_public_image('https://images.example.com/a'))
    assert e.value.code=='blocked_image_host' and len(calls)==1


def test_declared_image_type_does_not_make_html_or_svg_safe(monkeypatch):
    async def resolve(_): return '93.184.216.34'
    real_client=httpx.AsyncClient
    monkeypatch.setattr(images,'_assert_public_destination',resolve)
    monkeypatch.setattr(images.httpx,'AsyncClient',lambda **kw: real_client(transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'Content-Type':'image/png'},content=b'<svg onload="alert(1)"></svg>')),**kw))
    with pytest.raises(images.ImageProxyError) as e:
        asyncio.run(images.fetch_public_image('https://images.example.com/a'))
    assert e.value.code=='invalid_image_content'


def test_public_image_cache_combines_identical_inflight_requests(monkeypatch):
    module=importlib.import_module('webapp_routes.image_proxy')
    from fastapi.responses import Response
    async def load(*args,**kw):
        await asyncio.sleep(.02)
        return Response(b'abc', media_type='image/png')
    mock=AsyncMock(side_effect=load)
    monkeypatch.setattr(module,'_load_image_proxy',mock)
    async def scenario():
        responses=await asyncio.gather(*[module.api_image_proxy('https://cache.example.com/coalesced.png','') for _ in range(20)])
        assert all(response.body==b'abc' for response in responses)
        assert mock.await_count==1
        await module.api_image_proxy('https://cache.example.com/coalesced.png','')
        assert mock.await_count==1
    asyncio.run(scenario())


def test_invalid_crop_never_starts_upstream_work(monkeypatch):
    module=importlib.import_module('webapp_routes.image_proxy')
    load=AsyncMock()
    monkeypatch.setattr(module,'_load_image_proxy',load)
    with pytest.raises(HTTPException) as e:
        asyncio.run(module.api_image_proxy('https://cache.example.com/a','evil'))
    assert e.value.status_code==400 and load.await_count==0


def test_image_errors_are_not_cached(monkeypatch):
    module=importlib.import_module('webapp_routes.image_proxy')
    from fastapi.responses import Response
    load=AsyncMock(side_effect=[HTTPException(502,'temporary'),Response(b'ok',media_type='image/png')])
    monkeypatch.setattr(module,'_load_image_proxy',load)
    async def scenario():
        with pytest.raises(HTTPException):
            await module.api_image_proxy('https://cache.example.com/retry','')
        assert (await module.api_image_proxy('https://cache.example.com/retry','')).body==b'ok'
        assert load.await_count==2
    asyncio.run(scenario())
