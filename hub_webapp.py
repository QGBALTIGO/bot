from __future__ import annotations

from fastapi import Query, Request
from fastapi.responses import HTMLResponse

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
from utils.api_response import api_error, api_ok
from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def _failure(exc: Exception, status_code: int = 400):
    return api_error(
        getattr(exc, "message", str(exc) or "Não foi possível concluir."),
        code=getattr(exc, "code", "request_failed"),
        status_code=status_code,
    )


def _page() -> str:
    return f'''<!doctype html><html lang="pt-br"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#050711"><title>Baltigo</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script><style>{base_css()}
.view{{display:none;padding-bottom:84px}}.view.active{{display:block;animation:hubIn .22s ease}}@keyframes hubIn{{from{{opacity:.25;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
.hub-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;margin-top:13px}}.quick{{padding:14px;border:1px solid var(--line);border-radius:19px;background:var(--surface-soft);cursor:pointer;min-height:85px}}.quick small{{color:var(--muted);font-size:10px}}.quick b{{display:block;margin-top:7px;font-size:14px}}
.stack{{display:grid;gap:9px;margin-top:12px}}.item{{padding:13px;border:1px solid var(--line);border-radius:18px;background:var(--surface-soft)}}.head{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}}.item h3{{margin:0;font-size:15px}}.item p{{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.45}}.pill{{padding:5px 8px;border-radius:999px;background:rgba(255,255,255,.07);font-size:9px;font-weight:900;white-space:nowrap}}
.row{{display:flex;gap:8px;align-items:center}}.row>*{{flex:1}}.mini{{border:1px solid var(--line);border-radius:13px;background:rgba(255,255,255,.06);padding:9px 10px;font-weight:850;cursor:pointer}}.mini.primary{{border:0;background:linear-gradient(135deg,var(--pink),var(--violet))}}.progress{{height:7px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden;margin:9px 0}}.progress span{{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--violet))}}
.bottom-nav{{position:fixed;z-index:90;left:50%;bottom:calc(8px + var(--safe-bottom));transform:translateX(-50%);width:min(640px,calc(100% - 18px));display:grid;grid-template-columns:repeat(5,1fr);padding:6px;border:1px solid var(--line);border-radius:22px;background:rgba(8,13,27,.94);backdrop-filter:blur(18px);box-shadow:var(--shadow)}}.nav{{border:0;background:transparent;padding:7px 2px;border-radius:15px;color:var(--muted);font-size:9px;font-weight:900}}.nav i{{display:block;font-style:normal;font-size:18px;margin-bottom:2px}}.nav.active{{color:var(--text);background:rgba(255,255,255,.07)}}
@media(min-width:760px){{.hub-grid{{grid-template-columns:repeat(4,1fr)}}}}
</style></head><body data-v2-no-home="1"><div class="v2-shell">
<section id="home" class="view active"><div class="v2-hero"><div class="v2-eyebrow">Source Baltigo V2</div><h1 class="v2-title" id="hello">Seu universo anime.</h1><p class="v2-copy" id="subtitle">Carregando sua jornada…</p><div class="v2-metrics"><div class="v2-metric"><span class="v2-metric-label">Nível</span><b class="v2-metric-value" id="level">—</b></div><div class="v2-metric"><span class="v2-metric-label">Coins</span><b class="v2-metric-value" id="coins">—</b></div><div class="v2-metric"><span class="v2-metric-label">Cards</span><b class="v2-metric-value" id="cards">—</b></div></div></div><div class="v2-panel"><h2 class="v2-section-title">Continue de onde parou</h2><div id="continue" class="stack"></div></div><div class="hub-grid"><div class="quick" data-go="/game"><small>Jogar</small><b>🎮 Game Center</b></div><div class="quick" data-go="/collection"><small>Colecionar</small><b>🎴 Coleção</b></div><div class="quick" data-tab="missions"><small>Progredir</small><b>✅ Missões</b></div><div class="quick" data-go="/messages"><small>Conversar</small><b>💬 Mensagens</b></div><div class="quick" data-tab="library"><small>Acompanhar</small><b>⭐ Watchlist</b></div><div class="quick" data-go="/agenda"><small>Hoje</small><b>📅 Agenda</b></div><div class="quick" data-go="/ranking"><small>Competir</small><b>🏆 Ranking</b></div><div class="quick" data-go="/xcards"><small>Battle</small><b>⚔️ XCards</b></div></div><div class="v2-panel"><h2 class="v2-section-title">Para você</h2><p class="v2-section-copy">O Baltigo usa sua própria jornada para sugerir o próximo passo.</p><div id="recommendations" class="stack"></div></div></section>
<section id="explore" class="view"><div class="v2-hero"><div class="v2-eyebrow">Explorar</div><h1 class="v2-title">Uma busca.<br>Tudo.</h1><p class="v2-copy">Obras, personagens e jogadores públicos.</p></div><div class="v2-panel"><div class="v2-search">🔎 <input id="search" placeholder="Anime, personagem ou nickname…"></div><div id="searchResults" class="stack"></div></div><div class="v2-panel"><h2 class="v2-section-title">Notícias para você</h2><div id="news" class="stack"></div></div></section>
<section id="library" class="view"><div class="v2-hero"><div class="v2-eyebrow">Biblioteca</div><h1 class="v2-title">Favoritos &<br>Watchlist.</h1><p class="v2-copy">O que você acompanha alimenta agenda, notícias e recomendações.</p></div><div class="hub-grid"><div class="quick" data-go="/agenda"><small>Automática</small><b>📅 Próximos episódios</b></div><div class="quick" data-tab="explore"><small>Adicionar</small><b>🔎 Buscar obras</b></div></div><div id="libraryList" class="stack"></div></section>
<section id="social" class="view"><div class="v2-hero"><div class="v2-eyebrow">Social</div><h1 class="v2-title">Sua tripulação.</h1><p class="v2-copy">Amigos conectam mensagens, trocas e duelos.</p></div><div class="v2-panel"><div class="row"><input id="friendNick" style="min-height:48px;border:1px solid var(--line);border-radius:15px;background:var(--surface-soft);padding:0 12px" placeholder="nickname"><button id="addFriend" class="mini primary">Adicionar</button></div></div><div id="friends" class="stack"></div></section>
<section id="profile" class="view"><div class="v2-hero"><div class="v2-eyebrow">Sua jornada</div><h1 class="v2-title">Evolua e<br>personalize.</h1><p class="v2-copy">Missões, conquistas, títulos, histórico e alertas.</p></div><div class="hub-grid"><div class="quick" data-tab="missions"><small>Objetivos</small><b>✅ Missões</b></div><div class="quick" data-tab="achievements"><small>Marcos</small><b>🏅 Conquistas</b></div><div class="quick" data-tab="activity"><small>Histórico</small><b>🧾 Atividade</b></div><div class="quick" data-tab="notifications"><small>Controle</small><b>🔔 Notificações</b></div><div class="quick" data-go="/profile"><small>Identidade</small><b>👤 Perfil completo</b></div><div class="quick" data-go="/shop-v2"><small>Cosméticos & recursos</small><b>🛒 Loja</b></div></div></section>
<section id="missions" class="view"><div class="v2-hero"><div class="v2-eyebrow">Missões</div><h1 class="v2-title">Use todo o<br>Baltigo.</h1><p class="v2-copy">Diárias e semanais atravessam jogos, coleção e social.</p></div><div id="missionsList" class="stack"></div></section>
<section id="achievements" class="view"><div class="v2-hero"><div class="v2-eyebrow">Conquistas</div><h1 class="v2-title">Sua história<br>vira título.</h1><p class="v2-copy">Marcos desbloqueiam títulos equipáveis.</p></div><div id="achievementsList" class="stack"></div></section>
<section id="activity" class="view"><div class="v2-hero"><div class="v2-eyebrow">Atividade</div><h1 class="v2-title">Tudo deixa<br>rastro.</h1><p class="v2-copy">Uma timeline para jogos, coleção, social e progressão.</p></div><div id="activityList" class="stack"></div></section>
<section id="notifications" class="view"><div class="v2-hero"><div class="v2-eyebrow">Notificações</div><h1 class="v2-title">Você escolhe<br>o que importa.</h1><p class="v2-copy">Alertas granulares, sem transformar o bot em spam.</p></div><div id="notificationPrefs" class="stack"></div><div class="v2-panel"><h2 class="v2-section-title">Recentes</h2><div id="notificationList" class="stack"></div></div></section>
</div><nav class="bottom-nav"><button class="nav active" data-nav="home"><i>⌂</i>Início</button><button class="nav" data-nav="explore"><i>🔎</i>Explorar</button><button class="nav" data-nav="library"><i>🎴</i>Biblioteca</button><button class="nav" data-nav="social"><i>👥</i>Social</button><button class="nav" data-nav="profile"><i>👤</i>Perfil</button></nav><div id="v2Toast" class="v2-toast"></div><script>{telegram_bootstrap_js()}
let state=null;const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
function go(p){{location.href=p}}function tab(name){{document.querySelectorAll('.view').forEach(x=>x.classList.toggle('active',x.id===name));document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.nav===name));if(document.getElementById(name))history.replaceState(null,'','#'+name);scrollTo(0,0)}}document.addEventListener('click',e=>{{const g=e.target.closest('[data-go]');if(g)go(g.dataset.go);const t=e.target.closest('[data-tab]');if(t)tab(t.dataset.tab)}});document.querySelectorAll('[data-nav]').forEach(x=>x.onclick=()=>tab(x.dataset.nav));
function card(title,copy,badge='',actions=''){{return `<div class="item"><div class="head"><div><h3>${{esc(title)}}</h3><p>${{esc(copy)}}</p></div>${{badge?`<span class="pill">${{esc(badge)}}</span>`:''}}</div>${{actions}}</div>`}}
function render(){{const d=state.dashboard||{{}};$('hello').textContent=`Olá, ${{d.display_name||'Navegante'}}.`;$('subtitle').textContent=d.equipped_title?`“${{d.equipped_title}}” equipado • sua jornada está sincronizada.`:'Explore, colecione, jogue, socialize e evolua no mesmo universo.';$('level').textContent=d.progress?.level??1;$('coins').textContent=d.wallet?.coins??0;$('cards').textContent=d.collection?.unique??d.collection?.unique_cards??0;
$('continue').innerHTML=(d.continue||[]).map(x=>card(`${{x.icon}} ${{x.title}}`,x.copy,'',`<button class="mini primary" onclick="go('${{x.path}}')">Continuar</button>`)).join('')||'<div class="v2-empty">Tudo em dia. Explore algo novo.</div>';
$('recommendations').innerHTML=(state.recommendations||[]).map(x=>card(x.title,x.reason,`${{x.owned}}/${{x.total}}`,`<div class="progress"><span style="width:${{x.completion}}%"></span></div>`)).join('')||'<div class="v2-empty">Conquiste alguns cards para personalizar as recomendações.</div>';
$('libraryList').innerHTML=(state.library?.items||[]).map(x=>card(`${{x.is_favorite?'⭐ ':''}}${{x.title}}`,`${{x.media_type}} • ${{x.status}} • progresso ${{x.progress||0}}`,'',`<div class="row"><button class="mini" onclick="updateMedia(${{encodeURIComponent(JSON.stringify(x))}},'watching')">Assistindo</button><button class="mini" onclick="removeMedia('${{x.media_type}}',${{x.media_id}})">Remover</button></div>`)).join('')||'<div class="v2-empty">Sua biblioteca está vazia. Procure uma obra em Explorar.</div>';
$('missionsList').innerHTML=(state.missions||[]).map(m=>card(m.label,m.description,`${{m.progress}}/${{m.target}}`,`<div class="progress"><span style="width:${{Math.min(100,m.progress/m.target*100)}}%"></span></div>${{m.completed&&!m.claimed?`<button class="mini primary" onclick="claimMission('${{m.code}}')">Resgatar +${{m.reward.coins}} coins • +${{m.reward.xp}} XP</button>`:''}}`)).join('');
$('achievementsList').innerHTML=(state.achievements||[]).map(a=>card(`${{a.unlocked?'🏅':'🔒'}} ${{a.label}}`,a.description,`${{a.progress}}/${{a.target}}`,a.unlocked&&a.title?`<button class="mini" onclick="equipTitle('${{a.code}}')">Equipar “${{esc(a.title)}}”</button>`:'' )).join('');
$('activityList').innerHTML=(state.activity||[]).map(a=>card(a.label||a.event_code,a.category,a.created_at?new Date(a.created_at).toLocaleString('pt-BR'):'' )).join('')||'<div class="v2-empty">Sua timeline vai aparecer aqui.</div>';
const f=state.friends||{{}};$('friends').innerHTML=[...(f.incoming||[]).map(x=>card(`Pedido de ${{x.display_name}}`,'Quer entrar na sua tripulação?','novo',`<div class="row"><button class="mini primary" onclick="respondFriend(${{x.user_id}},true)">Aceitar</button><button class="mini" onclick="respondFriend(${{x.user_id}},false)">Recusar</button></div>`)),...(f.friends||[]).map(x=>card(`👥 ${{x.display_name}}`,'Amigo Baltigo','',`<div class="row"><button class="mini" onclick="go('/messages')">Mensagens</button><button class="mini" onclick="v2Toast('No grupo, responda uma mensagem desse jogador e use /duelo.')">Duelo</button></div>`))].join('')||'<div class="v2-empty">Adicione alguém pelo nickname.</div>';
$('news').innerHTML=(state.news||[]).map(n=>card(n.title,n.summary,n.followed?'seguindo':'',n.source_url?`<a class="mini" href="${{esc(n.source_url)}}">Abrir fonte</a>`:'' )).join('')||'<div class="v2-empty">Nenhuma notícia sincronizada agora.</div>';
const n=state.notifications||{{}};const labels={{daily:'Daily',dice_full:'Dados cheios',messages:'Mensagens',duels:'Duelos',trades:'Trocas',requests:'Pedidos',news:'Notícias',airing:'Novos episódios',missions:'Missões',achievements:'Conquistas'}};$('notificationPrefs').innerHTML=Object.entries(n.preferences||{{}}).map(([k,v])=>card(labels[k]||k,v?'Ativado':'Desativado','',`<button class="mini" onclick="togglePref('${{k}}',${{!v}})">${{v?'Desativar':'Ativar'}}</button>`)).join('');$('notificationList').innerHTML=(n.items||[]).map(x=>card(`${{x.read?'':'● '}}${{x.title}}`,x.body,x.kind,`<button class="mini" onclick="readNotification(${{x.id}},'${{esc(x.action_path||'')}}')">${{x.action_path?'Abrir':'Marcar lida'}}</button>`)).join('')||'<div class="v2-empty">Sem notificações.</div>'}}
async function load(){{try{{state=(await v2Api('/api/v2/ecosystem/state')).state;render();const h=location.hash.slice(1);if(h&&document.getElementById(h))tab(h)}}catch(e){{v2Toast(e.message)}}}}
async function claimMission(code){{try{{await v2Api('/api/v2/missions/claim',{{method:'POST',body:JSON.stringify({{code}})}});v2Notify('success');v2Toast('Recompensa resgatada.');await load()}}catch(e){{v2Toast(e.message)}}}}async function equipTitle(code){{try{{await v2Api('/api/v2/titles/equip',{{method:'POST',body:JSON.stringify({{code}})}});v2Toast('Título equipado.');await load()}}catch(e){{v2Toast(e.message)}}}}
async function removeMedia(media_type,media_id){{try{{await v2Api('/api/v2/library/remove',{{method:'POST',body:JSON.stringify({{media_type,media_id}})}});await load()}}catch(e){{v2Toast(e.message)}}}}async function updateMedia(encoded,status){{const x=JSON.parse(decodeURIComponent(encoded));try{{await v2Api('/api/v2/library/save',{{method:'POST',body:JSON.stringify({{media_type:x.media_type,media_id:x.media_id,title:x.title,cover_url:x.cover_url,status,favorite:x.is_favorite,progress:x.progress}})}});await load()}}catch(e){{v2Toast(e.message)}}}}
async function addAnime(a){{try{{await v2Api('/api/v2/library/save',{{method:'POST',body:JSON.stringify({{media_type:'anime',media_id:a.anime_id,title:a.title,cover_url:a.cover,status:'planned',favorite:false}})}});v2Toast('Adicionado à watchlist.');await load();tab('library')}}catch(e){{v2Toast(e.message)}}}}
$('addFriend').onclick=async()=>{{const nickname=$('friendNick').value.trim();if(!nickname)return;try{{await v2Api('/api/v2/friends/request',{{method:'POST',body:JSON.stringify({{nickname}})}});$('friendNick').value='';v2Toast('Pedido enviado.');await load()}}catch(e){{v2Toast(e.message)}}}};async function respondFriend(user_id,accept){{try{{await v2Api('/api/v2/friends/respond',{{method:'POST',body:JSON.stringify({{user_id,accept}})}});await load()}}catch(e){{v2Toast(e.message)}}}}
async function togglePref(kind,value){{try{{await v2Api('/api/v2/notifications/preferences',{{method:'POST',body:JSON.stringify({{[kind]:value}})}});await load()}}catch(e){{v2Toast(e.message)}}}}async function readNotification(id,path){{try{{await v2Api('/api/v2/notifications/read',{{method:'POST',body:JSON.stringify({{id}})}});if(path)go(path);else await load()}}catch(e){{v2Toast(e.message)}}}}
let timer;$('search').oninput=()=>{{clearTimeout(timer);timer=setTimeout(searchNow,250)}};async function searchNow(){{const q=$('search').value.trim();if(q.length<2){{$('searchResults').innerHTML='';return}};try{{const r=(await v2Api('/api/v2/search?q='+encodeURIComponent(q))).results;let out='';out+=(r.animes||[]).map(a=>card(`📺 ${{a.title}}`,'Anime','',`<button class="mini primary add-anime" data-a="${{encodeURIComponent(JSON.stringify(a))}}">+ Watchlist</button>`)).join('');out+=(r.characters||[]).map(c=>card(`🎴 ${{c.name}}`,c.anime,'Personagem')).join('');out+=(r.people||[]).map(p=>card(`👤 ${{p.display_name}}`,'Jogador público',p.nickname?'nickname':'',p.nickname?`<button class="mini add-person" data-n="${{esc(p.nickname)}}">Adicionar</button>`:'' )).join('');$('searchResults').innerHTML=out||'<div class="v2-empty">Nenhum resultado.</div>';document.querySelectorAll('.add-anime').forEach(b=>b.onclick=()=>addAnime(JSON.parse(decodeURIComponent(b.dataset.a))));document.querySelectorAll('.add-person').forEach(b=>b.onclick=()=>{{$('friendNick').value=b.dataset.n;tab('social')}})}}catch(e){{v2Toast(e.message)}}}}
load();</script></body></html>'''


def register_hub_routes(app) -> None:
    @app.get("/hub", response_class=HTMLResponse)
    async def hub_page():
        return HTMLResponse(_page())

    @app.get("/api/v2/ecosystem/state")
    async def state_api(request: Request):
        uid = _uid(request)
        if not await rate_limiter.allow(f"hub:state:{uid}", limit=45, window_seconds=60):
            return api_error("Muitas atualizações.", code="rate_limited", status_code=429)
        return api_ok(state=ecosystem_state(uid))

    @app.get("/api/v2/search")
    async def search_api(request: Request, q: str = Query(default="", max_length=100)):
        uid = _uid(request)
        if not await rate_limiter.allow(f"hub:search:{uid}", limit=30, window_seconds=60):
            return api_error("Muitas buscas.", code="rate_limited", status_code=429)
        return api_ok(results=universal_search(uid, q))

    @app.post("/api/v2/library/save")
    async def save_api(request: Request):
        try:
            return api_ok(item=save_library_item(_uid(request), await request.json()))
        except Exception as exc:
            return _failure(exc)

    @app.post("/api/v2/library/remove")
    async def remove_api(request: Request):
        try:
            p = await request.json()
            library_remove(_uid(request), str(p.get("media_type") or ""), int(p.get("media_id") or 0))
            return api_ok()
        except Exception as exc:
            return _failure(exc)

    @app.post("/api/v2/missions/claim")
    async def mission_api(request: Request):
        try:
            p = await request.json()
            return api_ok(result=claim_mission(_uid(request), str(p.get("code") or "")))
        except Exception as exc:
            status = 409 if getattr(exc, "code", "") in {"mission_claimed", "mission_incomplete"} else 400
            return _failure(exc, status)

    @app.post("/api/v2/titles/equip")
    async def title_api(request: Request):
        try:
            p = await request.json()
            return api_ok(title=equip_title(_uid(request), str(p.get("code") or "")))
        except Exception as exc:
            return _failure(exc)

    @app.post("/api/v2/notifications/preferences")
    async def preferences_api(request: Request):
        try:
            return api_ok(preferences=update_notification_preferences(_uid(request), await request.json()))
        except Exception as exc:
            return _failure(exc)

    @app.post("/api/v2/notifications/read")
    async def read_api(request: Request):
        try:
            p = await request.json()
            mark_notification_read(_uid(request), int(p.get("id") or 0))
            return api_ok()
        except Exception as exc:
            return _failure(exc)

    @app.post("/api/v2/friends/request")
    async def friend_request_api(request: Request):
        try:
            p = await request.json()
            target = find_identity_by_nickname(str(p.get("nickname") or ""))
            if not target:
                raise EcosystemError("user_not_found", "Nickname não encontrado.")
            return api_ok(friendship=friend_request(_uid(request), int(target["user_id"])))
        except Exception as exc:
            return _failure(exc, 409 if getattr(exc, "code", "") == "friend_exists" else 400)

    @app.post("/api/v2/friends/respond")
    async def friend_respond_api(request: Request):
        try:
            p = await request.json()
            friend_respond(_uid(request), int(p.get("user_id") or 0), bool(p.get("accept")))
            return api_ok()
        except Exception as exc:
            return _failure(exc)
