# webapp.py — MiniApps (Coleção + Loja + Dado) — ULTRA PREMIUM (1 arquivo)
# -----------------------------------------------------------------------------
# ✅ 3 sessões separadas:
#   /app  -> Coleção (galeria premium)
#   /shop -> Loja (estilo jogo)
#   /dado -> Dado (3D + gacha)
#
# ✅ Visual padrão igual nas 3 telas:
#   - Glow radial no fundo
#   - Partículas animadas (canvas)
#   - Glassmorphism nos cards
#   - Micro animações nos botões
#   - Cards premium + brilho
#   - Raridade animada (Common/Rare/Epic/Mythic)
#   - Abertura de carta estilo gacha + sparkle para raros
#   - Mini thumb nas opções (quando disponível; fallback bonito)
#
# ✅ Backend:
#   - Rotas /dado/start e /dado/pick (e /api/dado/* compat)
#   - Nº de opções = valor do dado (1..6)
#   - Refund se erro hard no fluxo do dado
#   - Loja: comprar GIRO, comprar DADO, comprar MAX
#
# Obs:
# - Este arquivo espera que seu database.py tenha (ou tente ter) as funções usadas.
# - Quando alguma função não existir, o código tenta fallback seguro.
# -----------------------------------------------------------------------------

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
SHOP_GIRO_PRICE = int(os.getenv("SHOP_GIRO_PRICE", "2"))
SHOP_DADO_PRICE = int(os.getenv("SHOP_DADO_PRICE", "1"))
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
    return {"fav_name": _safe_str(row.get("fav_name")), "fav_image": _safe_str(row.get("fav_image"))}


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
    payload = {"chat_id": int(chat_id), "photo": photo, "caption": caption, "parse_mode": "HTML", "disable_web_page_preview": True}
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
          coverImage { medium }
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
                cover = (m.get("coverImage") or {}).get("medium") or ""
                if anime_id is None:
                    continue
                items.append({"anime_id": int(anime_id), "title": title, "rank": rank, "cover": cover})
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

        cover = _safe_str(r.get("cover") or r.get("cover_image") or r.get("image") or r.get("thumb") or "")

        out.append({"id": int(opt_id), "title": title, "cover": cover})
        seen.add(title)
        opt_id += 1

        if len(out) >= n:
            break

    return out


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

    return JSONResponse({"ok": True, "mode": "me", "owner_id": user_id, "owner_name": first_name,
                         "collection_name": collection_name, "coins": coins, "giros": giros, "fav": fav, "cards": cards})


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

    return JSONResponse({"ok": True, "mode": "owner", "owner_id": owner_id, "owner_name": owner_name,
                         "collection_name": collection_name, "coins": coins, "giros": giros, "fav": fav, "cards": cards})


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

        out.append({"character_id": char_id, "character_name": name, "anime_title": anime,
                    "quantity": qty, "image": image, "custom_image": custom_image})

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

    return JSONResponse({"ok": True, "sold": {"character_id": char_id, "character_name": sold_name},
                         "coins": coins, "giros": giros, "sell_gain": SHOP_SELL_GAIN})


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

    return JSONResponse({"ok": True, "coins": coins, "giros": giros,
                         "dado_balance": int(dado_balance), "extra": int(extra),
                         "qty": int(qty), "price_each": int(SHOP_DADO_PRICE)})


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

    return JSONResponse({"ok": True, "coins": coins2, "giros": giros,
                         "dado_balance": int(dado_balance), "extra": int(extra),
                         "qty": int(max_qty), "price_each": int(SHOP_DADO_PRICE)})


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

        return JSONResponse({"ok": True, "roll_id": int(roll_id), "dice": int(dice_value),
                             "options": options, "balance": int(balance2), "extra": int(extra2)})
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
            caption=("🎁 <b>VOCÊ GANHOU!</b>\n\n"
                     f"🧧 <code>{char_id}</code>. <b>{name}</b>\n"
                     f"<i>{anime_title}</i>\n\n"
                     "📦 <b>Adicionado à sua coleção!</b>"),
        )

        rarity = _choose_rarity(dice_value=dice_value, char_id=char_id)
        return JSONResponse({"ok": True, "character": {"id": char_id, "name": name, "anime": anime_title, "image": image, "rarity": rarity}}, status_code=200)

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
# API: DADO (compat /api/dado/*)
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
async def api_dado_pick(anime_id: int = Query(...), roll_id: int = Query(...), x_telegram_init_data: str = Header(default="")):
    return await _dado_pick_impl(anime_id, roll_id, x_telegram_init_data)


# =========================
# API: DADO (rotas novas /dado/start e /dado/pick)
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
async def dado_pick_bar(anime_id: int = Query(...), roll_id: int = Query(...), x_telegram_init_data: str = Header(default="")):
    return await _dado_pick_impl(anime_id, roll_id, x_telegram_init_data)


# =========================
# UI Theme (shared)
# =========================
def _theme_css() -> str:
    # CSS compartilhado, sem f-strings com { } dentro do HTML (evita erro de f-string)
    return r"""
:root{
  --bg0:#05050a;
  --bg1:#0a0914;
  --glass: rgba(255,255,255,.055);
  --glass2: rgba(255,255,255,.035);
  --stroke: rgba(255,255,255,.12);
  --muted: rgba(255,255,255,.72);
  --muted2: rgba(255,255,255,.52);

  --a1:#ff2b4a;
  --a2:#b30f22;
  --a3:#ff6a88;
  --a4:#b06cff;
  --a5:#4da3ff;

  --c-common:#c9c9c9;
  --c-rare:#4da3ff;
  --c-epic:#b06cff;
  --c-mythic:#ffcc33;

  --shadow: 0 22px 70px rgba(0,0,0,.55);
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  color:#fff;
  padding:14px 14px 90px;
  overflow-x:hidden;
  background:
    radial-gradient(1000px 600px at 18% 0%, rgba(255,43,74,.18), transparent 60%),
    radial-gradient(900px 600px at 85% 10%, rgba(176,108,255,.16), transparent 60%),
    radial-gradient(1000px 700px at 50% 110%, rgba(77,163,255,.12), transparent 60%),
    linear-gradient(180deg, var(--bg1), var(--bg0));
  background-attachment: fixed;
}
#fx{
  position:fixed; inset:0;
  pointer-events:none;
  z-index:0;
}
.wrap{position:relative; z-index:2; max-width:860px; margin:0 auto;}
.glass{
  border:1px solid var(--stroke);
  background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.03));
  backdrop-filter: blur(14px);
  box-shadow: var(--shadow);
}
.top{
  display:flex; align-items:center; justify-content:space-between; gap:12px;
  margin-top:4px;
}
.title{display:flex; flex-direction:column; gap:3px; min-width:0;}
.title h1{margin:0; font-size:18px; font-weight:1000; letter-spacing:.2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.title .sub{font-size:12px; color:var(--muted2); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.pills{
  display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:999px;
  border:1px solid var(--stroke); background:rgba(255,255,255,.04); backdrop-filter: blur(14px);
  box-shadow: 0 16px 46px rgba(0,0,0,.45);
  flex-shrink:0;
}
.pill{display:flex; align-items:center; gap:6px; font-weight:950; font-size:13px;}
.sep{width:1px; height:16px; background:rgba(255,255,255,.14);}
.tabs{
  display:flex; gap:10px; margin:14px 0 12px;
  padding:8px; border-radius:999px; border:1px solid var(--stroke);
  background:rgba(255,255,255,.04); backdrop-filter: blur(14px);
  box-shadow: 0 18px 60px rgba(0,0,0,.45);
}
.tab{
  flex:1; text-align:center; padding:10px 12px; border-radius:999px;
  font-weight:950; font-size:14px; color:rgba(255,255,255,.78);
  background:transparent; border:0; cursor:pointer;
  transition: transform .12s ease, filter .12s ease;
}
.tab:active{transform: scale(.98)}
.tab.active{
  color:#fff;
  background: linear-gradient(90deg, rgba(255,43,74,.95), rgba(176,108,255,.75));
  box-shadow: 0 16px 60px rgba(255,43,74,.10);
}
.row{display:flex; gap:10px; align-items:center;}
.input{
  width:100%; padding:12px 12px; border-radius:14px;
  border:1px solid var(--stroke); background:rgba(255,255,255,.04);
  color:#fff; outline:none; font-size:14px;
  backdrop-filter: blur(14px);
}
.input::placeholder{color:rgba(255,255,255,.38)}
.btn{
  border:0; border-radius:16px; padding:14px 14px;
  font-weight:1000; font-size:14px; color:#fff;
  background: linear-gradient(90deg, rgba(255,43,74,.95), rgba(176,108,255,.75));
  box-shadow: 0 20px 70px rgba(255,43,74,.10);
  cursor:pointer;
  transition: transform .12s ease, filter .12s ease, opacity .12s ease;
}
.btn:hover{filter:brightness(1.06)}
.btn:active{transform:scale(.98)}
.btn.secondary{
  background: rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.14);
  box-shadow: 0 18px 60px rgba(0,0,0,.35);
}
.btn:disabled{opacity:.55; cursor:not-allowed}
.badge{
  display:inline-flex; align-items:center; gap:8px;
  padding:8px 10px; border-radius:999px; border:1px solid rgba(255,255,255,.14);
  background: rgba(0,0,0,.40); backdrop-filter: blur(12px);
  font-weight:1000; font-size:12px;
}
.bdot{width:8px;height:8px;border-radius:99px;background:#fff;opacity:.9}
@keyframes pulseGlow{0%,100%{transform:scale(1);filter:brightness(1)}50%{transform:scale(1.03);filter:brightness(1.15)}}
.badge.rare{border-color: rgba(77,163,255,.22)}
.badge.epic{border-color: rgba(176,108,255,.22)}
.badge.mythic{border-color: rgba(255,204,51,.22)}
.badge.rare .bdot{background:var(--c-rare)}
.badge.epic .bdot{background:var(--c-epic)}
.badge.mythic .bdot{background:var(--c-mythic)}
.badge.rare,.badge.epic,.badge.mythic{animation:pulseGlow 1.2s ease-in-out infinite}

.toast{
  margin:10px 0; padding:10px 12px; border-radius:14px; border:1px solid var(--stroke);
  background:rgba(255,255,255,.03); color:rgba(255,255,255,.80);
  font-size:13px; white-space:pre-wrap; backdrop-filter: blur(14px);
}
.toast.ok{border-color: rgba(0,255,140,.18)}
.toast.err{border-color: rgba(255,60,60,.18); color: rgba(255,140,140,.95)}
/* cards premium */
.grid{
  display:grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap:12px;
}
@media (min-width: 520px){
  .grid{grid-template-columns: repeat(3, minmax(0, 1fr));}
}
.card{
  position:relative; border-radius:22px; overflow:hidden; border:1px solid var(--stroke);
  background: rgba(18,17,27,.92);
  box-shadow: 0 20px 70px rgba(0,0,0,.55);
  transform: translateZ(0);
}
.card .img{
  width:100%; height:220px; object-fit:cover; display:block;
  filter:saturate(1.08) contrast(1.06);
}
.card .overlay{
  position:absolute; left:0; right:0; bottom:0;
  padding:12px;
  background: linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.86));
}
.card .name{margin:0; font-weight:1000; font-size:14px; letter-spacing:.1px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.card .meta{margin-top:4px; font-size:12px; color:rgba(255,255,255,.78); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.card .chip{
  position:absolute; top:10px; left:10px;
  padding:7px 10px; border-radius:999px;
  background: rgba(0,0,0,.45); border:1px solid rgba(255,255,255,.14);
  backdrop-filter: blur(12px);
  font-weight:1000; font-size:12px;
}
.card .shine{
  position:absolute; inset:-40%;
  background: radial-gradient(circle at 30% 30%, rgba(255,255,255,.24), transparent 40%);
  transform: rotate(12deg);
  opacity:0; pointer-events:none;
  transition: opacity .2s ease;
  mix-blend-mode: screen;
}
.card:hover .shine{opacity:.28}
.card:active .shine{opacity:.40}
.card.common{border-color: rgba(255,255,255,.10)}
.card.rare{border-color: rgba(77,163,255,.18)}
.card.epic{border-color: rgba(176,108,255,.18)}
.card.mythic{border-color: rgba(255,204,51,.18)}
/* overlay raridade */
.card .rar{
  position:absolute; top:10px; right:10px;
}
"""


def _fx_js() -> str:
    # Canvas partículas + glow mouse leve
    return r"""
<script>
(function(){
  const c = document.getElementById("fx");
  if(!c) return;
  const ctx = c.getContext("2d", { alpha:true });
  let W=0,H=0, DPR=1;
  const pts = [];
  const N = 70;

  function resize(){
    DPR = Math.min(2, window.devicePixelRatio || 1);
    W = window.innerWidth; H = window.innerHeight;
    c.width = Math.floor(W * DPR);
    c.height = Math.floor(H * DPR);
    c.style.width = W+"px";
    c.style.height = H+"px";
  }
  window.addEventListener("resize", resize);
  resize();

  function rand(a,b){ return a + Math.random()*(b-a); }
  function reset(p){
    p.x = rand(0,W); p.y = rand(0,H);
    p.vx = rand(-.18,.18); p.vy = rand(-.12,.22);
    p.r = rand(1.0,2.4);
    p.a = rand(.08,.22);
  }
  for(let i=0;i<N;i++){ const p={}; reset(p); pts.push(p); }

  let mx=W*0.3, my=H*0.2;
  window.addEventListener("pointermove",(e)=>{ mx=e.clientX; my=e.clientY; }, {passive:true});

  function draw(){
    ctx.setTransform(DPR,0,0,DPR,0,0);
    ctx.clearRect(0,0,W,H);

    // glow radial mouse
    const g = ctx.createRadialGradient(mx,my,0,mx,my,380);
    g.addColorStop(0,"rgba(255,43,74,.10)");
    g.addColorStop(.55,"rgba(176,108,255,.07)");
    g.addColorStop(1,"rgba(0,0,0,0)");
    ctx.fillStyle=g; ctx.fillRect(0,0,W,H);

    // particles
    for(const p of pts){
      p.x += p.vx; p.y += p.vy;
      if(p.x<-40) p.x=W+40;
      if(p.x>W+40) p.x=-40;
      if(p.y<-40) p.y=H+40;
      if(p.y>H+40) p.y=-40;

      ctx.beginPath();
      ctx.fillStyle = "rgba(255,255,255,"+p.a+")";
      ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fill();
    }

    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();
</script>
"""


def _tg_js_init() -> str:
    return r"""
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script>
  const tg = window.Telegram?.WebApp;
  if (tg) { tg.ready(); try { tg.expand(); } catch(e) {} }
  const INIT_DATA = tg?.initData || "";
  function apiGet(url){
    return fetch(url, { headers: { "X-Telegram-Init-Data": INIT_DATA } })
      .then(async r => ({ ok:r.ok, status:r.status, data: await r.json().catch(()=>({})) }))
  }
  function apiPost(url, body){
    return fetch(url, {
      method:"POST",
      headers: { "Content-Type":"application/json", "X-Telegram-Init-Data": INIT_DATA },
      body: JSON.stringify(body||{})
    }).then(async r => ({ ok:r.ok, status:r.status, data: await r.json().catch(()=>({})) }))
  }
  function esc(s){
    return String(s||"").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }
</script>
"""


# =========================
# UI: /app — Coleção (galeria premium)
# =========================
@app.get("/app", response_class=HTMLResponse)
def miniapp_collection():
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1, viewport-fit=cover'>"
        "<title>Baltigo • Coleção</title>"
        "<style>" + _theme_css() + r"""
.section{
  margin-top:12px;
  padding:12px;
  border-radius:22px;
}
.sectionHeader{
  display:flex; align-items:center; justify-content:space-between; gap:12px;
  margin:2px 4px 12px;
}
.sectionHeader .h{
  font-weight:1000; font-size:14px; color:rgba(255,255,255,.92);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.sectionHeader .c{
  font-size:12px; color:rgba(255,255,255,.55); font-weight:950;
}
.search{margin:10px 0 14px;}
.empty{
  color:rgba(255,255,255,.68);
  font-size:13px;
  padding:8px 4px;
}
.hero{
  margin-top:14px;
  padding:14px;
  border-radius:24px;
  border:1px solid var(--stroke);
  background: radial-gradient(800px 320px at 10% 0%, rgba(255,43,74,.16), transparent 60%),
              radial-gradient(800px 320px at 90% 10%, rgba(176,108,255,.12), transparent 60%),
              rgba(255,255,255,.03);
  backdrop-filter: blur(14px);
  box-shadow: 0 22px 70px rgba(0,0,0,.55);
}
.heroRow{display:flex; gap:12px; align-items:center; justify-content:space-between;}
.heroLeft{min-width:0}
.heroTitle{font-weight:1000; font-size:14px; margin:0 0 4px; letter-spacing:.2px;}
.heroHint{font-size:12px; color:rgba(255,255,255,.65); line-height:1.35;}
""" + "</style></head><body>"
        "<canvas id='fx'></canvas><div class='wrap'>"
        "<div class='top'>"
        "<div class='title'><h1 id='h1'>Minha coleção</h1><div class='sub' id='sub'>Carregando...</div></div>"
        "<div class='pills'><div class='pill'>🪙 <span id='coins'>-</span></div><div class='sep'></div>"
        "<div class='pill'>🎡 <span id='giros'>-</span></div></div>"
        "</div>"
        "<div class='tabs glass'><button class='tab active' id='tab_all'>📦 Coleção</button>"
        "<button class='tab' id='tab_fav'>⭐ Favorito</button></div>"
        "<div class='hero'><div class='heroRow'>"
        "<div class='heroLeft'><div class='heroTitle'>🖼️ Galeria</div>"
        "<div class='heroHint'>Toque em cards, use a busca e navegue por animes. Tudo com visual premium.</div></div>"
        "<div class='badge'><span class='bdot'></span> PREMIUM UI</div>"
        "</div></div>"
        "<div class='search'><input class='input glass' id='q' placeholder='Buscar personagem, anime ou ID...' /></div>"
        "<div class='toast' id='toast'>Conectando...</div>"
        "<div id='sections'></div>"
        + _tg_js_init()
        + r"""
<script>
  let allCards = [];
  let mode = "all";
  let favProfile = { fav_name:"", fav_image:"" };

  function setToast(text, type){
    const el = document.getElementById("toast");
    el.className = "toast" + (type ? (" " + type) : "");
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

  function getCharacterName(c){ return pickFirstString(c, ["character_name","name","character","nome","char_name"]) || "Personagem"; }
  function getAnimeTitle(c){ return pickFirstString(c, ["anime_title","anime","obra","title","series"]) || "Sem anime"; }
  function getImageUrl(c){ return pickFirstString(c, ["custom_image","image","img","photo","picture","url"]) || ""; }
  function getCharId(c){ return pickFirstNumber(c, ["character_id","char_id","id","card_id"]) ?? 0; }
  function getQty(c){ return pickFirstNumber(c, ["quantity","qty","qtd","amount","count"]) ?? 1; }

  function tierFromQty(q){
    if(q >= 8) return "mythic";
    if(q >= 5) return "epic";
    if(q >= 3) return "rare";
    return "common";
  }
  function cmpAZ(a,b){ return String(a).localeCompare(String(b),"pt-BR",{sensitivity:"base"}); }

  function buildGroups(list){
    const groups = new Map();
    for(const c of list){
      const anime = getAnimeTitle(c) || "Sem anime";
      if(!groups.has(anime)) groups.set(anime, []);
      groups.get(anime).push(c);
    }
    const animeTitles = Array.from(groups.keys()).sort(cmpAZ);
    return animeTitles.map(t => {
      const cards = groups.get(t) || [];
      cards.sort((x,y)=>cmpAZ(getCharacterName(x), getCharacterName(y)));
      return { title:t, cards };
    });
  }

  function render(){
    const q = (document.getElementById("q").value || "").trim().toLowerCase();
    const root = document.getElementById("sections");
    root.innerHTML = "";

    if(mode === "fav"){
      const favName = (favProfile?.fav_name || "").trim();
      const favImg  = (favProfile?.fav_image || "").trim();
      if(!favName){
        root.innerHTML = "<div class='empty'>Você ainda não definiu um favorito.</div>";
        return;
      }
      const c = { character_name:favName, anime_title:"Favorito", image:favImg, quantity:1, character_id:0 };
      const section = document.createElement("div");
      section.className = "section glass";
      section.innerHTML = "<div class='sectionHeader'><div class='h'>⭐ Favorito</div><div class='c'>1</div></div>";
      const grid = document.createElement("div");
      grid.className = "grid";
      const card = document.createElement("div");
      card.className = "card mythic";
      card.innerHTML = `
        <div class="shine"></div>
        ${favImg ? `<img class="img" src="${esc(favImg)}" alt="">` : `<div style="height:220px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.55)">Sem imagem</div>`}
        <div class="chip">⭐ FAVORITO</div>
        <div class="rar badge mythic" style="position:absolute;top:10px;right:10px;"><span class="bdot"></span> MYTHIC</div>
        <div class="overlay">
          <div class="name">${esc(favName)}</div>
          <div class="meta">Seu favorito</div>
        </div>
      `;
      grid.appendChild(card);
      section.appendChild(grid);
      root.appendChild(section);
      return;
    }

    let filtered = allCards;
    if(q){
      filtered = filtered.filter(c=>{
        const name = getCharacterName(c).toLowerCase();
        const anime = getAnimeTitle(c).toLowerCase();
        const id = String(getCharId(c));
        return name.includes(q) || anime.includes(q) || id.includes(q);
      });
    }

    if(!filtered.length){
      root.innerHTML = "<div class='empty'>Nenhum card encontrado.</div>";
      return;
    }

    const groups = buildGroups(filtered);
    for(const g of groups){
      const section = document.createElement("div");
      section.className = "section glass";

      const header = document.createElement("div");
      header.className = "sectionHeader";
      header.innerHTML = `<div class='h'>${esc(g.title)}</div><div class='c'>${g.cards.length}</div>`;
      section.appendChild(header);

      const grid = document.createElement("div");
      grid.className = "grid";

      for(const c of g.cards){
        const img = getImageUrl(c);
        const qty = getQty(c);
        const id  = getCharId(c);
        const nm  = getCharacterName(c);
        const tier = tierFromQty(qty);

        const card = document.createElement("div");
        card.className = "card " + tier;

        const badgeClass = (tier==="common") ? "badge" : ("badge " + tier);
        const label = tier.toUpperCase();

        card.innerHTML = `
          <div class="shine"></div>
          ${img ? `<img class="img" src="${esc(img)}" alt="">` : `<div style="height:220px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.55)">Sem imagem</div>`}
          <div class="chip">x${qty} • ID ${id}</div>
          <div class="rar ${badgeClass}" style="position:absolute;top:10px;right:10px;"><span class="bdot"></span> ${label}</div>
          <div class="overlay">
            <div class="name">${esc(nm)}</div>
            <div class="meta">${esc(g.title)}</div>
          </div>
        `;
        grid.appendChild(card);
      }

      section.appendChild(grid);
      root.appendChild(section);
    }
  }

  async function load(){
    try{
      setToast("Carregando...", "");
      const params = new URLSearchParams(window.location.search);
      const u = params.get("u");
      const ts = params.get("ts");
      const sig = params.get("sig") || "";

      let apiUrl = "/api/me/collection";
      let viewingOwner = false;
      if(u && ts){
        apiUrl = `/api/collection?u=${encodeURIComponent(u)}&ts=${encodeURIComponent(ts)}&sig=${encodeURIComponent(sig)}`;
        viewingOwner = true;
      }

      const r = await apiGet(apiUrl);
      if(!r.ok){
        setToast("❌ Falha ao carregar.\n\nStatus: " + r.status + "\n" + JSON.stringify(r.data||{}), "err");
        document.getElementById("sub").textContent = "Erro: " + r.status;
        return;
      }

      const data = r.data || {};
      if(viewingOwner && data.owner_name){
        document.getElementById("h1").textContent = "Coleção de " + data.owner_name;
      } else {
        document.getElementById("h1").textContent = data.collection_name || "Minha coleção";
      }

      document.getElementById("sub").textContent = "Cards: " + (data.cards?.length || 0);
      document.getElementById("coins").textContent = String(data.coins ?? "-");
      document.getElementById("giros").textContent = String(data.giros ?? "-");

      favProfile = data.fav || { fav_name:"", fav_image:"" };
      allCards = Array.isArray(data.cards) ? data.cards : [];

      setToast("✅ Pronto.", "ok");
      render();
    }catch(e){
      setToast("❌ Erro inesperado.", "err");
    }
  }

  const tabAll = document.getElementById("tab_all");
  const tabFav = document.getElementById("tab_fav");
  function setTab(which){
    [tabAll, tabFav].forEach(t=>t.classList.remove("active"));
    if(which==="all") tabAll.classList.add("active");
    if(which==="fav") tabFav.classList.add("active");
  }
  tabAll.onclick = ()=>{ mode="all"; setTab("all"); render(); };
  tabFav.onclick = ()=>{ mode="fav"; setTab("fav"); render(); };

  document.getElementById("q").addEventListener("input", render);
  load();
</script>
""" + _fx_js() + "</div></body></html>"
    )
    return HTMLResponse(content=html)


# =========================
# UI: /dado — Dado 3D + gacha premium
# =========================
@app.get("/dado", response_class=HTMLResponse)
def miniapp_dado():
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1, viewport-fit=cover'>"
        "<title>Baltigo • Dado</title>"
        "<style>" + _theme_css() + r"""
.panel{margin-top:14px; padding:14px; border-radius:22px;}
.h2{font-weight:1000; font-size:14px; margin:0 0 6px;}
.hint{color:rgba(255,255,255,.68); font-size:12px; line-height:1.35;}
.diceRow{display:flex; gap:12px; align-items:center; margin-top:14px;}
/* 3D dice */
.scene{width:84px; height:84px; perspective:520px;}
.cube{
  width:84px; height:84px; position:relative;
  transform-style:preserve-3d;
  transform: rotateX(-18deg) rotateY(22deg);
  transition: transform 700ms cubic-bezier(.2,.85,.2,1);
}
.face{
  position:absolute; width:84px; height:84px; border-radius:18px;
  background: radial-gradient(circle at 18% 18%, rgba(255,255,255,.20), rgba(255,255,255,.03));
  border:1px solid rgba(255,255,255,.14);
  display:flex; align-items:center; justify-content:center;
  box-shadow: inset 0 0 40px rgba(255,255,255,.05);
}
.pips{width:44px;height:44px; position:relative;}
.pip{
  width:8px;height:8px;border-radius:99px;background:rgba(255,255,255,.92);
  position:absolute;
  box-shadow: 0 0 14px rgba(255,255,255,.25);
}
.face1{transform: rotateY(0deg) translateZ(42px);}
.face2{transform: rotateY(90deg) translateZ(42px);}
.face3{transform: rotateY(180deg) translateZ(42px);}
.face4{transform: rotateY(-90deg) translateZ(42px);}
.face5{transform: rotateX(90deg) translateZ(42px);}
.face6{transform: rotateX(-90deg) translateZ(42px);}
@keyframes cubeRoll{
  0%{transform: rotateX(-18deg) rotateY(22deg) rotateZ(0deg)}
  50%{transform: rotateX(260deg) rotateY(320deg) rotateZ(120deg)}
  100%{transform: rotateX(-18deg) rotateY(22deg) rotateZ(0deg)}
}
.rolling{animation:cubeRoll 740ms cubic-bezier(.2,.85,.2,1) 1;}
/* options */
.opts{margin-top:14px; display:grid; grid-template-columns:repeat(2,1fr); gap:10px;}
.opt{
  text-align:left;
  border:1px solid rgba(255,255,255,.14);
  background: rgba(255,255,255,.04);
  border-radius:18px;
  padding:10px;
  cursor:pointer;
  transition: transform .12s ease, border-color .12s ease, filter .12s ease;
  backdrop-filter: blur(14px);
  display:flex; gap:10px; align-items:center;
  overflow:hidden;
}
.opt:hover{border-color: rgba(255,43,74,.22); filter:brightness(1.03)}
.opt:active{transform:scale(.98)}
.thumb{
  width:42px;height:42px;border-radius:14px;border:1px solid rgba(255,255,255,.14);
  background: radial-gradient(circle at 20% 20%, rgba(255,43,74,.18), rgba(255,255,255,.02));
  object-fit:cover; flex-shrink:0;
}
.optTitle{font-weight:1000;font-size:12px;line-height:1.2;max-height:2.4em;overflow:hidden;}
.status{margin-top:12px;color:rgba(255,255,255,.75);font-size:12px;white-space:pre-wrap;}
/* loot modal */
.loot{
  position:fixed; inset:0; z-index:9999; display:none; align-items:center; justify-content:center;
  background:
    radial-gradient(circle at 50% 30%, rgba(255,43,74,.14), transparent 55%),
    radial-gradient(circle at 60% 80%, rgba(176,108,255,.12), transparent 55%),
    rgba(0,0,0,.84);
  backdrop-filter: blur(14px);
  padding: 18px;
}
.loot.on{display:flex;}
.box{
  width:min(560px, 100%);
  border-radius:26px;
  border:1px solid rgba(255,255,255,.14);
  background: rgba(10,10,14,.90);
  box-shadow: 0 34px 140px rgba(0,0,0,.78);
  overflow:hidden;
  position:relative;
  transform: translateZ(0);
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
  animation: twinkle 1.1s ease infinite;
}
@keyframes twinkle{0%,100%{opacity:.38}50%{opacity:.68}}
.boxTop{padding: 14px; display:flex; align-items:center; justify-content:space-between; gap:10px;}
.boxTitle{font-weight:1000; letter-spacing:.2px}
.close{
  border:1px solid rgba(255,255,255,.14); background:rgba(255,255,255,.04);
  color:#fff; border-radius:14px; padding:10px 12px; font-weight:1000; cursor:pointer;
  transition: transform .12s ease, filter .12s ease;
}
.close:hover{filter:brightness(1.06)}
.close:active{transform:scale(.98)}
.boxBody{padding:14px; display:flex; gap:12px; align-items:center;}
.cardFlip{
  width:126px; height:170px; border-radius:22px; perspective:900px; flex-shrink:0;
}
.cardInner{
  width:100%; height:100%; position:relative; transform-style:preserve-3d;
  animation: flip 820ms cubic-bezier(.2,.85,.2,1) 1;
}
@keyframes flip{0%{transform:rotateY(0)}60%{transform:rotateY(180deg)}100%{transform:rotateY(180deg)}}
.front, .back{
  position:absolute; inset:0; border-radius:22px; overflow:hidden;
  backface-visibility:hidden;
  border:1px solid rgba(255,255,255,.14);
}
.front{
  background: radial-gradient(circle at 20% 20%, rgba(255,43,74,.20), rgba(255,255,255,.02));
  display:flex; align-items:center; justify-content:center;
  font-weight:1000; letter-spacing:.2px;
}
.back{
  transform: rotateY(180deg);
  background: rgba(18,17,27,.92);
}
.back img{
  width:100%; height:100%; object-fit:cover; display:block;
  filter:saturate(1.08) contrast(1.06);
}
.back .backShade{
  position:absolute; inset:0;
  background: linear-gradient(180deg, rgba(0,0,0,.05), rgba(0,0,0,.70));
}
.back .backMeta{
  position:absolute; left:0; right:0; bottom:0; padding:10px;
}
.bName{font-weight:1000; font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.bAnime{margin-top:4px; font-size:12px; color:rgba(255,255,255,.76); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.stars{margin-top:10px; font-size:14px; letter-spacing:1px;}
/* rarity glow */
.glow-common{box-shadow: 0 0 0 1px rgba(201,201,201,.14), 0 0 90px rgba(201,201,201,.06) inset;}
.glow-rare{box-shadow: 0 0 0 1px rgba(77,163,255,.18), 0 0 100px rgba(77,163,255,.10) inset;}
.glow-epic{box-shadow: 0 0 0 1px rgba(176,108,255,.18), 0 0 110px rgba(176,108,255,.10) inset;}
.glow-mythic{box-shadow: 0 0 0 1px rgba(255,204,51,.22), 0 0 130px rgba(255,204,51,.13) inset;}
.rareBurst{
  position:absolute; inset:-40%;
  background: radial-gradient(circle at 50% 50%, rgba(255,204,51,.18), transparent 55%);
  opacity:0; pointer-events:none; mix-blend-mode: screen;
}
.rareOn{opacity:1; animation: burst 820ms ease 1;}
@keyframes burst{0%{transform:scale(.4);opacity:0}35%{opacity:1}100%{transform:scale(1.08);opacity:0}}
""" + "</style></head><body>"
        "<canvas id='fx'></canvas><div class='wrap'>"
        "<div class='top'><div class='title'><h1>🎲 Dado</h1><div class='sub'>Role e escolha. Nº de opções = valor do dado.</div></div>"
        "<div class='pills'><div class='pill'>🎲 <span id='bal'>-</span></div><div class='sep'></div><div class='pill'>🎡 <span id='ext'>-</span></div></div></div>"
        "<div class='panel glass'><div class='h2'>Gacha</div><div class='hint'>Se uma opção falhar, escolha outra da mesma rolagem. Em erro hard, o dado é devolvido.</div>"
        "<div class='diceRow'><div class='scene'><div class='cube' id='cube'>"
        + _dice_faces_html()
        + "</div></div><button class='btn' id='roll'>ROLAR</button></div>"
        "<div class='opts' id='opts'></div><div class='status' id='status'></div></div>"
        "<div class='loot' id='loot'><div class='box' id='box'><div class='spark'></div><div class='rareBurst' id='burst'></div>"
        "<div class='boxTop'><div class='boxTitle'>✨ REVELAÇÃO</div><button class='close' id='close'>FECHAR</button></div>"
        "<div class='boxBody'><div class='cardFlip'><div class='cardInner' id='inner'>"
        "<div class='front'>BALTIGO</div><div class='back'><img id='img' src='' alt=''><div class='backShade'></div>"
        "<div class='backMeta'><div class='bName' id='nm'>...</div><div class='bAnime' id='an'>...</div><div class='stars' id='st'>☆☆☆☆☆</div></div></div>"
        "</div></div><div style='min-width:0'><div class='hint' style='font-size:13px;color:rgba(255,255,255,.82)'>✅ Entregue no PV do bot</div>"
        "<div class='hint' style='margin-top:8px'>Toque em FECHAR para voltar.</div></div></div></div></div>"
        + _tg_js_init()
        + r"""
<script>
  const bal = document.getElementById("bal");
  const ext = document.getElementById("ext");
  const roll = document.getElementById("roll");
  const opts = document.getElementById("opts");
  const status = document.getElementById("status");

  const cube = document.getElementById("cube");
  const loot = document.getElementById("loot");
  const close = document.getElementById("close");
  const img = document.getElementById("img");
  const nm  = document.getElementById("nm");
  const an  = document.getElementById("an");
  const st  = document.getElementById("st");
  const box = document.getElementById("box");
  const burst = document.getElementById("burst");

  let rollId = null;
  let options = [];

  close.onclick = () => loot.classList.remove("on");
  loot.onclick = (e) => { if(e.target === loot) loot.classList.remove("on"); };

  function starsString(n){
    n = Math.max(1, Math.min(5, Number(n||1)));
    let s="";
    for(let i=0;i<n;i++) s+="★";
    for(let i=n;i<5;i++) s+="☆";
    return s;
  }

  function applyRarity(tier){
    box.classList.remove("glow-common","glow-rare","glow-epic","glow-mythic");
    burst.classList.remove("rareOn");
    if(tier==="mythic"){ box.classList.add("glow-mythic"); burst.classList.add("rareOn"); }
    else if(tier==="epic"){ box.classList.add("glow-epic"); burst.classList.add("rareOn"); }
    else if(tier==="rare"){ box.classList.add("glow-rare"); }
    else { box.classList.add("glow-common"); }
  }

  function openLoot(character){
    img.src = character.image || "";
    nm.textContent = character.name || "???";
    an.textContent = character.anime || "Obra";
    const rar = character.rarity || {stars:2, tier:"common"};
    st.textContent = starsString(rar.stars || 2);
    applyRarity(rar.tier || "common");
    // força reflip (reinicia animação)
    const inner = document.getElementById("inner");
    inner.style.animation = "none";
    void inner.offsetWidth;
    inner.style.animation = "";
    loot.classList.add("on");
  }

  function rollCube(){
    cube.classList.add("rolling");
    setTimeout(()=>cube.classList.remove("rolling"), 780);
  }

  function makeThumb(o){
    const url = (o && o.cover) ? String(o.cover) : "";
    if(url) return `<img class="thumb" src="${esc(url)}" alt="">`;
    const t = String(o?.title || "A").trim().slice(0,1).toUpperCase();
    return `<div class="thumb" style="display:flex;align-items:center;justify-content:center;font-weight:1000">${esc(t)}</div>`;
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
      b.innerHTML = `${makeThumb(o)}<div style="min-width:0"><div class="optTitle">🎴 ${esc(o.title || "Anime")}</div></div>`;
      b.onclick = () => pick(o.id, b);
      opts.appendChild(b);
    });
  }

  async function pick(animeId, btn){
    if(!rollId) return;
    btn.disabled = true; btn.style.opacity=.7;
    status.textContent = "Processando...";

    const out = await apiPost(`/dado/pick?roll_id=${encodeURIComponent(rollId)}&anime_id=${encodeURIComponent(animeId)}`, {});
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

    rollCube();
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

    options = Array.isArray(data.options) ? data.options : [];
    renderOptions();

    status.textContent = `🎯 Escolha 1 das ${options.length} opções (dado: ${data.dice}).`;
    roll.disabled = false;
    roll.textContent = "ROLAR DE NOVO";
  };

  renderOptions();
</script>
""" + _fx_js() + "</div></body></html>"
    )
    return HTMLResponse(content=html)


def _dice_faces_html() -> str:
    # pip positions (3x3 grid)
    # each face uses same template; JS doesn't need to change faces; cube roll is cosmetic
    def p(x, y):  # 0..1 positions
        return f"<span class='pip' style='left:{x*36:.0f}px;top:{y*36:.0f}px'></span>"

    # faces:
    face1 = p(0.5,0.5)
    face2 = p(0.25,0.25)+p(0.75,0.75)
    face3 = p(0.25,0.25)+p(0.5,0.5)+p(0.75,0.75)
    face4 = p(0.25,0.25)+p(0.75,0.25)+p(0.25,0.75)+p(0.75,0.75)
    face5 = face4 + p(0.5,0.5)
    face6 = face4 + p(0.25,0.5)+p(0.75,0.5)

    def face(cls, pips):
        return f"<div class='face {cls}'><div class='pips'>{pips}</div></div>"

    return face("face1",face1)+face("face2",face2)+face("face3",face3)+face("face4",face4)+face("face5",face5)+face("face6",face6)


# =========================
# UI: /shop — Loja estilo jogo (comprar + vender)
# =========================
@app.get("/shop", response_class=HTMLResponse)
def miniapp_shop():
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1, viewport-fit=cover'>"
        "<title>Baltigo • Loja</title>"
        "<style>" + _theme_css() + r"""
.shopGrid{display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:12px; margin-top:12px;}
@media (min-width: 520px){ .shopGrid{grid-template-columns: repeat(3, minmax(0,1fr));} }
.shopCard{
  border-radius:22px; padding:14px;
  position:relative; overflow:hidden;
}
.shopCard h3{margin:0; font-size:14px; font-weight:1000;}
.shopCard p{margin:8px 0 12px; font-size:12px; color:rgba(255,255,255,.72); line-height:1.35;}
.shopCard .price{font-weight:1000; font-size:12px; color:rgba(255,255,255,.85);}
.shopCard .bg{
  position:absolute; inset:-40%;
  background: radial-gradient(circle at 30% 30%, rgba(255,43,74,.18), transparent 45%),
              radial-gradient(circle at 70% 10%, rgba(176,108,255,.14), transparent 55%);
  opacity:.9; pointer-events:none;
}
.shopCard .shine{position:absolute; inset:-40%; background: radial-gradient(circle at 30% 30%, rgba(255,255,255,.22), transparent 40%); transform:rotate(12deg); opacity:.18; pointer-events:none; mix-blend-mode:screen;}
.shopCard .actions{display:flex; gap:10px; align-items:center;}
.qty{
  width:86px; text-align:center;
  padding:12px 10px; border-radius:14px;
  border:1px solid var(--stroke); background:rgba(255,255,255,.04);
  color:#fff; outline:none; font-weight:1000;
}
.list{
  margin-top:12px;
  border-radius:22px;
  padding:12px;
}
.item{
  display:flex; gap:12px; align-items:center;
  padding:10px; border-radius:18px;
  border:1px solid rgba(255,255,255,.10);
  background: rgba(255,255,255,.02);
  margin-top:10px;
}
.item:first-child{margin-top:0}
.itImg{
  width:52px;height:52px;border-radius:16px;border:1px solid rgba(255,255,255,.14);
  background: radial-gradient(circle at 20% 20%, rgba(255,43,74,.16), rgba(255,255,255,.02));
  object-fit:cover; flex-shrink:0;
}
.itName{font-weight:1000; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.itAnime{margin-top:4px; font-size:12px; color:rgba(255,255,255,.72); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.itRight{margin-left:auto; display:flex; align-items:center; gap:10px;}
.small{font-size:12px;color:rgba(255,255,255,.72);font-weight:900}
""" + "</style></head><body>"
        "<canvas id='fx'></canvas><div class='wrap'>"
        "<div class='top'><div class='title'><h1>🏪 Loja</h1><div class='sub'>Comprar, vender e evoluir.</div></div>"
        "<div class='pills'><div class='pill'>🪙 <span id='coins'>-</span></div><div class='sep'></div><div class='pill'>🎲 <span id='dicebal'>-</span></div></div></div>"
        "<div class='tabs glass'><button class='tab active' id='tab_buy'>🛒 Comprar</button><button class='tab' id='tab_sell'>💰 Vender</button></div>"
        "<div class='toast' id='toast'>Carregando...</div>"

        "<div id='view_buy'>"
        "<div class='shopGrid'>"
        "<div class='shopCard glass' id='card_dado'><div class='bg'></div><div class='shine'></div>"
        "<h3>🎲 Dado</h3><p>Compre dados para rolar no gacha. Quanto mais, melhor.</p>"
        "<div class='price'>Preço: <span id='dado_price'>-</span> coins (cada)</div>"
        "<div class='actions' style='margin-top:12px;'><input class='qty' id='qty' value='2' inputmode='numeric' />"
        "<button class='btn' id='buy_dado'>COMPRAR</button></div>"
        "</div>"

        "<div class='shopCard glass' id='card_max'><div class='bg'></div><div class='shine'></div>"
        "<h3>💎 Comprar Máximo</h3><p>Compra automaticamente o máximo de dados possível com suas coins.</p>"
        "<div class='price'>Auto: coins / preço do dado</div>"
        "<div class='actions' style='margin-top:12px;'><button class='btn' id='buy_max'>COMPRAR MÁX</button></div>"
        "</div>"
        "</div>"
        "</div>"

        "<div id='view_sell' style='display:none;'>"
        "<div class='row' style='margin-top:12px;'><input class='input glass' id='q' placeholder='Buscar para vender...' />"
        "<button class='btn secondary' id='refresh'>ATUALIZAR</button></div>"
        "<div class='list glass' id='list'></div>"
        "</div>"

        + _tg_js_init()
        + r"""
<script>
  const toast = document.getElementById("toast");
  const coinsEl = document.getElementById("coins");
  const diceEl  = document.getElementById("dicebal");
  const giroPriceEl = document.getElementById("giro_price");
  const dadoPriceEl = document.getElementById("dado_price");

  const tabBuy = document.getElementById("tab_buy");
  const tabSell = document.getElementById("tab_sell");
  const viewBuy = document.getElementById("view_buy");
  const viewSell = document.getElementById("view_sell");

  const buyGiro = document.getElementById("buy_giro");
  const buyDado = document.getElementById("buy_dado");
  const buyMax  = document.getElementById("buy_max");
  const qtyEl   = document.getElementById("qty");

  const qEl = document.getElementById("q");
  const refreshBtn = document.getElementById("refresh");
  const listEl = document.getElementById("list");

  let state = null;

  function setToast(text, type){
    toast.className = "toast" + (type ? (" " + type) : "");
    toast.textContent = text;
  }

  function setTab(which){
    [tabBuy, tabSell].forEach(t=>t.classList.remove("active"));
    if(which==="buy"){ tabBuy.classList.add("active"); viewBuy.style.display=""; viewSell.style.display="none"; }
    if(which==="sell"){ tabSell.classList.add("active"); viewBuy.style.display="none"; viewSell.style.display=""; }
  }
  tabBuy.onclick = ()=> setTab("buy");
  tabSell.onclick = ()=> { setTab("sell"); loadSell(); };

  async function loadState(){
    setToast("Carregando loja...", "");
    const r = await apiGet("/api/shop/state");
    if(!r.ok){
      setToast("❌ Falha ao carregar: " + r.status + "\n" + JSON.stringify(r.data||{}), "err");
      return;
    }
    state = r.data || {};
    coinsEl.textContent = String(state.coins ?? "-");
    diceEl.textContent = String(state.dado_balance ?? "-");
    giroPriceEl.textContent = String(state.giro_price ?? "-");
    dadoPriceEl.textContent = String(state.dado_price ?? "-");
    setToast("✅ Pronto.", "ok");
  }

  async function loadSell(){
    const q = (qEl.value || "").trim();
    listEl.innerHTML = "<div style='color:rgba(255,255,255,.70);font-size:12px'>Carregando...</div>";
    const r = await apiGet("/api/shop/sell/all?q=" + encodeURIComponent(q));
    if(!r.ok || !r.data?.ok){
      listEl.innerHTML = "<div style='color:rgba(255,170,170,.95);font-size:12px'>Falha ao carregar lista.</div>";
      return;
    }
    const items = Array.isArray(r.data.items) ? r.data.items : [];
    if(!items.length){
      listEl.innerHTML = "<div style='color:rgba(255,255,255,.70);font-size:12px'>Nada para vender.</div>";
      return;
    }
    listEl.innerHTML = "";
    for(const it of items){
      const div = document.createElement("div");
      div.className = "item";
      const img = it.image ? `<img class='itImg' src='${esc(it.image)}' alt=''>`
                           : `<div class='itImg' style='display:flex;align-items:center;justify-content:center;font-weight:1000'>🎴</div>`;
      div.innerHTML = `
        ${img}
        <div style="min-width:0">
          <div class="itName">${esc(it.character_name || "Personagem")} <span class="small">x${esc(it.quantity||1)}</span></div>
          <div class="itAnime">${esc(it.anime_title || "Sem anime")}</div>
        </div>
        <div class="itRight">
          <button class="btn secondary" style="padding:12px 12px;border-radius:14px" data-id="${esc(it.character_id)}">VENDER</button>
        </div>
      `;
      const btn = div.querySelector("button");
      btn.onclick = async () => {
        btn.disabled = true;
        const r2 = await apiPost("/api/shop/sell/confirm", { character_id: Number(it.character_id||0) });
        if(!r2.ok || !r2.data?.ok){
          btn.disabled = false;
          try{ tg?.showAlert?.(String(r2.data?.error || "Falha ao vender.")); }catch(e){}
          return;
        }
        try{ tg?.showAlert?.("✅ Vendido!"); }catch(e){}
        await loadState();
        await loadSell();
      };
      listEl.appendChild(div);
    }
  }

  refreshBtn.onclick = loadSell;
  qEl.addEventListener("input", ()=>{ clearTimeout(window.__t); window.__t=setTimeout(loadSell, 260); });

  buyGiro.onclick = async () => {
    buyGiro.disabled = true;
    const r = await apiPost("/api/shop/buy/giro", {});
    buyGiro.disabled = false;
    if(!r.ok || !r.data?.ok){
      try{ tg?.showAlert?.(String(r.data?.error || "Falha ao comprar giro.")); }catch(e){}
      return;
    }
    try{ tg?.showAlert?.("✅ Giro comprado!"); }catch(e){}
    await loadState();
  };

  buyDado.onclick = async () => {
    let qty = Number(qtyEl.value || "1");
    if(!isFinite(qty) || qty <= 0) qty = 1;
    qty = Math.min(999, Math.floor(qty));
    buyDado.disabled = true;
    const r = await apiPost("/api/shop/buy/dado", { qty });
    buyDado.disabled = false;
    if(!r.ok || !r.data?.ok){
      try{ tg?.showAlert?.(String(r.data?.error || "Falha ao comprar dado.")); }catch(e){}
      return;
    }
    try{ tg?.showAlert?.("✅ Dados comprados: " + qty); }catch(e){}
    await loadState();
  };

  buyMax.onclick = async () => {
    buyMax.disabled = true;
    const r = await apiPost("/api/shop/buy/dado/max", {});
    buyMax.disabled = false;
    if(!r.ok || !r.data?.ok){
      try{ tg?.showAlert?.(String(r.data?.error || "Falha ao comprar máximo.")); }catch(e){}
      return;
    }
    try{ tg?.showAlert?.("✅ Comprou " + String(r.data?.qty || "?") + " dados!"); }catch(e){}
    await loadState();
  };

  loadState();
</script>
""" + _fx_js() + "</div></body></html>"
    )
    return HTMLResponse(content=html)
