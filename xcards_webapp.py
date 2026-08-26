from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from utils.runtime_guard import rate_limiter
from v2_ui import base_css, telegram_bootstrap_js
from xcards_repository import (
    XCardAlreadyPurchased,
    XCardInsufficientCoins,
    XCardLevelRequired,
    XCardOfferNotFound,
    buy_daily_offer,
    xcards_state,
)


def _uid(request: Request) -> int:
    return int(getattr(request.state, "telegram_user_id", 0) or 0)


def _page() -> str:
    return f'''<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#070a14">
<title>XColeção • Baltigo</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
{base_css()}
.tabs{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}}
.tab{{min-height:46px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.035);font-weight:900;cursor:pointer}}
.tab.active{{border-color:rgba(93,230,255,.38);background:rgba(93,230,255,.1)}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:14px}}
.card{{overflow:hidden;border:1px solid var(--line);border-radius:21px;background:linear-gradient(180deg,rgba(18,26,46,.92),rgba(8,13,27,.96));box-shadow:var(--shadow-soft)}}
.card img{{display:block;width:100%;aspect-ratio:.72;object-fit:cover;background:#0a1020}}
.card .body{{padding:11px}}
.name{{font-weight:950;font-size:13px;line-height:1.2}}
.meta{{margin-top:5px;color:var(--muted);font-size:10px;line-height:1.35}}
.row{{display:flex;align-items:center;justify-content:space-between;gap:7px;margin-top:9px}}
.bp{{font-size:11px;font-weight:950;color:var(--gold)}}
.qty{{font-size:10px;font-weight:950;color:var(--cyan)}}
.buy{{width:100%;min-height:42px;margin-top:9px;border:0;border-radius:14px;background:linear-gradient(135deg,var(--cyan),var(--violet));color:#07101a;font-weight:950;cursor:pointer}}
.buy:disabled{{opacity:.4;filter:grayscale(.5)}}
.locked{{border-color:rgba(255,211,108,.3)}}
.purchased{{border-color:rgba(114,241,189,.28)}}
.market-note{{margin-top:12px;color:var(--muted);font-size:11px;line-height:1.5}}
.hidden{{display:none!important}}
@media(min-width:700px){{.grid{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}
</style>
</head>
<body>
<div class="v2-shell">
  <section class="v2-hero">
    <div class="v2-eyebrow">Source Baltigo • Union Arena</div>
    <h1 class="v2-title">XColeção<br>competitiva.</h1>
    <p class="v2-copy">XCards usam BP e formam o baralho competitivo do duelo. O mercado diário muda todos os dias e usa a mesma carteira de coins do restante da Baltigo.</p>
    <div class="v2-metrics">
      <div class="v2-metric"><span class="v2-metric-label">Coins</span><span class="v2-metric-value" id="coins">—</span></div>
      <div class="v2-metric"><span class="v2-metric-label">XCards</span><span class="v2-metric-value" id="unique">—</span></div>
      <div class="v2-metric"><span class="v2-metric-label">Nível</span><span class="v2-metric-value" id="level">—</span></div>
    </div>
  </section>

  <section class="v2-panel">
    <div class="tabs">
      <button class="tab active" data-view="collection">Minha XColeção</button>
      <button class="tab" data-view="market">Mercado diário</button>
    </div>
    <div id="collectionView">
      <div class="v2-search"><span>⌕</span><input id="search" placeholder="Buscar personagem, obra ou número…"></div>
      <div class="grid" id="collectionGrid"></div>
      <div class="v2-empty hidden" id="collectionEmpty">Sua XColeção ainda está vazia. Abra o mercado diário para conquistar a primeira carta.</div>
    </div>
    <div id="marketView" class="hidden">
      <p class="market-note">Cada slot pode ser comprado uma vez por dia. Cartas com BP maior custam mais e podem exigir nível mínimo.</p>
      <div class="grid" id="marketGrid"></div>
      <div class="v2-empty hidden" id="marketEmpty">Não há ofertas disponíveis agora.</div>
    </div>
  </section>
</div>
<div class="v2-toast" id="v2Toast"></div>
<script>
{telegram_bootstrap_js()}
let state={{collection:[],offers:[],wallet:{{}},level:1}};
const esc=s=>String(s||'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
const fmt=n=>Number(n||0).toLocaleString('pt-BR');
function syncHud(){{document.getElementById('coins').textContent=fmt(state.wallet.coins);document.getElementById('unique').textContent=fmt(state.collection.length);document.getElementById('level').textContent=fmt(state.level)}}
function cardHtml(c,market=false){{
  const purchased=Boolean(c.purchased), locked=market&&Number(state.level)<Number(c.level_required||1);
  const button=market?`<button class="buy" data-slot="${{esc(c.slot_code)}}" ${{purchased||locked?'disabled':''}}>${{purchased?'Comprado':locked?`Nível ${{c.level_required}} necessário`:`Comprar • ${{c.price}} coins`}}</button>`:'';
  return `<article class="card ${{locked?'locked':''}} ${{purchased?'purchased':''}}"><img loading="lazy" src="${{esc(c.image)}}" alt=""><div class="body"><div class="name">${{esc(c.name)}}</div><div class="meta">${{esc(c.title)}}<br>${{esc(c.card_no||'')}} • ${{esc(c.rarity||'-')}}</div><div class="row"><span class="bp">⚔ BP ${{fmt(c.bp)}}</span>${{market?`<span class="qty">${{esc(c.tier||'')}}</span>`:`<span class="qty">×${{fmt(c.quantity)}}</span>`}}</div>${{button}}</div></article>`;
}}
function renderCollection(){{const q=document.getElementById('search').value.trim().toLocaleLowerCase('pt-BR');const items=state.collection.filter(c=>!q||`${{c.name}} ${{c.title}} ${{c.card_no}}`.toLocaleLowerCase('pt-BR').includes(q));const grid=document.getElementById('collectionGrid');grid.innerHTML=items.map(c=>cardHtml(c)).join('');document.getElementById('collectionEmpty').classList.toggle('hidden',items.length>0)}}
function renderMarket(){{const grid=document.getElementById('marketGrid');grid.innerHTML=state.offers.map(c=>cardHtml(c,true)).join('');document.getElementById('marketEmpty').classList.toggle('hidden',state.offers.length>0);grid.querySelectorAll('[data-slot]').forEach(btn=>btn.onclick=async()=>{{if(btn.disabled)return;const slot=btn.dataset.slot;if(!confirm('Comprar este XCard com coins?'))return;btn.disabled=true;try{{const data=await v2Api('/api/v2/xcards/buy',{{method:'POST',body:JSON.stringify({{slot_code:slot}})}});v2Haptic('medium');v2Toast('XCard adquirido.');await load()}}catch(e){{v2Toast(e.message);btn.disabled=false}}}})}}
async function load(){{try{{const data=await v2Api('/api/v2/xcards/state');state=data.state||state;syncHud();renderCollection();renderMarket()}}catch(e){{v2Toast(e.message)}}}}
document.getElementById('search').addEventListener('input',renderCollection);document.querySelectorAll('.tab').forEach(btn=>btn.onclick=()=>{{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===btn));const market=btn.dataset.view==='market';document.getElementById('marketView').classList.toggle('hidden',!market);document.getElementById('collectionView').classList.toggle('hidden',market)}});load();
</script>
</body></html>'''


def register_xcards_routes(app) -> None:
    @app.get("/xcollection", response_class=HTMLResponse)
    async def xcollection_page():
        return HTMLResponse(_page())

    @app.get("/api/v2/xcards/state")
    async def state_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        allowed = await rate_limiter.allow(f"webapp:xcards:state:{user_id}", limit=30, window_seconds=60)
        if not allowed:
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas atualizações em sequência."}, status_code=429)
        return JSONResponse({"ok": True, "state": xcards_state(user_id)})

    @app.post("/api/v2/xcards/buy")
    async def buy_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        allowed = await rate_limiter.allow(f"webapp:xcards:buy:{user_id}", limit=8, window_seconds=60)
        if not allowed:
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Aguarde antes de comprar novamente."}, status_code=429)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        slot_code = str((payload or {}).get("slot_code") or "").strip()
        if not slot_code:
            return JSONResponse({"ok": False, "code": "invalid_slot", "message": "Oferta inválida."}, status_code=400)
        try:
            result = buy_daily_offer(user_id, slot_code)
        except XCardAlreadyPurchased:
            return JSONResponse({"ok": False, "code": "already_purchased", "message": "Você já comprou esse slot hoje."}, status_code=409)
        except XCardInsufficientCoins:
            return JSONResponse({"ok": False, "code": "insufficient_coins", "message": "Coins insuficientes."}, status_code=409)
        except XCardLevelRequired as exc:
            return JSONResponse({"ok": False, "code": "level_required", "message": f"Essa oferta exige nível {exc.level_required}."}, status_code=403)
        except XCardOfferNotFound:
            return JSONResponse({"ok": False, "code": "offer_not_found", "message": "Essa oferta não existe mais."}, status_code=404)
        return JSONResponse({"ok": True, "purchase": result})
