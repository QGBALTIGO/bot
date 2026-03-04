
# webapp.py — MiniApps (Coleção + Loja) — FastAPI
# - valida initData (Telegram WebApp) corretamente
# - /app: coleção (minha ou do dono via link assinado)
# - /shop: loja (vender personagem + comprar giro)
# - setfoto: usa custom_image primeiro
# - sem duplicar FastAPI / sem HTML quebrado

import os
import json
import time
import hmac
import hashlib
from typing import Optional, Tuple, List, Dict, Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse


# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")

# Segredo para assinar links compartilhados (?u=&ts=&sig=) — tem que ser IGUAL no bot e no webapp
MINIAPP_SIGNING_SECRET = os.getenv("MINIAPP_SIGNING_SECRET", "").strip()

SHOP_SELL_GAIN = int(os.getenv("SHOP_SELL_GAIN", "1"))
SHOP_GIRO_PRICE = int(os.getenv("SHOP_GIRO_PRICE", "2"))
SHOP_PER_PAGE = int(os.getenv("SHOP_PER_PAGE", "8"))

# limite seguro pra não pesar
COLLECTION_LIMIT = int(os.getenv("COLLECTION_LIMIT", "500"))


# =========================
# Telegram WebApp initData verify (correto)
# =========================
def verify_telegram_init_data(init_data: str) -> dict:
    """
    Valida initData do Telegram WebApp (método correto).
    """
    if not init_data:
        raise HTTPException(status_code=401, detail="initData ausente")

    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="hash ausente")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

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


def _safe_str(x) -> str:
    return x.strip() if isinstance(x, str) else ""


# =========================
# Assinatura do link "coleção do dono"
# =========================
def _sign_owner_link(user_id: int, ts: int) -> str:
    if not MINIAPP_SIGNING_SECRET:
        return ""
    msg = f"{int(user_id)}:{int(ts)}".encode()
    return hmac.new(MINIAPP_SIGNING_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def _verify_owner_sig(user_id: int, ts: int, sig: str) -> bool:
    if not MINIAPP_SIGNING_SECRET:
        # sem secret -> não bloqueia (menos seguro)
        return True
    expected = _sign_owner_link(user_id, ts)
    return hmac.compare_digest(expected, sig or "")


# =========================
# DB safe wrappers (não quebram se faltar algo)
# =========================
def _ensure_user(db, user_id: int, first_name: str):
    try:
        fn = getattr(db, "ensure_user_row", None)
        if callable(fn):
            fn(user_id, first_name)
    except Exception:
        pass


def _get_user_row(db, user_id: int) -> dict:
    try:
        fn = getattr(db, "get_user_row", None)
        if callable(fn):
            r = fn(user_id)
            return r if isinstance(r, dict) else {}
    except Exception:
        pass
    return {}


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


def _list_collection_cards_safe(db, user_id: int, limit: int = 500) -> List[dict]:
    try:
        fn = getattr(db, "list_collection_cards", None)
        if callable(fn):
            cards = fn(user_id, limit=limit)
            if isinstance(cards, list):
                return [c for c in cards if isinstance(c, dict)]
    except Exception:
        pass
    return []


def _get_coins(db, user_id: int) -> int:
    # tenta get_user_coins, senão user_row.coins
    try:
        fn = getattr(db, "get_user_coins", None)
        if callable(fn):
            return _safe_int(fn(user_id), 0)
    except Exception:
        pass

    row = _get_user_row(db, user_id)
    return _safe_int(row.get("coins"), 0)


def _get_giros(db, user_id: int) -> int:
    # tenta get_extra_dado, senão extra_state.x
    try:
        fn = getattr(db, "get_extra_dado", None)
        if callable(fn):
            return _safe_int(fn(user_id), 0)
    except Exception:
        pass

    try:
        fn = getattr(db, "get_extra_state", None)
        if callable(fn):
            st = fn(user_id)
            if isinstance(st, dict):
                return _safe_int(st.get("x"), 0)
    except Exception:
        pass
    return 0


def _get_owner_display_name_safe(db, owner_id: int) -> str:
    row = _get_user_row(db, owner_id)
    nick = _safe_str(row.get("nick"))
    if nick:
        return nick
    fnm = _safe_str(row.get("first_name"))
    if fnm:
        return fnm
    return "Usuário"


def _get_fav_name(db, user_id: int) -> str:
    row = _get_user_row(db, user_id)
    return _safe_str(row.get("fav_name"))


def _get_sell_page(db, user_id: int, page: int, per_page: int):
    fn = getattr(db, "get_collection_page", None)
    if not callable(fn):
        raise HTTPException(status_code=500, detail="Função get_collection_page não existe no database.py")

    itens, total, total_pages = fn(user_id, page, per_page)
    if itens is None:
        itens = []
    return itens, _safe_int(total, 0), max(1, _safe_int(total_pages, 1))


def _get_character_full(db, user_id: int, char_id: int) -> Optional[dict]:
    try:
        fn = getattr(db, "get_collection_character_full", None)
        if callable(fn):
            it = fn(user_id, char_id)
            return it if isinstance(it, dict) else None
    except Exception:
        pass
    return None


def _remove_one(db, user_id: int, char_id: int) -> bool:
    try:
        fn = getattr(db, "remove_one_from_collection", None)
        if callable(fn):
            return bool(fn(user_id, char_id))
    except Exception:
        pass
    return False


def _add_coin(db, user_id: int, amount: int) -> bool:
    try:
        fn = getattr(db, "add_coin", None)
        if callable(fn):
            fn(user_id, amount)
            return True
    except Exception:
        pass
    return False


def _buy_giro(db, user_id: int, price: int) -> bool:
    fn = getattr(db, "spend_coins_and_add_giro", None)
    if not callable(fn):
        raise HTTPException(status_code=500, detail="Função spend_coins_and_add_giro não existe no database.py")
    return bool(fn(user_id, price, giros=1))


# =========================
# APP
# =========================
app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse("✅ Web rodando! Use /app (coleção) ou /shop (loja).")


# =========================
# API: Coleção (me)
# =========================
@app.get("/api/me/collection")
def api_me_collection(x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    import database as db

    _ensure_user(db, user_id, first_name)

    coins = _get_coins(db, user_id)
    giros = _get_giros(db, user_id)
    collection_name = _get_collection_name_safe(db, user_id)
    cards = _list_collection_cards_safe(db, user_id, limit=COLLECTION_LIMIT)

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
# API: Coleção do dono (owner)
# =========================
@app.get("/api/collection")
def api_owner_collection(
    x_telegram_init_data: str = Header(default=""),
    u: int = Query(...),
    ts: int = Query(...),
    sig: str = Query(default=""),
):
    verify_telegram_init_data(x_telegram_init_data)

    owner_id = int(u)
    ts_i = int(ts)

    if abs(int(time.time()) - ts_i) > 24 * 3600:
        raise HTTPException(status_code=403, detail="link expirou")

    if not _verify_owner_sig(owner_id, ts_i, sig):
        raise HTTPException(status_code=403, detail="assinatura inválida")

    import database as db

    coins = _get_coins(db, owner_id)
    giros = _get_giros(db, owner_id)
    collection_name = _get_collection_name_safe(db, owner_id)
    cards = _list_collection_cards_safe(db, owner_id, limit=COLLECTION_LIMIT)
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
# API: Loja
# =========================
@app.get("/api/shop/state")
def api_shop_state(x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    import database as db
    _ensure_user(db, user_id, first_name)

    coins = _get_coins(db, user_id)
    giros = _get_giros(db, user_id)
    fav_name = _get_fav_name(db, user_id)

    return JSONResponse(
        {"ok": True, "user_id": user_id, "coins": coins, "giros": giros, "fav_name": fav_name,
         "sell_gain": SHOP_SELL_GAIN, "giro_price": SHOP_GIRO_PRICE, "per_page": SHOP_PER_PAGE}
    )


@app.get("/api/shop/sell/list")
def api_sell_list(page: int = 1, q: str = "", x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    import database as db
    _ensure_user(db, user_id, first_name)

    fav_name = _get_fav_name(db, user_id)
    fav_norm = fav_name.strip().casefold()
    qn = (q or "").strip().casefold()

    page = max(1, _safe_int(page, 1))
    per_page = max(1, min(30, SHOP_PER_PAGE))

    itens, total, total_pages = _get_sell_page(db, user_id, page, per_page)

    out = []
    for r in itens:
        if not isinstance(r, dict):
            continue

        char_id = _safe_int(r.get("character_id") or r.get("id") or r.get("char_id") or 0, 0)
        name = _safe_str(r.get("character_name") or r.get("name") or r.get("char_name") or "Personagem")
        anime = _safe_str(r.get("anime_title") or r.get("anime") or r.get("title") or "")
        qty = max(1, _safe_int(r.get("quantity") or r.get("qty") or 1, 1))

        custom_image = _safe_str(r.get("custom_image"))
        image = custom_image or _safe_str(r.get("image"))

        is_custom = bool(custom_image)
        is_fav = bool(fav_norm) and (name.strip().casefold() == fav_norm)

        if qn:
            if qn not in name.casefold() and qn not in anime.casefold() and qn not in str(char_id):
                continue

        out.append(
            {
                "character_id": char_id,
                "character_name": name,
                "anime_title": anime,
                "quantity": qty,
                "image": image,
                "custom_image": custom_image,
                "is_custom": is_custom,
                "is_favorite": is_fav,
            }
        )

    return JSONResponse(
        {
            "ok": True,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "items": out,
            "sell_gain": SHOP_SELL_GAIN,
        }
    )


@app.post("/api/shop/sell/confirm")
def api_sell_confirm(payload_body: dict = Body(default={}), x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    import database as db
    _ensure_user(db, user_id, first_name)

    char_id = _safe_int(payload_body.get("character_id"), 0)
    if char_id <= 0:
        raise HTTPException(status_code=400, detail="character_id inválido")

    item = _get_character_full(db, user_id, char_id)
    if not item:
        return JSONResponse({"ok": False, "error": "Você não tem esse personagem."}, status_code=200)

    ok_remove = _remove_one(db, user_id, char_id)
    if not ok_remove:
        return JSONResponse({"ok": False, "error": "Não consegui vender agora. Tente novamente."}, status_code=200)

    _add_coin(db, user_id, SHOP_SELL_GAIN)

    coins = _get_coins(db, user_id)
    giros = _get_giros(db, user_id)
    sold_name = _safe_str(item.get("character_name") or item.get("name") or "Personagem")

    return JSONResponse(
        {
            "ok": True,
            "sold": {"character_id": char_id, "character_name": sold_name},
            "coins": coins,
            "giros": giros,
            "sell_gain": SHOP_SELL_GAIN,
        }
    )


@app.post("/api/shop/buy/giro")
def api_buy_giro(x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    import database as db
    _ensure_user(db, user_id, first_name)

    ok_buy = _buy_giro(db, user_id, SHOP_GIRO_PRICE)
    if not ok_buy:
        return JSONResponse({"ok": False, "error": "Você não tem coins suficientes."}, status_code=200)

    coins = _get_coins(db, user_id)
    giros = _get_giros(db, user_id)

    return JSONResponse({"ok": True, "coins": coins, "giros": giros, "price": SHOP_GIRO_PRICE})


# =========================
# UI: Coleção (/app)
# =========================
@app.get("/app", response_class=HTMLResponse)
def miniapp_collection():
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1, viewport-fit=cover">
  <title>Coleção</title>
  <style>
    :root{
      --bg:#0b0b0f; --card:#151522; --muted: rgba(255,255,255,.65);
      --muted2: rgba(255,255,255,.45); --stroke: rgba(255,255,255,.12);
      --accent:#ff4fd8; --accent2:#7c4dff; --heart:#ff3b7a; --section: rgba(255,255,255,.06);
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:#fff;padding:12px 12px 88px;}
    .top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:4px;}
    .title{display:flex;flex-direction:column;gap:2px;min-width:0;}
    .title h1{margin:0;font-size:18px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .title .sub{font-size:12px;color:var(--muted2);}
    .stats{display:flex;align-items:center;gap:8px;padding:10px 12px;border:1px solid var(--stroke);background:rgba(255,255,255,.04);border-radius:999px;white-space:nowrap;flex-shrink:0;}
    .stat{display:flex;align-items:center;gap:6px;font-weight:900;font-size:13px;}
    .dot{width:1px;height:16px;background:var(--stroke);}
    .tabs{display:flex;gap:10px;margin:14px 0 10px;padding:8px;border:1px solid var(--stroke);border-radius:999px;background:rgba(255,255,255,.04);}
    .tab{flex:1;text-align:center;padding:10px 12px;border-radius:999px;font-weight:900;font-size:14px;color:var(--muted);background:transparent;border:0;}
    .tab.active{color:#fff;background:linear-gradient(90deg, rgba(255,79,216,.9), rgba(124,77,255,.9));box-shadow:0 10px 30px rgba(255,79,216,.15);}
    .search{display:flex;gap:10px;align-items:center;margin:8px 0 14px;}
    .search input{width:100%;padding:12px 12px;border-radius:14px;border:1px solid var(--stroke);background:rgba(255,255,255,.04);color:#fff;outline:none;font-size:14px;}
    .search input::placeholder{color:rgba(255,255,255,.35)}
    .status{margin:10px 0;padding:10px 12px;border-radius:14px;border:1px solid var(--stroke);background:rgba(255,255,255,.03);color:var(--muted);font-size:13px;white-space:pre-wrap;}
    .status.ok{border-color: rgba(0,255,140,.18);}
    .status.err{border-color: rgba(255,60,60,.18);color: rgba(255,120,120,.95);}
    .section{margin-top:12px;padding:10px 10px 6px;border-radius:16px;border:1px solid var(--stroke);background:var(--section);}
    .section-title{font-weight:900;font-size:14px;color:rgba(255,255,255,.92);margin:2px 4px 10px;display:flex;align-items:center;justify-content:space-between;gap:8px;}
    .section-count{font-size:12px;color:rgba(255,255,255,.55);font-weight:800;}
    .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}
    .card{position:relative;border-radius:20px;overflow:hidden;border:1px solid var(--stroke);background:var(--card);min-height:220px;}
    .card img{width:100%;height:220px;object-fit:cover;display:block;}
    .overlay{position:absolute;left:0;right:0;bottom:0;padding:10px;background:linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.78));}
    .name{font-weight:900;font-size:16px;margin:0;}
    .meta{margin-top:3px;font-size:12px;color:rgba(255,255,255,.75);}
    .pill{position:absolute;top:10px;left:10px;padding:6px 10px;background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.14);border-radius:999px;font-weight:900;font-size:12px;}
    .heart{position:absolute;top:10px;right:10px;width:34px;height:34px;border-radius:999px;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.14);font-size:16px;color:var(--heart);}
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
      return pickFirstString(c, ["character_name","name","character","personagem","nome","char_name","card_name"]) || "Personagem";
    }
    function getAnimeTitle(c){
      return pickFirstString(c, ["anime_title","anime","anime_name","obra","title","series","serie"]) || "Sem anime";
    }
    function getImageUrl(c){
      return pickFirstString(c, ["custom_image","image","img","photo","picture","url"]) || "";
    }
    function getCharId(c){
      return pickFirstNumber(c, ["character_id","char_id","id","card_id","personagem_id"]) ?? 0;
    }
    function getQty(c){
      return pickFirstNumber(c, ["quantity","qty","qtd","amount","count"]) ?? 1;
    }
    function isFavorite(c){
      const v = c?.is_favorite ?? c?.favorite ?? c?.fav;
      return v === true || v === 1 || v === "1" || v === "true";
    }

    function cmpAZ(a, b){
      return String(a).localeCompare(String(b), "pt-BR", { sensitivity: "base" });
    }

    function buildGroups(list){
      const groups = new Map();
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
        header.innerHTML = `<div>${g.title}</div><div class="section-count">${g.cards.length}</div>`;
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
            ${img ? `<img src="${img}" alt="">`
                 : `<div style="height:220px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5)">Sem imagem</div>`}
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
        setStatus("Carregando...", "");
        const initData = tg?.initData || "";

        const params = new URLSearchParams(window.location.search);
        const u = params.get("u");
        const ts = params.get("ts");
        const sig = params.get("sig") || "";

        let apiUrl = "/api/me/collection";
        let viewingOwner = false;

        if (u && ts){
          apiUrl = `/api/collection?u=${encodeURIComponent(u)}&ts=${encodeURIComponent(ts)}&sig=${encodeURIComponent(sig)}`;
          viewingOwner = true;
        }

        const res = await fetch(apiUrl, { headers: { "X-Telegram-Init-Data": initData } });
        if (!res.ok){
          const txt = await res.text().catch(()=> "");
          setStatus("❌ Falha ao carregar.\n\nStatus: " + res.status + "\n" + txt, "err");
          document.getElementById("sub").textContent = "Erro: " + res.status;
          return;
        }

        const data = await res.json();

        if (viewingOwner && data.owner_name){
          document.getElementById("h1").textContent = "Coleção de " + data.owner_name;
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
        setStatus("❌ Erro inesperado.", "err");
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


# =========================
# UI: Loja (/shop)
# =========================
@app.get("/shop", response_class=HTMLResponse)
def miniapp_shop():
    # PASSA configs pro JS com JSON seguro
    cfg = json.dumps(
        {"sell_gain": SHOP_SELL_GAIN, "giro_price": SHOP_GIRO_PRICE, "per_page": SHOP_PER_PAGE},
        ensure_ascii=False,
    )

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1, viewport-fit=cover">
  <title>Loja</title>
  <style>
    :root{{
      --bg:#0b0b0f; --card:#151522; --muted: rgba(255,255,255,.65); --muted2: rgba(255,255,255,.45);
      --stroke: rgba(255,255,255,.12); --accent:#ff4fd8; --accent2:#7c4dff; --heart:#ff3b7a;
      --good: rgba(0,255,140,.18); --bad: rgba(255,60,60,.18);
    }}
    *{{box-sizing:border-box}}
    body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:#fff;padding:12px 12px 88px;}}
    .top{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:4px;}}
    .title{{display:flex;flex-direction:column;gap:2px;}}
    .title h1{{margin:0;font-size:18px;font-weight:900;}}
    .title .sub{{font-size:12px;color:var(--muted2);}}
    .stats{{display:flex;align-items:center;gap:8px;padding:10px 12px;border:1px solid var(--stroke);background:rgba(255,255,255,.04);border-radius:999px;white-space:nowrap;}}
    .stat{{display:flex;align-items:center;gap:6px;font-weight:900;font-size:13px;}}
    .dot{{width:1px;height:16px;background:var(--stroke);}}
    .tabs{{display:flex;gap:10px;margin:14px 0 10px;padding:8px;border:1px solid var(--stroke);border-radius:999px;background:rgba(255,255,255,.04);}}
    .tab{{flex:1;text-align:center;padding:10px 12px;border-radius:999px;font-weight:900;font-size:14px;color:var(--muted);background:transparent;border:0;}}
    .tab.active{{color:#fff;background:linear-gradient(90deg, rgba(255,79,216,.9), rgba(124,77,255,.9));box-shadow:0 10px 30px rgba(255,79,216,.15);}}
    .status{{margin:10px 0;padding:10px 12px;border-radius:14px;border:1px solid var(--stroke);background:rgba(255,255,255,.03);color:var(--muted);font-size:13px;white-space:pre-wrap;}}
    .status.ok{{border-color: var(--good);}}
    .status.err{{border-color: var(--bad);color: rgba(255,120,120,.95);}}
    .search{{display:flex;gap:10px;align-items:center;margin:8px 0 14px;}}
    .search input{{width:100%;padding:12px 12px;border-radius:14px;border:1px solid var(--stroke);background:rgba(255,255,255,.04);color:#fff;outline:none;font-size:14px;}}
    .search input::placeholder{{color:rgba(255,255,255,.35)}}
    .grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}}
    .card{{position:relative;border-radius:20px;overflow:hidden;border:1px solid var(--stroke);background:var(--card);min-height:220px;}}
    .card img{{width:100%;height:220px;object-fit:cover;display:block;}}
    .overlay{{position:absolute;left:0;right:0;bottom:0;padding:10px;background:linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.78));}}
    .name{{font-weight:900;font-size:15px;margin:0;}}
    .meta{{margin-top:3px;font-size:12px;color:rgba(255,255,255,.75);}}
    .pill{{position:absolute;top:10px;left:10px;padding:6px 10px;background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.14);border-radius:999px;font-weight:900;font-size:12px;}}
    .heart{{position:absolute;top:10px;right:10px;width:34px;height:34px;border-radius:999px;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.14);font-size:16px;color: var(--heart);}}
    .actions{{display:flex;gap:10px;margin-top:12px;}}
    .btn{{flex:1;padding:12px 12px;border-radius:14px;border:1px solid var(--stroke);background:rgba(255,255,255,.06);color:#fff;font-weight:900;font-size:14px;}}
    .btn.primary{{background:linear-gradient(90deg, rgba(255,79,216,.9), rgba(124,77,255,.9));border:0;}}
    .btn:disabled{{opacity:.5}}
    .pager{{display:flex;gap:10px;margin:14px 0 0;align-items:center;justify-content:space-between;}}
    .pager .pbtn{{padding:10px 12px;border-radius:14px;border:1px solid var(--stroke);background:rgba(255,255,255,.06);color:#fff;font-weight:900;min-width:70px;}}
    .pager .info{{color:rgba(255,255,255,.75);font-weight:900;}}
    .buyBox{{margin-top:10px;padding:12px;border-radius:16px;border:1px solid var(--stroke);background:rgba(255,255,255,.04);}}
    .buyBox h2{{margin:0 0 8px;font-size:16px;font-weight:900;}}
    .buyBox p{{margin:0;color:rgba(255,255,255,.75);font-size:13px;line-height:1.35;}}
  </style>
</head>
<body>
  <div class="top">
    <div class="title">
      <h1>🛒 Loja Baltigo</h1>
      <div class="sub" id="sub">Carregando...</div>
    </div>
    <div class="stats">
      <div class="stat">🪙 <span id="coins">-</span></div>
      <div class="dot"></div>
      <div class="stat">🎡 <span id="giros">-</span></div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" id="tab_sell">📦 Vender</button>
    <button class="tab" id="tab_buy">🎡 Comprar</button>
  </div>

  <div class="status" id="status">Conectando...</div>

  <div id="sellView">
    <div class="search">
      <input id="q" placeholder="Buscar personagem ou anime..." />
    </div>
    <div class="grid" id="grid"></div>

    <div class="pager">
      <button class="pbtn" id="prev">⬅️</button>
      <div class="info" id="pinfo">1/1</div>
      <button class="pbtn" id="next">➡️</button>
    </div>
  </div>

  <div id="buyView" style="display:none;">
    <div class="buyBox">
      <h2>🎡 Comprar GIRO</h2>
      <p id="buyText">Carregando...</p>
      <div class="actions">
        <button class="btn primary" id="buyBtn">Comprar</button>
      </div>
    </div>
  </div>

  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script>
    const CFG = {cfg};

    const tg = window.Telegram?.WebApp;
    if (tg) {{ tg.ready(); try {{ tg.expand(); }} catch(e) {{}} }}

    const statusEl = document.getElementById("status");
    function setStatus(text, type){{
      statusEl.className = "status" + (type ? (" " + type) : "");
      statusEl.textContent = text;
    }}

    function esc(s){{
      return String(s || "").replace(/[&<>"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
    }}

    let coins = 0;
    let giros = 0;
    let page = 1;
    let totalPages = 1;
    let items = [];
    let tab = "sell";

    let sellGain = Number(CFG.sell_gain || 1);
    let price = Number(CFG.giro_price || 2);

    async function apiGet(url){{
      const initData = tg?.initData || "";
      const res = await fetch(url, {{ headers: {{ "X-Telegram-Init-Data": initData }} }});
      const data = await res.json().catch(()=> ({{}}));
      return {{ ok: res.ok, res, data }};
    }}
    async function apiPost(url, body){{
      const initData = tg?.initData || "";
      const res = await fetch(url, {{
        method: "POST",
        headers: {{ "Content-Type":"application/json", "X-Telegram-Init-Data": initData }},
        body: JSON.stringify(body || {{}})
      }});
      const data = await res.json().catch(()=> ({{}}));
      return {{ ok: res.ok, res, data }};
    }}

    function updateStats(){{
      document.getElementById("coins").textContent = String(coins ?? "-");
      document.getElementById("giros").textContent = String(giros ?? "-");
      document.getElementById("sub").textContent = tab === "sell"
        ? "Venda 1 unidade e ganhe +" + sellGain + " coin"
        : "Compre GIRO por " + price + " coins";
    }}

    function renderGrid(){{
      const grid = document.getElementById("grid");
      grid.innerHTML = "";

      if (!items.length){{
        grid.innerHTML = "<div style='color:rgba(255,255,255,.65)'>Nada para mostrar.</div>";
        return;
      }}

      for (const c of items){{
        const img = c.custom_image || c.image || "";
        const qty = c.quantity || 1;

        const isFav = !!c.is_favorite;
        const isCustom = !!c.is_custom;

        const badgeLeft = `x${{qty}} • ID ${{c.character_id}}`;
        const badgeRight = (isFav ? "❤️" : (isCustom ? "📸" : ""));

        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `
          ${{img ? `<img src="${{esc(img)}}" alt="">`
                 : `<div style="height:220px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5)">Sem imagem</div>`}}
          <div class="pill">${{esc(badgeLeft)}}</div>
          ${{badgeRight ? `<div class="heart">${{esc(badgeRight)}}</div>` : ``}}
          <div class="overlay">
            <div class="name">${{esc(c.character_name || "Personagem")}}</div>
            <div class="meta">${{esc(c.anime_title || "")}}</div>
            <div class="actions">
              <button class="btn primary" data-sell="${{c.character_id}}">Vender (+${{sellGain}})</button>
            </div>
          </div>
        `;
        grid.appendChild(card);
      }}

      grid.querySelectorAll("button[data-sell]").forEach(btn=>{{
        btn.onclick = async () => {{
          const id = Number(btn.getAttribute("data-sell"));
          btn.disabled = true;
          try{{
            setStatus("Processando venda...", "");
            const r = await apiPost("/api/shop/sell/confirm", {{ character_id: id }});
            if (!r.ok) {{ setStatus("❌ Falha ao vender.", "err"); return; }}
            if (!r.data.ok) {{ setStatus("⚠️ " + (r.data.error || "Não consegui vender."), "err"); return; }}

            coins = r.data.coins ?? coins;
            giros = r.data.giros ?? giros;

            updateStats();
            setStatus("✅ Venda concluída!", "ok");
            await loadSell();
          }} finally {{
            btn.disabled = false;
          }}
        }};
      }});
    }}

    async function loadState(){{
      setStatus("Carregando...", "");
      const r = await apiGet("/api/shop/state");
      if (!r.ok){{ setStatus("❌ Falha ao conectar.", "err"); return false; }}

      coins = r.data.coins ?? 0;
      giros = r.data.giros ?? 0;

      sellGain = Number(r.data.sell_gain ?? sellGain);
      price = Number(r.data.giro_price ?? price);

      updateStats();
      return true;
    }}

    async function loadSell(){{
      const q = (document.getElementById("q").value || "").trim();
      const r = await apiGet("/api/shop/sell/list?page=" + page + "&q=" + encodeURIComponent(q));
      if (!r.ok){{ setStatus("❌ Falha ao carregar lista.", "err"); return; }}
      if (!r.data.ok){{ setStatus("⚠️ Erro ao carregar.", "err"); return; }}

      items = Array.isArray(r.data.items) ? r.data.items : [];
      totalPages = Number(r.data.total_pages ?? 1);
      sellGain = Number(r.data.sell_gain ?? sellGain);

      document.getElementById("pinfo").textContent = page + "/" + totalPages;
      document.getElementById("prev").disabled = page <= 1;
      document.getElementById("next").disabled = page >= totalPages;

      updateStats();
      setStatus("✅ Pronto.", "ok");
      renderGrid();
    }}

    async function loadBuy(){{
      document.getElementById("buyText").textContent = "Troque " + price + " coins por +1 giro.";
      updateStats();
    }}

    document.getElementById("tab_sell").onclick = async () => {{
      tab = "sell";
      document.getElementById("tab_sell").classList.add("active");
      document.getElementById("tab_buy").classList.remove("active");
      document.getElementById("sellView").style.display = "";
      document.getElementById("buyView").style.display = "none";
      setStatus("Carregando...", "");
      await loadSell();
    }};

    document.getElementById("tab_buy").onclick = async () => {{
      tab = "buy";
      document.getElementById("tab_buy").classList.add("active");
      document.getElementById("tab_sell").classList.remove("active");
      document.getElementById("sellView").style.display = "none";
      document.getElementById("buyView").style.display = "";
      await loadBuy();
      setStatus("✅ Pronto.", "ok");
    }};

    document.getElementById("q").addEventListener("input", async () => {{
      page = 1;
      await loadSell();
    }});
    document.getElementById("prev").onclick = async () => {{
      page = Math.max(1, page - 1);
      await loadSell();
    }};
    document.getElementById("next").onclick = async () => {{
      page = Math.min(totalPages, page + 1);
      await loadSell();
    }};

    document.getElementById("buyBtn").onclick = async () => {{
      const btn = document.getElementById("buyBtn");
      btn.disabled = true;
      try{{
        setStatus("Processando compra...", "");
        const r = await apiPost("/api/shop/buy/giro", {{}});
        if (!r.ok){{ setStatus("❌ Falha ao comprar.", "err"); return; }}
        if (!r.data.ok){{ setStatus("⚠️ " + (r.data.error || "Você não tem coins suficientes."), "err"); return; }}

        coins = r.data.coins ?? coins;
        giros = r.data.giros ?? giros;
        updateStats();
        setStatus("✅ GIRO comprado!", "ok");
      }} finally {{
        btn.disabled = false;
      }}
    }};

    (async () => {{
      const ok = await loadState();
      if (!ok) return;
      await loadSell();
      await loadBuy();
    }})();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)

# ==========================================================
# BALTIGO ENGINE WEB EXTENSIONS
# ==========================================================
@app.get("/api/engine/stats")
def api_engine_stats():
    return {
        "status": "ok",
        "engine": "Baltigo",
        "message": "Engine running"
    }
