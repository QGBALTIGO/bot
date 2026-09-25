"""Real UI, synthetic identity: one entrypoint, one document, and safe update notices."""
from __future__ import annotations
import argparse
import re
import json
import os
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import verify_native_browser as fixture
fixture.BOOT = fixture.BOOT.replace('onEvent(){},offEvent(){},', 'onEvent(name,fn){window.__miniappResume ||= {}; (window.__miniappResume[name] ||= new Set()).add(fn)},offEvent(name,fn){window.__miniappResume?.[name]?.delete(fn)},')


def run(output: Path):
    from playwright.sync_api import sync_playwright
    output.mkdir(parents=True, exist_ok=True)
    report = {'data': 'synthetic APIs; real compiled frontend', 'routes': [], 'checks': [], 'errors': []}
    server = ThreadingHTTPServer(('127.0.0.1', fixture.PORT), fixture.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or shutil.which('chromium'), args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':390,'height':844}, reduced_motion='reduce')
        page.set_default_timeout(12000)
        page.on('pageerror', lambda e: report['errors'].append(str(e)))
        page.on('console', lambda m: report['errors'].append(m.text) if m.type=='error' else None)
        try:
            routes=json.loads((fixture.ROOT/'aninexus_frontend/src/native/routes.json').read_text())
            for width in [390,1280]:
                page.set_viewport_size({'width':width,'height':844})
                for path,config in routes.items():
                    page.goto(f'http://127.0.0.1:{fixture.PORT}{path}?probe=1')
                    page.wait_for_selector('main h1')
                    assert urlsplit(page.url).path=='/menu',page.url
                    if path!='/menu': assert parse_qs(urlsplit(page.url).query)['tab']==[config['tab']]
                    assert page.locator('[data-source-shell]').count()==1
                    assert page.locator('iframe').count()==0
                    assert page.locator('[data-source-version-notice]').count()==0
                    report['routes'].append({'legacy':path,'tab':config['tab'],'width':width,'canonical':'/menu'})
            page.set_viewport_size({'width':390,'height':844})
            page.goto(f'http://127.0.0.1:{fixture.PORT}/menu#profile')
            page.wait_for_selector('[data-profile-identity]')
            boot=page.evaluate('__bootCount')
            page.get_by_role('button',name='Abrir menu',exact=True).click()
            page.get_by_role('button',name='Loja',exact=True).click()
            page.get_by_role('heading',name=re.compile(r'^loja aninexus$', re.I)).wait_for()
            assert page.evaluate('__bootCount')==boot
            page.screenshot(path=str(output/'loja-mesmo-aplicativo.png'))
            page.get_by_role('button',name='Ir para o painel',exact=True).click()
            page.wait_for_selector('[data-profile-identity]')
            assert page.evaluate('__bootCount')==boot
            report['checks'].append('menu to shop to profile: same document and one shared shell; no external windows')
            assert not page.evaluate('__external')
            before_me=fixture.STATE['gets'].count('/api/v1_7b82/me')
            page.route('**/api/native/version',lambda route:route.fulfill(json={'version':'0123456789abcdef','entrypoint':'/menu'}))
            page.evaluate("const realNow=Date.now;Date.now=()=>realNow()+61000;window.__miniappResume.activated.forEach(fn=>fn())")
            page.locator('[data-source-version-notice]').wait_for()
            assert page.evaluate('__bootCount')==boot
            assert fixture.STATE['gets'].count('/api/v1_7b82/me')==before_me
            page.screenshot(path=str(output/'aviso-versao-aberta.png'))
            page.once('dialog',lambda dialog:dialog.dismiss())
            page.get_by_role('button',name='Atualizar aplicativo',exact=True).click()
            assert page.evaluate('__bootCount')==boot
            report['checks'].append('stale version detected on resume; no automatic reload, account refresh or discarded form')
            page.once('dialog',lambda dialog:dialog.accept())
            page.get_by_role('button',name='Atualizar aplicativo',exact=True).click()
            page.wait_for_function('(old)=>window.__bootCount>old',arg=boot)
            report['checks'].append('update reload requires explicit user confirmation')
            assert not report['errors'],report['errors']
        except Exception:
            page.screenshot(path=str(output/'failure.png'))
            raise
        finally:
            (output/'single-miniapp-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            browser.close();server.shutdown();server.server_close()
    print(json.dumps({'routes':len(report['routes']),'checks':report['checks'],'errors':report['errors']},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('/tmp/single-miniapp-proof'))
    run(parser.parse_args().output)
