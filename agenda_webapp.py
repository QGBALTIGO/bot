from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from airing_service import get_airing_agenda
from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def _page() -> str:
    return f'''<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#050711"><title>Agenda • Baltigo</title><script src="https://telegram.org/js/telegram-web-app.js"></script><style>{base_css()}
.timeline{{display:grid;gap:10px;margin-top:14px}}.air{{display:grid;grid-template-columns:68px 1fr;gap:12px;padding:12px;border:1px solid var(--line);border-radius:18px;background:var(--surface-soft)}}.air img{{width:68px;height:92px;object-fit:cover;border-radius:13px;background:var(--surface-2)}}.air h3{{margin:2px 0 6px;font-size:15px}}.when{{font-size:12px;color:var(--cyan);font-weight:900}}.meta{{font-size:11px;color:var(--muted);margin-top:5px}}.refresh{{margin-top:12px}}
</style></head><body><div class="v2-shell"><section class="v2-hero"><div class="v2-eyebrow">Watchlist • AniList</div><h1 class="v2-title">Próximos<br>episódios.</h1><p class="v2-copy">A agenda é montada automaticamente a partir dos animes que você acompanha no Baltigo.</p></section><section class="v2-panel"><h2 class="v2-section-title">Sua semana</h2><p class="v2-section-copy">Horários são exibidos no horário do seu dispositivo.</p><button id="refresh" class="v2-btn refresh">Atualizar agenda</button><div class="timeline" id="timeline"><div class="v2-empty">Carregando…</div></div></section></div><div id="v2Toast" class="v2-toast"></div><script>{telegram_bootstrap_js()}
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
function relative(sec){{sec=Math.max(0,Number(sec||0));const d=Math.floor(sec/86400),h=Math.floor((sec%86400)/3600),m=Math.floor((sec%3600)/60);if(d)return `em ${{d}}d ${{h}}h`;if(h)return `em ${{h}}h ${{m}}min`;return `em ${{m}}min`}}
async function load(force=false){{$('timeline').innerHTML='<div class="v2-empty">Atualizando agenda…</div>';try{{const d=await v2Api('/api/v2/agenda'+(force?'?force=1':''));const items=d.items||[];$('timeline').innerHTML=items.length?items.map(x=>`<div class="air"><img src="${{esc(x.cover_url)}}" alt=""><div><div class="when">${{relative(x.seconds_until)}}</div><h3>${{esc(x.title)}}</h3><div class="meta">Episódio ${{x.episode||'?'}} • ${{new Date(x.airing_at).toLocaleString('pt-BR',{{weekday:'short',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}})}}</div>${{x.site_url?`<a class="v2-chip" style="margin-top:9px" href="${{esc(x.site_url)}}">AniList</a>`:''}}</div></div>`).join(''):'<div class="v2-empty">Nenhum próximo episódio encontrado. Adicione animes em Favoritos/Watchlist e marque como assistindo ou planejado.</div>'}}catch(e){{$('timeline').innerHTML='<div class="v2-empty">Não consegui consultar a agenda agora.</div>';v2Toast(e.message)}}}}
$('refresh').onclick=()=>load(true);load();</script></body></html>'''


def register_agenda_routes(app) -> None:
    @app.get('/agenda',response_class=HTMLResponse)
    async def agenda_page(): return HTMLResponse(_page())

    @app.get('/api/v2/agenda')
    async def agenda_api(request:Request,force:int=0):
        uid=_uid(request)
        if not await rate_limiter.allow(f'agenda:{uid}',limit=20,window_seconds=60):
            return JSONResponse({'ok':False,'message':'Muitas atualizações de agenda.'},status_code=429)
        items=await get_airing_agenda(uid,force=bool(force))
        return JSONResponse({'ok':True,'items':items})
