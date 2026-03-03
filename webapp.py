# webapp.py — Mini App Coleção (REAL) + validação initData (Telegram WebApp)

import os
import json
import hmac
import hashlib
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from database import (
    init_db,
    ensure_user_row,
    list_collection_cards,
    get_collection_name,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")


def verify_telegram_init_data(init_data: str) -> dict:
    """
    Valida initData do Telegram WebApp.
    Sem isso, qualquer um poderia fingir ser outro usuário.
    """
    if not init_data:
        raise HTTPException(status_code=401, detail="initData ausente")

    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="hash ausente")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="initData inválido")

    user_json = data.get("user")
    user = json.loads(user_json) if user_json else None
    if not user or "id" not in user:
        raise HTTPException(status_code=401, detail="user inválido")

    return {"user": user, "raw": data}


app = FastAPI()


@app.on_event("startup")
def _startup():
    # garante tabelas/migrações (para o serviço WEB também)
    init_db()


@app.get("/", response_class=HTMLResponse)
def root():
    return "✅ Web rodando! Abra /app para ver a miniapp."


from database import get_user_coins, get_user_giros  # ou as funções que você já tem

@app.get("/api/me/collection")
def api_me_collection(x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    ensure_user_row(user_id, first_name)

    cards = list_collection_cards(user_id, limit=200)
    coins = get_user_coins(user_id)
    giros = get_user_giros(user_id)

    return JSONResponse({
        "ok": True,
        "user_id": user_id,
        "collection_name": get_collection_name(user_id),
        "coins": coins,
        "giros": giros,
        "cards": cards,
    })
from fastapi.responses import HTMLResponse

@app.get("/app", response_class=HTMLResponse)
def miniapp():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1, viewport-fit=cover">
  <title>Coleção</title>
  <style>
    :root{
      --bg:#0b0b0f;
      --card:#151522;
      --muted: rgba(255,255,255,.65);
      --muted2: rgba(255,255,255,.45);
      --stroke: rgba(255,255,255,.12);
      --pill: rgba(255,255,255,.08);
      --accent:#ff4fd8;
      --accent2:#7c4dff;
    }

    *{box-sizing:border-box}
    body{
      margin:0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      background: var(--bg);
      color:#fff;
      padding: 12px 12px 88px;
    }

    .top{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:10px;
      margin-top: 4px;
    }
    .title{
      display:flex;
      flex-direction:column;
      gap:2px;
    }
    .title h1{
      margin:0;
      font-size:18px;
      font-weight:800;
      letter-spacing:.2px;
    }
    .title .sub{
      font-size:12px;
      color:var(--muted2);
    }

    .stats{
      display:flex;
      align-items:center;
      gap:8px;
      padding:10px 12px;
      border:1px solid var(--stroke);
      background: rgba(255,255,255,.04);
      border-radius: 999px;
      white-space:nowrap;
    }
    .stat{
      display:flex;
      align-items:center;
      gap:6px;
      font-weight:700;
      font-size:13px;
      color:#fff;
    }
    .dot{width:1px; height:16px; background:var(--stroke);}

    .tabs{
      display:flex;
      gap:10px;
      margin:14px 0 10px;
      padding:8px;
      border:1px solid var(--stroke);
      border-radius:999px;
      background: rgba(255,255,255,.04);
    }
    .tab{
      flex:1;
      text-align:center;
      padding:10px 12px;
      border-radius:999px;
      font-weight:800;
      font-size:14px;
      color:var(--muted);
      background: transparent;
      border:0;
    }
    .tab.active{
      color:#fff;
      background: linear-gradient(90deg, rgba(255,79,216,.9), rgba(124,77,255,.9));
      box-shadow: 0 10px 30px rgba(255,79,216,.15);
    }

    .search{
      display:flex;
      gap:10px;
      align-items:center;
      margin: 8px 0 14px;
    }
    .search input{
      width:100%;
      padding:12px 12px;
      border-radius: 14px;
      border:1px solid var(--stroke);
      background: rgba(255,255,255,.04);
      color:#fff;
      outline:none;
      font-size:14px;
    }
    .search input::placeholder{color:rgba(255,255,255,.35)}

    .status{
      margin: 10px 0;
      padding: 10px 12px;
      border-radius: 14px;
      border:1px solid var(--stroke);
      background: rgba(255,255,255,.03);
      color: var(--muted);
      font-size:13px;
    }
    .status.ok{ border-color: rgba(0,255,140,.18); }
    .status.err{ border-color: rgba(255,60,60,.18); color: rgba(255,120,120,.9); }

    .grid{
      display:grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .card{
      position:relative;
      border-radius: 20px;
      overflow:hidden;
      border:1px solid var(--stroke);
      background: var(--card);
      min-height: 220px;
    }
    .card img{
      width:100%;
      height: 220px;
      object-fit: cover;
      display:block;
      filter: saturate(1.1);
    }
    .overlay{
      position:absolute;
      left:0; right:0; bottom:0;
      padding: 10px 10px 10px;
      background: linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.75));
    }
    .name{
      font-weight:900;
      font-size:16px;
      margin:0;
      text-shadow: 0 8px 24px rgba(0,0,0,.35);
    }
    .meta{
      margin-top:3px;
      font-size:12px;
      color: rgba(255,255,255,.75);
    }
    .pill{
      position:absolute;
      top:10px; left:10px;
      padding:6px 10px;
      background: rgba(0,0,0,.45);
      border:1px solid rgba(255,255,255,.14);
      border-radius:999px;
      font-weight:800;
      font-size:12px;
    }

    .bottom{
      position:fixed;
      left:12px; right:12px;
      bottom: 14px;
      padding: 12px 14px;
      border-radius: 18px;
      border:1px solid var(--stroke);
      background: rgba(20,20,30,.72);
      backdrop-filter: blur(14px);
      display:flex;
      justify-content:space-between;
      gap:10px;
    }
    .nav{
      flex:1;
      text-align:center;
      color: rgba(255,255,255,.75);
      font-weight:800;
      font-size:12px;
      border-radius: 14px;
      padding:10px 8px;
      background: transparent;
      border:0;
    }
    .nav.active{
      color:#fff;
      background: rgba(255,255,255,.06);
    }
  </style>
</head>
<body>
  <div class="top">
    <div class="title">
      <h1 id="h1">Minha coleção</h1>
      <div class="sub" id="sub">Carregando...</div>
    </div>

    <div class="stats">
      <div class="stat">🪙 <span id="coins">-</span></div>
      <div class="dot"></div>
      <div class="stat">🎡 <span id="giros">-</span></div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" id="tab_all">📦 Coleção</button>
    <button class="tab" id="tab_fav">⭐ Favoritos</button>
  </div>

  <div class="search">
    <input id="q" placeholder="Buscar personagem ou anime..." />
  </div>

  <div class="status" id="status">Conectando...</div>

  <div class="grid" id="grid"></div>

  <div class="bottom">
    <button class="nav active" id="nav_explore">Explore</button>
    <button class="nav" id="nav_chats">Chats</button>
    <button class="nav" id="nav_profile">Profile</button>
  </div>

  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      try { tg.expand(); } catch(e) {}
    }

    let allCards = [];
    let showFav = false;

    function setStatus(text, type){
      const el = document.getElementById("status");
      el.className = "status" + (type ? (" " + type) : "");
      el.textContent = text;
    }

    function render(){
      const grid = document.getElementById("grid");
      const q = (document.getElementById("q").value || "").trim().toLowerCase();

      const list = allCards.filter(c => {
        if (showFav && !c.is_favorite) return false;
        const name = (c.character_name || "").toLowerCase();
        const anime = (c.anime_title || "").toLowerCase();
        if (!q) return true;
        return name.includes(q) || anime.includes(q) || String(c.character_id).includes(q);
      });

      grid.innerHTML = "";
      if (!list.length){
        grid.innerHTML = "<div style='color:rgba(255,255,255,.65)'>Nenhum card encontrado.</div>";
        return;
      }

      for (const c of list){
        const img = c.custom_image || c.image || "";
        const qty = c.quantity || 1;

        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
          ${img ? `<img src="${img}" alt="">` : `<div style="height:220px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5)">Sem imagem</div>`}
          <div class="pill">x${qty} • ID ${c.character_id}</div>
          <div class="overlay">
            <div class="name">${c.character_name || "Personagem"}</div>
            <div class="meta">${c.anime_title || ""}</div>
          </div>
        `;
        grid.appendChild(card);
      }
    }

    async function load(){
      try{
        setStatus("Carregando sua coleção...", "");
        const initData = tg?.initData || "";
        const res = await fetch("/api/me/collection", {
          headers: { "X-Telegram-Init-Data": initData }
        });

        if (!res.ok){
          const txt = await res.text().catch(()=> "");
          setStatus("❌ Falha ao carregar (login do Telegram não passou).", "err");
          document.getElementById("sub").textContent = "Erro: " + res.status;
          console.log("API error:", res.status, txt);
          return;
        }

        const data = await res.json();
        document.getElementById("h1").textContent = data.collection_name || "Minha coleção";
        document.getElementById("sub").textContent = "Cards: " + (data.cards?.length || 0);

        document.getElementById("coins").textContent = String(data.coins ?? "-");
        document.getElementById("giros").textContent = String(data.giros ?? "-");

        allCards = data.cards || [];
        setStatus("✅ Coleção carregada.", "ok");
        render();
      } catch(e){
        console.log(e);
        setStatus("❌ Erro inesperado ao carregar.", "err");
      }
    }

    // tabs
    document.getElementById("tab_all").onclick = () => {
      showFav = false;
      document.getElementById("tab_all").classList.add("active");
      document.getElementById("tab_fav").classList.remove("active");
      render();
    }
    document.getElementById("tab_fav").onclick = () => {
      showFav = true;
      document.getElementById("tab_fav").classList.add("active");
      document.getElementById("tab_all").classList.remove("active");
      render();
    }

    document.getElementById("q").addEventListener("input", render);

    load();
  </script>
</body>
</html>
    """
