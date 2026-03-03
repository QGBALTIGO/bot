# webapp.py — Mini App Coleção (REAL) + validação initData (Telegram WebApp)
# + modo "coleção do dono" via URL (?u=...&ts=...&sig=...)
# + favorito com coração
# + agrupado por anime e ordenação alfabética
# + foto do setfoto (custom_image) tem prioridade

import os
import json
import time
import hmac
import hashlib
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

# Segredo para assinar links de coleção compartilhada (tem que ser IGUAL no bot e no webapp)
MINIAPP_SIGNING_SECRET = os.getenv("MINIAPP_SIGNING_SECRET", "").strip()


def verify_telegram_init_data(init_data: str) -> dict:
    """
    Valida initData do Telegram WebApp (MÉTODO CERTO).
    """
    if not init_data:
        raise HTTPException(status_code=401, detail="initData ausente")

    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="hash ausente")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

    # ✅ CHAVE CORRETA DO WEBAPP:
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="initData inválido")

    user_json = data.get("user")
    user = json.loads(user_json) if user_json else None
    if not user or "id" not in user:
        raise HTTPException(status_code=401, detail="user inválido")

    return {"user": user, "raw": data}


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _sign_owner_link(user_id: int, ts: int) -> str:
    """
    Assina o link para impedir troca do u=.
    Se MINIAPP_SIGNING_SECRET não estiver configurada, retorna "".
    """
    if not MINIAPP_SIGNING_SECRET:
        return ""
    msg = f"{int(user_id)}:{int(ts)}".encode()
    return hmac.new(MINIAPP_SIGNING_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def _verify_owner_sig(user_id: int, ts: int, sig: str) -> bool:
    """
    Verifica assinatura do link.
    Se MINIAPP_SIGNING_SECRET não estiver configurada, NÃO bloqueia (menos seguro).
    """
    if not MINIAPP_SIGNING_SECRET:
        return True
    expected = _sign_owner_link(user_id, ts)
    return hmac.compare_digest(expected, sig or "")


def _get_collection_name_safe(db, user_id: int) -> str:
    try:
        fn = getattr(db, "get_collection_name", None)
        if callable(fn):
            name = fn(user_id)
            if isinstance(name, str) and name.strip():
                return name.strip()
    except Exception:
        pass
    return "Minha coleção"


def _list_collection_cards_safe(db, user_id: int, limit: int = 500) -> list[dict]:
    try:
        fn = getattr(db, "list_collection_cards", None)
        if callable(fn):
            cards = fn(user_id, limit=limit)
            if isinstance(cards, list):
                # garante dict e mantém chaves originais (incluindo custom_image)
                return [c for c in cards if isinstance(c, dict)]
    except Exception:
        pass
    return []


def _get_coins_and_giros_safe(db, user_id: int) -> tuple[int, int]:
    coins = 0
    giros = 0

    # COINS
    try:
        fn = getattr(db, "get_user_row", None)
        if callable(fn):
            row = fn(user_id)
            if isinstance(row, dict):
                coins = _safe_int(row.get("coins"), 0)
    except Exception:
        coins = 0

    # GIROS (extra_dado)
    try:
        fn = getattr(db, "get_extra_state", None)
        if callable(fn):
            st = fn(user_id)
            if isinstance(st, dict):
                giros = _safe_int(st.get("x"), 0)
    except Exception:
        giros = 0

    return coins, giros


def _get_owner_display_name_safe(db, owner_id: int) -> str:
    """
    Nome para mostrar no topo: tenta nick -> first_name -> fallback.
    """
    try:
        fn = getattr(db, "get_user_row", None)
        if callable(fn):
            row = fn(owner_id)
            if isinstance(row, dict):
                nick = (row.get("nick") or "").strip() if isinstance(row.get("nick"), str) else ""
                if nick:
                    return nick
                fnm = (row.get("first_name") or "").strip() if isinstance(row.get("first_name"), str) else ""
                if fnm:
                    return fnm
    except Exception:
        pass
    return "Usuário"


app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(content="✅ Web rodando! Abra /app para ver a miniapp.")


# =========================
# API: MINHA coleção (quem clicou)
# =========================
@app.get("/api/me/collection")
def api_me_collection(x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    import database as db

    # garante user row se existir
    try:
        fn = getattr(db, "ensure_user_row", None)
        if callable(fn):
            fn(user_id, first_name)
    except Exception:
        pass

    coins, giros = _get_coins_and_giros_safe(db, user_id)
    collection_name = _get_collection_name_safe(db, user_id)
    cards = _list_collection_cards_safe(db, user_id, limit=500)

    return JSONResponse(
        {
            "ok": True,
            "mode": "me",
            "owner_id": user_id,
            "owner_name": first_name,
            "collection_name": collection_name,
            "coins": coins,
            "giros": giros,
            "cards": cards,
        }
    )


# =========================
# API: COLEÇÃO do DONO (link compartilhado no grupo)
# =========================
@app.get("/api/collection")
def api_owner_collection(
    x_telegram_init_data: str = Header(default=""),
    u: int = Query(...),
    ts: int = Query(...),
    sig: str = Query(default=""),
):
    # 1) garante que foi aberto dentro do Telegram (initData válido)
    verify_telegram_init_data(x_telegram_init_data)

    owner_id = int(u)
    ts_i = int(ts)

    # 2) expira link em 24h (anti link eterno)
    if abs(int(time.time()) - ts_i) > 24 * 3600:
        raise HTTPException(status_code=403, detail="link expirou")

    # 3) valida assinatura (anti trocar u=)
    if not _verify_owner_sig(owner_id, ts_i, sig):
        raise HTTPException(status_code=403, detail="assinatura inválida")

    import database as db

    coins, giros = _get_coins_and_giros_safe(db, owner_id)
    collection_name = _get_collection_name_safe(db, owner_id)
    cards = _list_collection_cards_safe(db, owner_id, limit=500)
    owner_name = _get_owner_display_name_safe(db, owner_id)

    return JSONResponse(
        {
            "ok": True,
            "mode": "owner",
            "owner_id": owner_id,
            "owner_name": owner_name,
            "collection_name": collection_name,
            "coins": coins,
            "giros": giros,
            "cards": cards,
        }
    )


# =========================
# APP UI
# =========================
@app.get("/app", response_class=HTMLResponse)
def miniapp():
    html = r"""<!doctype html>
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
      --accent:#ff4fd8;
      --accent2:#7c4dff;
      --heart:#ff3b7a;
      --section: rgba(255,255,255,.06);
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
      background:var(--bg);
      color:#fff;
      padding:12px 12px 88px;
    }
    .top{
      display:flex; align-items:center; justify-content:space-between; gap:10px;
      margin-top:4px;
    }
    .title{display:flex; flex-direction:column; gap:2px; min-width: 0;}
    .title h1{margin:0; font-size:18px; font-weight:900; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
    .title .sub{font-size:12px; color:var(--muted2);}

    .stats{
      display:flex; align-items:center; gap:8px;
      padding:10px 12px;
      border:1px solid var(--stroke);
      background:rgba(255,255,255,.04);
      border-radius:999px;
      white-space:nowrap;
      flex-shrink: 0;
    }
    .stat{display:flex; align-items:center; gap:6px; font-weight:900; font-size:13px;}
    .dot{width:1px; height:16px; background:var(--stroke);}

    .tabs{
      display:flex; gap:10px;
      margin:14px 0 10px;
      padding:8px;
      border:1px solid var(--stroke);
      border-radius:999px;
      background:rgba(255,255,255,.04);
    }
    .tab{
      flex:1; text-align:center;
      padding:10px 12px; border-radius:999px;
      font-weight:900; font-size:14px;
      color:var(--muted);
      background:transparent; border:0;
    }
    .tab.active{
      color:#fff;
      background:linear-gradient(90deg, rgba(255,79,216,.9), rgba(124,77,255,.9));
      box-shadow:0 10px 30px rgba(255,79,216,.15);
    }

    .search{display:flex; gap:10px; align-items:center; margin:8px 0 14px;}
    .search input{
      width:100%;
      padding:12px 12px;
      border-radius:14px;
      border:1px solid var(--stroke);
      background:rgba(255,255,255,.04);
      color:#fff;
      outline:none;
      font-size:14px;
    }
    .search input::placeholder{color:rgba(255,255,255,.35)}

    .status{
      margin:10px 0;
      padding:10px 12px;
      border-radius:14px;
      border:1px solid var(--stroke);
      background:rgba(255,255,255,.03);
      color:var(--muted);
      font-size:13px;
      white-space:pre-wrap;
    }
    .status.ok{ border-color: rgba(0,255,140,.18); }
    .status.err{ border-color: rgba(255,60,60,.18); color: rgba(255,120,120,.95); }

    .section{
      margin-top: 12px;
      padding: 10px 10px 6px;
      border-radius: 16px;
      border: 1px solid var(--stroke);
      background: var(--section);
    }
    .section-title{
      font-weight: 900;
      font-size: 14px;
      color: rgba(255,255,255,.92);
      margin: 2px 4px 10px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:8px;
    }
    .section-count{
      font-size:12px;
      color: rgba(255,255,255,.55);
      font-weight: 800;
    }

    .grid{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px;}
    .card{
      position:relative;
      border-radius:20px;
      overflow:hidden;
      border:1px solid var(--stroke);
      background:var(--card);
      min-height:220px;
    }
    .card img{width:100%; height:220px; object-fit:cover; display:block;}
    .overlay{
      position:absolute; left:0; right:0; bottom:0;
      padding:10px;
      background:linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.78));
    }
    .name{font-weight:900; font-size:16px; margin:0;}
    .meta{margin-top:3px; font-size:12px; color:rgba(255,255,255,.75);}

    .pill{
      position:absolute; top:10px; left:10px;
      padding:6px 10px;
      background:rgba(0,0,0,.45);
      border:1px solid rgba(255,255,255,.14);
      border-radius:999px;
      font-weight:900; font-size:12px;
      display:flex;
      align-items:center;
      gap:6px;
    }
    .heart{
      position:absolute;
      top:10px;
      right:10px;
      width:34px;
      height:34px;
      border-radius:999px;
      display:flex;
      align-items:center;
      justify-content:center;
      background: rgba(0,0,0,.45);
      border: 1px solid rgba(255,255,255,.14);
      font-size: 16px;
      color: var(--heart);
      text-shadow: 0 10px 25px rgba(0,0,0,.35);
    }

    .bottom{
      position:fixed; left:12px; right:12px; bottom:14px;
      padding:12px 14px;
      border-radius:18px;
      border:1px solid var(--stroke);
      background:rgba(20,20,30,.72);
      backdrop-filter:blur(14px);
      display:flex; justify-content:space-between; gap:10px;
    }
    .nav{
      flex:1; text-align:center;
      color:rgba(255,255,255,.75);
      font-weight:900; font-size:12px;
      border-radius:14px;
      padding:10px 8px;
      background:transparent; border:0;
    }
    .nav.active{ color:#fff; background:rgba(255,255,255,.06); }
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

  <div id="sections"></div>

  <div class="bottom">
    <button class="nav active" id="nav_explore">Explore</button>
    <button class="nav" id="nav_chats">Chats</button>
    <button class="nav" id="nav_profile">Profile</button>
  </div>

  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) { tg.ready(); try { tg.expand(); } catch(e) {} }

    let allCards = [];
    let showFav = false;

    function setStatus(text, type){
      const el = document.getElementById("status");
      el.className = "status" + (type ? (" " + type) : "");
      el.textContent = text;
    }

    // ==========================
    // Utils (normalização)
    // ==========================
    function pickFirstString(obj, keys){
      for (const k of keys){
        const v = obj?.[k];
        if (typeof v === "string" && v.trim()) return v.trim();
      }
      return "";
    }
    function pickFirstNumber(obj, keys){
      for (const k of keys){
        const v = obj?.[k];
        if (typeof v === "number") return v;
        if (typeof v === "string" && v.trim() && !isNaN(Number(v))) return Number(v);
      }
      return null;
    }

    function getCharacterName(c){
      return pickFirstString(c, [
        "character_name","name","character","personagem","nome",
        "char_name","card_name"
      ]) || "Personagem";
    }

    function getAnimeTitle(c){
      return pickFirstString(c, [
        "anime_title","anime","anime_name","obra","title","series","serie"
      ]) || "Sem anime";
    }

    function getImageUrl(c){
      // ✅ PRIORIDADE: custom_image (setfoto) -> image (anilist)
      return pickFirstString(c, [
        "custom_image","image","img","photo","picture","url"
      ]) || "";
    }

    function getCharId(c){
      return pickFirstNumber(c, [
        "character_id","char_id","id","card_id","personagem_id"
      ]) ?? 0;
    }

    function getQty(c){
      return pickFirstNumber(c, [
        "quantity","qty","qtd","amount","count"
      ]) ?? 1;
    }

    function isFavorite(c){
      const v = c?.is_favorite ?? c?.favorite ?? c?.fav;
      return v === true || v === 1 || v === "1" || v === "true";
    }

    function cmpAZ(a, b){
      return String(a).localeCompare(String(b), "pt-BR", { sensitivity: "base" });
    }

    function buildGroups(list){
      const groups = new Map(); // anime -> cards[]
      for (const c of list){
        const anime = getAnimeTitle(c) || "Sem anime";
        if (!groups.has(anime)) groups.set(anime, []);
        groups.get(anime).push(c);
      }

      const animeTitles = Array.from(groups.keys()).sort(cmpAZ);

      const out = [];
      for (const title of animeTitles){
        const cards = groups.get(title) || [];
        cards.sort((x, y) => cmpAZ(getCharacterName(x), getCharacterName(y)));
        out.push({ title, cards });
      }
      return out;
    }

    function render(){
      const q = (document.getElementById("q").value || "").trim().toLowerCase();

      const filtered = allCards.filter(c => {
        if (showFav && !isFavorite(c)) return false;
        if (!q) return true;

        const name = getCharacterName(c).toLowerCase();
        const anime = getAnimeTitle(c).toLowerCase();
        const id = String(getCharId(c));
        return name.includes(q) || anime.includes(q) || id.includes(q);
      });

      const sectionsRoot = document.getElementById("sections");
      sectionsRoot.innerHTML = "";

      if (!filtered.length){
        sectionsRoot.innerHTML = "<div style='color:rgba(255,255,255,.65)'>Nenhum card encontrado.</div>";
        return;
      }

      const groups = buildGroups(filtered);

      for (const g of groups){
        const section = document.createElement("div");
        section.className = "section";

        const header = document.createElement("div");
        header.className = "section-title";
        header.innerHTML = `
          <div>${g.title}</div>
          <div class="section-count">${g.cards.length}</div>
        `;
        section.appendChild(header);

        const grid = document.createElement("div");
        grid.className = "grid";

        for (const c of g.cards){
          const img = getImageUrl(c);
          const qty = getQty(c);
          const charId = getCharId(c);
          const name = getCharacterName(c);
          const fav = isFavorite(c);

          const card = document.createElement("div");
          card.className = "card";
          card.innerHTML = `
            ${img
              ? `<img src="${img}" alt="">`
              : `<div style="height:220px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5)">Sem imagem</div>`
            }
            <div class="pill">x${qty} • ID ${charId}</div>
            ${fav ? `<div class="heart">❤️</div>` : ``}
            <div class="overlay">
              <div class="name">${name}</div>
              <div class="meta">${g.title}</div>
            </div>
          `;
          grid.appendChild(card);
        }

        section.appendChild(grid);
        sectionsRoot.appendChild(section);
      }
    }

    async function load(){
      try{
        setStatus("Carregando sua coleção...", "");

        const initData = tg?.initData || "";

        // ✅ se tiver u/ts na URL, carrega coleção do DONO (compartilhada no grupo)
        const params = new URLSearchParams(window.location.search);
        const u = params.get("u");
        const ts = params.get("ts");
        const sig = params.get("sig") || "";

        let apiUrl = "/api/me/collection";
        let viewingOwner = false;

        if (u && ts) {
          apiUrl = `/api/collection?u=${encodeURIComponent(u)}&ts=${encodeURIComponent(ts)}&sig=${encodeURIComponent(sig)}`;
          viewingOwner = true;
        }

        const res = await fetch(apiUrl, {
          headers: { "X-Telegram-Init-Data": initData }
        });

        if (!res.ok){
          const txt = await res.text().catch(()=> "");
          setStatus("❌ Falha ao carregar.\n\nMotivo: " + res.status + "\n" + txt, "err");
          document.getElementById("sub").textContent = "Erro: " + res.status;
          return;
        }

        const data = await res.json();

        // topo: "Coleção de X" quando for compartilhada
        const ownerName = data.owner_name || "";
        if (viewingOwner && ownerName) {
          document.getElementById("h1").textContent = "Coleção de " + ownerName;
        } else {
          document.getElementById("h1").textContent = data.collection_name || "Minha coleção";
        }

        document.getElementById("sub").textContent = "Cards: " + (data.cards?.length || 0);
        document.getElementById("coins").textContent = String(data.coins ?? "-");
        document.getElementById("giros").textContent = String(data.giros ?? "-");

        allCards = Array.isArray(data.cards) ? data.cards : [];
        setStatus("✅ Coleção carregada.", "ok");
        render();
      } catch(e){
        setStatus("❌ Erro inesperado ao carregar.", "err");
      }
    }

    document.getElementById("tab_all").onclick = () => {
      showFav = false;
      document.getElementById("tab_all").classList.add("active");
      document.getElementById("tab_fav").classList.remove("active");
      render();
    };

    document.getElementById("tab_fav").onclick = () => {
      showFav = true;
      document.getElementById("tab_fav").classList.add("active");
      document.getElementById("tab_all").classList.remove("active");
      render();
    };

    document.getElementById("q").addEventListener("input", render);

    load();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)
