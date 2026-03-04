# webapp.py — MiniApps (Coleção + Loja + Dado separado) — PREMIUM UI + FIXES + SHOP UPGRADES
# ✅ Objetivos atendidos:
# 1) Visual premium (estilo “Your Waifu”) com fundo FIXO + símbolos (pattern) nas 3 telas
# 2) Dado separado em /dado (barra dado) — coleção fica só em /app
# 3) Rotas /dado/start e /dado/pick (além de /api/dado/*) — evita {"detail":"Not Found"}
# 4) Nº de opções = valor do dado (1..6)
# 5) Se der erro hard no fluxo do dado, devolve o dado (refund)
# 6) Loja:
#    - Comprar GIRO por 2 coins (config SHOP_GIRO_PRICE default=2)
#    - Comprar DADO por X coins (SHOP_DADO_PRICE default=1)
#    - Botão "Comprar máximo possível" (compra todos os dados que der com suas coins)
# 7) Correção REAL: _pick_random_animes não tem mais código morto / variável inexistente
# 8) Rate limit leve no WebApp

import os
import json
import time
import hmac
import hashlib
import random
import asyncio
import aiohttp
from typing import Optional, Tuple, List, Dict
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

MINIAPP_SIGNING_SECRET = os.getenv("MINIAPP_SIGNING_SECRET", "").strip()

SHOP_SELL_GAIN = int(os.getenv("SHOP_SELL_GAIN", "1"))
SHOP_GIRO_PRICE = int(os.getenv("SHOP_GIRO_PRICE", "2"))  # ✅ giro = 2 coins por padrão
SHOP_DADO_PRICE = int(os.getenv("SHOP_DADO_PRICE", "1"))  # ✅ dado = 1 coin por padrão
COLLECTION_LIMIT = int(os.getenv("COLLECTION_LIMIT", "500"))

ANILIST_API = os.getenv("ANILIST_API", "https://graphql.anilist.co").strip()

DADO_NEW_USER_START = int(os.getenv("DADO_NEW_USER_START", "4"))
DADO_WEB_EXPIRE_SECONDS = int(os.getenv("DADO_WEB_EXPIRE_SECONDS", "300"))

DADO_PICK_IMAGE = os.getenv(
    "DADO_PICK_IMAGE",
    "https://photo.chelpbot.me/AgACAgEAAxkBZqAk02mfJAxu6F0SV9i2MqA5qQ6fDy3PAAKhC2sbjP74RFhnKn29pt05AQADAgADeQADOgQ/photo.jpg",
).strip()
DADO_FALLBACK_IMAGE = os.getenv(
    "DADO_FALLBACK_IMAGE",
    "https://photo.chelpbot.me/AgACAgEAAxkBZqnFu2mfsGZK0p1QU7Az5i2pp9C07ahKAALQC2sbS__4RF78U7yIQqiiAQADAgADeQADOgQ/photo.jpg",
).strip()

WEB_RATE_LIMIT_SECONDS = float(os.getenv("WEB_RATE_LIMIT_SECONDS", "0.45"))
_WEB_RATE: Dict[Tuple[int, str], float] = {}

DADO_MAX_BALANCE = int(os.getenv("DADO_MAX_BALANCE", "18"))
GIRO_MAX_BALANCE = int(os.getenv("GIRO_MAX_BALANCE", "24"))


# =========================
# helpers
# =========================
def _rate_limit(user_id: int, key: str) -> bool:
    now = time.time()
    k = (int(user_id), str(key))
    last = _WEB_RATE.get(k, 0.0)
    if now - last < WEB_RATE_LIMIT_SECONDS:
        return False
    _WEB_RATE[k] = now
    return True


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _safe_str(x) -> str:
    return x.strip() if isinstance(x, str) else ""


# =========================
# Telegram WebApp initData verify (correto)
# =========================
def verify_telegram_init_data(init_data: str) -> dict:
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
        return True
    expected = _sign_owner_link(user_id, ts)
    return hmac.compare_digest(expected, sig or "")


# =========================
# DB safe wrappers (compat)
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


def _get_fav_profile(db, user_id: int) -> dict:
    row = _get_user_row(db, user_id)
    return {
        "fav_name": _safe_str(row.get("fav_name")),
        "fav_image": _safe_str(row.get("fav_image")),
    }


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


def _spend_coins(db, user_id: int, amount: int) -> bool:
    """
    Tenta gastar coins de forma compatível.
    Preferências:
      1) db.spend_coins(user_id, amount) -> bool
      2) db.try_spend_coins(user_id, amount) -> bool
      3) fallback: checa coins e usa db.add_coin(user_id, -amount) se existir
    """
    amount = int(amount)
    if amount <= 0:
        return True

    for name in ("spend_coins", "try_spend_coins"):
        fn = getattr(db, name, None)
        if callable(fn):
            try:
                return bool(fn(int(user_id), amount))
            except Exception:
                pass

    cur = _get_coins(db, user_id)
    if cur < amount:
        return False

    fn_add = getattr(db, "add_coin", None)
    if callable(fn_add):
        try:
            fn_add(int(user_id), -amount)
            return True
        except Exception:
            return False

    return False


# =========================
# Telegram send (PV)
# =========================
async def _tg_send_photo(chat_id: int, photo: str, caption: str):
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
# DADO backend
# =========================
def _now_slot_4h(ts: Optional[float] = None) -> int:
    if ts is None:
        ts = time.time()
    return int(int(ts) // (4 * 3600))


def _now_giro_slot_3h(ts: Optional[float] = None) -> int:
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
        return
    # fallback: tenta setar pelo state (se não existir inc)
    st = _get_dado_state(db, user_id)
    b = _safe_int(st.get("b"), 0)
    s = _safe_int(st.get("s"), _now_slot_4h())
    nb = min(int(max_balance), max(0, b + int(amount)))
    _set_dado_state(db, user_id, nb, s)


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
    _inc_dado_balance(db, user_id, 1, max_balance=DADO_MAX_BALANCE)


def _buy_dado(db, user_id: int, qty: int, price_each: int) -> Tuple[bool, str]:
    qty = int(qty)
    price_each = int(price_each)
    if qty <= 0:
        return False, "Quantidade inválida."
    if price_each <= 0:
        return False, "Preço inválido."

    total = qty * price_each
    ok = _spend_coins(db, user_id, total)
    if not ok:
        return False, "Você não tem coins suficientes."

    try:
        _inc_dado_balance(db, user_id, qty, max_balance=DADO_MAX_BALANCE)
    except Exception:
        _add_coin(db, user_id, total)
        return False, "Falha ao adicionar dados. Reembolsado."

    return True, "ok"


# -------------------------
# Cache / blacklist (best-effort)
# -------------------------
_CHAR_POOL_CACHE: Dict[int, dict] = {}
_POOL_LOCKS: Dict[int, asyncio.Lock] = {}
_REFRESH_LOCK = asyncio.Lock()


def _get_pool_lock(anime_id: int) -> asyncio.Lock:
    lk = _POOL_LOCKS.get(int(anime_id))
    if lk is None:
        lk = asyncio.Lock()
        _POOL_LOCKS[int(anime_id)] = lk
    return lk


def _db_is_anime_blacklisted(db, anime_id: int) -> bool:
    fn = getattr(db, "is_bad_anime", None)
    if callable(fn):
        try:
            return bool(fn(int(anime_id)))
        except Exception:
            return False
    fn2 = getattr(db, "is_dado_anime_blacklisted", None)
    if callable(fn2):
        try:
            return bool(fn2(int(anime_id)))
        except Exception:
            return False
    return False


def _db_blacklist_anime(db, anime_id: int, reason: str = "no_chars"):
    fn = getattr(db, "mark_bad_anime", None)
    if callable(fn):
        try:
            fn(int(anime_id), str(reason))
        except Exception:
            pass
        return
    fn2 = getattr(db, "blacklist_dado_anime", None)
    if callable(fn2):
        try:
            fn2(int(anime_id), str(reason))
        except Exception:
            pass


async def _fetch_top500_anime_from_anilist() -> List[dict]:
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
    items: List[dict] = []
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


def _pick_random_animes(db, n: int) -> List[dict]:
    """
    ✅ CORRIGIDO: sem código morto / sem variáveis inexistentes.
    Retorna N opções de anime do pool (TOP500) em formato:
      [{id:int, title:str}]
    OBS: id aqui é um ID de opção (1..N), porque seu pool_random_character usa título.
    """
    n = max(1, min(6, int(n)))

    try:
        fn = getattr(db, "pool_random_animes", None)
        rows = fn(int(n)) if callable(fn) else []
    except Exception:
        rows = []

    rows = rows or []
    if not rows:
        return []

    out: List[dict] = []
    seen: set = set()
    opt_id = 1

    for r in rows:
        if not isinstance(r, dict):
            continue

        title = _safe_str(r.get("anime") or r.get("title") or "")
        if not title or title in seen:
            continue

        out.append({"id": int(opt_id), "title": title})
        seen.add(title)
        opt_id += 1

        if len(out) >= n:
            break

    return out


async def _build_char_pool_for_anime(anime_id: int, max_pages: int = 4) -> Optional[dict]:
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

    chars: List[dict] = []
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
            async with session.post(
                ANILIST_API, json={"query": q, "variables": {"id": int(anime_id), "page": int(page)}}
            ) as r2:
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
    now = int(time.time())

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

    cover = (_CHAR_POOL_CACHE[int(anime_id)].get("cover") or "") or DADO_FALLBACK_IMAGE
    c = pick_list[0]
    return {
        "id": int(c["id"]),
        "name": c["name"],
        "image": cover,
        "anime_title": (_CHAR_POOL_CACHE[int(anime_id)].get("title") or "Obra"),
        "anime_cover": (_CHAR_POOL_CACHE[int(anime_id)].get("cover") or ""),
    }


async def _try_get_character_from_selected_only(db, anime_id: int) -> Optional[dict]:
    return await _get_random_character_from_anime(db, int(anime_id), tries=14)


def _get_custom_global_image_if_any(db, char_id: int) -> str:
    try:
        fn = getattr(db, "get_global_character_image", None)
        if callable(fn):
            url = fn(int(char_id)) or ""
            return _safe_str(url)
    except Exception:
        pass
    try:
        fn2 = getattr(db, "get_character_custom_image", None)
        if callable(fn2):
            url = fn2(int(char_id)) or ""
            return _safe_str(url)
    except Exception:
        pass
    return ""


def _choose_rarity(dice_value: int, char_id: int) -> dict:
    seed = (int(char_id) * 1103515245 + int(dice_value) * 12345) & 0xFFFFFFFF
    r = seed % 1000
    if r < 30:
        stars, tier = 5, "mythic"
    elif r < 150:
        stars, tier = 4, "epic"
    elif r < 450:
        stars, tier = 3, "rare"
    else:
        stars, tier = 2, "common"
    return {"stars": stars, "tier": tier}


# =========================
# APP
# =========================
app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse("✅ Web rodando! Use /app (coleção), /shop (loja) ou /dado (gacha).")


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
    fav = _get_fav_profile(db, user_id)

    return JSONResponse(
        {
            "ok": True,
            "mode": "me",
            "owner_id": user_id,
            "owner_name": first_name,
            "collection_name": collection_name,
            "coins": coins,
            "giros": giros,
            "fav": fav,
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
    fav = {"fav_name": "", "fav_image": ""}

    return JSONResponse(
        {
            "ok": True,
            "mode": "owner",
            "owner_id": owner_id,
            "owner_name": owner_name,
            "collection_name": collection_name,
            "coins": coins,
            "giros": giros,
            "fav": fav,
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

    # dado balance (com refresh para refletir recarga automática)
    dado_balance = _refresh_user_dado_balance(db, user_id)
    extra = _refresh_user_giros(db, user_id)

    return JSONResponse(
        {
            "ok": True,
            "user_id": user_id,
            "coins": coins,
            "giros": giros,
            "dado_balance": int(dado_balance),
            "extra": int(extra),
            "sell_gain": SHOP_SELL_GAIN,
            "giro_price": SHOP_GIRO_PRICE,
            "dado_price": SHOP_DADO_PRICE,
            "dado_max_balance": DADO_MAX_BALANCE,
            "giro_max_balance": GIRO_MAX_BALANCE,
        }
    )


@app.get("/api/shop/sell/all")
def api_sell_all(q: str = "", x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    if not _rate_limit(user_id, "shop_all"):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)

    import database as db
    _ensure_user(db, user_id, first_name)

    items = _list_collection_cards_safe(db, user_id, limit=COLLECTION_LIMIT)

    qn = (q or "").strip().casefold()
    out = []
    for r in items:
        if not isinstance(r, dict):
            continue
        char_id = _safe_int(r.get("character_id") or 0, 0)
        name = _safe_str(r.get("character_name") or "Personagem")
        anime = _safe_str(r.get("anime_title") or "Sem anime")
        qty = max(1, _safe_int(r.get("quantity") or 1, 1))

        custom_image = _safe_str(r.get("custom_image"))
        image = custom_image or _safe_str(r.get("image")) or ""

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
            }
        )

    return JSONResponse({"ok": True, "items": out, "sell_gain": SHOP_SELL_GAIN})


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
    sold_name = _safe_str(item.get("character_name") or "Personagem")

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


@app.post("/api/shop/buy/dado")
def api_buy_dado(payload_body: dict = Body(default={}), x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    import database as db
    _ensure_user(db, user_id, first_name)

    qty = _safe_int(payload_body.get("qty"), 1)
    qty = max(1, min(999, qty))

    ok, msg = _buy_dado(db, user_id, qty=qty, price_each=SHOP_DADO_PRICE)
    if not ok:
        return JSONResponse({"ok": False, "error": msg}, status_code=200)

    coins = _get_coins(db, user_id)
    dado_balance = _refresh_user_dado_balance(db, user_id)
    extra = _refresh_user_giros(db, user_id)
    giros = _get_giros(db, user_id)

    return JSONResponse(
        {
            "ok": True,
            "coins": coins,
            "giros": giros,
            "dado_balance": int(dado_balance),
            "extra": int(extra),
            "qty": int(qty),
            "price_each": int(SHOP_DADO_PRICE),
        }
    )


@app.post("/api/shop/buy/dado/max")
def api_buy_dado_max(x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    import database as db
    _ensure_user(db, user_id, first_name)

    coins = _get_coins(db, user_id)
    if SHOP_DADO_PRICE <= 0:
        return JSONResponse({"ok": False, "error": "Preço do dado inválido."}, status_code=200)

    max_qty = coins // SHOP_DADO_PRICE
    if max_qty <= 0:
        return JSONResponse({"ok": False, "error": "Você não tem coins suficientes."}, status_code=200)

    ok, msg = _buy_dado(db, user_id, qty=max_qty, price_each=SHOP_DADO_PRICE)
    if not ok:
        return JSONResponse({"ok": False, "error": msg}, status_code=200)

    coins2 = _get_coins(db, user_id)
    dado_balance = _refresh_user_dado_balance(db, user_id)
    extra = _refresh_user_giros(db, user_id)
    giros = _get_giros(db, user_id)

    return JSONResponse(
        {
            "ok": True,
            "coins": coins2,
            "giros": giros,
            "dado_balance": int(dado_balance),
            "extra": int(extra),
            "qty": int(max_qty),
            "price_each": int(SHOP_DADO_PRICE),
        }
    )


# =========================
# API: DADO (core impl)
# =========================
async def _dado_start_impl(x_telegram_init_data: str):
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
            {
                "ok": False,
                "error": "no_balance",
                "msg": "Você está sem dados/giros agora.\n\nEles recarregam automaticamente com o tempo.\nVolte mais tarde e tente de novo.",
                "now": datetime.utcnow().strftime("%H:%M"),
            },
            status_code=200,
        )

    consumed = _consume_one_die(db, user_id)
    if not consumed:
        return JSONResponse({"ok": False, "error": "consume_failed"}, status_code=200)

    try:
        try:
            await _ensure_top_cache_fresh(db)
        except Exception:
            pass

        dice_value = random.SystemRandom().randint(1, 6)

        # ✅ N opções = valor do dado
        n = max(1, min(6, int(dice_value)))

        options = _pick_random_animes(db, n)
        if not options:
            _refund_one_die(db, user_id)
            return JSONResponse({"ok": False, "error": "no_anime_cache"}, status_code=200)

        fn = getattr(db, "create_dice_roll", None)
        if not callable(fn):
            _refund_one_die(db, user_id)
            return JSONResponse({"ok": False, "error": "db_missing_roll"}, status_code=200)

        try:
            roll_id = fn(user_id, int(dice_value), json.dumps(options, ensure_ascii=False), "pending", int(time.time()))
        except TypeError:
            roll_id = fn(user_id, int(dice_value), json.dumps(options, ensure_ascii=False))

        balance2 = _refresh_user_dado_balance(db, user_id)
        extra2 = _refresh_user_giros(db, user_id)

        return JSONResponse(
            {
                "ok": True,
                "roll_id": int(roll_id),
                "dice": int(dice_value),
                "options": options,
                "balance": int(balance2),
                "extra": int(extra2),
            }
        )
    except Exception:
        _refund_one_die(db, user_id)
        return JSONResponse({"ok": False, "error": "server_error_refunded"}, status_code=200)


async def _dado_pick_impl(anime_id: int, roll_id: int, x_telegram_init_data: str):
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
    dice_value = _safe_int(roll.get("dice_value") or 1, 1)

    if status == "resolved":
        return JSONResponse({"ok": False, "error": "used"}, status_code=200)

    if created_at and int(time.time()) - created_at > DADO_WEB_EXPIRE_SECONDS:
        try:
            fn = getattr(db, "set_dice_roll_status", None)
            if callable(fn):
                fn(int(roll_id), "expired_refunded")
        except Exception:
            pass
        _refund_one_die(db, user_id)
        return JSONResponse({"ok": False, "error": "expired_refunded"}, status_code=200)

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
        try:
            opts = json.loads(str(roll.get("options_json") or "[]"))
        except Exception:
            opts = []

        chosen_title = ""
        for o in (opts or []):
            try:
                if int(o.get("id") or 0) == int(anime_id):
                    chosen_title = _safe_str(o.get("title"))
                    break
            except Exception:
                continue

        if not chosen_title:
            try:
                fn = getattr(db, "set_dice_roll_status", None)
                if callable(fn):
                    fn(int(roll_id), "pending")
            except Exception:
                pass
            return JSONResponse({"ok": False, "error": "invalid_choice"}, status_code=200)

        fn_pool = getattr(db, "pool_random_character", None)
        info = fn_pool(chosen_title) if callable(fn_pool) else None
        if not info:
            try:
                fn = getattr(db, "set_dice_roll_status", None)
                if callable(fn):
                    fn(int(roll_id), "pending")
            except Exception:
                pass
            return JSONResponse({"ok": False, "error": "try_other"}, status_code=200)

        try:
            fn = getattr(db, "set_dice_roll_status", None)
            if callable(fn):
                fn(int(roll_id), "resolved")
        except Exception:
            pass

        char_id = int(info.get("character_id") or 0)
        name = _safe_str(info.get("name"))
        anime_title = _safe_str(info.get("anime")) or "Obra"

        gimg = _get_custom_global_image_if_any(db, char_id)
        image = gimg or (f"https://img.anili.st/character/{char_id}" if char_id else "") or DADO_FALLBACK_IMAGE

        try:
            fn_add = getattr(db, "add_character_to_collection", None)
            if callable(fn_add):
                try:
                    fn_add(user_id, char_id, name, image, anime_title=anime_title)
                except TypeError:
                    fn_add(user_id, char_id, name, image)
        except Exception:
            pass

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

        rarity = _choose_rarity(dice_value=dice_value, char_id=char_id)
        return JSONResponse(
            {"ok": True, "character": {"id": char_id, "name": name, "anime": anime_title, "image": image, "rarity": rarity}},
            status_code=200,
        )

    except Exception:
        try:
            fn = getattr(db, "set_dice_roll_status", None)
            if callable(fn):
                fn(int(roll_id), "failed_refunded")
        except Exception:
            pass
        _refund_one_die(db, user_id)
        return JSONResponse({"ok": False, "error": "server_error_refunded"}, status_code=200)


# =========================
# API: DADO (rotas antigas /api/dado/*)
# =========================
@app.post("/api/dado/start")
@app.post("/api/dado/start/")
@app.get("/api/dado/start")
@app.get("/api/dado/start/")
async def api_dado_start(x_telegram_init_data: str = Header(default="")):
    return await _dado_start_impl(x_telegram_init_data)


@app.post("/api/dado/pick")
@app.post("/api/dado/pick/")
@app.get("/api/dado/pick")
@app.get("/api/dado/pick/")
async def api_dado_pick(
    anime_id: int = Query(...),
    roll_id: int = Query(...),
    x_telegram_init_data: str = Header(default=""),
):
    return await _dado_pick_impl(anime_id, roll_id, x_telegram_init_data)


# =========================
# ✅ API: DADO (rotas novas na "barra dado": /dado/start e /dado/pick)
# =========================
@app.post("/dado/start")
@app.post("/dado/start/")
@app.get("/dado/start")
@app.get("/dado/start/")
async def dado_start_bar(x_telegram_init_data: str = Header(default="")):
    return await _dado_start_impl(x_telegram_init_data)


@app.post("/dado/pick")
@app.post("/dado/pick/")
@app.get("/dado/pick")
@app.get("/dado/pick/")
async def dado_pick_bar(
    anime_id: int = Query(...),
    roll_id: int = Query(...),
    x_telegram_init_data: str = Header(default=""),
):
    return await _dado_pick_impl(anime_id, roll_id, x_telegram_init_data)


# =========================
# UI THEME (shared)
# =========================
# SVG pattern com símbolos (fixo), bem leve, sem depender de assets externos
_BG_SYMBOLS_SVG = """
<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220' viewBox='0 0 220 220'>
  <defs>
    <filter id='b' x='-20%' y='-20%' width='140%' height='140%'>
      <feGaussianBlur stdDeviation='0.6'/>
    </filter>
  </defs>
  <g fill='none' stroke='rgba(255,255,255,0.14)' stroke-width='1' filter='url(#b)'>
    <path d='M30 40 l12 0 l0 12 l-12 0 Z'/>
    <path d='M160 30 l14 14 l-14 14 l-14-14 Z'/>
    <circle cx='60' cy='150' r='10'/>
    <path d='M140 155 l20 0'/>
    <path d='M140 155 l0 20'/>
    <path d='M180 165 l10-10 l10 10 l-10 10 Z'/>
    <path d='M25 185 l16 0'/>
    <path d='M25 185 l0 16'/>
  </g>
  <g fill='rgba(255,255,255,0.10)'>
    <circle cx='110' cy='110' r='2'/>
    <circle cx='116' cy='116' r='1.5'/>
    <circle cx='104' cy='118' r='1.2'/>
  </g>
</svg>
""".strip()


def _bg_css_block() -> str:
    # data uri safe
    import urllib.parse
    svg = urllib.parse.quote(_BG_SYMBOLS_SVG)
    return f"""
    :root{{
      --bg0:#06060c;
      --bg1:#0b0a14;
      --card:#12111b;
      --stroke: rgba(255,255,255,.10);
      --muted: rgba(255,255,255,.72);
      --muted2: rgba(255,255,255,.50);

      --a1:#ff2b4a;
      --a2:#b30f22;
      --a3:#ff6a88;
      --a4:#b06cff;

      --c-common:#c9c9c9;
      --c-rare:#4da3ff;
      --c-epic:#b06cff;
      --c-mythic:#ffcc33;

      --good: rgba(0,255,140,.18);
      --bad: rgba(255,60,60,.18);
    }}
    *{{box-sizing:border-box}}
    html,body{{height:100%}}
    body{{
      margin:0;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
      color:#fff;
      padding:14px 14px 90px;
      overflow-x:hidden;
      background:
        radial-gradient(900px 600px at 15% 0%, rgba(255,43,74,.18), transparent 60%),
        radial-gradient(900px 600px at 85% 10%, rgba(176,108,255,.14), transparent 60%),
        radial-gradient(900px 700px at 40% 110%, rgba(77,163,255,.10), transparent 60%),
        linear-gradient(180deg, var(--bg1), var(--bg0));
      background-attachment: fixed;
      position:relative;
    }}
    /* camada símbolos */
    body::before{{
      content:"";
      position:fixed; inset:0;
      background-image: url("data:image/svg+xml,{svg}");
      background-repeat: repeat;
      background-size: 220px 220px;
      opacity: .20;
      pointer-events:none;
      mix-blend-mode: overlay;
      transform: translateZ(0);
    }}
    /* brilho superior */
    body::after{{
      content:"";
      position:fixed; inset:-20% -20% auto -20%;
      height: 55%;
      background:
        radial-gradient(700px 380px at 20% 30%, rgba(255,43,74,.22), transparent 60%),
        radial-gradient(620px 360px at 70% 10%, rgba(176,108,255,.18), transparent 65%);
      opacity:.55;
      pointer-events:none;
      filter: blur(0px);
      transform: translateZ(0);
    }}
    """


# =========================
# UI: /app — Coleção + Favoritos (SEM DADO)
# =========================
@app.get("/app", response_class=HTMLResponse)
def miniapp_collection():
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1, viewport-fit=cover">
  <title>Baltigo • Coleção</title>
  <style>
  """ + _bg_css_block() + r"""
    .top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:4px;position:relative;z-index:2;}
    .title{display:flex;flex-direction:column;gap:3px;min-width:0;}
    .title h1{margin:0;font-size:18px;font-weight:1000;letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .title .sub{font-size:12px;color:var(--muted2);}

    .stats{
      display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--stroke);
      background:rgba(255,255,255,.035);border-radius:999px;white-space:nowrap;flex-shrink:0;
      box-shadow: 0 12px 38px rgba(0,0,0,.35);
      backdrop-filter: blur(12px);
      position:relative;z-index:2;
    }
    .stat{display:flex;align-items:center;gap:6px;font-weight:950;font-size:13px;}
    .dot{width:1px;height:16px;background:var(--stroke);}

    .tabs{
      display:flex;gap:10px;margin:14px 0 12px;padding:8px;border:1px solid var(--stroke);
      border-radius:999px;background:rgba(255,255,255,.035);
      box-shadow: 0 14px 46px rgba(0,0,0,.35);
      backdrop-filter: blur(12px);
      position:relative;z-index:2;
    }
    .tab{
      flex:1;text-align:center;padding:10px 12px;border-radius:999px;
      font-weight:950;font-size:14px;color:rgba(255,255,255,.75);
      background:transparent;border:0;cursor:pointer;
      transition: transform .12s ease, background .12s ease;
    }
    .tab:active{transform: scale(.98);}
    .tab.active{
      color:#fff;
      background: linear-gradient(90deg, rgba(255,43,74,.92), rgba(176,108,255,.70));
      box-shadow: 0 14px 44px rgba(255,43,74,.10);
    }

    .search{display:flex;gap:10px;align-items:center;margin:6px 0 14px;position:relative;z-index:2;}
    .search input{
      width:100%;padding:12px 12px;border-radius:14px;border:1px solid var(--stroke);
      background:rgba(255,255,255,.035);color:#fff;outline:none;font-size:14px;
      backdrop-filter: blur(12px);
    }
    .search input::placeholder{color:rgba(255,255,255,.35)}

    .status{
      margin:10px 0;padding:10px 12px;border-radius:14px;border:1px solid var(--stroke);
      background:rgba(255,255,255,.03);color:rgba(255,255,255,.80);
      font-size:13px;white-space:pre-wrap;backdrop-filter: blur(12px);
      position:relative;z-index:2;
    }
    .status.ok{border-color: var(--good);}
    .status.err{border-color: var(--bad);color: rgba(255,120,120,.95);}

    .section{
      margin-top:12px;padding:10px 10px 6px;border-radius:18px;border:1px solid var(--stroke);
      background:rgba(255,255,255,.03);backdrop-filter: blur(12px);
      position:relative;z-index:2;
    }
    .section-title{
      font-weight:950;font-size:14px;color:rgba(255,255,255,.92);
      margin:2px 4px 10px;display:flex;align-items:center;justify-content:space-between;gap:8px;
    }
    .section-count{font-size:12px;color:rgba(255,255,255,.55);font-weight:900;}

    .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}
    .card{
      position:relative;border-radius:20px;overflow:hidden;border:1px solid var(--stroke);
      background:var(--card);min-height:220px;
      box-shadow: 0 18px 56px rgba(0,0,0,.45);
      transform: translateZ(0);
    }
    .card img{width:100%;height:220px;object-fit:cover;display:block;filter:saturate(1.08) contrast(1.06);}
    .overlay{
      position:absolute;left:0;right:0;bottom:0;padding:10px;
      background:linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.86));
    }
    .name{font-weight:1000;font-size:15px;margin:0;letter-spacing:.1px;}
    .meta{margin-top:3px;font-size:12px;color:rgba(255,255,255,.78);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .pill{
      position:absolute;top:10px;left:10px;padding:6px 10px;background:rgba(0,0,0,.52);
      border:1px solid rgba(255,255,255,.14);border-radius:999px;font-weight:1000;font-size:12px;
      backdrop-filter: blur(10px);
    }
    .shine{
      position:absolute;inset:-40%;
      background: radial-gradient(circle at 30% 30%, rgba(255,255,255,.22), transparent 38%);
      transform: rotate(12deg);
      opacity:.0; pointer-events:none;
      transition: opacity .2s ease;
      mix-blend-mode: screen;
    }
    .card:hover .shine{opacity:.35}
    .card:active .shine{opacity:.45}

    .rar{
      position:absolute;top:10px;right:10px;padding:6px 10px;border-radius:999px;
      background:rgba(0,0,0,.52);border:1px solid rgba(255,255,255,.14);
      font-weight:1000;font-size:12px;backdrop-filter: blur(10px);
      display:flex;align-items:center;gap:6px;
    }
    .rar .dot{width:8px;height:8px;border-radius:99px;background:#fff;opacity:.9}
    .tier-common .rar .dot{background:var(--c-common)}
    .tier-rare   .rar .dot{background:var(--c-rare)}
    .tier-epic   .rar .dot{background:var(--c-epic)}
    .tier-mythic .rar .dot{background:var(--c-mythic)}

    .emptyHint{
      color:rgba(255,255,255,.68);
      font-size:13px;
      padding:8px 4px;
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
    <button class="tab" id="tab_fav">⭐ Favorito</button>
  </div>

  <div class="search" id="search_box">
    <input id="q" placeholder="Buscar personagem ou anime..." />
  </div>

  <div class="status" id="status">Conectando...</div>
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

    let allCards = [];
    let mode = "all";
    let favProfile = { fav_name: "", fav_image: "" };

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

    function computeTierHint(c){
      const q = getQty(c);
      if (q >= 8) return "tier-mythic";
      if (q >= 5) return "tier-epic";
      if (q >= 3) return "tier-rare";
      return "tier-common";
    }

    function renderCollection(){
      const q = (document.getElementById("q").value || "").trim().toLowerCase();

      if (mode === "fav"){
        const root = document.getElementById("sections");
        root.innerHTML = "";
        const favName = (favProfile?.fav_name || "").trim();
        const favImg = (favProfile?.fav_image || "").trim();

        if (!favName){
          root.innerHTML = "<div class='emptyHint'>Você ainda não definiu um favorito.</div>";
          return;
        }

        const fake = [{ character_name: favName, anime_title: "Favorito", image: favImg, quantity: 1, character_id: 0 }];
        const g = buildGroups(fake);
        for (const secData of g){
          const section = document.createElement("div");
          section.className = "section";
          const header = document.createElement("div");
          header.className = "section-title";
          header.innerHTML = `<div>${escapeHtml(secData.title)}</div><div class="section-count">${secData.cards.length}</div>`;
          section.appendChild(header);

          const grid = document.createElement("div");
          grid.className = "grid";

          for (const c of secData.cards){
            const img = getImageUrl(c);
            const name = getCharacterName(c);

            const card = document.createElement("div");
            card.className = "card tier-mythic";
            card.innerHTML = `
              <div class="shine"></div>
              ${img ? `<img src="${escapeHtml(img)}" alt="">`
                   : `<div style="height:220px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5)">Sem imagem</div>`}
              <div class="rar"><span class="dot"></span> FAVORITO</div>
              <div class="overlay">
                <div class="name">${escapeHtml(name)}</div>
                <div class="meta">Seu favorito</div>
              </div>
            `;
            grid.appendChild(card);
          }

          section.appendChild(grid);
          root.appendChild(section);
        }
        return;
      }

      let filtered = allCards;
      filtered = filtered.filter(c => {
        if (!q) return true;
        const name = getCharacterName(c).toLowerCase();
        const anime = getAnimeTitle(c).toLowerCase();
        const id = String(getCharId(c));
        return name.includes(q) || anime.includes(q) || id.includes(q);
      });

      const sectionsRoot = document.getElementById("sections");
      sectionsRoot.innerHTML = "";

      if (!filtered.length){
        sectionsRoot.innerHTML = "<div class='emptyHint'>Nenhum card encontrado.</div>";
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
          const tier = computeTierHint(c);

          const card = document.createElement("div");
          card.className = "card " + tier;
          card.innerHTML = `
            <div class="shine"></div>
            ${img ? `<img src="${escapeHtml(img)}" alt="">`
                 : `<div style="height:220px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.5)">Sem imagem</div>`}
            <div class="pill">x${qty} • ID ${charId}</div>
            <div class="rar"><span class="dot"></span> ${tier.replace("tier-","").toUpperCase()}</div>
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

        favProfile = data.fav || { fav_name:"", fav_image:"" };
        allCards = Array.isArray(data.cards) ? data.cards : [];

        setStatus("✅ Pronto.", "ok");
        renderCollection();
      } catch(e){
        setStatus("❌ Erro inesperado.", "err");
      }
    }

    const tabAll = document.getElementById("tab_all");
    const tabFav = document.getElementById("tab_fav");

    function setActiveTab(which){
      [tabAll, tabFav].forEach(t=>t.classList.remove("active"));
      if(which==="all") tabAll.classList.add("active");
      if(which==="fav") tabFav.classList.add("active");
    }

    tabAll.onclick = () => { mode="all"; setActiveTab("all"); renderCollection(); };
    tabFav.onclick = () => { mode="fav"; setActiveTab("fav"); renderCollection(); };

    document.getElementById("q").addEventListener("input", renderCollection);
    loadCollection();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


# =========================
# UI: /dado — Dado separado (barra dado)
# =========================
@app.get("/dado", response_class=HTMLResponse)
def miniapp_dado():
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1, viewport-fit=cover">
  <title>Baltigo • Dado</title>
  <style>
  """ + _bg_css_block() + r"""
    .top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:4px;position:relative;z-index:2;}
    .title{display:flex;flex-direction:column;gap:3px;min-width:0;}
    .title h1{margin:0;font-size:18px;font-weight:1000;letter-spacing:.2px;}
    .title .sub{font-size:12px;color:rgba(255,255,255,.55);}

    .pill{
      font-weight:1000;font-size:12px;border:1px solid var(--stroke);
      padding:10px 12px;border-radius:999px;background:rgba(255,255,255,.03);white-space:nowrap;
      backdrop-filter: blur(12px);
      box-shadow: 0 12px 38px rgba(0,0,0,.35);
    }
    .panel{
      margin-top:14px;padding:14px;border:1px solid var(--stroke);
      background:rgba(255,255,255,.035);border-radius:18px;
      box-shadow: 0 18px 56px rgba(0,0,0,.45);
      backdrop-filter: blur(12px);
      position:relative;z-index:2;
    }
    .row{display:flex;gap:12px;align-items:center;margin-top:12px;}
    .dice{
      width:80px;height:80px;border-radius:18px;border:1px solid rgba(255,255,255,.14);
      background:
        radial-gradient(circle at 20% 20%, rgba(255,43,74,.22), rgba(255,255,255,.02));
      display:flex;align-items:center;justify-content:center;
      font-size:34px;font-weight:1000;
      box-shadow: 0 18px 56px rgba(0,0,0,.35);
      user-select:none;
    }
    @keyframes wobble{
      0%{transform:rotate(0deg) scale(1)}
      20%{transform:rotate(-10deg) scale(1.02)}
      45%{transform:rotate(12deg) scale(1.03)}
      70%{transform:rotate(-8deg) scale(1.02)}
      100%{transform:rotate(0deg) scale(1)}
    }
    .wobble{animation:wobble 650ms cubic-bezier(.2,.85,.2,1) 1;}
    .btn{
      flex:1;border:0;border-radius:16px;padding:14px 14px;font-weight:1000;font-size:14px;color:#fff;
      background: linear-gradient(90deg, rgba(255,43,74,.92), rgba(176,108,255,.70));
      box-shadow: 0 18px 56px rgba(255,43,74,.08);
      cursor:pointer;
    }
    .btn:disabled{opacity:.55;cursor:not-allowed}

    .grid{margin-top:14px;display:grid;grid-template-columns:repeat(2,1fr);gap:10px;}
    .opt{
      text-align:left;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.04);color:#fff;
      border-radius:16px;padding:10px;cursor:pointer;transition: transform .12s ease, border-color .12s ease;
      position:relative;overflow:hidden;
      backdrop-filter: blur(12px);
    }
    .opt:active{transform:scale(.98)}
    .opt:hover{border-color: rgba(255,43,74,.22)}
    .optTitle{margin-top:2px;font-weight:1000;font-size:12px;line-height:1.25;max-height:2.6em;overflow:hidden;}
    .status{
      margin-top:12px;
      color:rgba(255,255,255,.75);
      font-size:12px;
      white-space:pre-wrap;
    }

    /* Lootbox */
    .lootbox{
      position: fixed; inset: 0; z-index: 9999; display: none; align-items: center; justify-content: center;
      background:
        radial-gradient(circle at 50% 30%, rgba(255,43,74,.14), transparent 55%),
        radial-gradient(circle at 60% 80%, rgba(176,108,255,.12), transparent 55%),
        rgba(0,0,0,.84);
      backdrop-filter: blur(12px);
      padding: 18px;
    }
    .lootbox.on{display:flex;}
    .box{
      width:min(520px, 100%);
      border-radius:22px;border:1px solid rgba(255,255,255,.14);
      background: rgba(10,10,14,.88);
      box-shadow: 0 30px 120px rgba(0,0,0,.75);
      overflow:hidden;
      position:relative;
    }
    .spark{
      position:absolute; inset:0; pointer-events:none;
      background:
        radial-gradient(2px 2px at 15% 30%, rgba(255,255,255,.45), transparent 55%),
        radial-gradient(2px 2px at 35% 65%, rgba(255,255,255,.35), transparent 55%),
        radial-gradient(2px 2px at 70% 25%, rgba(255,255,255,.40), transparent 55%),
        radial-gradient(2px 2px at 82% 60%, rgba(255,255,255,.30), transparent 55%),
        radial-gradient(2px 2px at 55% 40%, rgba(255,255,255,.35), transparent 55%);
      opacity:.55;
      animation: twinkle 1.2s ease infinite;
    }
    @keyframes twinkle{0%,100%{opacity:.38}50%{opacity:.62}}

    .boxTop{padding: 14px; display:flex; align-items:center; justify-content:space-between; gap:10px;}
    .boxTitle{font-weight:1000;letter-spacing:.2px}
    .close{
      border:1px solid rgba(255,255,255,.14); background:rgba(255,255,255,.04);
      color:#fff; border-radius:14px; padding:10px 12px; font-weight:1000; cursor:pointer;
    }
    .boxBody{padding:14px;display:flex;gap:12px;align-items:center;}
    .img{
      width:110px;height:110px;border-radius:18px;object-fit:cover;border:1px solid rgba(255,255,255,.14);
      box-shadow: 0 20px 70px rgba(0,0,0,.55);
      background: radial-gradient(circle at 20% 20%, rgba(255,43,74,.18), rgba(255,255,255,.02));
    }
    .name{font-weight:1000;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .anime{margin-top:4px;color:rgba(255,255,255,.72);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .stars{margin-top:8px;font-size:14px;letter-spacing:1px}
    .stars.common{color:var(--c-common)}
    .stars.rare{color:var(--c-rare)}
    .stars.epic{color:var(--c-epic)}
    .stars.mythic{color:var(--c-mythic)}
    .note{margin-top:10px;color:rgba(255,255,255,.70);font-size:12px;}

    .glow-common{box-shadow: 0 0 0 1px rgba(201,201,201,.14), 0 0 80px rgba(201,201,201,.05) inset;}
    .glow-rare{box-shadow: 0 0 0 1px rgba(77,163,255,.18), 0 0 90px rgba(77,163,255,.09) inset;}
    .glow-epic{box-shadow: 0 0 0 1px rgba(176,108,255,.18), 0 0 90px rgba(176,108,255,.09) inset;}
    .glow-mythic{box-shadow: 0 0 0 1px rgba(255,204,51,.20), 0 0 100px rgba(255,204,51,.11) inset;}
  </style>
</head>
<body>
  <div class="top">
    <div class="title">
      <h1>🎲 Dado</h1>
      <div class="sub">Role e escolha. Nº de opções = valor do dado.</div>
    </div>
    <div class="pill">Dados: <span id="bal">-</span> | Giros: <span id="ext">-</span></div>
  </div>

  <div class="panel">
    <div style="font-weight:1000">Gacha</div>
    <div style="margin-top:6px;color:rgba(255,255,255,.70);font-size:12px;line-height:1.35">
      Se uma opção falhar, tente outra da mesma rolagem sem perder o dado. Se der erro do servidor, o dado é devolvido.
    </div>

    <div class="row">
      <div class="dice" id="dice">🎲</div>
      <button class="btn" id="roll">ROLAR</button>
    </div>

    <div class="grid" id="opts"></div>
    <div class="status" id="status"></div>
  </div>

  <div class="lootbox" id="loot">
    <div class="box" id="box">
      <div class="spark"></div>
      <div class="boxTop">
        <div class="boxTitle">✨ REVELAÇÃO</div>
        <button class="close" id="close">FECHAR</button>
      </div>
      <div class="boxBody">
        <img class="img" id="img" src="" alt="">
        <div style="min-width:0">
          <div class="name" id="nm">...</div>
          <div class="anime" id="an">...</div>
          <div class="stars common" id="st">☆☆☆☆☆</div>
          <div class="note">✅ Entregue no PV do bot</div>
        </div>
      </div>
    </div>
  </div>

  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) { tg.ready(); try { tg.expand(); } catch(e) {} }
    const INIT_DATA = tg?.initData || "";

    async function apiPost(url, body){
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type":"application/json", "X-Telegram-Init-Data": INIT_DATA },
        body: JSON.stringify(body || {})
      });
      const data = await res.json().catch(()=> ({}));
      return { ok: res.ok, status: res.status, data };
    }

    function esc(s){ return String(s||""); }

    const bal = document.getElementById("bal");
    const ext = document.getElementById("ext");
    const dice = document.getElementById("dice");
    const roll = document.getElementById("roll");
    const opts = document.getElementById("opts");
    const status = document.getElementById("status");

    const loot = document.getElementById("loot");
    const close = document.getElementById("close");
    const img = document.getElementById("img");
    const nm = document.getElementById("nm");
    const an = document.getElementById("an");
    const st = document.getElementById("st");
    const box = document.getElementById("box");

    let rollId = null;
    let options = [];

    close.onclick = () => loot.classList.remove("on");
    loot.onclick = (e) => { if(e.target === loot) loot.classList.remove("on"); }

    function starsString(n){
      n = Math.max(1, Math.min(5, Number(n||1)));
      let s="";
      for(let i=0;i<n;i++) s+="★";
      for(let i=n;i<5;i++) s+="☆";
      return s;
    }
    function applyGlow(tier){
      box.classList.remove("glow-common","glow-rare","glow-epic","glow-mythic");
      st.classList.remove("common","rare","epic","mythic");
      if(tier==="mythic"){ box.classList.add("glow-mythic"); st.classList.add("mythic"); }
      else if(tier==="epic"){ box.classList.add("glow-epic"); st.classList.add("epic"); }
      else if(tier==="rare"){ box.classList.add("glow-rare"); st.classList.add("rare"); }
      else { box.classList.add("glow-common"); st.classList.add("common"); }
    }
    function openLoot(character){
      img.src = character.image || "";
      nm.textContent = character.name || "???";
      an.textContent = character.anime || "Obra";
      const rar = character.rarity || {stars:2, tier:"common"};
      st.textContent = starsString(rar.stars || 2);
      applyGlow(rar.tier || "common");
      loot.classList.add("on");
    }

    function animateDice(finalValue){
      const faces = ["🎲","🎯","🎲","🎴","🎲","✨","🎲","🔥","🎲"];
      let i=0;
      dice.classList.add("wobble");
      const t=setInterval(()=>{
        dice.textContent = faces[i % faces.length];
        i++;
      }, 90);
      setTimeout(()=>{
        clearInterval(t);
        dice.textContent = "🎲 " + String(finalValue||"");
        dice.classList.remove("wobble");
      }, 720);
    }

    function renderOptions(){
      opts.innerHTML = "";
      if(!options.length){
        opts.innerHTML = `<div style="grid-column:1/-1;color:rgba(255,255,255,.68);font-size:12px;padding:8px;">
          Role para aparecerem opções.
        </div>`;
        return;
      }
      options.forEach(o=>{
        const b=document.createElement("button");
        b.className="opt";
        b.innerHTML = `<div class="optTitle">🎴 ${esc(o.title || "Anime")}</div>`;
        b.onclick = () => pick(o.id, b);
        opts.appendChild(b);
      });
    }

    async function pick(animeId, btn){
      if(!rollId) return;
      btn.disabled = true; btn.style.opacity=.7;
      status.textContent = "Processando...";

      const out = await apiPost(`/dado/pick?roll_id=${encodeURIComponent(rollId)}&anime_id=${encodeURIComponent(animeId)}`);
      const data = out.data || {};

      if(!data.ok){
        btn.disabled = false; btn.style.opacity=1;

        if(data.error === "try_other"){
          status.textContent = "⚠️ Essa opção falhou. Escolha outra da lista.";
          try{ tg?.showAlert?.("⚠️ Essa opção falhou. Escolha outra da lista."); }catch(e){}
          return;
        }
        if(data.error === "expired_refunded"){
          status.textContent = "⏳ Expirou. Seu dado foi devolvido. Role novamente.";
          try{ tg?.showAlert?.("⏳ Expirou. Seu dado foi devolvido. Role novamente."); }catch(e){}
          rollId = null; options=[]; renderOptions();
          return;
        }
        if(data.error === "server_error_refunded"){
          status.textContent = "❌ Erro do servidor. Seu dado foi devolvido. Role novamente.";
          try{ tg?.showAlert?.("❌ Erro do servidor. Seu dado foi devolvido. Role novamente."); }catch(e){}
          rollId = null; options=[]; renderOptions();
          return;
        }

        status.textContent = "❌ Falha ao entregar. Tente outra opção ou role de novo.";
        try{ tg?.showAlert?.("❌ Falha ao entregar. Tente outra opção ou role de novo."); }catch(e){}
        return;
      }

      status.textContent = "✅ Entregue no PV!";
      openLoot(data.character || {});
      rollId = null;
      options = [];
      renderOptions();
    }

    roll.onclick = async () => {
      roll.disabled = true;
      roll.textContent = "ROLANDO...";
      status.textContent = "";

      const out = await apiPost("/dado/start", {});
      const data = out.data || {};

      if(!data.ok){
        roll.disabled = false;
        roll.textContent = "ROLAR";
        if(data.error === "no_balance"){
          status.textContent = data.msg || "Sem saldo.";
          try{ tg?.showAlert?.(data.msg || "Sem saldo."); }catch(e){}
          return;
        }
        if(data.error === "server_error_refunded"){
          status.textContent = "❌ Erro do servidor. Seu dado foi devolvido. Tente de novo.";
          try{ tg?.showAlert?.("❌ Erro do servidor. Seu dado foi devolvido. Tente de novo."); }catch(e){}
          return;
        }
        status.textContent = "❌ Falha ao rolar. Tente novamente.";
        try{ tg?.showAlert?.("❌ Falha ao rolar. Tente novamente."); }catch(e){}
        return;
      }

      rollId = data.roll_id;
      bal.textContent = String(data.balance ?? "-");
      ext.textContent = String(data.extra ?? "-");

      animateDice(data.dice);
      options = Array.isArray(data.options) ? data.options : [];
      renderOptions();

      status.textContent = `🎯 Escolha 1 das ${options.length} opções (dado: ${data.dice}).`;
      roll.disabled = false;
      roll.textContent = "ROLAR DE NOVO";
    };

    renderOptions();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


# =========================
# UI: /shop — Loja (Vender + Comprar (GIRO + DADO + MAX))
# =========================
@app.get("/shop", response_class=HTMLResponse)
def miniapp_shop():
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1, viewport-fit=cover">
  <title>Baltigo • Loja</title>
  <style>
  {_bg_css_block()}
  .top{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:4px;position:relative;z-index:2;}}
  .title{{display:flex;flex-direction:column;gap:3px;min-width:0;}}
  .title h1{{margin:0;font-size:18px;font-weight:1000;}}
  .title .sub{{font-size:12px;color:var(--muted2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .stats{{
    display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--stroke);
    background:rgba(255,255,255,.035);border-radius:999px;white-space:nowrap;
    box-shadow: 0 12px 38px rgba(0,0,0,.35);
    backdrop-filter: blur(12px);
  }}
  .stat{{display:flex;align-items:center;gap:6px;font-weight:950;font-size:13px;}}
  .dot{{width:1px;height:16px;background:var(--stroke);}}

  .tabs{{
    display:flex;gap:10px;margin:14px 0 12px;padding:8px;border:1px solid var(--stroke);
    border-radius:999px;background:rgba(255,255,255,.035);
    box-shadow: 0 14px 46px rgba(0,0,0,.35);
    backdrop-filter: blur(12px);
    position:relative;z-index:2;
  }}
  .tab{{
    flex:1;text-align:center;padding:10px 12px;border-radius:999px;font-weight:950;font-size:14px;color:var(--muted);
    background:transparent;border:0;cursor:pointer;transition: transform .12s ease;
  }}
  .tab:active{{transform: scale(.98);}}
  .tab.active{{
    color:#fff;background:linear-gradient(90deg, rgba(255,43,74,.92), rgba(176,108,255,.70));
    box-shadow:0 14px 44px rgba(255,43,74,.10);
  }}

  .status{{margin:10px 0;padding:10px 12px;border-radius:14px;border:1px solid var(--stroke);background:rgba(255,255,255,.03);color:var(--muted);font-size:13px;white-space:pre-wrap;backdrop-filter: blur(12px);position
:absolute;z-index:2;}

  </style>
</head>

<body>

<div class="top">
  <div class="title">
    <h1>🛒 Loja Baltigo</h1>
    <div class="sub">Compre giros e dados</div>
  </div>
</div>

<div style="margin-top:20px;color:white;font-family:sans-serif">
<p>Interface da loja carregada.</p>
</div>

</body>
</html>
"""
    return HTMLResponse(content=html)
