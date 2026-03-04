# ================================
# webapp.py — MiniApps (Dado / Coleção / Loja)
# FastAPI + HTML inline (SEM arquivos .html externos)
# Validação initData Telegram + modo DEV opcional
# ================================

import os
import json
import time
import hmac
import hashlib
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

import database as db

# ----------------
# ENV
# ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")
DEV_BYPASS_INITDATA = os.getenv("DEV_BYPASS_INITDATA", "0").strip() == "1"  # para testar no browser fora do Telegram

# Loja: quanto ganha por vender (ajuste como quiser)
SELL_COIN_GAIN = int(os.getenv("SHOP_SELL_GAIN", "1"))

app = FastAPI(title="Baltigo MiniApps")

# garante schema
db.init_db()


# ----------------
# Telegram WebApp initData validation
# ----------------
def _parse_init_data(init_data: str) -> dict:
    return dict(parse_qsl(init_data, strict_parsing=False, keep_blank_values=True))


def _check_init_data(init_data: str) -> dict:
    """
    Valida initData conforme Telegram:
    - calcula HMAC-SHA256 no "data_check_string"
    - compara com hash recebido
    Retorna dict com user_id e user data.
    """
    if DEV_BYPASS_INITDATA:
        # modo dev: permite simular user_id por query (?uid=123)
        return {"ok": True, "user_id": None, "user": None, "dev": True}

    if not init_data:
        raise HTTPException(status_code=401, detail="initData ausente.")

    data = _parse_init_data(init_data)
    recv_hash = data.pop("hash", None)
    if not recv_hash:
        raise HTTPException(status_code=401, detail="initData inválido (hash ausente).")

    # monta data_check_string
    pairs = [f"{k}={data[k]}" for k in sorted(data.keys())]
    data_check_string = "\n".join(pairs)

    secret_key = hashlib.sha256(BOT_TOKEN.encode("utf-8")).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, recv_hash):
        raise HTTPException(status_code=401, detail="initData inválido (hash mismatch).")

    user_json = data.get("user")
    user = json.loads(user_json) if user_json else None
    user_id = int(user["id"]) if user and "id" in user else None
    return {"ok": True, "user_id": user_id, "user": user, "dev": False}


def _get_user_id_from_request(init_data: str | None, uid: int | None) -> int:
    """
    - Em produção: pega do initData (Telegram)
    - Em DEV_BYPASS_INITDATA=1: permite ?uid=...
    """
    if DEV_BYPASS_INITDATA:
        if not uid:
            raise HTTPException(status_code=400, detail="DEV: passe ?uid=SEU_ID para testar.")
        return int(uid)

    info = _check_init_data(init_data or "")
    if not info.get("user_id"):
        raise HTTPException(status_code=401, detail="Usuário não encontrado no initData.")
    return int(info["user_id"])


# ----------------
# HTML (inline)
# ----------------
BASE_CSS = """
:root{
  --bg1:#0b1020; --bg2:#171a2b; --card:#11162a; --muted:#a8b0d6;
  --txt:#eef1ff; --accent:#7c5cff; --accent2:#2dd4bf; --danger:#ff4d6d;
  --shadow: 0 10px 30px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{
  margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
  background: radial-gradient(1200px 800px at 20% 10%, rgba(124,92,255,.25), transparent 60%),
              radial-gradient(900px 600px at 90% 20%, rgba(45,212,191,.18), transparent 55%),
              linear-gradient(180deg,var(--bg1),var(--bg2));
  color:var(--txt);
}
.header{
  padding:18px 18px 10px; display:flex; gap:12px; align-items:center; justify-content:space-between;
}
.brand{display:flex; flex-direction:column; gap:2px}
.brand h1{margin:0; font-size:16px; letter-spacing:.3px}
.brand p{margin:0; color:var(--muted); font-size:12px}
.badge{
  padding:8px 10px; border-radius:12px; background: rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.08);
}
.container{padding:14px; max-width:860px; margin:0 auto}
.card{
  background: rgba(17,22,42,.86);
  border:1px solid rgba(255,255,255,.08);
  border-radius:16px; box-shadow: var(--shadow);
  padding:14px;
}
.row{display:flex; gap:12px; flex-wrap:wrap}
.col{flex:1 1 320px}
.btn{
  appearance:none; border:none; cursor:pointer;
  padding:12px 14px; border-radius:14px; font-weight:700;
  background: linear-gradient(135deg,var(--accent), #4f46e5);
  color:white;
  box-shadow: 0 10px 25px rgba(124,92,255,.25);
}
.btn:disabled{opacity:.55; cursor:not-allowed}
.btn2{
  background: rgba(255,255,255,.08);
  border:1px solid rgba(255,255,255,.10);
  box-shadow:none;
}
.grid{
  display:grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap:10px; margin-top:10px;
}
@media (min-width:720px){
  .grid{grid-template-columns: repeat(3, minmax(0, 1fr));}
}
.tile{
  padding:12px; border-radius:14px;
  background: rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.08);
  cursor:pointer;
  transition: transform .12s ease, border-color .12s ease, background .12s ease;
}
.tile:hover{transform: translateY(-1px); border-color: rgba(124,92,255,.35)}
.small{color:var(--muted); font-size:12px}
.hr{height:1px; background: rgba(255,255,255,.08); margin:12px 0}
.msg{padding:10px 12px; border-radius:14px; background: rgba(45,212,191,.12); border:1px solid rgba(45,212,191,.22)}
.err{background: rgba(255,77,109,.12); border:1px solid rgba(255,77,109,.22)}
.img{
  width:100%; aspect-ratio: 1/1; border-radius:16px; object-fit:cover;
  border:1px solid rgba(255,255,255,.08);
  background: rgba(0,0,0,.2);
}
.kpi{display:flex; gap:10px; flex-wrap:wrap}
.kpi .pill{padding:8px 10px; border-radius:999px; background: rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.08); font-size:12px; color:var(--muted)}
.footer{padding:16px; text-align:center; color:var(--muted); font-size:12px}
a{color:inherit}
"""

DADO_HTML = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Dado</title>
  <style>{BASE_CSS}</style>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
</head>
<body>
  <div class="header">
    <div class="brand">
      <h1>🎲 DADO DA SORTE</h1>
      <p>Role o dado, escolha um anime e ganhe um personagem.</p>
    </div>
    <div class="badge" id="badge">…</div>
  </div>

  <div class="container">
    <div class="row">
      <div class="col">
        <div class="card">
          <div class="kpi">
            <div class="pill" id="coins">🪙 Coins: …</div>
            <div class="pill" id="dice">🎟️ Dados: …</div>
            <div class="pill" id="giros">🎡 Giros: …</div>
          </div>
          <div class="hr"></div>
          <button class="btn" id="btnRoll">🎲 Rolar Dado</button>
          <div style="height:10px"></div>
          <div id="state" class="msg" style="display:none"></div>
        </div>

        <div style="height:12px"></div>

        <div class="card" id="pickCard" style="display:none">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:10px">
            <div>
              <div style="font-weight:800">Escolha um anime</div>
              <div class="small" id="subtitle"></div>
            </div>
            <div class="badge" id="diceValue">🎲 …</div>
          </div>
          <div class="grid" id="options"></div>
        </div>
      </div>

      <div class="col">
        <div class="card" id="resultCard" style="display:none">
          <div style="font-weight:900; font-size:15px">🎴 Seu personagem</div>
          <div class="small" id="resAnime"></div>
          <div style="height:10px"></div>
          <img class="img" id="resImg" />
          <div style="height:10px"></div>
          <div style="font-weight:900" id="resName"></div>
          <div class="small" id="resMeta"></div>
        </div>

        <div style="height:12px"></div>

        <div class="card">
          <div style="font-weight:800">Dicas</div>
          <div class="small">
            • O número do dado define quantas opções aparecem.<br/>
            • Se algo falhar, você não perde o dado (idempotência).<br/>
            • Tudo é salvo no banco em tempo real.
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">Baltigo MiniApp • Dado</div>

<script>
const tg = window.Telegram?.WebApp;
if (tg) tg.ready();

function qs(name){ return new URLSearchParams(location.search).get(name); }

let INIT = "";
let UID = qs("uid") || "";
try{
  INIT = tg?.initData || "";
}catch(e){}

async function api(path, payload){
  const headers = { "Content-Type":"application/json" };
  if (INIT) headers["X-Tg-Init-Data"] = INIT;
  const url = UID ? `${path}?uid=${encodeURIComponent(UID)}` : path;
  const r = await fetch(url, {method:"POST", headers, body: JSON.stringify(payload||{})});
  const j = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(j.detail || j.error || "Erro");
  return j;
}

async function apiGet(path){
  const headers = {};
  if (INIT) headers["X-Tg-Init-Data"] = INIT;
  const url = UID ? `${path}?uid=${encodeURIComponent(UID)}` : path;
  const r = await fetch(url, {method:"GET", headers});
  const j = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(j.detail || j.error || "Erro");
  return j;
}

function showMsg(text, isErr=false){
  const el = document.getElementById("state");
  el.style.display = "block";
  el.className = "msg" + (isErr ? " err" : "");
  el.textContent = text;
}

function setBadge(text){ document.getElementById("badge").textContent = text; }

function setStats(st){
  document.getElementById("coins").textContent = `🪙 Coins: ${st.coins}`;
  document.getElementById("dice").textContent  = `🎟️ Dados: ${st.dado_balance}`;
  document.getElementById("giros").textContent = `🎡 Giros: ${st.extra_dado}`;
}

let currentRoll = null;

async function refresh(){
  const st = await apiGet("/api/me");
  setStats(st);
  setBadge(st.nick || "User");
}

function clearUI(){
  document.getElementById("pickCard").style.display = "none";
  document.getElementById("resultCard").style.display = "none";
  document.getElementById("options").innerHTML = "";
}

async function roll(){
  clearUI();
  showMsg("Rolando o dado…");
  const data = await api("/api/dado/roll", {});
  currentRoll = data.roll_id;

  document.getElementById("diceValue").textContent = `🎲 ${data.dice_value}`;
  document.getElementById("subtitle").textContent = `Você tem ${data.dice_value} opção(ões).`;

  const opts = document.getElementById("options");
  opts.innerHTML = "";
  for(const o of data.options){
    const div = document.createElement("div");
    div.className = "tile";
    div.innerHTML = `<div style="font-weight:900">${o.title || o.anime || "Anime"}</div>
                     <div class="small">Toque para escolher</div>`;
    div.onclick = ()=>pick(o.anime || o.title || "");
    opts.appendChild(div);
  }

  document.getElementById("pickCard").style.display = "block";
  showMsg("Agora escolha um anime.");
  await refresh();
}

async function pick(anime){
  if(!currentRoll) return;
  showMsg("Gerando personagem…");
  try{
    const data = await api("/api/dado/pick", { roll_id: currentRoll, anime: anime });
    document.getElementById("pickCard").style.display = "none";

    document.getElementById("resAnime").textContent = data.anime_title || "";
    document.getElementById("resImg").src = data.image || "";
    document.getElementById("resName").textContent = data.character_name || "";
    document.getElementById("resMeta").textContent = `ID: ${data.character_id} • +1 na coleção`;
    document.getElementById("resultCard").style.display = "block";

    showMsg("✅ Personagem adicionado na sua coleção!");
    currentRoll = null;
    await refresh();
  }catch(e){
    showMsg("❌ " + (e.message || "Falhou ao gerar personagem."), true);
    currentRoll = null;
    await refresh();
  }
}

document.getElementById("btnRoll").onclick = async ()=>{
  try{
    document.getElementById("btnRoll").disabled = true;
    await roll();
  }catch(e){
    showMsg("❌ " + (e.message || "Erro ao rolar dado."), true);
  }finally{
    document.getElementById("btnRoll").disabled = false;
  }
};

refresh().catch(e=>{
  showMsg("❌ " + (e.message || "Falha ao carregar."), true);
});
</script>
</body>
</html>
"""

COLECAO_HTML = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Coleção</title>
  <style>{BASE_CSS}</style>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
</head>
<body>
  <div class="header">
    <div class="brand">
      <h1>🧩 COLEÇÃO</h1>
      <p>Seus personagens, com paginação.</p>
    </div>
    <div class="badge" id="badge">…</div>
  </div>

  <div class="container">
    <div class="card">
      <div class="kpi">
        <div class="pill" id="total">📦 Itens: …</div>
        <div class="pill" id="unique">🧿 Únicos: …</div>
        <div class="pill" id="coins">🪙 Coins: …</div>
      </div>
      <div class="hr"></div>

      <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap">
        <button class="btn btn2" id="prev">⬅️</button>
        <div class="badge" id="page">Página …</div>
        <button class="btn btn2" id="next">➡️</button>
      </div>

      <div class="grid" id="grid"></div>
      <div style="height:8px"></div>
      <div id="msg" class="msg" style="display:none"></div>
    </div>
  </div>

  <div class="footer">Baltigo MiniApp • Coleção</div>

<script>
const tg = window.Telegram?.WebApp;
if (tg) tg.ready();

function qs(name){ return new URLSearchParams(location.search).get(name); }

let INIT = "";
let UID = qs("uid") || "";
try{ INIT = tg?.initData || ""; }catch(e){}

async function apiGet(path){
  const headers = {};
  if (INIT) headers["X-Tg-Init-Data"] = INIT;
  const url = UID ? `${path}${path.includes("?")?"&":"?"}uid=${encodeURIComponent(UID)}` : path;
  const r = await fetch(url, {method:"GET", headers});
  const j = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(j.detail || j.error || "Erro");
  return j;
}

function setBadge(text){ document.getElementById("badge").textContent = text; }
function showMsg(text, isErr=false){
  const el = document.getElementById("msg");
  el.style.display = "block";
  el.className = "msg" + (isErr ? " err" : "");
  el.textContent = text;
}

let page = 1;
const per = 24;

async function load(){
  const me = await apiGet("/api/me");
  setBadge(me.nick || "User");
  document.getElementById("coins").textContent = `🪙 Coins: ${me.coins}`;
  document.getElementById("unique").textContent = `🧿 Únicos: ${me.collection_unique}`;

  const data = await apiGet(`/api/collection?page=${page}&per=${per}`);
  document.getElementById("total").textContent = `📦 Itens: ${data.total}`;
  document.getElementById("page").textContent = `Página ${data.page} / ${data.total_pages}`;

  const grid = document.getElementById("grid");
  grid.innerHTML = "";
  for(const c of data.items){
    const div = document.createElement("div");
    div.className = "tile";
    const img = c.image || "";
    div.innerHTML = `
      <img class="img" src="${img}" onerror="this.style.display='none'"/>
      <div style="height:8px"></div>
      <div style="font-weight:900">${c.character_name}</div>
      <div class="small">${c.anime_title || ""}</div>
      <div class="small">x${c.quantity}</div>
    `;
    grid.appendChild(div);
  }

  document.getElementById("prev").disabled = (page <= 1);
  document.getElementById("next").disabled = (page >= data.total_pages);

  showMsg(data.items.length ? "✅ Carregado." : "Você ainda não tem personagens.", false);
}

document.getElementById("prev").onclick = ()=>{ page = Math.max(1, page-1); load().catch(e=>showMsg("❌ "+e.message,true)); };
document.getElementById("next").onclick = ()=>{ page = page+1; load().catch(e=>showMsg("❌ "+e.message,true)); };

load().catch(e=>showMsg("❌ "+(e.message||"Falha ao carregar."), true));
</script>
</body>
</html>
"""

SHOP_HTML = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Loja</title>
  <style>{BASE_CSS}</style>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
</head>
<body>
  <div class="header">
    <div class="brand">
      <h1>🛒 LOJA</h1>
      <p>Venda 1 unidade por +{SELL_COIN_GAIN} coin.</p>
    </div>
    <div class="badge" id="badge">…</div>
  </div>

  <div class="container">
    <div class="card">
      <div class="kpi">
        <div class="pill" id="coins">🪙 Coins: …</div>
        <div class="pill" id="unique">🧿 Únicos: …</div>
        <div class="pill" id="total">📦 Total: …</div>
      </div>
      <div class="hr"></div>

      <div class="grid" id="grid"></div>

      <div style="height:10px"></div>
      <div id="msg" class="msg" style="display:none"></div>
    </div>
  </div>

  <div class="footer">Baltigo MiniApp • Loja</div>

<script>
const tg = window.Telegram?.WebApp;
if (tg) tg.ready();

function qs(name){ return new URLSearchParams(location.search).get(name); }

let INIT = "";
let UID = qs("uid") || "";
try{ INIT = tg?.initData || ""; }catch(e){}

async function api(path, payload){
  const headers = { "Content-Type":"application/json" };
  if (INIT) headers["X-Tg-Init-Data"] = INIT;
  const url = UID ? `${path}?uid=${encodeURIComponent(UID)}` : path;
  const r = await fetch(url, {method:"POST", headers, body: JSON.stringify(payload||{})});
  const j = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(j.detail || j.error || "Erro");
  return j;
}

async function apiGet(path){
  const headers = {};
  if (INIT) headers["X-Tg-Init-Data"] = INIT;
  const url = UID ? `${path}${path.includes("?")?"&":"?"}uid=${encodeURIComponent(UID)}` : path;
  const r = await fetch(url, {method:"GET", headers});
  const j = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(j.detail || j.error || "Erro");
  return j;
}

function setBadge(text){ document.getElementById("badge").textContent = text; }
function showMsg(text, isErr=false){
  const el = document.getElementById("msg");
  el.style.display = "block";
  el.className = "msg" + (isErr ? " err" : "");
  el.textContent = text;
}

async function load(){
  const me = await apiGet("/api/me");
  setBadge(me.nick || "User");
  document.getElementById("coins").textContent = `🪙 Coins: ${me.coins}`;
  document.getElementById("unique").textContent = `🧿 Únicos: ${me.collection_unique}`;
  document.getElementById("total").textContent = `📦 Total: ${me.collection_total_qty}`;

  const data = await apiGet("/api/shop/items?limit=120");
  const grid = document.getElementById("grid");
  grid.innerHTML = "";
  for(const c of data.items){
    const div = document.createElement("div");
    div.className = "tile";
    const img = c.image || "";
    div.innerHTML = `
      <img class="img" src="${img}" onerror="this.style.display='none'"/>
      <div style="height:8px"></div>
      <div style="font-weight:900">${c.character_name}</div>
      <div class="small">${c.anime_title || ""}</div>
      <div class="small">x${c.quantity} • +${c.sell_gain} coin</div>
      <div style="height:10px"></div>
      <button class="btn" style="width:100%" data-id="${c.character_id}">Vender 1</button>
    `;
    div.querySelector("button").onclick = async ()=>{
      try{
        showMsg("Vendendo…");
        await api("/api/shop/sell", { character_id: c.character_id });
        showMsg("✅ Vendido!");
        await load();
      }catch(e){
        showMsg("❌ " + (e.message || "Falhou."), true);
      }
    };
    grid.appendChild(div);
  }
  showMsg(data.items.length ? "✅ Itens carregados." : "Nada para vender ainda.", false);
}

load().catch(e=>showMsg("❌ "+(e.message||"Falha ao carregar."), true));
</script>
</body>
</html>
"""


# ----------------
# PAGES
# ----------------
@app.get("/health")
def health():
    return {"ok": True, "ts": int(time.time())}


@app.get("/dado", response_class=HTMLResponse)
def page_dado():
    return HTMLResponse(DADO_HTML)


@app.get("/colecao", response_class=HTMLResponse)
def page_colecao():
    return HTMLResponse(COLECAO_HTML)


@app.get("/shop", response_class=HTMLResponse)
def page_shop():
    return HTMLResponse(SHOP_HTML)


# ----------------
# API: Me / Collection / Shop
# ----------------
@app.get("/api/me")
def api_me(
    x_tg_init_data: Optional[str] = Header(default=None, alias="X-Tg-Init-Data"),
    uid: Optional[int] = Query(default=None),
):
    user_id = _get_user_id_from_request(x_tg_init_data, uid)
    u = db.get_user_row_safe(user_id)
    # garante que exista
    db.ensure_user_row(user_id, u.get("nick") or "User", new_user_dice=0)
    st = db.get_user_stats(user_id)
    return st


@app.get("/api/collection")
def api_collection(
    page: int = Query(default=1),
    per: int = Query(default=24),
    x_tg_init_data: Optional[str] = Header(default=None, alias="X-Tg-Init-Data"),
    uid: Optional[int] = Query(default=None),
):
    user_id = _get_user_id_from_request(x_tg_init_data, uid)
    u = db.get_user_row_safe(user_id)
    db.ensure_user_row(user_id, u.get("nick") or "User", new_user_dice=0)

    items, total, total_pages = db.get_collection_page(user_id, page, per)
    out = []
    for it in items:
        out.append({
            "character_id": int(it["character_id"]),
            "character_name": it["character_name"],
            "anime_title": it.get("anime_title") or "",
            "quantity": int(it.get("quantity") or 1),
            "image": (it.get("custom_image") or it.get("image") or ""),
        })

    return {
        "page": int(page),
        "per": int(per),
        "total": int(total),
        "total_pages": int(total_pages),
        "items": out,
    }


@app.get("/api/shop/items")
def api_shop_items(
    limit: int = Query(default=120),
    x_tg_init_data: Optional[str] = Header(default=None, alias="X-Tg-Init-Data"),
    uid: Optional[int] = Query(default=None),
):
    user_id = _get_user_id_from_request(x_tg_init_data, uid)
    u = db.get_user_row_safe(user_id)
    db.ensure_user_row(user_id, u.get("nick") or "User", new_user_dice=0)

    items = db.get_collection_for_webapp(user_id, limit=limit)
    # só mostra quem tem qty >= 1
    out = []
    for c in items:
        out.append({
            "character_id": int(c["character_id"]),
            "character_name": c["character_name"],
            "anime_title": c.get("anime_title") or "",
            "quantity": int(c.get("quantity") or 1),
            "image": c.get("image") or "",
            "sell_gain": SELL_COIN_GAIN,
        })
    return {"items": out}


@app.post("/api/shop/sell")
def api_shop_sell(
    payload: dict,
    x_tg_init_data: Optional[str] = Header(default=None, alias="X-Tg-Init-Data"),
    uid: Optional[int] = Query(default=None),
):
    user_id = _get_user_id_from_request(x_tg_init_data, uid)
    char_id = int(payload.get("character_id") or 0)
    if char_id <= 0:
        raise HTTPException(status_code=400, detail="character_id inválido")

    ok = db.sell_character_from_collection(user_id, char_id, coin_gain=SELL_COIN_GAIN)
    if not ok:
        raise HTTPException(status_code=400, detail="Você não possui esse personagem.")
    return {"ok": True}


# ----------------
# API: Dado (roll + pick)
# ----------------
@app.post("/api/dado/roll")
def api_dado_roll(
    payload: dict,
    x_tg_init_data: Optional[str] = Header(default=None, alias="X-Tg-Init-Data"),
    uid: Optional[int] = Query(default=None),
):
    user_id = _get_user_id_from_request(x_tg_init_data, uid)
    u = db.get_user_row_safe(user_id)
    db.ensure_user_row(user_id, u.get("nick") or "User", new_user_dice=0)

    st = db.get_user_stats(user_id)
    balance = int(st.get("dado_balance") or 0)
    extra = int(st.get("extra_dado") or 0)

    # regra simples:
    # - se tiver dado_balance > 0: usa 1 dado_balance
    # - senão, se tiver extra_dado > 0: usa 1 extra (giro)
    # - senão: erro
    source = None
    if balance > 0:
        source = "dado"
        db.set_dado_state(user_id, balance - 1, st.get("dado_slot") or -1)
    elif extra > 0:
        source = "giro"
        db.consume_extra_dado(user_id)
    else:
        raise HTTPException(status_code=400, detail="Você não tem dados/giros suficientes.")

    import random
    dice_value = random.randint(1, 6)

    # pega N animes do pool (N = dice_value)
    options = db.pool_random_animes(dice_value)  # já tem fallback TOP500
    options_json = json.dumps(options, ensure_ascii=False)

    roll_id = db.create_dice_roll(
        user_id=user_id,
        dice_value=dice_value,
        options_json=options_json,
        status="pending",
        created_at=int(time.time()),
    )

    # retorna opções pro frontend
    return {
        "roll_id": int(roll_id),
        "dice_value": int(dice_value),
        "source": source,
        "options": options,
    }


@app.post("/api/dado/pick")
def api_dado_pick(
    payload: dict,
    x_tg_init_data: Optional[str] = Header(default=None, alias="X-Tg-Init-Data"),
    uid: Optional[int] = Query(default=None),
):
    user_id = _get_user_id_from_request(x_tg_init_data, uid)
    u = db.get_user_row_safe(user_id)
    db.ensure_user_row(user_id, u.get("nick") or "User", new_user_dice=0)

    roll_id = int(payload.get("roll_id") or 0)
    anime = (payload.get("anime") or "").strip()
    if roll_id <= 0:
        raise HTTPException(status_code=400, detail="roll_id inválido")
    if not anime:
        raise HTTPException(status_code=400, detail="anime inválido")

    roll = db.get_dice_roll(roll_id)
    if not roll or int(roll.get("user_id") or 0) != int(user_id):
        raise HTTPException(status_code=404, detail="Roll não encontrado.")

    # idempotência: só permite resolver 1x
    ok = db.try_set_dice_roll_status(roll_id, expected="pending", new_status="resolving")
    if not ok:
        # já resolveu/expirou/etc
        # se já resolved, retorna erro leve
        raise HTTPException(status_code=400, detail="Este roll já foi usado.")

    # valida se anime está nas opções
    try:
        opts = json.loads(roll.get("options_json") or "[]") or []
    except Exception:
        opts = []

    allowed = set()
    for o in opts:
        a = (o.get("anime") or o.get("title") or "").strip()
        if a:
            allowed.add(a)

    if anime not in allowed:
        # volta status pra pending (não pune o usuário)
        db.set_dice_roll_status(roll_id, "pending")
        raise HTTPException(status_code=400, detail="Opção inválida.")

    # escolhe personagem do pool por anime
    ch = db.pool_random_character(anime=anime)
    if not ch:
        # fallback: tenta qualquer
        ch = db.pool_random_character(anime=None)

    if not ch:
        db.set_dice_roll_status(roll_id, "pending")
        raise HTTPException(status_code=500, detail="Pool vazio. Importe o TXT do TOP500.")

    character_id = int(ch["character_id"])
    character_name = str(ch["name"])
    anime_title = str(ch["anime"])

    # imagem: tenta global, senão vazio (você pode plugar AniList aqui depois)
    img = db.get_global_character_image(character_id) or ""

    # adiciona na coleção
    db.add_character_to_collection(
        user_id=user_id,
        char_id=character_id,
        name=character_name,
        image=img,
        anime_title=anime_title,
    )

    # finaliza roll
    db.set_dice_roll_status(roll_id, "resolved")

    return {
        "ok": True,
        "character_id": character_id,
        "character_name": character_name,
        "anime_title": anime_title,
        "image": img,
    }
