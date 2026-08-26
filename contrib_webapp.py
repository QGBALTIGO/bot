from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from admin_security import is_admin
from contrib_repository import ContributionError
from contrib_service import (
    contribution_state,
    pending_for_admin,
    review_contribution,
    submit_image,
    submit_work,
)
from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def _page() -> str:
    return f'''<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#070a14"><title>Contribuições • Baltigo</title><script src="https://telegram.org/js/telegram-web-app.js"></script><style>{base_css()}
.tabs{{display:flex;gap:8px;overflow:auto;margin-top:14px}}.tab{{border:1px solid var(--line);background:var(--surface-soft);padding:10px 13px;border-radius:999px;font-weight:900;font-size:11px;white-space:nowrap}}.tab.active{{border-color:rgba(93,230,255,.45);background:rgba(93,230,255,.1)}}
.view{{display:none}}.view.active{{display:block;animation:fade .25s both}}@keyframes fade{{from{{opacity:0;transform:translateY(5px)}}to{{opacity:1;transform:none}}}}
.field{{margin-top:12px}}.field label{{display:block;margin-bottom:6px;font-size:10px;color:var(--muted);font-weight:900;text-transform:uppercase;letter-spacing:.1em}}.field input,.field textarea,.field select{{width:100%;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.04);padding:13px;outline:0}}.field textarea{{min-height:90px;resize:vertical}}
.list{{display:grid;gap:9px;margin-top:13px}}.item{{padding:13px;border:1px solid var(--line);border-radius:17px;background:var(--surface-soft)}}.status{{font-size:10px;font-weight:950;text-transform:uppercase;letter-spacing:.1em}}.pending{{color:var(--gold)}}.approved{{color:var(--green)}}.rejected{{color:var(--danger)}}
.results{{max-height:260px;overflow:auto;margin-top:8px;display:grid;gap:7px}}.result{{display:flex;gap:10px;align-items:center;padding:9px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.035);cursor:pointer}}.result img{{width:42px;height:54px;border-radius:10px;object-fit:cover}}.selected{{border-color:rgba(93,230,255,.55)!important}}
</style></head><body><div class="v2-shell"><section class="v2-hero"><div class="v2-eyebrow">Comunidade • Catálogo V2</div><h1 class="v2-title">Ajude a melhorar<br>o Baltigo.</h1><p class="v2-copy">Sugestões nunca alteram o catálogo direto. Elas passam por validação e moderação, com histórico de quem aprovou.</p><div class="tabs"><button class="tab active" data-tab="image">Imagem</button><button class="tab" data-tab="work">Nova obra</button><button class="tab" data-tab="mine">Minhas sugestões</button><button class="tab" id="adminTab" data-tab="admin" style="display:none">Moderação</button></div></section>
<section class="v2-panel view active" id="image"><h2 class="v2-section-title">Sugerir imagem</h2><p class="v2-section-copy">Busque um personagem existente e envie uma imagem pública melhor.</p><div class="v2-search"><span>⌕</span><input id="charSearch" placeholder="Buscar personagem ou anime"></div><div class="results" id="charResults"></div><div id="selectedChar" class="v2-empty" style="margin-top:10px">Nenhum personagem selecionado.</div><div class="field"><label>URL da nova imagem</label><input id="imageUrl" placeholder="https://..."></div><div class="field"><label>Observação</label><textarea id="imageNote" placeholder="Explique por que essa imagem é melhor (opcional)."></textarea></div><button class="v2-btn" id="sendImage" style="margin-top:13px">Enviar para moderação</button></section>
<section class="v2-panel view" id="work"><h2 class="v2-section-title">Sugerir nova obra</h2><p class="v2-section-copy">Envie os dados editoriais. A moderação decide se a obra entra no ecossistema de cards.</p><div class="field"><label>Tipo</label><select id="mediaType"><option value="anime">Anime</option><option value="manga">Mangá</option></select></div><div class="field"><label>Título</label><input id="workTitle" maxlength="220"></div><div class="field"><label>AniList ID (opcional)</label><input id="anilistId" inputmode="numeric"></div><div class="field"><label>Cover pública (opcional)</label><input id="coverUrl" placeholder="https://..."></div><div class="field"><label>Observação</label><textarea id="workNote"></textarea></div><button class="v2-btn" id="sendWork" style="margin-top:13px">Enviar sugestão</button></section>
<section class="v2-panel view" id="mine"><h2 class="v2-section-title">Minhas sugestões</h2><div class="list" id="mineList"></div></section>
<section class="v2-panel view" id="admin"><h2 class="v2-section-title">Fila de moderação</h2><p class="v2-section-copy">Aprovação de imagem aplica o override do catálogo. Obras anime com AniList ID podem criar a obra-base.</p><div class="list" id="adminList"></div></section></div><div class="v2-toast" id="v2Toast"></div><script>{telegram_bootstrap_js()}
let state={{characters:[],mine:{{images:[],works:[]}},admin:false}},selected=null;
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
function status(x){{return `<span class="status ${{esc(x)}}">${{esc(x)}}</span>`}}
function switchTab(name){{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab===name));document.querySelectorAll('.view').forEach(x=>x.classList.toggle('active',x.id===name));if(name==='admin')loadAdmin()}}
document.querySelectorAll('.tab').forEach(x=>x.onclick=()=>switchTab(x.dataset.tab));
function renderMine(){{const items=[...(state.mine.images||[]).map(x=>({{...x,kind:'Imagem',label:x.character_name}})),...(state.mine.works||[]).map(x=>({{...x,kind:'Obra',label:x.title}}))].sort((a,b)=>Number(b.id)-Number(a.id));$('mineList').innerHTML=items.length?items.map(x=>`<div class="item">${{status(x.status)}} <b>${{esc(x.kind)}} #${{x.id}}</b><div style="margin-top:6px">${{esc(x.label)}}</div>${{x.review_note?`<small>${{esc(x.review_note)}}</small>`:''}}</div>`).join(''):'<div class="v2-empty">Você ainda não enviou sugestões.</div>'}}
function renderSearch(){{const q=$('charSearch').value.trim().toLocaleLowerCase('pt-BR');const results=q?state.characters.filter(x=>`${{x.name}} ${{x.anime}}`.toLocaleLowerCase('pt-BR').includes(q)).slice(0,30):[];$('charResults').innerHTML=results.map(x=>`<div class="result" data-id="${{x.id}}"><img src="${{esc(x.image)}}" alt=""><div><b>${{esc(x.name)}}</b><br><small>${{esc(x.anime)}}</small></div></div>`).join('');document.querySelectorAll('.result').forEach(el=>el.onclick=()=>{{selected=state.characters.find(x=>Number(x.id)===Number(el.dataset.id));$('selectedChar').innerHTML=`<b>${{esc(selected.name)}}</b><br>${{esc(selected.anime)}}`;document.querySelectorAll('.result').forEach(x=>x.classList.toggle('selected',x===el))}})}}
$('charSearch').oninput=renderSearch;
async function load(){{try{{const d=await v2Api('/api/v2/contrib/state');state=d.state;$('adminTab').style.display=d.admin?'block':'none';renderMine()}}catch(e){{v2Toast(e.message)}}}}
$('sendImage').onclick=async()=>{{if(!selected)return v2Toast('Selecione um personagem.');try{{await v2Api('/api/v2/contrib/image',{{method:'POST',body:JSON.stringify({{character_id:selected.id,image_url:$('imageUrl').value,note:$('imageNote').value}})}});v2Haptic('medium');v2Toast('Sugestão enviada.');$('imageUrl').value='';$('imageNote').value='';await load();switchTab('mine')}}catch(e){{v2Toast(e.message)}}}};
$('sendWork').onclick=async()=>{{try{{await v2Api('/api/v2/contrib/work',{{method:'POST',body:JSON.stringify({{media_type:$('mediaType').value,title:$('workTitle').value,anilist_id:$('anilistId').value,cover_url:$('coverUrl').value,note:$('workNote').value}})}});v2Haptic('medium');v2Toast('Sugestão enviada.');await load();switchTab('mine')}}catch(e){{v2Toast(e.message)}}}};
async function loadAdmin(){{try{{const d=await v2Api('/api/v2/contrib/admin/pending');const all=[...(d.pending.images||[]).map(x=>({{...x,kind:'image',label:x.character_name,detail:x.suggested_image_url}})),...(d.pending.works||[]).map(x=>({{...x,kind:'work',label:x.title,detail:x.cover_url||''}}))];$('adminList').innerHTML=all.length?all.map(x=>`<div class="item"><b>${{esc(x.kind)}} #${{x.id}} • ${{esc(x.label)}}</b><div style="margin:7px 0;word-break:break-all"><small>${{esc(x.detail)}}</small></div><div style="display:flex;gap:8px"><button class="v2-btn review" data-k="${{x.kind}}" data-i="${{x.id}}" data-d="approved">Aprovar</button><button class="v2-btn review" data-k="${{x.kind}}" data-i="${{x.id}}" data-d="rejected">Rejeitar</button></div></div>`).join(''):'<div class="v2-empty">Fila vazia.</div>';document.querySelectorAll('.review').forEach(b=>b.onclick=async()=>{{try{{await v2Api('/api/v2/contrib/admin/review',{{method:'POST',body:JSON.stringify({{kind:b.dataset.k,id:Number(b.dataset.i),decision:b.dataset.d}})}});v2Toast('Moderação registrada.');loadAdmin()}}catch(e){{v2Toast(e.message)}}}})}}catch(e){{v2Toast(e.message)}}}}
load();</script></body></html>'''


def register_contribution_routes(app) -> None:
    @app.get('/contribute', response_class=HTMLResponse)
    async def contribute_page():
        return HTMLResponse(_page())

    @app.get('/api/v2/contrib/state')
    async def contrib_state(request: Request):
        uid=_uid(request)
        if not await rate_limiter.allow(f'contrib:state:{uid}',limit=40,window_seconds=60):
            return JSONResponse({'ok':False,'message':'Muitas atualizações.'},status_code=429)
        return JSONResponse({'ok':True,'state':contribution_state(uid),'admin':is_admin(uid)})

    @app.post('/api/v2/contrib/image')
    async def contrib_image(request: Request):
        uid=_uid(request)
        if not await rate_limiter.allow(f'contrib:image:{uid}',limit=5,window_seconds=3600):
            return JSONResponse({'ok':False,'message':'Limite de sugestões atingido. Tente mais tarde.'},status_code=429)
        try: row=submit_image(uid,await request.json())
        except ContributionError as exc: return JSONResponse({'ok':False,'message':str(exc)},status_code=400)
        return JSONResponse({'ok':True,'suggestion':row})

    @app.post('/api/v2/contrib/work')
    async def contrib_work(request: Request):
        uid=_uid(request)
        if not await rate_limiter.allow(f'contrib:work:{uid}',limit=4,window_seconds=86400):
            return JSONResponse({'ok':False,'message':'Limite diário de novas obras atingido.'},status_code=429)
        try: row=submit_work(uid,await request.json())
        except ContributionError as exc: return JSONResponse({'ok':False,'message':str(exc)},status_code=400)
        return JSONResponse({'ok':True,'suggestion':row})

    @app.get('/api/v2/contrib/admin/pending')
    async def contrib_admin_pending(request: Request):
        uid=_uid(request)
        if not is_admin(uid): return JSONResponse({'ok':False,'message':'Sem permissão.'},status_code=403)
        return JSONResponse({'ok':True,'pending':pending_for_admin()})

    @app.post('/api/v2/contrib/admin/review')
    async def contrib_admin_review(request: Request):
        uid=_uid(request)
        if not is_admin(uid): return JSONResponse({'ok':False,'message':'Sem permissão.'},status_code=403)
        if not await rate_limiter.allow(f'contrib:review:{uid}',limit=30,window_seconds=60):
            return JSONResponse({'ok':False,'message':'Ações rápidas demais.'},status_code=429)
        try:
            p=await request.json(); row=await review_contribution(uid,kind=p.get('kind'),suggestion_id=int(p.get('id') or 0),decision=p.get('decision'),review_note=str(p.get('note') or ''))
        except (ContributionError,ValueError) as exc: return JSONResponse({'ok':False,'message':str(exc)},status_code=400)
        return JSONResponse({'ok':True,'suggestion':row})
