"""Real compiled app + synthetic Telegram fullscreen/safe-area bridge. No live accounts."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import threading
from http.server import ThreadingHTTPServer
import verify_native_browser as base

PORT = 8766
base.BOOT += r"""
(() => {
 const tg=Telegram.WebApp, mode=new URLSearchParams(location.search).get('tg_case')||'ios';
 window.__fullRequests=0;window.__expandRequests=0;window.__headers=[];
 const events=new Map();
 window.__emit=(name,data)=>{for(const fn of (events.get(name)||[]))fn(data)};
 tg.onEvent=(name,fn)=>{if(!events.has(name))events.set(name,new Set());events.get(name).add(fn)};
 tg.offEvent=(name,fn)=>events.get(name)?.delete(fn);
 tg.version=mode==='old'?'7.10':'9.1';
 tg.platform=mode==='browser'?'unknown':mode==='desktop'?'tdesktop':mode==='android'?'android':'ios';
 if(mode==='browser')tg.initData='';
 tg.isVersionAtLeast=v=>{const [a,b]=tg.version.split('.').map(Number),[x,y]=v.split('.').map(Number);return a>x||(a===x&&b>=y)};
 tg.isFullscreen=mode==='already';tg.expand=()=>window.__expandRequests++;
 tg.setHeaderColor=c=>window.__headers.push(c);tg.setBottomBarColor=()=>{};
 tg.safeAreaInset={top:0,bottom:0,left:0,right:0};tg.contentSafeAreaInset={top:0,bottom:0,left:0,right:0};
 window.__setInsets=(device,content)=>{tg.safeAreaInset=device;tg.contentSafeAreaInset=content;__emit('safeAreaChanged');__emit('contentSafeAreaChanged');window.__paintChrome?.()};
 window.__rotate=()=>{tg.viewportStableHeight=innerHeight;tg.viewportHeight=innerHeight;if(tg.isFullscreen)__setInsets(innerWidth>innerHeight?{top:0,bottom:21,left:59,right:59}:{top:59,bottom:34,left:0,right:0},{top:56,bottom:0,left:0,right:0});__emit('viewportChanged',{isStateStable:true})};
 tg.viewportStableHeight=innerHeight;tg.viewportHeight=innerHeight;
 tg.requestFullscreen=()=>{window.__fullRequests++;if(mode==='throw')throw new Error('WebAppMethodUnsupported');if(mode==='ignored')return;if(mode==='unsupported'){__emit('fullscreenFailed',{error:'UNSUPPORTED'});return}tg.isFullscreen=true;__emit('fullscreenChanged');if(mode!=='delayed')__rotate()};
 if(mode==='already')__rotate();
 window.__paintChrome=()=>{
  let el=document.getElementById('fixture-native-chrome');
  if(!tg.isFullscreen){el?.remove();return}
  if(!el){el=document.createElement('div');el.id='fixture-native-chrome';el.innerHTML='<button aria-label="Fechar Telegram simulado">Fechar</button><span>TELEGRAM · SIMULAÇÃO</span><button aria-label="Menu Telegram simulado">•••</button>';el.firstElementChild.onclick=()=>window.__closed=true;document.body.append(el)}
  const a=tg.safeAreaInset,c=tg.contentSafeAreaInset;
  el.style.cssText=`position:fixed;top:${a.top}px;left:${a.left}px;right:${a.right}px;height:${c.top}px;z-index:2147483000;display:flex;align-items:center;justify-content:space-between;padding:6px 10px;background:#09090b;color:#aaa;font:9px sans-serif;`;
  for(const b of el.querySelectorAll('button'))b.style.cssText='border:1px solid #555;background:#222;color:white;border-radius:20px;padding:8px 12px;font:12px sans-serif;';
 };
 document.addEventListener('DOMContentLoaded',()=>window.__paintChrome());
})();
"""


def bounds(page, selector):
    box=page.locator(selector).first.bounding_box()
    assert box,(selector,'missing')
    s=page.evaluate('''() => {const t=Telegram.WebApp,d=t.safeAreaInset,c=t.contentSafeAreaInset;return {top:d.top+c.top,bottom:d.bottom+c.bottom,left:d.left+c.left,right:d.right+c.right,h:innerHeight,w:innerWidth}}''')
    assert box['y']>=s['top']-1,(selector,'top',box,s)
    assert box['x']>=s['left']-1,(selector,'left',box,s)
    assert box['x']+box['width']<=s['w']-s['right']+1,(selector,'right',box,s)
    assert box['y']+box['height']<=s['h']-s['bottom']+1,(selector,'bottom',box,s)
    return box


def run(output):
    from playwright.sync_api import sync_playwright
    output.mkdir(parents=True,exist_ok=True)
    report={'bridge':'synthetic Telegram; real compiled application','routes':[],'checks':[],'errors':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
        ctx=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce')
        page=ctx.new_page();page.set_default_timeout(8000)
        page.on('pageerror',lambda e:report['errors'].append(str(e)))
        page.on('console',lambda m:report['errors'].append(m.text) if m.type=='error' else None)
        def go(path,case='ios'):
            parts=path.split('#',1);url=parts[0]+('&' if '?' in parts[0] else '?')+'tg_case='+case
            if len(parts)==2:url+='#'+parts[1]
            page.goto(f'http://127.0.0.1:{PORT}{url}');page.wait_for_selector('main h1');page.wait_for_timeout(60)
        try:
            routes=list(json.loads((base.ROOT/'aninexus_frontend/src/native/routes.json').read_text()))
            routes+=['/menu#settings','/cards/anime?anime_id=1','/menu?section=sell#shop','/menu?section=nickname#shop']
            for width,height in [(320,740),(390,844),(844,390)]:
                page.set_viewport_size({'width':width,'height':height})
                for path in routes:
                    go(path)
                    assert page.evaluate('__fullRequests')==1,path
                    assert page.get_attribute('html','data-source-fullscreen')=='true'
                    bounds(page,'header.sticky');bounds(page,'.app-scroller')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    assert page.locator('iframe').count()==0
                    report['routes'].append({'path':path,'width':width,'height':height})
                for path,name in [('/dado','dado'),('/shop','loja'),('/cards','cards')]:
                    go(path);page.screenshot(path=str(output/f'{name}-{width}.png'))
            report['checks'].append('29 entry/detail routes: one fullscreen request and safe content at three sizes')
            page.set_viewport_size({'width':390,'height':844});go('/cards')
            boots=page.evaluate('__bootCount')
            page.get_by_role('button',name='Abrir menu').click();page.get_by_role('dialog',name='Navegação').wait_for();page.wait_for_timeout(240)
            bounds(page,'.source-navigation-drawer');page.screenshot(path=str(output/'menu-seguro.png'))
            page.get_by_role('button',name='Loja',exact=True).click();page.wait_for_selector('main h1')
            assert page.evaluate('__bootCount')==boots and page.evaluate('__fullRequests')==1
            page.evaluate("Telegram.WebApp.isFullscreen=false;__setInsets({top:0,bottom:0,left:0,right:0},{top:0,bottom:0,left:0,right:0});__emit('fullscreenChanged');__emit('activated')")
            page.get_by_role('button',name='Ir para o painel').click();page.wait_for_timeout(100)
            assert page.evaluate('__fullRequests')==1 and page.locator('header.sticky').bounding_box()['y']==0
            report['checks'].append('SPA no reload/repeated fullscreen; user exit respected')
            go('/menu#settings');page.get_by_role('button',name='Alterar favorito',exact=True).click();page.get_by_role('dialog').wait_for();bounds(page,'[role="dialog"]')
            page.get_by_role('textbox',name='Buscar personagem favorito').fill('02');page.get_by_role('button',name='Favoritar Personagem 02',exact=True).click();page.get_by_role('dialog').wait_for(state='hidden')
            assert base.STATE['favorite']['id']==2
            bounds(page,'.source-toast-viewport');page.screenshot(path=str(output/'favorito-seguro.png'))
            page.get_by_role('button',name='Alterar favorito',exact=True).click();page.get_by_role('dialog').wait_for();page.evaluate('for(const f of Array.from(__backHandlers))f()');page.get_by_role('dialog').wait_for(state='hidden');assert page.evaluate('location.hash')=='#settings';page.get_by_role('button',name='Alterar favorito',exact=True).wait_for()
            report['checks'].append('favorite persists; picker/toast safe; native Back closes dialog')
            page.get_by_role('button',name='Alterar favorito',exact=True).click();page.set_viewport_size({'width':844,'height':390});page.evaluate('__rotate()');page.wait_for_timeout(150)
            bounds(page,'[role="dialog"]');bounds(page,'[role="dialog"] button[aria-label="Fechar"]');page.screenshot(path=str(output/'favoritos-horizontal.png'))
            page.get_by_role('dialog').get_by_role('button',name='Fechar',exact=True).click()
            report['checks'].append('orientation update constrains an already-open dialog on four edges')
            go('/menu');page.locator('main img[alt="Personagem 01"]').first.click();page.get_by_role('dialog').wait_for();page.wait_for_timeout(300)
            bounds(page,'[role="dialog"]');bounds(page,'[role="dialog"] button[aria-label="Fechar"]');page.get_by_role('dialog').get_by_role('button',name='Fechar',exact=True).click()
            report['checks'].append('character sheet and dismiss control safe in landscape')
            go('/dado');page.get_by_role('button',name='Rolar dado',exact=True).click();page.get_by_role('button',name='Obra de teste 01 Selecionar').click();page.get_by_role('button',name='Continuar',exact=True).wait_for();page.wait_for_timeout(300)
            bounds(page,'.source-gacha-details');bounds(page,'.source-gacha-details button');page.screenshot(path=str(output/'recompensa-horizontal.png'));page.get_by_role('button',name='Continuar',exact=True).click()
            report['checks'].append('dice roll, pick and reward Continue action in short landscape')
            page.set_viewport_size({'width':390,'height':844});go('/menu#settings');page.get_by_role('button',name='Alterar favorito',exact=True).click();page.get_by_role('textbox',name='Buscar personagem favorito').focus()
            page.evaluate("Object.defineProperty(visualViewport,'height',{configurable:true,value:420});visualViewport.dispatchEvent(new Event('resize'))");page.wait_for_timeout(100)
            b=page.get_by_role('dialog').bounding_box();assert b['y']>=115 and b['y']+b['height']<=420-34+1,b
            page.get_by_role('dialog').get_by_role('button',name='Fechar',exact=True).click();page.evaluate("delete visualViewport.height;visualViewport.dispatchEvent(new Event('resize'))")
            report['checks'].append('keyboard keeps search and dialog Close above obscured area')
            go('/cards','delayed');assert page.locator('header.sticky').bounding_box()['y']>=56
            page.evaluate('__setInsets({top:47,bottom:20,left:12,right:18},{top:64,bottom:8,left:4,right:6})');page.wait_for_timeout(80);bounds(page,'header.sticky');assert page.locator('header.sticky').bounding_box()['y']==111
            page.evaluate('__setInsets({top:0,bottom:0,left:0,right:0},{top:0,bottom:0,left:0,right:0})');page.wait_for_timeout(80);assert page.locator('header.sticky').bounding_box()['y']==0
            report['checks'].append('late insets, additive system/content padding and authoritative zero')
            for case,count in [('old',0),('unsupported',1),('throw',1),('browser',0),('already',0),('ignored',1)]:
                go('/cards',case);assert page.evaluate('__fullRequests')==count,(case,count)
                page.get_by_role('button',name='Abrir menu').click();page.get_by_role('dialog',name='Navegação').wait_for();assert page.evaluate('__fullRequests')==count
                if case=='ignored':page.wait_for_timeout(1900);assert page.locator('header.sticky').bounding_box()['y']==0
            report['checks'].append('old/unsupported/throwing/ignored/already-fullscreen/browser compatibility')
            go('/cards','android');bounds(page,'header.sticky');page.get_by_role('button',name='Fechar Telegram simulado').click();assert page.evaluate('__closed');assert page.evaluate('__headers.at(-1)')=='#09090b'
            report['checks'].append('native Close accessible and dark contrasting native header configured')
            assert not report['errors'],report['errors'];report['result']='passed'
        except Exception as e:
            report['result']='failed';report['failure']=str(e);page.screenshot(path=str(output/'failure.png'));raise
        finally:
            (output/'fullscreen-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));browser.close()
    print(json.dumps({'result':report['result'],'routes':len(report['routes']),'flows':len(report['checks'])}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--serve',action='store_true');parser.add_argument('--output',type=Path,default=Path('/tmp/fullscreen-proof'));args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',PORT),base.Handler)
    if args.serve:server.serve_forever()
    else:
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:run(args.output)
        finally:server.shutdown()
