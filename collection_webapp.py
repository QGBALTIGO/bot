from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from collection_service import get_collection_state
from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def _page() -> str:
    return f'''<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#070a14">
<title>Minha Coleção • Baltigo</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
{base_css()}
.collection-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px;margin-top:14px}}
.collection-card{{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:21px;background:linear-gradient(180deg,rgba(18,26,46,.9),rgba(8,13,27,.96));box-shadow:var(--shadow-soft);animation:cardIn .38s both}}
.collection-card img{{display:block;width:100%;aspect-ratio:.74;object-fit:cover;background:#0b1020}}
.collection-card .body{{padding:11px}}
.collection-card .name{{font-size:14px;font-weight:950;line-height:1.22;letter-spacing:-.02em}}
.collection-card .anime{{margin-top:5px;color:var(--muted);font-size:11px;line-height:1.3}}
.qty{{position:absolute;right:9px;top:9px;z-index:2;display:grid;place-items:center;min-width:34px;height:34px;padding:0 8px;border:1px solid rgba(255,255,255,.2);border-radius:999px;background:rgba(5,8,18,.72);backdrop-filter:blur(12px);font-size:11px;font-weight:950}}
.orphan{{border-color:rgba(255,111,134,.35)}}
.progress-wrap{{margin-top:13px;height:11px;border-radius:999px;background:rgba(255,255,255,.055);overflow:hidden;border:1px solid var(--line)}}
.progress-bar{{height:100%;width:0;background:linear-gradient(90deg,var(--cyan),var(--violet),var(--pink));border-radius:inherit;transition:width .7s cubic-bezier(.2,.8,.2,1)}}
.filters{{display:flex;gap:8px;overflow:auto;margin-top:11px;padding-bottom:2px;scrollbar-width:none}}.filters::-webkit-scrollbar{{display:none}}.filter{{flex:0 0 auto;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.035);padding:8px 11px;font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.08em;cursor:pointer}}.filter.active{{border-color:rgba(93,230,255,.34);background:rgba(93,230,255,.10)}}
@keyframes cardIn{{from{{opacity:0;transform:translateY(8px) scale(.985)}}to{{opacity:1;transform:none}}}}
@media(min-width:680px){{.collection-grid{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}
</style>
</head>
<body>
<div class="v2-shell">
  <section class="v2-hero">
    <div class="v2-eyebrow">Source Baltigo • Coleção V2</div>
    <h1 class="v2-title">Sua coleção,<br>de verdade.</h1>
    <p class="v2-copy">Tudo que você ganha no dado e nos sistemas de cards aparece aqui. Duplicatas continuam visíveis e contam separadamente.</p>
    <div class="v2-metrics">
      <div class="v2-metric"><span class="v2-metric-label">Únicos</span><span class="v2-metric-value" id="unique">—</span></div>
      <div class="v2-metric"><span class="v2-metric-label">Cópias</span><span class="v2-metric-value" id="copies">—</span></div>
      <div class="v2-metric"><span class="v2-metric-label">Completo</span><span class="v2-metric-value" id="completion">—</span></div>
    </div>
    <div class="progress-wrap"><div class="progress-bar" id="progress"></div></div>
  </section>

  <section class="v2-panel">
    <h2 class="v2-section-title">Personagens</h2>
    <p class="v2-section-copy" id="summary">Carregando sua coleção…</p>
    <div class="v2-search"><span>⌕</span><input id="search" placeholder="Buscar personagem ou anime…" autocomplete="off"></div>
    <div class="filters"><button class="filter active" data-filter="all">Todos</button><button class="filter" data-filter="duplicates">Duplicatas</button><button class="filter" data-filter="single">Únicos</button></div>
    <div id="grid" class="collection-grid"></div>
    <div id="empty" class="v2-empty" style="display:none;margin-top:14px"></div>
  </section>
</div>
<div class="v2-toast" id="v2Toast"></div>
<script>
{telegram_bootstrap_js()}
let allItems=[]; let filter='all';
const esc=(s)=>String(s||'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
function render(){{
  const q=document.getElementById('search').value.trim().toLocaleLowerCase('pt-BR');
  let items=allItems.filter(item=>!q || `${{item.name}} ${{item.anime}}`.toLocaleLowerCase('pt-BR').includes(q));
  if(filter==='duplicates')items=items.filter(x=>Number(x.quantity)>1);
  if(filter==='single')items=items.filter(x=>Number(x.quantity)===1);
  const grid=document.getElementById('grid'); const empty=document.getElementById('empty'); grid.innerHTML='';
  if(!items.length){{empty.style.display='block';empty.innerHTML=allItems.length?'Nenhum personagem combina com esse filtro.':'Sua coleção ainda está vazia.<br><br>Use <b>/dado</b> para conseguir o primeiro personagem.';return}}
  empty.style.display='none';
  items.forEach((item,i)=>{{const el=document.createElement('article');el.className='collection-card'+(item.orphaned?' orphan':'');el.style.animationDelay=`${{Math.min(i,18)*18}}ms`;el.innerHTML=`<div class="qty">×${{Number(item.quantity||1)}}</div><img loading="lazy" src="${{esc(item.image)}}" alt=""><div class="body"><div class="name">${{esc(item.name)}}</div><div class="anime">${{esc(item.anime)}}</div></div>`;grid.appendChild(el)}});
}}
async function load(){{
  try{{const data=await v2Api('/api/v2/collection');allItems=data.collection.items||[];const s=data.collection.stats||{{}};document.getElementById('unique').textContent=s.unique??0;document.getElementById('copies').textContent=s.copies??0;document.getElementById('completion').textContent=`${{Number(s.completion_percent||0).toFixed(1)}}%`;document.getElementById('progress').style.width=`${{Math.min(100,Number(s.completion_percent||0))}}%`;document.getElementById('summary').textContent=`${{s.unique||0}} de ${{s.catalog_total||0}} personagens • ${{s.duplicates||0}} duplicata(s)`;render()}}
  catch(e){{v2Toast(e.message);document.getElementById('empty').style.display='block';document.getElementById('empty').textContent='Abra esta coleção pelo Telegram para carregar sua conta.'}}
}}
document.getElementById('search').addEventListener('input',render);document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{{filter=b.dataset.filter;document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x===b));render()}});load();
</script>
</body></html>'''


def register_collection_routes(app) -> None:
    @app.get("/collection", response_class=HTMLResponse)
    async def collection_page():
        return HTMLResponse(_page())

    @app.get("/api/v2/collection")
    async def collection_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        allowed = await rate_limiter.allow(f"webapp:collection:{user_id}", limit=40, window_seconds=60)
        if not allowed:
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas atualizações em sequência."}, status_code=429)
        return JSONResponse({"ok": True, "collection": get_collection_state(user_id)})
