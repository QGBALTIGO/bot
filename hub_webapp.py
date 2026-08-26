from __future__ import annotations

from fastapi import Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ecosystem_repository import EcosystemError
from ecosystem_service import (
    claim_mission,
    ecosystem_state,
    equip_title,
    friend_request,
    friend_respond,
    library_remove,
    mark_notification_read,
    save_library_item,
    universal_search,
    update_notification_preferences,
)
from identity_repository import find_identity_by_nickname
from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def _err(exc: Exception, status: int = 400) -> JSONResponse:
    code=getattr(exc,"code","request_failed")
    message=getattr(exc,"message",str(exc) or "Não foi possível concluir.")
    return JSONResponse({"ok":False,"code":code,"message":message},status_code=status)


def _page() -> str:
    return f'''<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#050711"><title>Baltigo</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
{base_css()}
.hub-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}}
.quick{{padding:15px;border:1px solid var(--line);border-radius:20px;background:var(--surface-soft);cursor:pointer}}
.quick b{{display:block;font-size:15px;margin-top:6px}}.quick span{{font-size:11px;color:var(--muted)}}
.view{{display:none;padding-bottom:82px}}.view.active{{display:block;animation:enter .22s ease}}
@keyframes enter{{from{{opacity:.2;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
.bottom-nav{{position:fixed;z-index:80;left:50%;bottom:calc(8px + var(--safe-bottom));transform:translateX(-50%);width:min(640px,calc(100% - 18px));display:grid;grid-template-columns:repeat(5,1fr);padding:7px;border:1px solid var(--line);border-radius:22px;background:rgba(8,13,27,.94);backdrop-filter:blur(18px);box-shadow:var(--shadow)}}
.nav-btn{{border:0;background:transparent;padding:8px 3px;border-radius:15px;color:var(--muted);font-size:10px;font-weight:850;cursor:pointer}}.nav-btn i{{display:block;font-style:normal;font-size:19px;margin-bottom:3px}}.nav-btn.active{{background:rgba(255,255,255,.07);color:var(--text)}}
.stack{{display:grid;gap:9px;margin-top:13px}}.item{{padding:14px;border:1px solid var(--line);border-radius:18px;background:var(--surface-soft)}}
.item-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}}.item h3{{margin:0;font-size:15px}}.item p{{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.45}}
.pill{{display:inline-flex;padding:6px 9px;border-radius:999px;background:rgba(255,255,255,.07);font-size:10px;font-weight:900}}
.row{{display:flex;gap:8px;align-items:center}}.row>*{{flex:1}}
.small-btn{{border:1px solid var(--line);border-radius:13px;background:rgba(255,255,255,.06);padding:9px 10px;font-weight:800;cursor:pointer}}
.small-btn.primary{{background:linear-gradient(135deg,var(--pink),var(--violet));border:0}}
.progress{{height:8px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:9px}}.progress>span{{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--violet))}}
.search-results{{display:grid;gap:8px;margin-top:10px}}.hero-name{{font-size:12px;color:var(--muted-strong)}}
@media(min-width:760px){{.hub-grid{{grid-template-columns:repeat(4,1fr)}}}}
</style>
</head><body>
<div class="v2-shell">
<section id="home" class="view active">
 <div class="v2-hero"><div class="v2-eyebrow">Source Baltigo V2</div><h1 class="v2-title" id="hello">Seu universo anime</h1><p class="v2-copy" id="subtitle">Carregando sua jornada…</p><div class="v2-metrics"><div class="v2-metric"><span class="v2-metric-label">Nível</span><b class="v2-metric-value" id="level">—</b></div><div class="v2-metric"><span class="v2-metric-label">Coins</span><b class="v2-metric-value" id="coins">—</b></div><div class="v2-metric"><span class="v2-metric-label">Cards</span><b class="v2-metric-value" id="cards">—</b></div></div></div>
 <div class="v2-panel"><h2 class="v2-section-title">Continue de onde parou</h2><div id="continue" class="stack"></div></div>
 <div class="hub-grid">
  <div class="quick" data-go="/game"><span>Jogar</span><b>🎮 Game Center</b></div><div class="quick" data-go="/collection"><span>Colecionar</span><b>🎴 Coleção</b></div>
  <div class="quick" data-tab="missions"><span>Progredir</span><b>✅ Missões</b></div><div class="quick" data-go="/messages"><span>Socializar</span><b>💬 Mensagens</b></div>
  <div class="quick" data-tab="library"><span>Acompanhar</span><b>⭐ Favoritos</b></div><div class="quick" data-go="/ranking"><span>Competir</span><b>🏆 Ranking</b></div>
  <div class="quick" data-go="/xcards"><span>Duelo</span><b>⚔️ XCards</b></div><div class="quick" data-tab="achievements"><span>Personalizar</span><b>🏅 Conquistas</b></div>
 </div>
 <div class="v2-panel"><h2 class="v2-section-title">Para você</h2><p class="v2-section-copy">Sugestões baseadas no que você já coleciona.</p><div id="recommendations" class="stack"></div></div>
</section>
<section id="explore" class="view"><div class="v2-hero"><div class="v2-eyebrow">Explorar</div><h1 class="v2-title">Encontre tudo</h1><p class="v2-copy">Anime, personagem ou jogador numa única busca.</p></div><div class="v2-panel"><div class="v2-search">🔎 <input id="search" placeholder="Buscar anime, personagem ou nickname…"></div><div id="searchResults" class="search-results"></div></div><div class="v2-panel"><h2 class="v2-section-title">Notícias</h2><div id="news" class="stack"></div></div></section>
<section id="library" class="view"><div class="v2-hero"><div class="v2-eyebrow">Sua biblioteca</div><h1 class="v2-title">Favoritos & watchlist</h1><p class="v2-copy">Planejado, assistindo, concluído e favoritos no mesmo lugar.</p></div><div id="libraryList" class="stack"></div></section>
<section id="social" class="view"><div class="v2-hero"><div class="v2-eyebrow">Social</div><h1 class="v2-title">Sua tripulação</h1><p class="v2-copy">Amigos, mensagens, trocas e duelos usam a mesma identidade.</p></div><div class="v2-panel"><div class="row"><input id="friendNick" class="v2-search" style="min-height:50px;padding:0 13px" placeholder="nickname"><button class="small-btn primary" id="addFriend">Adicionar</button></div></div><div id="friends" class="stack"></div></section>
<section id="profile" class="view"><div class="v2-hero"><div class="v2-eyebrow">Progresso</div><h1 class="v2-title">Sua jornada</h1><p class="v2-copy">Missões, conquistas, títulos, atividade e notificações.</p></div><div class="hub-grid"><div class="quick" data-tab="missions"><span>Objetivos</span><b>✅ Missões</b></div><div class="quick" data-tab="achievements"><span>Marcos</span><b>🏅 Conquistas</b></div><div class="quick" data-tab="activity"><span>Histórico</span><b>🧾 Atividade</b></div><div class="quick" data-tab="notifications"><span>Alertas</span><b>🔔 Notificações</b></div></div></section>
<section id="missions" class="view"><div class="v2-hero"><div class="v2-eyebrow">Missões</div><h1 class="v2-title">Jogue o ecossistema</h1><p class="v2-copy">Objetivos atravessam jogos, coleção e social sem criar moedas paralelas.</p></div><div id="missionsList" class="stack"></div></section>
<section id="achievements" class="view"><div class="v2-hero"><div class="v2-eyebrow">Conquistas</div><h1 class="v2-title">Marcas da jornada</h1><p class="v2-copy">Desbloqueie títulos e equipe o que representa você.</p></div><div id="achievementsList" class="stack"></div></section>
<section id="activity" class="view"><div class="v2-hero"><div class="v2-eyebrow">Atividade</div><h1 class="v2-title">Tudo deixa rastro</h1><p class="v2-copy">Economia, jogos e social aparecem numa linha do tempo única.</p></div><div id="activityList" class="stack"></div></section>
<section id="notifications" class="view"><div class="v2-hero"><div class="v2-eyebrow">Notificações</div><h1 class="v2-title">Você decide</h1><p class="v2-copy">Controle os tipos de alerta sem perder eventos importantes.</p></div><div id="notificationPrefs" class="stack"></div><div id="notificationList" class="stack"></div></section>
</div>
<nav class="bottom-nav"><button class="nav-btn active" data-nav="home"><i>⌂</i>Início</button><button class="nav-btn" data-nav="explore"><i>🔎</i>Explorar</button><button class="nav-btn" data-nav="library"><i>🎴</i>Biblioteca</button><button class="nav-btn" data-nav="social"><i>👥</i>Social</button><button class="nav-btn" data-nav="profile"><i>👤</i>Perfil</button></nav>
<div id="v2Toast" class="v2-toast"></div>
<script>{telegram_bootstrap_js()}
let state=null;
const $=id=>document.getElementById(id); const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
function openPath(path){{location.href=path}}
function tab(name){{document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===name));document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.nav===name));if(['home','explore','library','social','profile'].includes(name))history.replaceState(null,'','#'+name);scrollTo(0,0)}}
document.addEventListener('click',e=>{{const go=e.target.closest('[data-go]');if(go)openPath(go.dataset.go);const t=e.target.closest('[data-tab]');if(t)tab(t.dataset.tab)}});document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>tab(b.dataset.nav));
function item(title,copy,badge='',actions=''){{return `<div class="item"><div class="item-head"><div><h3>${{esc(title)}}</h3><p>${{esc(copy)}}</p></div>${{badge?`<span class="pill">${{esc(badge)}}</span>`:''}}</div>${{actions}}</div>`}}
function render(){{const d=state.dashboard||{{}};$('hello').textContent=`Olá, ${{d.display_name||'Navegante'}}`; $('subtitle').textContent=d.equipped_title?`Título equipado: ${{d.equipped_title}}`:'Explore, colecione, jogue e evolua no mesmo universo.';$('level').textContent=d.progress?.level??1;$('coins').textContent=d.wallet?.coins??0;$('cards').textContent=d.collection?.unique??d.collection?.unique_cards??0;
 $('continue').innerHTML=(d.continue||[]).map(x=>item(`${{x.icon}} ${{x.title}}`,x.copy,'',`<button class="small-btn primary" onclick="openPath('${{x.path}}')">Continuar</button>`)).join('')||'<div class="v2-empty">Tudo em dia. Explore algo novo.</div>';
 $('recommendations').innerHTML=(state.recommendations||[]).map(x=>item(x.title,x.reason,`${{x.owned}}/${{x.total}}`,`<div class="progress"><span style="width:${{x.completion}}%"></span></div>`)).join('')||'<div class="v2-empty">Colecione alguns personagens para eu montar recomendações.</div>';
 $('libraryList').innerHTML=(state.library?.items||[]).map(x=>item(`${{x.is_favorite?'⭐ ':''}}${{x.title}}`,`${{x.media_type}} • ${{x.status}} • progresso ${{x.progress||0}}`,'',`<button class="small-btn" onclick="removeMedia('${{x.media_type}}',${{x.media_id}})">Remover</button>`)).join('')||'<div class="v2-empty">Sua watchlist está vazia. Use a busca para adicionar obras.</div>';
 $('missionsList').innerHTML=(state.missions||[]).map(m=>item(m.label,m.description,`${{m.progress}}/${{m.target}}`,`<div class="progress"><span style="width:${{Math.min(100,m.progress/m.target*100)}}%"></span></div>${{m.completed&&!m.claimed?`<button class="small-btn primary" onclick="claimMission('${{m.code}}')">Resgatar +${{m.reward.coins}} coins • +${{m.reward.xp}} XP</button>`:''}}`)).join('');
 $('achievementsList').innerHTML=(state.achievements||[]).map(a=>item(`${{a.unlocked?'🏅':'🔒'}} ${{a.label}}`,a.description,`${{a.progress}}/${{a.target}}`,a.unlocked&&a.title?`<button class="small-btn" onclick="equipTitle('${{a.code}}')">Equipar “${{esc(a.title)}}”</button>`:'' )).join('');
 $('activityList').innerHTML=(state.activity||[]).map(a=>item(a.label||a.event_code,a.category,new Date(a.created_at).toLocaleString('pt-BR'))).join('')||'<div class="v2-empty">Sua linha do tempo começa nas próximas ações.</div>';
 const fs=state.friends||{{}};$('friends').innerHTML=[...(fs.incoming||[]).map(f=>item(`Pedido de ${{f.display_name}}`,'Quer entrar na sua tripulação?','novo',`<div class="row"><button class="small-btn primary" onclick="respondFriend(${{f.user_id}},true)">Aceitar</button><button class="small-btn" onclick="respondFriend(${{f.user_id}},false)">Recusar</button></div>`)),...(fs.friends||[]).map(f=>item(`👥 ${{f.display_name}}`,'Amigo Baltigo','',`<div class="row"><button class="small-btn" onclick="openPath('/messages')">Mensagem</button><button class="small-btn" onclick="v2Toast('Responda uma mensagem desse jogador no grupo e use /duelo.')">Duelo</button></div>`))].join('')||'<div class="v2-empty">Adicione jogadores pelo nickname.</div>';
 $('news').innerHTML=(state.news||[]).map(n=>item(n.title,n.summary,n.followed?'seguindo':'',n.source_url?`<button class="small-btn" onclick="location.href='${{esc(n.source_url)}}'">Abrir fonte</button>`:'' )).join('')||'<div class="v2-empty">Nenhuma notícia publicada no momento.</div>';
 const notif=state.notifications||{{}};$('notificationList').innerHTML=(notif.items||[]).map(n=>item(`${{n.read?'':'● '}}${{n.title}}`,n.body,n.kind,`<button class="small-btn" onclick="readNotification(${{n.id}},'${{n.action_path||''}}')">${{n.action_path?'Abrir':'Marcar lida'}}</button>`)).join('')||'<div class="v2-empty">Nenhuma notificação.</div>';
 const labels={{daily:'Daily',dice_full:'Dados cheios',messages:'Mensagens',duels:'Duelos',trades:'Trocas',requests:'Pedidos',news:'Notícias',airing:'Novos episódios',missions:'Missões',achievements:'Conquistas'}};$('notificationPrefs').innerHTML=Object.entries(notif.preferences||{{}}).map(([k,v])=>item(labels[k]||k,v?'Ativado':'Desativado','',`<button class="small-btn" onclick="togglePref('${{k}}',${{!v}})">${{v?'Desativar':'Ativar'}}</button>`)).join('');
}}
async function load(){{state=await v2Api('/api/v2/ecosystem/state');state=state.state;render();const initial=location.hash.slice(1);if(document.getElementById(initial))tab(initial)}}
async function claimMission(code){{try{{await v2Api('/api/v2/missions/claim',{{method:'POST',body:JSON.stringify({{code}})}});v2Haptic('medium');v2Toast('Recompensa resgatada.');await load()}}catch(e){{v2Toast(e.message)}}}}
async function equipTitle(code){{try{{await v2Api('/api/v2/titles/equip',{{method:'POST',body:JSON.stringify({{code}})}});v2Toast('Título equipado.');await load()}}catch(e){{v2Toast(e.message)}}}}
async function removeMedia(type,id){{try{{await v2Api('/api/v2/library/remove',{{method:'POST',body:JSON.stringify({{media_type:type,media_id:id}})}});await load()}}catch(e){{v2Toast(e.message)}}}}
async function addMedia(item){{try{{await v2Api('/api/v2/library/save',{{method:'POST',body:JSON.stringify({{media_type:'anime',media_id:item.anime_id,title:item.title,cover_url:item.cover,status:'planned',favorite:false}})}});v2Toast('Adicionado à watchlist.');await load()}}catch(e){{v2Toast(e.message)}}}}
async function respondFriend(uid,accept){{try{{await v2Api('/api/v2/friends/respond',{{method:'POST',body:JSON.stringify({{user_id:uid,accept}})}});await load()}}catch(e){{v2Toast(e.message)}}}}
$('addFriend').onclick=async()=>{{const nickname=$('friendNick').value.trim();if(!nickname)return;try{{await v2Api('/api/v2/friends/request',{{method:'POST',body:JSON.stringify({{nickname}})}});v2Toast('Pedido enviado.');$('friendNick').value='';await load()}}catch(e){{v2Toast(e.message)}}}};
async function togglePref(kind,value){{try{{await v2Api('/api/v2/notifications/preferences',{{method:'POST',body:JSON.stringify({{[kind]:value}})}});await load()}}catch(e){{v2Toast(e.message)}}}}
async function readNotification(id,path){{try{{await v2Api('/api/v2/notifications/read',{{method:'POST',body:JSON.stringify({{id}})}});if(path)openPath(path);else await load()}}catch(e){{v2Toast(e.message)}}}}
let searchTimer;$('search').oninput=()=>{{clearTimeout(searchTimer);searchTimer=setTimeout(doSearch,250)}};async function doSearch(){{const q=$('search').value.trim();if(q.length<2){{$('searchResults').innerHTML='';return}};try{{const data=await v2Api('/api/v2/search?q='+encodeURIComponent(q));const r=data.results;let html='';html+=(r.animes||[]).map(a=>item(`📺 ${{a.title}}`,'Anime','',`<button class="small-btn primary" data-anime='${{encodeURIComponent(JSON.stringify(a))}}'>+ Watchlist</button>`)).join('');html+=(r.characters||[]).map(c=>item(`🎴 ${{c.name}}`,c.anime,'Personagem')).join('');html+=(r.people||[]).map(p=>item(`👤 ${{p.display_name}}`,'Jogador público','',`<button class="small-btn" onclick="$('friendNick').value='${{esc(p.display_name)}}';tab('social')">Adicionar</button>`)).join('');$('searchResults').innerHTML=html||'<div class="v2-empty">Nenhum resultado.</div>';document.querySelectorAll('[data-anime]').forEach(b=>b.onclick=()=>addMedia(JSON.parse(decodeURIComponent(b.dataset.anime))))}}catch(e){{v2Toast(e.message)}}}}
load();
</script></body></html>'''


def register_hub_routes(app) -> None:
    @app.get("/hub",response_class=HTMLResponse)
    async def hub_page(): return HTMLResponse(_page())

    @app.get("/api/v2/ecosystem/state")
    async def ecosystem_state_api(request:Request):
        uid=_uid(request)
        if not await rate_limiter.allow(f"hub:state:{uid}",limit=45,window_seconds=60): return JSONResponse({"ok":False,"message":"Muitas atualizações."},status_code=429)
        return JSONResponse({"ok":True,"state":ecosystem_state(uid)})

    @app.get("/api/v2/search")
    async def search_api(request:Request,q:str=Query(default="",max_length=100)):
        uid=_uid(request)
        if not await rate_limiter.allow(f"hub:search:{uid}",limit=30,window_seconds=60): return JSONResponse({"ok":False,"message":"Muitas buscas."},status_code=429)
        return JSONResponse({"ok":True,"results":universal_search(uid,q)})

    @app.post("/api/v2/library/save")
    async def library_save_api(request:Request):
        try: payload=await request.json(); row=save_library_item(_uid(request),payload); return JSONResponse({"ok":True,"item":row},default=str)
        except Exception as exc: return _err(exc)

    @app.post("/api/v2/library/remove")
    async def library_remove_api(request:Request):
        try:
            p=await request.json(); library_remove(_uid(request),str(p.get("media_type") or ""),int(p.get("media_id") or 0)); return JSONResponse({"ok":True})
        except Exception as exc:return _err(exc)

    @app.post("/api/v2/missions/claim")
    async def mission_claim_api(request:Request):
        try: p=await request.json(); return JSONResponse({"ok":True,**claim_mission(_uid(request),str(p.get("code") or ""))})
        except Exception as exc:return _err(exc,409 if getattr(exc,"code","") in {"mission_claimed","mission_incomplete"} else 400)

    @app.post("/api/v2/titles/equip")
    async def title_equip_api(request:Request):
        try:p=await request.json(); return JSONResponse({"ok":True,"title":equip_title(_uid(request),str(p.get("code") or ""))})
        except Exception as exc:return _err(exc)

    @app.post("/api/v2/notifications/preferences")
    async def notification_preferences_api(request:Request):
        try:return JSONResponse({"ok":True,"preferences":update_notification_preferences(_uid(request),await request.json())})
        except Exception as exc:return _err(exc)

    @app.post("/api/v2/notifications/read")
    async def notification_read_api(request:Request):
        try:p=await request.json();mark_notification_read(_uid(request),int(p.get("id") or 0));return JSONResponse({"ok":True})
        except Exception as exc:return _err(exc)

    @app.post("/api/v2/friends/request")
    async def friend_request_api(request:Request):
        try:
            p=await request.json(); target=find_identity_by_nickname(str(p.get("nickname") or ""))
            if not target: raise EcosystemError("user_not_found","Nickname não encontrado.")
            return JSONResponse({"ok":True,"friendship":friend_request(_uid(request),int(target["user_id"]))},default=str)
        except Exception as exc:return _err(exc,409 if getattr(exc,"code","")=="friend_exists" else 400)

    @app.post("/api/v2/friends/respond")
    async def friend_respond_api(request:Request):
        try:p=await request.json();friend_respond(_uid(request),int(p.get("user_id") or 0),bool(p.get("accept")));return JSONResponse({"ok":True})
        except Exception as exc:return _err(exc)
