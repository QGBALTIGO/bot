# webapp.py — MiniApps (Coleção + Dado + Loja) — FastAPI
# - valida initData (Telegram WebApp) corretamente
# - /app: coleção + favoritos + DADO (tudo no mesmo MiniApp)
# - /shop: loja (MiniApp separado) (continua existindo)
# - Dado: 3D + lootbox reveal + grid com capas + busca/filtro + recomendado
# - Dado: MAIN/SUPPORTING only (no backend), auto-reroll silencioso, cache por anime, blacklist persistida (best-effort)
# - setfoto: usa custom_image primeiro; se não tiver, usa AniList; se não tiver, fallback

import os
import json
import time
import hmac
import hashlib
import random
import asyncio
import aiohttp
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
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

# AniList
ANILIST_API = os.getenv("ANILIST_API", "https://graphql.anilist.co").strip()

# Dado MiniApp
DADO_NEW_USER_START = int(os.getenv("DADO_NEW_USER_START", "4"))
DADO_WEB_EXPIRE_SECONDS = int(os.getenv("DADO_WEB_EXPIRE_SECONDS", "300"))
DADO_WEB_MAX_OPTIONS = int(os.getenv("DADO_WEB_MAX_OPTIONS", "36"))  # quantas opções no grid (máx 36)
DADO_PICK_IMAGE = os.getenv(
    "DADO_PICK_IMAGE",
    "https://photo.chelpbot.me/AgACAgEAAxkBZqAk02mfJAxu6F0SV9i2MqA5qQ6fDy3PAAKhC2sbjP74RFhnKn29pt05AQADAgADeQADOgQ/photo.jpg",
).strip()
DADO_FALLBACK_IMAGE = os.getenv(
    "DADO_FALLBACK_IMAGE",
    "https://photo.chelpbot.me/AgACAgEAAxkBZqnFu2mfsGZK0p1QU7Az5i2pp9C07ahKAALQC2sbS__4RF78U7yIQqiiAQADAgADeQADOgQ/photo.jpg",
).strip()

# Anti-abuso simples (web)
WEB_RATE_LIMIT_SECONDS = float(os.getenv("WEB_RATE_LIMIT_SECONDS", "0.5"))
_WEB_RATE: Dict[Tuple[int, str], float] = {}


def _rate_limit(user_id: int, key: str) -> bool:
    now = time.time()
    k = (int(user_id), str(key))
    last = _WEB_RATE.get(k, 0.0)
    if now - last < WEB_RATE_LIMIT_SECONDS:
        return False
    _WEB_RATE[k] = now
    return True


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
# DB safe wrappers
# =========================
def _ensure_user(db, user_id: int, first_name: str):
    try:
        fn = getattr(db, "ensure_user_row", None)
        if callable(fn):
            try:
                fn(user_id, first_name, new_user_dice=DADO_NEW_USER_START)
            except TypeError:
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
    try:
        fn = getattr(db, "get_user_coins", None)
        if callable(fn):
            return _safe_int(fn(user_id), 0)
    except Exception:
        pass
    row = _get_user_row(db, user_id)
    return _safe_int(row.get("coins"), 0)


def _get_giros(db, user_id: int) -> int:
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
# Telegram send (PV)
# =========================
async def _tg_send_photo(chat_id: int, photo: str, caption: str):
    # envio best-effort
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": int(chat_id),
        "photo": photo,
        "caption": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        try:
            async with s.post(url, data=payload) as r:
                await r.text()
        except Exception:
            pass


# =========================
# DADO backend helpers (compatíveis com database.py via getattr)
# =========================
DADO_MAX_BALANCE = int(os.getenv("DADO_MAX_BALANCE", "18"))
GIRO_MAX_BALANCE = int(os.getenv("GIRO_MAX_BALANCE", "24"))


def _now_slot_4h(ts: Optional[float] = None) -> int:
    if ts is None:
        ts = time.time()
    return int(int(ts) // (4 * 3600))


def _now_giro_slot_3h(ts: Optional[float] = None) -> int:
    # 8 slots/dia (aprox a cada 3h) sem timezone (web), estável o suficiente
    if ts is None:
        ts = time.time()
    return int(int(ts) // (3 * 3600))


def _get_dado_state(db, user_id: int) -> dict:
    fn = getattr(db, "get_dado_state", None)
    if callable(fn):
        st = fn(user_id)
        if isinstance(st, dict):
            return st
    return {"b": 0, "s": -1}


def _set_dado_state(db, user_id: int, balance: int, slot: int):
    fn = getattr(db, "set_dado_state", None)
    if callable(fn):
        fn(user_id, int(balance), int(slot))


def _get_extra_state(db, user_id: int) -> dict:
    fn = getattr(db, "get_extra_state", None)
    if callable(fn):
        st = fn(user_id)
        if isinstance(st, dict):
            return st
    return {"x": 0, "s": -1}


def _set_extra_state(db, user_id: int, extra: int, slot: int):
    fn = getattr(db, "set_extra_state", None)
    if callable(fn):
        fn(user_id, int(extra), int(slot))


def _inc_dado_balance(db, user_id: int, amount: int, max_balance: int):
    fn = getattr(db, "inc_dado_balance", None)
    if callable(fn):
        fn(user_id, int(amount), max_balance=int(max_balance))


def _consume_extra_dado(db, user_id: int) -> bool:
    fn = getattr(db, "consume_extra_dado", None)
    if callable(fn):
        return bool(fn(user_id))
    return False


def _refresh_user_dado_balance(db, user_id: int) -> int:
    st = _get_dado_state(db, user_id)
    balance = _safe_int(st.get("b"), 0)
    last_slot = _safe_int(st.get("s"), -1)
    cur_slot = _now_slot_4h()

    if last_slot < 0:
        _set_dado_state(db, user_id, balance, cur_slot)
        return balance

    diff = cur_slot - last_slot
    if diff <= 0:
        return balance

    new_balance = min(DADO_MAX_BALANCE, balance + diff)
    _set_dado_state(db, user_id, new_balance, cur_slot)
    return new_balance


def _refresh_user_giros(db, user_id: int) -> int:
    st = _get_extra_state(db, user_id)
    extra = _safe_int(st.get("x"), 0)
    last_slot = _safe_int(st.get("s"), -1)
    cur_slot = _now_giro_slot_3h()

    if last_slot < 0:
        _set_extra_state(db, user_id, extra, cur_slot)
        return extra

    diff = cur_slot - last_slot
    if diff <= 0:
        return extra

    new_extra = min(GIRO_MAX_BALANCE, extra + diff)
    _set_extra_state(db, user_id, new_extra, cur_slot)
    return new_extra


def _consume_one_die(db, user_id: int) -> bool:
    st = _get_dado_state(db, user_id)
    b = _safe_int(st.get("b"), 0)
    s = _safe_int(st.get("s"), -1)
    if b > 0:
        _set_dado_state(db, user_id, b - 1, s)
        return True
    return _consume_extra_dado(db, user_id)


def _refund_one_die(db, user_id: int):
    # devolve no saldo normal (simples)
    _inc_dado_balance(db, user_id, 1, max_balance=DADO_MAX_BALANCE)


# -------------------------
# Cache / blacklist (best-effort)
# -------------------------
_CHAR_POOL_CACHE: Dict[int, dict] = {}  # anime_id -> {"exp":ts, "title":..., "cover":..., "chars":[...]}
_POOL_LOCKS: Dict[int, asyncio.Lock] = {}
_REFRESH_LOCK = asyncio.Lock()


def _get_pool_lock(anime_id: int) -> asyncio.Lock:
    lk = _POOL_LOCKS.get(int(anime_id))
    if lk is None:
        lk = asyncio.Lock()
        _POOL_LOCKS[int(anime_id)] = lk
    return lk


def _db_is_anime_blacklisted(db, anime_id: int) -> bool:
    fn = getattr(db, "is_dado_anime_blacklisted", None)
    if callable(fn):
        try:
            return bool(fn(int(anime_id)))
        except Exception:
            return False
    return False


def _db_blacklist_anime(db, anime_id: int, reason: str = "no_chars"):
    fn = getattr(db, "blacklist_dado_anime", None)
    if callable(fn):
        try:
            fn(int(anime_id), str(reason))
        except Exception:
            pass


async def _fetch_top500_anime_from_anilist() -> list[dict]:
    query = """
    query ($page: Int) {
      Page(page: $page, perPage: 50) {
        media(type: ANIME, sort: POPULARITY_DESC) {
          id
          title { romaji }
        }
      }
    }
    """
    items: list[dict] = []
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        rank = 1
        for page in range(1, 11):
            async with session.post(ANILIST_API, json={"query": query, "variables": {"page": page}}) as resp:
                data = await resp.json()
            media = data.get("data", {}).get("Page", {}).get("media", []) or []
            for m in media:
                anime_id = m.get("id")
                title = (m.get("title") or {}).get("romaji") or "Anime"
                if anime_id is None:
                    continue
                items.append({"anime_id": int(anime_id), "title": title, "rank": rank})
                rank += 1
    return items[:500]


async def _ensure_top_cache_fresh(db):
    async with _REFRESH_LOCK:
        last = 0
        try:
            fn = getattr(db, "top_cache_last_updated", None)
            if callable(fn):
                last = int(fn() or 0)
        except Exception:
            last = 0

        now = int(time.time())
        if last and now - last < 24 * 3600:
            return

        items = await _fetch_top500_anime_from_anilist()
        if not items:
            return
        try:
            fn = getattr(db, "replace_top_anime_cache", None)
            if callable(fn):
                fn(items, updated_at=now)
        except Exception:
            pass


def _pick_random_animes(db, n: int) -> list[dict]:
    try:
        fn = getattr(db, "get_top_anime_list", None)
        all_items = fn(500) if callable(fn) else []
    except Exception:
        all_items = []

    all_items = all_items or []
    if not all_items:
        return []

    n = max(1, min(n, len(all_items)))
    chosen = random.sample(all_items, n)
    # opcional: trazer capa no frontend depois (grid)
    return [{"id": int(x["anime_id"]), "title": x.get("title") or "Anime"} for x in chosen]


async def _build_char_pool_for_anime(anime_id: int, max_pages: int = 4) -> Optional[dict]:
    """
    Pool MAIN/SUPPORTING only.
    Se personagem não tiver foto, usa coverImage do anime.
    """
    q = """
    query ($id: Int, $page: Int) {
      Media(id: $id, type: ANIME) {
        title { romaji }
        coverImage { large }
        characters(page: $page, perPage: 25) {
          pageInfo { currentPage lastPage }
          edges {
            role
            node {
              id
              name { full }
              image { large }
            }
          }
        }
      }
    }
    """
    timeout = aiohttp.ClientTimeout(total=20)

    chars: list[dict] = []
    anime_title = "Obra"
    cover = None

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(ANILIST_API, json={"query": q, "variables": {"id": int(anime_id), "page": 1}}) as resp:
            data = await resp.json()

        media = data.get("data", {}).get("Media")
        if not media:
            return None

        anime_title = (media.get("title") or {}).get("romaji") or "Obra"
        cover = (media.get("coverImage") or {}).get("large") or None
        last_page = int(((media.get("characters") or {}).get("pageInfo") or {}).get("lastPage") or 1)

        pages = {1}
        for _ in range(max_pages - 1):
            pages.add(random.randint(1, max(1, last_page)))

        for page in pages:
            async with session.post(ANILIST_API, json={"query": q, "variables": {"id": int(anime_id), "page": int(page)}}) as r2:
                d2 = await r2.json()
            m2 = d2.get("data", {}).get("Media")
            if not m2:
                continue
            edges = (((m2.get("characters") or {}).get("edges")) or [])
            for e in edges:
                role = (e.get("role") or "").upper()
                if role not in ("MAIN", "SUPPORTING"):
                    continue
                node = (e.get("node") or {})
                cid = node.get("id")
                name = ((node.get("name") or {}).get("full")) or None
                img = ((node.get("image") or {}).get("large")) or None
                if cid and name:
                    chars.append({"id": int(cid), "name": name, "image": img})

    seen = set()
    uniq = []
    for c in chars:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        uniq.append(c)

    return {"title": anime_title, "cover": cover, "chars": uniq}


async def _get_random_character_from_anime(db, anime_id: int, tries: int = 14) -> Optional[dict]:
    """
    Cache por anime + fallback cover se sem foto.
    Nunca retorna None se conseguir montar pool com chars.
    """
    now = int(time.time())

    # blacklist persistida (best-effort)
    if _db_is_anime_blacklisted(db, anime_id):
        return None

    lk = _get_pool_lock(anime_id)
    async with lk:
        cached = _CHAR_POOL_CACHE.get(int(anime_id))
        if not cached or int(cached.get("exp") or 0) < now:
            built = await _build_char_pool_for_anime(int(anime_id), max_pages=4)
            if not built or not (built.get("chars") or []):
                _db_blacklist_anime(db, anime_id, "no_chars_main_supporting")
                return None
            cached = {
                "exp": now + 6 * 3600,
                "title": built["title"],
                "cover": built["cover"],
                "chars": built["chars"],
            }
            _CHAR_POOL_CACHE[int(anime_id)] = cached

    chars = list((_CHAR_POOL_CACHE.get(int(anime_id)) or {}).get("chars") or [])
    if not chars:
        _db_blacklist_anime(db, anime_id, "no_chars_cached")
        return None

    # auto-reroll silencioso: tenta vários antes de desistir
    random.shuffle(chars)
    pick_list = chars[: max(1, min(len(chars), tries))]

    for c in pick_list:
        img = c.get("image")
        if img:
            return {
                "id": int(c["id"]),
                "name": c["name"],
                "image": img,
                "anime_title": (_CHAR_POOL_CACHE[int(anime_id)].get("title") or "Obra"),
                "anime_cover": (_CHAR_POOL_CACHE[int(anime_id)].get("cover") or ""),
            }

    # sem foto em todos: usa cover do anime (não falha)
    cover = (_CHAR_POOL_CACHE[int(anime_id)].get("cover") or "") or DADO_FALLBACK_IMAGE
    c = pick_list[0]
    return {
        "id": int(c["id"]),
        "name": c["name"],
        "image": cover,
        "anime_title": (_CHAR_POOL_CACHE[int(anime_id)].get("title") or "Obra"),
        "anime_cover": (_CHAR_POOL_CACHE[int(anime_id)].get("cover") or ""),
    }


async def _auto_reroll_character(db, options: list[dict], preferred_anime_id: int, user_id: int) -> Optional[dict]:
    """
    Solução definitiva:
    - tenta o anime clicado
    - se falhar, tenta outros da lista (silencioso)
    - se todos falharem, tenta “reserva”: mais animes aleatórios do top cache (silencioso)
    - só retorna None se realmente não existir personagem MAIN/SUPPORTING em nada (muito raro)
    """
    # tenta o preferido
    order: list[int] = []
    try:
        order.append(int(preferred_anime_id))
    except Exception:
        pass

    for o in options or []:
        try:
            aid = int(o.get("id"))
            if aid not in order:
                order.append(aid)
        except Exception:
            continue

    # tenta até 20 da própria lista
    for aid in order[:20]:
        info = await _get_random_character_from_anime(db, aid, tries=14)
        if info:
            return info

    # reserva: tenta 18 aleatórios extras
    extra_pool = _pick_random_animes(db, 18)
    for o in extra_pool:
        aid = int(o["id"])
        info = await _get_random_character_from_anime(db, aid, tries=14)
        if info:
            return info

    return None


# =========================
# APP
# =========================
app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse("✅ Web rodando! Use /app (coleção+dado) ou /shop (loja).")


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
        {
            "ok": True,
            "user_id": user_id,
            "coins": coins,
            "giros": giros,
            "fav_name": fav_name,
            "sell_gain": SHOP_SELL_GAIN,
            "giro_price": SHOP_GIRO_PRICE,
            "per_page": SHOP_PER_PAGE,
        }
    )


@app.get("/api/shop/sell/list")
def api_sell_list(page: int = 1, q: str = "", x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    if not _rate_limit(user_id, "shop_list"):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)

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
# API: DADO (MiniApp)
# =========================
@app.post("/api/dado/start")
async def api_dado_start(x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    if not _rate_limit(user_id, "dado_start"):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)

    import database as db
    _ensure_user(db, user_id, first_name)

    balance = _refresh_user_dado_balance(db, user_id)
    extra = _refresh_user_giros(db, user_id)
    if balance <= 0 and extra <= 0:
        return JSONResponse(
            {"ok": False, "error": "no_balance", "msg": "Você está sem dados/giros agora.", "now": datetime.utcnow().strftime("%H:%M")},
            status_code=200,
        )

    if not _consume_one_die(db, user_id):
        return JSONResponse({"ok": False, "error": "consume_failed"}, status_code=200)

    # garante top cache (best-effort)
    try:
        await _ensure_top_cache_fresh(db)
    except Exception:
        pass

    dice_value = random.SystemRandom().randint(1, 6)

    # mais opções pra grid (ex: 1->6, 6->36)
    n = max(6, min(int(dice_value) * 6, DADO_WEB_MAX_OPTIONS))
    options = _pick_random_animes(db, n)
    if not options:
        _refund_one_die(db, user_id)
        return JSONResponse({"ok": False, "error": "no_anime_cache"}, status_code=200)

    # cria roll
    try:
        fn = getattr(db, "create_dice_roll", None)
        if callable(fn):
            try:
                roll_id = fn(user_id, int(dice_value), json.dumps(options, ensure_ascii=False), "pending", int(time.time()))
            except TypeError:
                roll_id = fn(user_id, int(dice_value), json.dumps(options, ensure_ascii=False))
        else:
            _refund_one_die(db, user_id)
            return JSONResponse({"ok": False, "error": "db_missing_roll"}, status_code=200)
    except Exception:
        _refund_one_die(db, user_id)
        return JSONResponse({"ok": False, "error": "roll_create_failed"}, status_code=200)

    balance2 = _refresh_user_dado_balance(db, user_id)
    extra2 = _refresh_user_giros(db, user_id)

    return JSONResponse(
        {"ok": True, "roll_id": int(roll_id), "dice": int(dice_value), "options": options, "balance": int(balance2), "extra": int(extra2)},
        status_code=200,
    )


@app.post("/api/dado/pick")
async def api_dado_pick(
    anime_id: int = Query(...),
    roll_id: int = Query(...),
    x_telegram_init_data: str = Header(default=""),
):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])

    if not _rate_limit(user_id, "dado_pick"):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)

    import database as db

    fn_get = getattr(db, "get_dice_roll", None)
    if not callable(fn_get):
        raise HTTPException(status_code=500, detail="Função get_dice_roll não existe no database.py")

    roll = fn_get(int(roll_id))
    if not roll or int(roll.get("user_id") or 0) != int(user_id):
        raise HTTPException(status_code=404, detail="roll inválido")

    status = str(roll.get("status") or "")
    created_at = int(roll.get("created_at") or 0)

    if status not in ("pending", "processing"):
        return JSONResponse({"ok": False, "error": "used"}, status_code=200)

    if created_at and int(time.time()) - created_at > DADO_WEB_EXPIRE_SECONDS:
        try:
            fn = getattr(db, "set_dice_roll_status", None)
            if callable(fn):
                fn(int(roll_id), "expired")
        except Exception:
            pass
        _refund_one_die(db, user_id)
        return JSONResponse({"ok": False, "error": "expired"}, status_code=200)

    # lock no DB (best-effort)
    if status == "pending":
        try:
            fn = getattr(db, "try_set_dice_roll_status", None)
            if callable(fn):
                locked = bool(fn(int(roll_id), expected="pending", new_status="processing"))
                if not locked:
                    return JSONResponse({"ok": False, "error": "race"}, status_code=200)
        except Exception:
            pass

    try:
        options = json.loads(roll.get("options_json") or "[]")
    except Exception:
        options = []

    info = await _auto_reroll_character(db, options, preferred_anime_id=int(anime_id), user_id=user_id)
    if not info:
        _refund_one_die(db, user_id)
        try:
            fn = getattr(db, "set_dice_roll_status", None)
            if callable(fn):
                fn(int(roll_id), "failed_soft")
        except Exception:
            pass
        return JSONResponse({"ok": False, "error": "no_char"}, status_code=200)

    # resolved
    try:
        fn = getattr(db, "set_dice_roll_status", None)
        if callable(fn):
            fn(int(roll_id), "resolved")
    except Exception:
        pass

    char_id = int(info["id"])
    name = info["name"]
    anime_title = info.get("anime_title") or "Obra"

    # prioridade: custom_image global (setfoto) -> anilist -> fallback
    img = ""
    try:
        fn = getattr(db, "get_character_custom_image", None)
        if callable(fn):
            img = fn(char_id) or ""
    except Exception:
        img = ""
    image = img or (info.get("image") or "") or DADO_FALLBACK_IMAGE

    # permite repetir (sem coin por repetido)
    try:
        fn_add = getattr(db, "add_character_to_collection", None)
        if callable(fn_add):
            try:
                fn_add(user_id, char_id, name, image, anime_title=anime_title)
            except TypeError:
                fn_add(user_id, char_id, name, image)
    except Exception:
        pass

    # entrega no PV do bot (best-effort)
    await _tg_send_photo(
        chat_id=user_id,
        photo=image,
        caption=(
            "🎁 <b>VOCÊ GANHOU!</b>\n\n"
            f"🧧 <code>{char_id}</code>. <b>{name}</b>\n"
            f"<i>{anime_title}</i>\n\n"
            "📦 <b>Adicionado à sua coleção!</b>"
        ),
    )

    return JSONResponse({"ok": True, "character": {"id": char_id, "name": name, "anime": anime_title, "image": image}}, status_code=200)


# =========================
# UI: Coleção + Dado (/app)
# =========================
@app.get("/app", response_class=HTMLResponse)
def miniapp_collection():
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1, viewport-fit=cover">
  <title>Baltigo MiniApp</title>
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

    /* ===== DADO PREMIUM UI ===== */
    .dado-card { padding: 14px; border: 1px solid var(--stroke); background: rgba(255,255,255,.04); border-radius: 18px; }
    .dado-header { display:flex; align-items:center; justify-content:space-between; gap:10px; }
    .dado-title { font-weight: 900; font-size: 16px; }
    .dado-sub { color: rgba(255,255,255,.65); font-size: 12px; margin-top: 2px; }
    .dado-pill { font-weight: 900; font-size: 12px; border: 1px solid var(--stroke); padding: 8px 10px; border-radius: 999px; background: rgba(255,255,255,.03); white-space: nowrap; }
    .dado-actions { margin-top: 14px; display:flex; gap:12px; align-items:center; }
    .dado-btn { flex: 1; border: 0; border-radius: 16px; padding: 14px 14px; font-weight: 900; font-size: 14px; color: #000; background: linear-gradient(90deg, var(--accent), var(--accent2)); }
    .dado-btn.secondary { flex: 0; padding: 14px 14px; color: #fff; border: 1px solid rgba(255,255,255,.14); background: rgba(255,255,255,.04); }
    .dado-controls { margin-top: 10px; display:flex; gap:10px; align-items:center; }
    .dado-input, .dado-select { width: 100%; border-radius: 14px; border: 1px solid rgba(255,255,255,.14); background: rgba(255,255,255,.04); color: #fff; padding: 12px 12px; outline: none; font-weight: 700; }
    .dado-tip { margin-top: 10px; color: rgba(255,255,255,.65); font-size: 12px; }

    .anime-grid { margin-top: 12px; display:grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    @media (min-width: 520px){ .anime-grid { grid-template-columns: repeat(3, 1fr); } }
    .anime-card { text-align:left; border: 1px solid rgba(255,255,255,.14); background: rgba(255,255,255,.04); color: #fff; border-radius: 16px; padding: 10px; cursor:pointer; transition: transform .12s ease, background .12s ease; }
    .anime-card:active { transform: scale(.98); }
    .anime-cover { width:100%; aspect-ratio: 16/9; border-radius: 12px; object-fit: cover; border: 1px solid rgba(255,255,255,.10); background: radial-gradient(circle at 20% 20%, rgba(255,255,255,.10), rgba(255,255,255,.02)); }
    .anime-title { margin-top: 8px; font-weight: 900; font-size: 12px; line-height: 1.2; max-height: 2.4em; overflow: hidden; }

    .dice-wrap { width: 74px; height: 74px; perspective: 700px; }
    .dice { position: relative; width: 74px; height: 74px; transform-style: preserve-3d; transition: transform 900ms cubic-bezier(.2,.85,.2,1); }
    .dice-face { position: absolute; width: 74px; height: 74px; border-radius: 18px; border: 1px solid rgba(255,255,255,.18); background: linear-gradient(180deg, rgba(255,255,255,.12), rgba(255,255,255,.04)); display:flex; align-items:center; justify-content:center; font-weight: 900; font-size: 22px; box-shadow: 0 12px 28px rgba(0,0,0,.25); user-select:none; }
    .dice-face::after{ content:""; position:absolute; inset: 10px; border-radius: 14px; border: 1px solid rgba(255,255,255,.10); pointer-events:none; }
    .dice-face.f1 { transform: translateZ(37px); }
    .dice-face.f2 { transform: rotateY(90deg) translateZ(37px); }
    .dice-face.f3 { transform: rotateY(180deg) translateZ(37px); }
    .dice-face.f4 { transform: rotateY(-90deg) translateZ(37px); }
    .dice-face.f5 { transform: rotateX(90deg) translateZ(37px); }
    .dice-face.f6 { transform: rotateX(-90deg) translateZ(37px); }
    @keyframes diceShake { 0% { transform: translateY(0); } 30% { transform: translateY(-2px); } 60% { transform: translateY(2px); } 100% { transform: translateY(0); } }
    .dice-shake { animation: diceShake 300ms ease 2; }

    .lootbox { position: fixed; inset: 0; z-index: 9999; display: none; align-items: center; justify-content: center; background: radial-gradient(circle at 50% 30%, rgba(255,255,255,.10), rgba(0,0,0,.85)); backdrop-filter: blur(10px); padding: 18px; }
    .lootbox.on { display:flex; }
    .lootbox-panel { width: min(520px, 100%); border-radius: 22px; border: 1px solid rgba(255,255,255,.14); background: rgba(10,10,12,.85); box-shadow: 0 24px 80px rgba(0,0,0,.6); overflow: hidden; transform: translateY(10px) scale(.98); opacity: 0; transition: all 420ms cubic-bezier(.2,.85,.2,1); }
    .lootbox.on .lootbox-panel { transform: translateY(0) scale(1); opacity: 1; }
    .lootbox-top { padding: 14px 14px 0 14px; display:flex; align-items:center; justify-content: space-between; gap: 10px; }
    .lootbox-title { font-weight: 900; }
    .lootbox-close { border: 1px solid rgba(255,255,255,.14); background: rgba(255,255,255,.04); color:#fff; border-radius: 14px; padding: 10px 12px; font-weight: 900; cursor: pointer; }
    .lootbox-stage { padding: 14px; display:flex; gap: 12px; align-items:center; }
    .lootbox-img { width: 104px; height: 104px; border-radius: 18px; object-fit: cover; border: 1px solid rgba(255,255,255,.14); background: radial-gradient(circle at 20% 20%, rgba(255,255,255,.10), rgba(255,255,255,.02)); }
    .lootbox-info { min-width:0; }
    .lootbox-name { font-weight: 900; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .lootbox-anime { margin-top: 4px; color: rgba(255,255,255,.70); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .lootbox-note { margin-top: 10px; color: rgba(255,255,255,.70); font-size: 12px; }
    @keyframes revealPulse { 0% { box-shadow: 0 0 0 rgba(124,255,178,0); } 100% { box-shadow: 0 0 60px rgba(124,255,178,.22); } }
    .reveal-glow { animation: revealPulse 800ms ease 1; }
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
    <button class="tab" id="tab_dado">🎲 Dado</button>
    <button class="tab" id="tab_shop">🛒 Loja</button>
  </div>

  <div class="search" id="search_box">
    <input id="q" placeholder="Buscar personagem ou anime..." />
  </div>

  <div class="status" id="status">Conectando...</div>

  <!-- DADO VIEW -->
  <div id="dado_view" style="display:none;margin-top:12px;">
    <div class="dado-card">
      <div class="dado-header">
        <div>
          <div class="dado-title">🎲 Dado Premium</div>
          <div class="dado-sub">Rola aqui no MiniApp (3D). Escolha 1 anime no grid e receba o personagem no PV.</div>
        </div>
        <div class="dado-pill">Dados: <span id="dado_balance">-</span> | Giros: <span id="dado_extra">-</span></div>
      </div>

      <div class="dado-actions">
        <div class="dice-wrap">
          <div id="dice3d" class="dice">
            <div class="dice-face f1">1</div>
            <div class="dice-face f2">2</div>
            <div class="dice-face f3">3</div>
            <div class="dice-face f4">4</div>
            <div class="dice-face f5">5</div>
            <div class="dice-face f6">6</div>
          </div>
        </div>

        <button id="btn_roll" class="dado-btn">ROLAR AGORA</button>
        <button id="btn_reco" class="dado-btn secondary" title="Escolhe uma opção recomendada sozinho">🧠</button>
      </div>

      <div class="dado-controls">
        <input id="dado_search" class="dado-input" placeholder="🔎 Buscar anime..." />
        <select id="dado_filter" class="dado-select" style="max-width: 150px;">
          <option value="popular">Popular</option>
          <option value="az">A–Z</option>
          <option value="random">Aleatório</option>
        </select>
      </div>

      <div class="dado-tip" id="dado_tip">Dica: clique em um card. Se quiser, aperta 🧠 pra ele escolher recomendado.</div>
      <div id="anime_grid" class="anime-grid"></div>
    </div>
  </div>

  <!-- LOOTBOX -->
  <div id="lootbox" class="lootbox">
    <div class="lootbox-panel" id="lootbox_panel">
      <div class="lootbox-top">
        <div class="lootbox-title">✨ Lootbox Reveal</div>
        <button class="lootbox-close" id="lootbox_close">FECHAR</button>
      </div>
      <div class="lootbox-stage" id="lootbox_stage">
        <img class="lootbox-img" id="lootbox_img" src="" alt="character"/>
        <div class="lootbox-info">
          <div class="lootbox-name" id="lootbox_name">...</div>
          <div class="lootbox-anime" id="lootbox_anime">...</div>
          <div class="lootbox-note">✅ Entregue no PV do bot</div>
        </div>
      </div>
    </div>
  </div>

  <div id="sections"></div>

  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) { tg.ready(); try { tg.expand(); } catch(e) {} }
    const INIT_DATA = tg?.initData || "";

    function escapeHtml(s){
      return String(s || "").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
    }

    async function apiGet(url){
      const res = await fetch(url, { headers: { "X-Telegram-Init-Data": INIT_DATA } });
      const data = await res.json().catch(()=> ({}));
      return { ok: res.ok, status: res.status, data };
    }

    async function apiPost(url, body){
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type":"application/json", "X-Telegram-Init-Data": INIT_DATA },
        body: JSON.stringify(body || {})
      });
      const data = await res.json().catch(()=> ({}));
      return { ok: res.ok, status: res.status, data };
    }

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
        header.innerHTML = `<div>${escapeHtml(g.title)}</div><div class="section-count">${g.cards.length}</div>`;
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
            ${img ? `<img src="${escapeHtml(img)}" alt="">`
                 : `<div style="height:220px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5)">Sem imagem</div>`}
            <div class="pill">x${qty} • ID ${charId}</div>
            ${fav ? `<div class="heart">❤️</div>` : ``}
            <div class="overlay">
              <div class="name">${escapeHtml(name)}</div>
              <div class="meta">${escapeHtml(g.title)}</div>
            </div>
          `;
          grid.appendChild(card);
        }

        section.appendChild(grid);
        sectionsRoot.appendChild(section);
      }
    }

    async function loadCollection(){
      try{
        setStatus("Carregando...", "");
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

        const r = await apiGet(apiUrl);
        if (!r.ok){
          setStatus("❌ Falha ao carregar.\n\nStatus: " + r.status + "\n" + JSON.stringify(r.data||{}), "err");
          document.getElementById("sub").textContent = "Erro: " + r.status;
          return;
        }

        const data = r.data || {};

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

    // =========================
    // Tabs + Views
    // =========================
    const tabAll = document.getElementById("tab_all");
    const tabFav = document.getElementById("tab_fav");
    const tabDado = document.getElementById("tab_dado");
    const tabShop = document.getElementById("tab_shop");

    const sections = document.getElementById("sections");
    const searchBox = document.getElementById("search_box");
    const statusBox = document.getElementById("status");
    const dadoView = document.getElementById("dado_view");

    function showView(mode){
      if(mode === "dado"){
        if(sections) sections.style.display = "none";
        if(searchBox) searchBox.style.display = "none";
        if(statusBox) statusBox.style.display = "none";
        if(dadoView) dadoView.style.display = "block";

        tabAll?.classList.remove("active");
        tabFav?.classList.remove("active");
        tabShop?.classList.remove("active");
        tabDado?.classList.add("active");
        return;
      }

      if(mode === "shop"){
        // abre a loja em miniapp separado (mais leve)
        try { tg?.openLink(window.location.origin + "/shop"); } catch(e){ window.location.href = "/shop"; }
        return;
      }

      // coleção/fav
      if(dadoView) dadoView.style.display = "none";
      if(sections) sections.style.display = "";
      if(searchBox) searchBox.style.display = "";
      if(statusBox) statusBox.style.display = "";

      if(mode === "fav"){
        showFav = true;
        tabFav?.classList.add("active");
        tabAll?.classList.remove("active");
        tabDado?.classList.remove("active");
        tabShop?.classList.remove("active");
        render();
        return;
      }

      // all
      showFav = false;
      tabAll?.classList.add("active");
      tabFav?.classList.remove("active");
      tabDado?.classList.remove("active");
      tabShop?.classList.remove("active");
      render();
    }

    tabAll.onclick = () => showView("all");
    tabFav.onclick = () => showView("fav");
    tabDado.onclick = () => showView("dado");
    tabShop.onclick = () => showView("shop");

    document.getElementById("q").addEventListener("input", render);

    // =========================
    // 🎲 DADO (Premium)
    // =========================
    const animeGrid = document.getElementById("anime_grid");
    const btnRoll = document.getElementById("btn_roll");
    const btnReco = document.getElementById("btn_reco");
    const dadoBalance = document.getElementById("dado_balance");
    const dadoExtra = document.getElementById("dado_extra");
    const dice3d = document.getElementById("dice3d");
    const dadoSearch = document.getElementById("dado_search");
    const dadoFilter = document.getElementById("dado_filter");

    const lootbox = document.getElementById("lootbox");
    const lootboxClose = document.getElementById("lootbox_close");
    const lootboxImg = document.getElementById("lootbox_img");
    const lootboxName = document.getElementById("lootbox_name");
    const lootboxAnime = document.getElementById("lootbox_anime");
    const lootboxStage = document.getElementById("lootbox_stage");

    let currentRollId = null;
    let currentOptions = [];

    const FACE_ROT = {
      1: 'rotateX(0deg) rotateY(0deg)',
      2: 'rotateX(0deg) rotateY(-90deg)',
      3: 'rotateX(0deg) rotateY(180deg)',
      4: 'rotateX(0deg) rotateY(90deg)',
      5: 'rotateX(-90deg) rotateY(0deg)',
      6: 'rotateX(90deg) rotateY(0deg)',
    };

    function diceRoll3D(finalValue){
      if(!dice3d) return;
      dice3d.classList.add('dice-shake');
      const sx = (Math.random() > 0.5 ? 1 : -1) * (360 * (2 + Math.floor(Math.random()*2)));
      const sy = (Math.random() > 0.5 ? 1 : -1) * (360 * (2 + Math.floor(Math.random()*2)));
      dice3d.style.transform = `rotateX(${sx}deg) rotateY(${sy}deg)`;
      setTimeout(() => {
        dice3d.classList.remove('dice-shake');
        dice3d.style.transform = FACE_ROT[finalValue] || FACE_ROT[1];
      }, 860);
    }

    function openLootbox(character){
      if(!lootbox) return;
      lootboxImg.src = character.image || '';
      lootboxName.textContent = character.name || '???';
      lootboxAnime.textContent = character.anime || 'Obra';

      lootbox.classList.add('on');
      lootboxStage.classList.remove('reveal-glow');
      void lootboxStage.offsetWidth;
      lootboxStage.classList.add('reveal-glow');
    }
    function closeLootbox(){ lootbox?.classList.remove('on'); }
    lootboxClose?.addEventListener('click', closeLootbox);
    lootbox?.addEventListener('click', (e) => { if(e.target === lootbox) closeLootbox(); });

    function normalizeOptions(opts){
      return (opts || []).map(o => ({
        id: o.id,
        title: o.title || 'Anime',
        cover: o.cover || o.image || ''
      }));
    }

    function applyFilterAndSearch(){
      const q = (dadoSearch?.value || '').trim().toLowerCase();
      const mode = (dadoFilter?.value || 'popular');
      let list = [...currentOptions];

      if(q){
        list = list.filter(o => (o.title || '').toLowerCase().includes(q));
      }
      if(mode === 'az'){
        list.sort((a,b)=> (a.title||'').localeCompare(b.title||''));
      } else if(mode === 'random'){
        list.sort(()=> Math.random() - 0.5);
      }
      renderGrid(list);
    }

    function renderGrid(list){
      if(!animeGrid) return;
      animeGrid.innerHTML = '';

      const maxShow = Math.min(list.length, 36);
      for(let i=0;i<maxShow;i++){
        const o = list[i];
        const btn = document.createElement('button');
        btn.className = 'anime-card';
        btn.innerHTML = `
          <img class="anime-cover" src="${o.cover ? o.cover : ''}" onerror="this.style.display='none'" />
          <div class="anime-title">🎴 ${escapeHtml(o.title)}</div>
        `;
        btn.onclick = () => pickAnime(o.id, btn);
        animeGrid.appendChild(btn);
      }

      if(maxShow === 0){
        animeGrid.innerHTML = `<div style="grid-column:1/-1;color:rgba(255,255,255,.65);font-size:12px;padding:10px;">Nenhum anime encontrado.</div>`;
      }
    }

    async function pickAnime(animeId, btn){
      if(!currentRollId) return;
      if(btn){ btn.disabled = true; btn.style.opacity = .7; }

      const out = await apiPost(`/api/dado/pick?roll_id=${encodeURIComponent(currentRollId)}&anime_id=${encodeURIComponent(animeId)}`);
      const data = out.data || out; // compat

      if(!(data && data.ok)){
        if(btn){ btn.disabled = false; btn.style.opacity = 1; }
        alert('⚠️ Falha ao entregar. Tenta outra opção.');
        return;
      }
      openLootbox(data.character);
    }

    function pickRecommended(){
      if(!currentRollId || currentOptions.length === 0) return;
      const idx = Math.min(currentOptions.length - 1, Math.floor(Math.random() * Math.min(8, currentOptions.length)));
      const o = currentOptions[idx];
      pickAnime(o.id, null);
    }

    btnReco?.addEventListener('click', pickRecommended);
    dadoSearch?.addEventListener('input', applyFilterAndSearch);
    dadoFilter?.addEventListener('change', applyFilterAndSearch);

    btnRoll?.addEventListener('click', async () => {
      btnRoll.disabled = true;
      btnRoll.textContent = 'ROLANDO...';
      animeGrid.innerHTML = '';

      const out = await apiPost('/api/dado/start');
      const data = out.data || out;

      if(!(data && data.ok)){
        btnRoll.disabled = false;
        btnRoll.textContent = 'ROLAR AGORA';
        if(data && data.error === 'no_balance'){
          alert((data.msg || 'Sem saldo') + '\nAgora: ' + (data.now || ''));
        } else {
          alert('Falha ao rolar agora. Tenta novamente.');
        }
        return;
      }

      currentRollId = data.roll_id;
      dadoBalance.textContent = data.balance;
      dadoExtra.textContent = data.extra;

      diceRoll3D(data.dice);

      currentOptions = normalizeOptions(data.options || []);
      applyFilterAndSearch();

      btnRoll.disabled = false;
      btnRoll.textContent = 'ROLAR DE NOVO';
    });

    // bootstrap
    (async () => {
      await loadCollection();
      // auto abre a aba dado se veio por URL (?tab=dado)
      try{
        const url = new URL(location.href);
        if((url.searchParams.get('tab')||'') === 'dado'){ showView('dado'); }
      }catch(e){}
    })();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


# =========================
# UI: Loja (/shop) — MiniApp separado
# =========================
@app.get("/shop", response_class=HTMLResponse)
def miniapp_shop():
    cfg = json.dumps({"sell_gain": SHOP_SELL_GAIN, "giro_price": SHOP_GIRO_PRICE, "per_page": SHOP_PER_PAGE}, ensure_ascii=False)
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
    <button class="tab" id="tab_back">⬅️ Voltar</button>
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
    const INIT_DATA = tg?.initData || "";

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
      const res = await fetch(url, {{ headers: {{ "X-Telegram-Init-Data": INIT_DATA }} }});
      const data = await res.json().catch(()=> ({{}}));
      return {{ ok: res.ok, status: res.status, data }};
    }}
    async function apiPost(url, body){{
      const res = await fetch(url, {{
        method: "POST",
        headers: {{ "Content-Type":"application/json", "X-Telegram-Init-Data": INIT_DATA }},
        body: JSON.stringify(body || {{}})
      }});
      const data = await res.json().catch(()=> ({{}}));
      return {{ ok: res.ok, status: res.status, data }};
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
      if (!r.data.ok){{ setStatus("⚠️ " + (r.data.error || "Erro ao carregar."), "err"); return; }}

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

    document.getElementById("tab_back").onclick = () => {{
      try {{ tg?.openLink(window.location.origin + "/app"); }} catch(e) {{ window.location.href = "/app"; }}
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
# ADMIN DASHBOARD API (read-only)
# ==========================================================
@app.get("/api/admin/stats")
def api_admin_stats(x_telegram_init_data: str = Header(default="")):
    verify_telegram_init_data(x_telegram_init_data)
    import database as db
    try:
        fn = getattr(db, "get_global_stats", None)
        if callable(fn):
            return {"ok": True, "stats": fn()}
    except Exception:
        pass
    return {"ok": True, "stats": {"users": 0, "coins": 0, "chars": 0, "market": 0}}
