from __future__ import annotations

import html

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse


def _h(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def build_source_v2_router(*, banner_url: str = "") -> APIRouter:
    router = APIRouter(tags=["source-v2"])

    @router.get("/source-v2", response_class=HTMLResponse)
    @router.get("/app-v2", response_class=HTMLResponse)
    def source_v2_page(uid: int = Query(default=0)):
        banner = _h(banner_url)
        page = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#09090b">
<title>Source Baltigo V2</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700;800&display=swap">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{
  color-scheme:dark;
  --bg:#09090b;
  --bg2:#0c0c0e;
  --surface:#18181b;
  --surface2:#111113;
  --glass:rgba(9,9,11,.91);
  --line:rgba(255,255,255,.08);
  --line2:rgba(255,255,255,.14);
  --text:#fafafa;
  --muted:#a1a1aa;
  --dim:#71717a;
  --blue:#3b82f6;
  --blue-soft:rgba(59,130,246,.12);
  --green:#10b981;
  --amber:#f59e0b;
  --red:#ef4444;
  --purple:#a855f7;
  --cyan:#06b6d4;
  --safe-top:env(safe-area-inset-top,0px);
  --safe-bottom:env(safe-area-inset-bottom,0px);
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text)}
body{font-family:"Outfit",system-ui,sans-serif;-webkit-font-smoothing:antialiased;letter-spacing:-.01em}
button,input{font:inherit;color:inherit}
button{cursor:pointer}
a{color:inherit;text-decoration:none}
img{display:block;max-width:100%}
.mono{font-family:"JetBrains Mono",monospace}
#app{height:100%;display:flex;flex-direction:column;overflow:hidden;background:radial-gradient(800px 420px at 100% -10%,rgba(59,130,246,.13),transparent 60%),var(--bg)}
.intro{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;background:#09090b;transition:opacity .34s ease,visibility .34s ease}
.intro.hidden{opacity:0;visibility:hidden;pointer-events:none}
.intro-core{width:min(300px,78vw);text-align:center}
.intro-mark{width:68px;height:68px;border-radius:22px;margin:0 auto 22px;display:grid;place-items:center;background:linear-gradient(145deg,#2563eb,#60a5fa);box-shadow:0 18px 54px rgba(37,99,235,.25);font-size:29px;font-weight:900;animation:introPulse 1.8s ease-in-out infinite}
.intro-title{font-weight:900;font-size:21px;letter-spacing:.18em}.intro-sub{margin-top:8px;color:var(--muted);font-size:12px;letter-spacing:.08em}
.intro-line{height:2px;border-radius:999px;background:#18181b;margin-top:24px;overflow:hidden}.intro-line::after{content:"";display:block;height:100%;width:44%;background:var(--blue);animation:loading 1.1s ease-in-out infinite}
@keyframes introPulse{50%{transform:scale(1.05);filter:brightness(1.12)}}
@keyframes loading{0%{transform:translateX(-110%)}100%{transform:translateX(330%)}}
.topbar{flex:0 0 auto;height:calc(64px + var(--safe-top));padding:calc(var(--safe-top) + 10px) 16px 10px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:rgba(9,9,11,.94);backdrop-filter:blur(16px);z-index:30}
.brand{display:flex;align-items:center;gap:11px;min-width:0}.brand-mark{width:38px;height:38px;border-radius:12px;background:linear-gradient(145deg,#2563eb,#60a5fa);display:grid;place-items:center;font-weight:900;box-shadow:0 8px 24px rgba(37,99,235,.22)}
.brand-copy{min-width:0}.brand-name{font-weight:900;letter-spacing:.11em;font-size:13px}.brand-status{font-size:10px;color:var(--muted);margin-top:2px;white-space:nowrap}
.icon-btn{width:40px;height:40px;border-radius:12px;border:1px solid var(--line);background:#111113;display:grid;place-items:center}.icon-btn:active{transform:scale(.96)}
.scroller{flex:1 1 auto;min-height:0;overflow-y:auto;overscroll-behavior:none;scrollbar-width:none}.scroller::-webkit-scrollbar{display:none}
.page{max-width:920px;margin:0 auto;padding:18px 16px calc(94px + var(--safe-bottom));animation:pageIn .26s cubic-bezier(.16,1,.3,1)}
@keyframes pageIn{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
.hero{position:relative;min-height:260px;border:1px solid var(--line);border-radius:24px;overflow:hidden;background:#111113;box-shadow:0 18px 50px rgba(0,0,0,.28)}
.hero-bg{position:absolute;inset:0;background-size:cover;background-position:center 24%;opacity:.72}.hero-bg::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(9,9,11,.12),rgba(9,9,11,.92) 84%),linear-gradient(90deg,rgba(9,9,11,.52),transparent)}
.hero-body{position:relative;z-index:1;min-height:260px;padding:22px;display:flex;flex-direction:column;justify-content:flex-end}.eyebrow{font:700 10px "JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.18em;color:#93c5fd}.hero h1{margin:7px 0 8px;font-size:clamp(30px,8vw,48px);line-height:.94;letter-spacing:-.055em}.hero p{margin:0;color:#d4d4d8;font-size:13px;line-height:1.55;max-width:570px}
.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:14px}.metric{padding:13px;border:1px solid var(--line);border-radius:16px;background:rgba(24,24,27,.66);backdrop-filter:blur(12px)}.metric-label{font:700 9px "JetBrains Mono",monospace;letter-spacing:.13em;text-transform:uppercase;color:var(--dim)}.metric-value{font-weight:800;font-size:17px;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.section{margin-top:20px}.section-head{display:flex;justify-content:space-between;align-items:end;gap:12px;margin-bottom:12px}.section-title{margin:0;font-size:19px;letter-spacing:-.035em}.section-kicker{font:700 9px "JetBrains Mono",monospace;color:var(--dim);letter-spacing:.14em;text-transform:uppercase;margin-bottom:5px}.section-link{font-size:11px;font-weight:800;color:#93c5fd}
.quick-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.quick{min-height:112px;border:1px solid var(--line);border-radius:18px;padding:14px;background:linear-gradient(145deg,#18181b,#111113);text-align:left;position:relative;overflow:hidden}.quick::after{content:"";position:absolute;width:96px;height:96px;border-radius:50%;right:-40px;top:-40px;background:radial-gradient(circle,rgba(59,130,246,.18),transparent 70%)}.quick-icon{font-size:20px}.quick-title{font-weight:800;font-size:14px;margin-top:18px}.quick-sub{font-size:10px;color:var(--dim);margin-top:3px}.quick:active{transform:scale(.985)}
.card-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.char-card{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:#111113;position:relative}.char-art{aspect-ratio:2/3;background:#18181b;position:relative;overflow:hidden}.char-art img{width:100%;height:100%;object-fit:cover}.char-art::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,transparent 55%,rgba(9,9,11,.72))}.char-qty{position:absolute;right:9px;bottom:9px;z-index:2;padding:6px 8px;border-radius:999px;border:1px solid var(--line2);background:rgba(9,9,11,.72);backdrop-filter:blur(10px);font:700 9px "JetBrains Mono",monospace}.char-body{padding:11px}.char-name{font-weight:800;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.char-anime{font-size:10px;color:var(--dim);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.skeleton{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:#111113}.skeleton-art{aspect-ratio:2/3;background:linear-gradient(90deg,#111113,#222226,#111113);background-size:200% 100%;animation:shimmer 1.3s linear infinite}.skeleton-line{height:10px;margin:11px;border-radius:999px;background:linear-gradient(90deg,#18181b,#27272a,#18181b);background-size:200% 100%;animation:shimmer 1.3s linear infinite}@keyframes shimmer{to{background-position:-200% 0}}
.empty{padding:26px 18px;border:1px dashed var(--line2);border-radius:18px;text-align:center;color:var(--muted);font-size:12px}.empty strong{display:block;color:var(--text);font-size:15px;margin-bottom:5px}
.drawer-backdrop{position:fixed;inset:0;z-index:80;background:rgba(0,0,0,.62);backdrop-filter:blur(3px);opacity:0;visibility:hidden;transition:.24s}.drawer-backdrop.open{opacity:1;visibility:visible}.drawer{position:absolute;top:0;bottom:0;left:0;width:min(86vw,360px);padding:calc(16px + var(--safe-top)) 14px calc(18px + var(--safe-bottom));background:#0c0c0e;border-right:1px solid var(--line);transform:translateX(-102%);transition:transform .28s cubic-bezier(.16,1,.3,1);overflow-y:auto}.drawer-backdrop.open .drawer{transform:none}.drawer-head{padding:8px 6px 18px;border-bottom:1px solid var(--line);margin-bottom:12px}.drawer-brand{font-size:18px;font-weight:900}.drawer-caption{font-size:11px;color:var(--dim);margin-top:4px}.nav-group{margin-top:16px}.nav-label{font:700 9px "JetBrains Mono",monospace;color:#52525b;letter-spacing:.15em;text-transform:uppercase;padding:0 10px 7px}.nav-item{width:100%;display:flex;align-items:center;gap:12px;padding:12px 11px;border:0;border-radius:13px;background:transparent;text-align:left;color:#d4d4d8}.nav-item.active{background:var(--blue-soft);color:#dbeafe}.nav-item:hover{background:#18181b}.nav-ico{width:25px;text-align:center}.nav-copy{flex:1}.nav-title{font-weight:700;font-size:13px}.nav-meta{font-size:9px;color:var(--dim);margin-top:1px}.nav-badge{font:700 8px "JetBrains Mono",monospace;padding:4px 6px;border-radius:999px;background:#18181b;color:var(--muted)}
.bottom-nav{position:fixed;left:50%;bottom:calc(10px + var(--safe-bottom));transform:translateX(-50%);z-index:35;width:min(calc(100% - 24px),560px);height:62px;padding:6px;display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--line2);border-radius:20px;background:rgba(9,9,11,.91);backdrop-filter:blur(20px);box-shadow:0 18px 50px rgba(0,0,0,.4)}.bottom-btn{border:0;border-radius:14px;background:transparent;color:var(--dim);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:9px;font-weight:700}.bottom-btn span:first-child{font-size:18px}.bottom-btn.active{background:var(--blue-soft);color:#dbeafe}
.panel{border:1px solid var(--line);border-radius:18px;background:#111113;padding:16px}.profile-row{display:flex;align-items:center;gap:14px}.avatar{width:60px;height:60px;border-radius:20px;border:1px solid var(--line2);background:linear-gradient(145deg,#1d4ed8,#60a5fa);display:grid;place-items:center;font-size:23px;font-weight:900}.profile-name{font-weight:900;font-size:20px}.profile-user{font:600 10px "JetBrains Mono",monospace;color:var(--dim);margin-top:3px}.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}.mini-stat{padding:10px;border:1px solid var(--line);border-radius:13px;background:#18181b}.mini-stat b{display:block;font-size:15px}.mini-stat span{font-size:9px;color:var(--dim)}
.future{display:grid;gap:9px}.future-row{display:flex;align-items:center;gap:12px;padding:13px;border:1px solid var(--line);border-radius:15px;background:#111113}.future-ico{font-size:20px}.future-copy{flex:1}.future-title{font-weight:800;font-size:13px}.future-sub{font-size:10px;color:var(--dim);margin-top:2px}.future-tag{font:700 8px "JetBrains Mono",monospace;padding:5px 7px;border-radius:999px;background:#18181b;color:#93c5fd}
.credit{text-align:center;color:#52525b;font-size:9px;line-height:1.5;margin:28px 0 4px}.credit strong{color:#71717a}
.toast{position:fixed;left:50%;bottom:calc(84px + var(--safe-bottom));z-index:200;transform:translate(-50%,16px);opacity:0;pointer-events:none;transition:.22s;padding:10px 13px;border:1px solid var(--line2);border-radius:13px;background:#18181b;box-shadow:0 16px 40px rgba(0,0,0,.35);font-size:11px;max-width:calc(100% - 30px);text-align:center}.toast.show{opacity:1;transform:translate(-50%,0)}
@media(min-width:680px){.card-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.quick-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.metrics{grid-template-columns:repeat(4,1fr)}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
</style>
</head>
<body>
<div class="intro" id="intro"><div class="intro-core"><div class="intro-mark">S</div><div class="intro-title">SOURCE</div><div class="intro-sub">Inicializando seu universo</div><div class="intro-line"></div></div></div>
<div id="app">
<header class="topbar"><div class="brand"><div class="brand-mark">S</div><div class="brand-copy"><div class="brand-name">SOURCE BALTIGO</div><div class="brand-status" id="topStatus">Sincronizando perfil...</div></div></div><button class="icon-btn" id="menuBtn" aria-label="Menu">☰</button></header>
<div class="scroller" id="scroller"><main class="page" id="page"></main></div>
<nav class="bottom-nav" id="bottomNav">
<button class="bottom-btn" data-route="profile"><span>◉</span><span>Perfil</span></button>
<button class="bottom-btn" data-route="collection"><span>▦</span><span>Coleção</span></button>
<button class="bottom-btn" data-route="gacha"><span>✦</span><span>Gacha</span></button>
<button class="bottom-btn" data-route="quests"><span>✓</span><span>Missões</span></button>
<button class="bottom-btn" data-route="games"><span>◆</span><span>Jogos</span></button>
</nav>
</div>
<div class="drawer-backdrop" id="drawerBackdrop"><aside class="drawer"><div class="drawer-head"><div class="drawer-brand">Source Baltigo</div><div class="drawer-caption">Colecione. Evolua. Descubra.</div></div><div id="drawerNav"></div><div class="credit"><strong>Source Baltigo</strong><br>Interface e sistemas adaptados com referência ao projeto AniNexus, de bisug.</div></aside></div>
<div class="toast" id="toast"></div>
<script>
const BANNER_URL = '__BANNER__';
const TG = window.Telegram?.WebApp || null;
const state = { profile:null, stats:null, cards:[], route:'profile', loaded:false, uid:0, scroll:new Map() };
const routeAliases = {home:'profile',me:'profile',harem:'collection',inventory:'collection',cards:'collection',roll:'gacha',dice:'gacha',missions:'quests',tasks:'quests',memory:'games',memoria:'games'};
const routes = new Set(['profile','collection','gacha','shop','incubation','pets','quests','pass','achievements','leaderboard','trading','exchange','referrals','games','catalog','manga','music','news','akira','admin']);
const drawerGroups = [
  ['Jogo', [['profile','◉','Perfil','Sua identidade no Source'],['collection','▦','Coleção','Personagens e progresso'],['gacha','✦','Gacha','Rolagens e pity'],['shop','◇','Loja','Itens e economia'],['incubation','◌','Incubadora','Ovos e recompensas'],['pets','♢','Companheiros','Pets e bônus']]],
  ['Progressão', [['quests','✓','Missões','Diárias e semanais'],['pass','▤','Temporada','Pass e recompensas'],['achievements','✹','Conquistas','Metas e badges'],['leaderboard','△','Rankings','Competição global'],['trading','⇄','Trocas','Negociações seguras'],['exchange','↔','Câmbio','Conversão de recursos'],['referrals','＋','Indicações','Convide amigos']]],
  ['Ecossistema', [['games','◆','Jogos','Memória e Termo'],['catalog','▶','Animes','Catálogo Source'],['manga','▥','Mangás','Biblioteca'],['news','◫','AniNexus','Notícias'],['music','♫','Música','Player e rádios'],['akira','✧','Akira','Assistente Source']]],
  ['Administração', [['admin','⌘','Source Admin','Staff, assets e sistema']]],
];
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function num(v){return new Intl.NumberFormat('pt-BR').format(Number(v||0));}
function getUid(){const q=new URLSearchParams(location.search);const u=Number(q.get('uid')||0);return Number.isFinite(u)&&u>0?u:0;}
function haptic(kind='selection'){try{if(kind==='success')TG?.HapticFeedback?.notificationOccurred?.('success');else TG?.HapticFeedback?.selectionChanged?.();}catch(_){}}
function toast(msg){const el=document.getElementById('toast');el.textContent=msg;el.classList.add('show');clearTimeout(toast._t);toast._t=setTimeout(()=>el.classList.remove('show'),1800);}
async function api(url,opts={}){const headers={...(opts.headers||{})};if(TG?.initData)headers['x-telegram-init-data']=TG.initData;if(state.uid)headers['x-webapp-uid']=String(state.uid);const u=new URL(url,location.origin);if(state.uid&&!u.searchParams.has('uid'))u.searchParams.set('uid',String(state.uid));const r=await fetch(u.pathname+u.search,{...opts,headers});let data={};try{data=await r.json()}catch(_){data={ok:false,message:'Resposta inválida'}}if(!r.ok)throw new Error(data.message||`HTTP ${r.status}`);return data;}
function normalizeRoute(raw){let t=String(raw||'').trim().toLowerCase().replace(/^#/,'').split(/[?&=]/)[0].replace(/[-\s]+/g,'_').replace(/[^a-z0-9_]/g,'');return routeAliases[t]||t||'profile';}
function initialRoute(){const parts=location.hash.replace(/^#/,'').split(/[?&]/);const hash=parts.find(p=>p&&!p.includes('='));const candidates=[hash,new URLSearchParams(location.search).get('tab'),TG?.initDataUnsafe?.start_param];for(const c of candidates){const r=normalizeRoute(c);if(routes.has(r))return r;}return 'profile';}
function setChrome(){try{TG?.ready?.();TG?.expand?.();const p=TG?.themeParams||{};const bg=p.bg_color||p.secondary_bg_color||'#09090b';TG?.setHeaderColor?.(bg);TG?.setBackgroundColor?.(bg);document.documentElement.style.colorScheme=TG?.colorScheme==='light'?'light':'dark';}catch(_){}}
function setBackButton(){try{TG?.BackButton?.offClick?.(onBack);if(document.getElementById('drawerBackdrop').classList.contains('open')||state.route!=='profile'){TG?.BackButton?.show?.();TG?.BackButton?.onClick?.(onBack);}else TG?.BackButton?.hide?.();}catch(_){}}
function onBack(){const d=document.getElementById('drawerBackdrop');if(d.classList.contains('open')){closeDrawer();return;}navigate('profile');}
function openDrawer(){document.getElementById('drawerBackdrop').classList.add('open');try{TG?.disableVerticalSwipes?.()}catch(_){}setBackButton();haptic();}
function closeDrawer(){document.getElementById('drawerBackdrop').classList.remove('open');try{TG?.enableVerticalSwipes?.()}catch(_){}setBackButton();}
function drawerHtml(){return drawerGroups.map(([label,items])=>`<div class="nav-group"><div class="nav-label">${label}</div>${items.map(([r,i,t,m])=>`<button class="nav-item ${state.route===r?'active':''}" data-route="${r}"><span class="nav-ico">${i}</span><span class="nav-copy"><span class="nav-title">${t}</span><span class="nav-meta">${m}</span></span>${['gacha','quests','pass','pets','trading'].includes(r)?'<span class="nav-badge">V2</span>':''}</button>`).join('')}</div>`).join('');}
function bindNav(){document.querySelectorAll('[data-route]').forEach(el=>el.onclick=()=>navigate(el.dataset.route));document.getElementById('menuBtn').onclick=openDrawer;document.getElementById('drawerBackdrop').onclick=e=>{if(e.target.id==='drawerBackdrop')closeDrawer();};}
function navigate(route){route=normalizeRoute(route);const sc=document.getElementById('scroller');state.scroll.set(state.route,sc.scrollTop);state.route=route;if(location.hash!==`#${route}`)history.replaceState(null,'',`#${route}`);haptic();render();closeDrawer();requestAnimationFrame(()=>{sc.scrollTop=state.scroll.get(route)||0});}
function profileHero(){const p=state.profile||{};const favorite=p.favorite||{};return `<section class="hero"><div class="hero-bg" style="background-image:url('${esc(favorite.image||BANNER_URL)}')"></div><div class="hero-body"><div class="eyebrow">SOURCE // PLAYER PROFILE</div><h1>${esc(p.nickname||p.display_name||'Source Player')}</h1><p>${favorite.name?`Personagem favorito: <b>${esc(favorite.name)}</b> · ${esc(favorite.anime||'')}`:'Seu perfil, coleção e progressão em um único lugar.'}</p><div class="metrics"><div class="metric"><div class="metric-label">Nível</div><div class="metric-value">${num(p.level||1)}</div></div><div class="metric"><div class="metric-label">Coins</div><div class="metric-value">${num(p.coins)}</div></div><div class="metric"><div class="metric-label">Coleção</div><div class="metric-value">${num(p.collection_total)}</div></div><div class="metric"><div class="metric-label">País</div><div class="metric-value">${esc(p.country_code||'BR')}</div></div></div></div></section>`;}
function quickActions(){const xs=[['collection','▦','Coleção','Abrir personagens'],['gacha','✦','Gacha','Rolagens e pity'],['quests','✓','Missões','Progresso diário'],['games','◆','Jogos','Memória e Termo']];return `<section class="section"><div class="section-head"><div><div class="section-kicker">Acesso rápido</div><h2 class="section-title">Continue de onde parou</h2></div></div><div class="quick-grid">${xs.map(([r,i,t,s])=>`<button class="quick" data-route="${r}"><div class="quick-icon">${i}</div><div class="quick-title">${t}</div><div class="quick-sub">${s}</div></button>`).join('')}</div></section>`;}
function profilePanel(){const p=state.profile||{};return `<section class="section"><div class="section-head"><div><div class="section-kicker">Identidade</div><h2 class="section-title">Conta Source</h2></div></div><div class="panel"><div class="profile-row"><div class="avatar">${esc((p.nickname||p.display_name||'S').slice(0,1).toUpperCase())}</div><div><div class="profile-name">${esc(p.nickname||p.display_name||'Source Player')}</div><div class="profile-user">${p.username?'@'+esc(p.username):'ID '+esc(p.user_id||'—')}</div></div></div><div class="stat-row"><div class="mini-stat"><b>${num(p.coins)}</b><span>COINS</span></div><div class="mini-stat"><b>${num(p.level||1)}</b><span>NÍVEL</span></div><div class="mini-stat"><b>${num(p.collection_total)}</b><span>CARDS</span></div></div></div></section>`;}
function skeletonCards(n=6){return `<div class="card-grid">${Array.from({length:n},()=>'<div class="skeleton"><div class="skeleton-art"></div><div class="skeleton-line"></div></div>').join('')}</div>`;}
function cardsGrid(limit=12){const items=state.cards.slice(0,limit);if(!items.length)return '<div class="empty"><strong>Nenhum personagem encontrado.</strong>Sua coleção aparecerá aqui.</div>';return `<div class="card-grid">${items.map(c=>`<article class="char-card"><div class="char-art">${c.image?`<img loading="lazy" src="${esc(c.image)}" alt="${esc(c.name)}" onerror="this.remove()">`:''}<span class="char-qty">×${num(c.quantity||1)}</span></div><div class="char-body"><div class="char-name">${esc(c.name)}</div><div class="char-anime">${esc(c.anime)}</div></div></article>`).join('')}</div>`;}
function futurePage(route){const map={gacha:['✦','Gacha Source','Pity, fragmentos, banners e revelação animada.'],shop:['◇','Loja V2','Economia unificada, ofertas e marketplace.'],incubation:['◌','Incubadora','Ovos, timers e recompensas.'],pets:['♢','Companheiros','Pets equipáveis e bônus passivos.'],quests:['✓','Missões','Diárias, semanais e eventos.'],pass:['▤','Temporada','Progressão sazonal e recompensas.'],achievements:['✹','Conquistas','Badges, tiers e metas secretas.'],leaderboard:['△','Rankings','Coleção, XP, jogos e temporadas.'],trading:['⇄','Trocas','Negociação com confirmação e escrow.'],exchange:['↔','Câmbio','Conversão entre recursos da economia.'],referrals:['＋','Indicações','Convites, marcos e recompensas.'],admin:['⌘','Source Admin','Personagens, artes, staff, logs e economia.']};const d=map[route]||['◆','Source V2','Módulo em migração.'];return `<section class="hero"><div class="hero-bg" style="background-image:url('${esc(BANNER_URL)}')"></div><div class="hero-body"><div class="eyebrow">SOURCE V2 // MIGRATION</div><h1>${d[0]} ${d[1]}</h1><p>${d[2]}</p></div></section><section class="section"><div class="panel"><div class="future"><div class="future-row"><div class="future-ico">✓</div><div class="future-copy"><div class="future-title">Shell e navegação prontos</div><div class="future-sub">Tema Telegram, haptics, BackButton, scroll por aba e loading global.</div></div><span class="future-tag">OK</span></div><div class="future-row"><div class="future-ico">↻</div><div class="future-copy"><div class="future-title">Backend em adaptação</div><div class="future-sub">O sistema será conectado aos IDs e dados atuais do Source, sem recriar personagens.</div></div><span class="future-tag">P1</span></div><div class="future-row"><div class="future-ico">2:3</div><div class="future-copy"><div class="future-title">Assets padronizados</div><div class="future-sub">Cards da nova interface já usam proporção fixa 2:3.</div></div><span class="future-tag">MEDIA</span></div></div></div></section>`;}
function ecosystemPage(route){const links={games:['◆ Jogos','/memoria','Memória já está funcional; Termo continuará integrado no bot.'],catalog:['▶ Animes','/catalogo','Abrir catálogo atual do Source.'],manga:['▥ Mangás','/mangas','Abrir biblioteca atual de mangás.'],news:['◫ AniNexus','https://aninexus.com.br','Abrir o portal AniNexus.'],music:['♫ Música','#','Player será integrado ao shell V2.'],akira:['✧ Akira','#','Assistente será conectada ao perfil, catálogo e coleção.']};const d=links[route];return `<section class="hero"><div class="hero-bg" style="background-image:url('${esc(BANNER_URL)}')"></div><div class="hero-body"><div class="eyebrow">SOURCE ECOSYSTEM</div><h1>${d[0]}</h1><p>${d[2]}</p></div></section><section class="section"><div class="panel"><button class="quick" style="width:100%;min-height:88px" id="ecosystemOpen"><div class="quick-title">Abrir módulo atual</div><div class="quick-sub">A migração para o shell V2 será incremental.</div></button></div></section>`;}
function render(){document.getElementById('drawerNav').innerHTML=drawerHtml();document.querySelectorAll('.bottom-btn').forEach(b=>b.classList.toggle('active',b.dataset.route===state.route));let out='';if(state.route==='profile')out=profileHero()+quickActions()+profilePanel()+`<section class="section"><div class="section-head"><div><div class="section-kicker">Recentes</div><h2 class="section-title">Sua coleção</h2></div><button class="section-link" data-route="collection">Ver tudo</button></div>${state.loaded?cardsGrid(8):skeletonCards(4)}</section>`;else if(state.route==='collection')out=`<section class="hero"><div class="hero-bg" style="background-image:url('${esc(BANNER_URL)}')"></div><div class="hero-body"><div class="eyebrow">SOURCE // COLLECTION</div><h1>Sua coleção.</h1><p>Os mesmos personagens e IDs que você já possui, agora dentro da fundação visual V2.</p><div class="metrics"><div class="metric"><div class="metric-label">Únicos</div><div class="metric-value">${num(state.stats?.unique_cards)}</div></div><div class="metric"><div class="metric-label">Cópias</div><div class="metric-value">${num(state.stats?.total_copies)}</div></div><div class="metric"><div class="metric-label">Obras</div><div class="metric-value">${num(state.stats?.active_animes)}</div></div><div class="metric"><div class="metric-label">Completas</div><div class="metric-value">${num(state.stats?.completed_animes)}</div></div></div></div></section><section class="section">${state.loaded?cardsGrid(80):skeletonCards(8)}</section>`;else if(['games','catalog','manga','news','music','akira'].includes(state.route))out=ecosystemPage(state.route);else out=futurePage(state.route);out+=`<div class="credit"><strong>Source Baltigo V2</strong><br>Adaptação com atribuição ao projeto AniNexus (bisug).</div>`;document.getElementById('page').innerHTML=out;bindNav();if(['games','catalog','manga','news'].includes(state.route)){const btn=document.getElementById('ecosystemOpen');if(btn){btn.onclick=()=>{const url={games:'/memoria',catalog:'/catalogo',manga:'/mangas',news:'https://aninexus.com.br'}[state.route];haptic();if(url.startsWith('http')){try{TG?.openLink?.(url)}catch(_){location.href=url}}else location.href=url;};}}setBackButton();}
async function loadData(){state.uid=getUid();try{const [p,s,c]=await Promise.all([api('/api/menu/profile'),api('/api/collection/state'),api('/api/collection/cards')]);state.profile=p.profile||{};state.stats=s.stats||{};state.cards=c.items||[];document.getElementById('topStatus').textContent=`Nível ${state.profile.level||1} · ${num(state.cards.length)} personagens`;state.loaded=true;render();haptic('success');}catch(err){console.error(err);document.getElementById('topStatus').textContent='Falha ao sincronizar';state.loaded=true;render();toast(err.message||'Falha ao carregar dados');}finally{setTimeout(()=>document.getElementById('intro').classList.add('hidden'),180);}}
window.addEventListener('hashchange',()=>{state.route=initialRoute();render()});
document.addEventListener('DOMContentLoaded',()=>{setChrome();state.route=initialRoute();render();bindNav();loadData();try{TG?.onEvent?.('themeChanged',setChrome)}catch(_){};setTimeout(()=>document.getElementById('intro').classList.add('hidden'),2400);});
</script>
</body>
</html>'''
        return HTMLResponse(page.replace("__BANNER__", banner))

    return router
