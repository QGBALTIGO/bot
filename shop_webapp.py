from __future__ import annotations

from typing import Any, Dict

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from shop_service import ShopServiceError, get_shop_state, purchase, sell_duplicate
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
<title>Loja • Baltigo</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
{base_css()}
.wallet{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:16px}}.wallet>div{{padding:12px;border:1px solid var(--line);border-radius:17px;background:rgba(255,255,255,.04)}}.wallet span{{display:block;color:var(--muted);font-size:9px;font-weight:900;text-transform:uppercase;letter-spacing:.1em}}.wallet b{{display:block;margin-top:5px;font-size:19px}}
.shop-tabs{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:14px;padding:5px;border:1px solid var(--line);border-radius:18px;background:rgba(255,255,255,.03)}}.shop-tab{{border:0;border-radius:13px;min-height:44px;background:transparent;color:var(--muted);font-size:11px;font-weight:900}}.shop-tab.active{{color:#fff;background:linear-gradient(135deg,rgba(157,115,255,.25),rgba(93,230,255,.12))}}
.products{{display:grid;gap:10px}}.product{{padding:15px;border:1px solid var(--line);border-radius:20px;background:linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.025))}}.product-top{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}}.product h3{{margin:0;font-size:17px}}.product p{{margin:7px 0 0;color:var(--muted);font-size:11px;line-height:1.5}}.price{{white-space:nowrap;padding:7px 9px;border-radius:999px;border:1px solid rgba(255,211,108,.25);background:rgba(255,211,108,.08);color:var(--gold);font-size:11px;font-weight:950}}.buy-btn,.sell-btn{{width:100%;margin-top:12px;min-height:45px;border:0;border-radius:14px;background:linear-gradient(135deg,var(--violet),var(--pink));font-size:11px;font-weight:950;color:#fff}}.sell-btn{{background:linear-gradient(135deg,rgba(93,230,255,.28),rgba(157,115,255,.24));border:1px solid var(--line)}}
.sell-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.sell-card{{overflow:hidden;border:1px solid var(--line);border-radius:19px;background:rgba(255,255,255,.035)}}.sell-card img{{display:block;width:100%;aspect-ratio:.76;object-fit:cover;background:#0a0f1e}}.sell-copy{{padding:11px}}.sell-name{{font-size:12px;font-weight:950;line-height:1.2}}.sell-anime{{margin-top:4px;color:var(--muted);font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.sell-meta{{margin-top:7px;color:var(--cyan);font-size:10px;font-weight:900}}
.confirm{{position:fixed;z-index:100;inset:0;display:none;place-items:end center;padding:16px;background:rgba(0,0,0,.58);backdrop-filter:blur(5px)}}.confirm.show{{display:grid}}.confirm-card{{width:min(520px,100%);padding:18px;border:1px solid var(--line-strong);border-radius:25px;background:#0d1324;box-shadow:var(--shadow)}}.confirm-actions{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}}.confirm-actions button{{min-height:46px;border-radius:14px;border:1px solid var(--line);font-weight:900}}.confirm-no{{background:rgba(255,255,255,.04)}}.confirm-yes{{background:linear-gradient(135deg,var(--violet),var(--pink));border:0!important}}
.hidden{{display:none!important}}@media(min-width:700px){{.products{{grid-template-columns:repeat(2,1fr)}}.sell-grid{{grid-template-columns:repeat(4,1fr)}}}}
</style>
</head>
<body>
<div class="v2-shell">
<section class="v2-hero">
  <div class="v2-eyebrow">Source Baltigo • Loja V2</div>
  <h1 class="v2-title">Economia que fecha a conta.</h1>
  <p class="v2-copy">Compre recursos reais e venda apenas duplicatas. A última cópia fica protegida para você não perder progresso por engano.</p>
  <div class="wallet"><div><span>Coins</span><b id="coins">—</b></div><div><span>Dados</span><b id="dice">—</b></div><div><span>Giros</span><b id="spins">—</b></div></div>
</section>
<section class="v2-panel">
  <div class="shop-tabs"><button class="shop-tab active" data-tab="buy">🛒 Comprar</button><button class="shop-tab" data-tab="sell">📦 Duplicatas</button></div>
  <div id="buyView"><div class="products" id="products"></div></div>
  <div id="sellView" class="hidden"><div class="v2-search"><span>⌕</span><input id="search" placeholder="Buscar duplicata…"></div><div class="sell-grid" id="sellGrid" style="margin-top:12px"></div></div>
</section>
</div>
<div class="confirm" id="confirm"><div class="confirm-card"><div class="v2-eyebrow">Confirmar operação</div><h2 class="v2-section-title" id="confirmTitle">—</h2><p class="v2-section-copy" id="confirmText">—</p><div class="confirm-actions"><button class="confirm-no" id="confirmNo">Cancelar</button><button class="confirm-yes" id="confirmYes">Confirmar</button></div></div></div>
<div class="v2-toast" id="v2Toast"></div>
<script>
{telegram_bootstrap_js()}
let state=null;let pending=null;
const fmt=n=>new Intl.NumberFormat('pt-BR').format(Number(n||0));
function syncWallet(w){{if(!w)return;document.getElementById('coins').textContent=fmt(w.coins);document.getElementById('dice').textContent=fmt(w.dice);document.getElementById('spins').textContent=fmt(w.spins)}}
function ask(title,text,fn){{pending=fn;document.getElementById('confirmTitle').textContent=title;document.getElementById('confirmText').textContent=text;document.getElementById('confirm').classList.add('show');v2Haptic('light')}}
function closeConfirm(){{pending=null;document.getElementById('confirm').classList.remove('show')}}
document.getElementById('confirmNo').onclick=closeConfirm;document.getElementById('confirmYes').onclick=async()=>{{const fn=pending;closeConfirm();if(fn)await fn()}};
function renderProducts(){{const root=document.getElementById('products');root.innerHTML='';(state?.products||[]).forEach(p=>{{const card=document.createElement('div');card.className='product';const top=document.createElement('div');top.className='product-top';const info=document.createElement('div');const h=document.createElement('h3');h.textContent=p.label;const desc=document.createElement('p');desc.textContent=p.description;info.append(h,desc);const price=document.createElement('div');price.className='price';price.textContent=fmt(p.coin_price)+' coins';top.append(info,price);const btn=document.createElement('button');btn.className='buy-btn';btn.textContent='Comprar';btn.onclick=()=>ask('Comprar '+p.label,`Essa compra custa ${{p.coin_price}} coins e entra imediatamente na sua wallet.`,async()=>{{try{{const r=await v2Api('/api/v2/shop/buy',{{method:'POST',body:JSON.stringify({{product_code:p.code}})}});syncWallet(r.result.wallet);v2Haptic('success');v2Toast('Compra concluída.');await load()}}catch(e){{v2Haptic('error');v2Toast(e.message)}}}});card.append(top,btn);root.appendChild(card)}})}}
function renderSell(){{const q=(document.getElementById('search').value||'').trim().toLowerCase();const root=document.getElementById('sellGrid');root.innerHTML='';const rows=(state?.sellable||[]).filter(x=>!q||(x.name+' '+x.anime).toLowerCase().includes(q));if(!rows.length){{root.innerHTML='<div class="v2-empty" style="grid-column:1/-1">Nenhuma duplicata disponível. Sua última cópia é sempre protegida.</div>';return}}rows.forEach(c=>{{const card=document.createElement('div');card.className='sell-card';const img=document.createElement('img');img.src=c.image||'';img.alt='';const copy=document.createElement('div');copy.className='sell-copy';const name=document.createElement('div');name.className='sell-name';name.textContent=c.name;const anime=document.createElement('div');anime.className='sell-anime';anime.textContent=c.anime;const meta=document.createElement('div');meta.className='sell-meta';meta.textContent=`x${{c.quantity}} • ${{c.sellable_copies}} vendável(is)`;const btn=document.createElement('button');btn.className='sell-btn';btn.textContent='Vender 1 por +'+c.coin_value;btn.onclick=()=>ask('Vender duplicata',`${{c.name}} continuará na sua coleção. Você receberá ${{c.coin_value}} coin.`,async()=>{{try{{const r=await v2Api('/api/v2/shop/sell',{{method:'POST',body:JSON.stringify({{character_id:c.id}})}});syncWallet(r.result.wallet);v2Haptic('success');v2Toast('Duplicata vendida.');await load()}}catch(e){{v2Haptic('error');v2Toast(e.message)}}}});copy.append(name,anime,meta,btn);card.append(img,copy);root.appendChild(card)}})}}
async function load(){{try{{const data=await v2Api('/api/v2/shop');state=data.shop;syncWallet(state.wallet);renderProducts();renderSell()}}catch(e){{v2Toast(e.message)}}}}
document.getElementById('search').oninput=renderSell;document.querySelectorAll('.shop-tab').forEach(btn=>btn.onclick=()=>{{document.querySelectorAll('.shop-tab').forEach(b=>b.classList.toggle('active',b===btn));document.getElementById('buyView').classList.toggle('hidden',btn.dataset.tab!=='buy');document.getElementById('sellView').classList.toggle('hidden',btn.dataset.tab!=='sell');v2Haptic('light')}});load();
</script>
</body></html>'''


def register_shop_routes(app) -> None:
    @app.get("/shop-v2", response_class=HTMLResponse)
    async def shop_page():
        return HTMLResponse(_page())

    @app.get("/api/v2/shop")
    async def shop_state_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        if not await rate_limiter.allow(f"webapp:shop:get:{user_id}", limit=24, window_seconds=60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas atualizações em sequência."}, status_code=429)
        return JSONResponse({"ok": True, "shop": get_shop_state(user_id)})

    @app.post("/api/v2/shop/buy")
    async def shop_buy_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        if not await rate_limiter.allow(f"webapp:shop:buy:{user_id}", limit=8, window_seconds=60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas compras em sequência."}, status_code=429)
        try:
            payload: Dict[str, Any] = await request.json()
            result = purchase(user_id, str(payload.get("product_code") or ""))
            return JSONResponse({"ok": True, "result": result})
        except ShopServiceError as exc:
            return JSONResponse({"ok": False, "code": exc.code, "message": exc.message}, status_code=409)
        except Exception:
            return JSONResponse({"ok": False, "code": "invalid_payload", "message": "Dados inválidos."}, status_code=400)

    @app.post("/api/v2/shop/sell")
    async def shop_sell_api(request: Request):
        user_id = _uid(request)
        if not user_id:
            return JSONResponse({"ok": False, "code": "unauthorized", "message": "Abra pelo Telegram."}, status_code=401)
        if not await rate_limiter.allow(f"webapp:shop:sell:{user_id}", limit=10, window_seconds=60):
            return JSONResponse({"ok": False, "code": "rate_limited", "message": "Muitas vendas em sequência."}, status_code=429)
        try:
            payload: Dict[str, Any] = await request.json()
            result = sell_duplicate(user_id, payload.get("character_id"))
            return JSONResponse({"ok": True, "result": result})
        except ShopServiceError as exc:
            return JSONResponse({"ok": False, "code": exc.code, "message": exc.message}, status_code=409)
        except Exception:
            return JSONResponse({"ok": False, "code": "invalid_payload", "message": "Dados inválidos."}, status_code=400)
