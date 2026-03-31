# =============================================================================
# webapp.py — Source Baltigo WebApp
# Refatorado: design system unificado, duplicatas removidas, bugs corrigidos
# =============================================================================
import os
import json
import re
import html
import traceback
import asyncio
import time
import httpx
import random
import hashlib
import hmac
from pathlib import Path
from urllib.parse import parse_qsl
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Query, Body, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from database import (
    create_or_get_user,
    accept_terms,
    set_language,
    get_dado_state,
    get_next_dado_recharge_info,
    expire_stale_dice_rolls,
    get_active_dice_roll,
    create_dice_roll,
    cancel_dice_roll,
    pick_dice_roll_anime,
    resolve_dice_roll,
    create_purchase_intent,
    get_user_referrer,
    attach_checkout_data_to_purchase_intent,
    get_purchase_intent_by_external_reference,
    get_purchase_intent_by_cakto_order_id,
    mark_purchase_intent_status,
    create_affiliate_commission_for_purchase,
    reverse_affiliate_commission_by_purchase,
    save_cakto_webhook_event,
    mark_cakto_webhook_event_processed,
    mark_cakto_webhook_event_error,
    touch_user_identity,
    get_user_status,
    get_progress_row,
    get_user_card_collection,
    get_profile_settings,
    set_profile_nickname,
    set_profile_favorite,
    set_profile_country,
    set_profile_language,
    set_profile_private,
    set_profile_notifications,
    delete_user_account,
    create_media_request_tables,
    count_user_media_requests_last_24h,
    media_request_exists,
    save_media_request,
    save_webapp_report,
    normalize_media_title,
)

from cards_service import (
    build_cards_final_data,
    find_anime,
    list_subcategories,
    reload_cards_cache,
    search_characters,
    get_character_by_id,
)

app = FastAPI()

# =============================================================================
# DESIGN SYSTEM — CSS compartilhado entre todas as páginas
# =============================================================================
_DS_CSS = """\
:root {
  --bg0: #050912;
  --bg1: #0a1020;
  --panel: rgba(255,255,255,.05);
  --panel2: rgba(255,255,255,.03);
  --stroke: rgba(255,255,255,.10);
  --stroke2: rgba(255,255,255,.18);
  --txt: rgba(255,255,255,.94);
  --muted: rgba(255,255,255,.58);
  --accent: #5aa8ff;
  --accent2: rgba(90,168,255,.20);
  --ok: #4ade80;
  --warn: #ffcf5a;
  --danger: #ff5a76;
  --brand: #ff8a00;
  --brand2: #ff3d00;
  --shadow: 0 18px 38px rgba(0,0,0,.46);
  --shadow2: 0 10px 22px rgba(0,0,0,.30);
  --r-sm: 14px;
  --r-md: 20px;
  --r-lg: 28px;
  --r-xl: 36px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
html, body { height: 100%; }
body {
  margin: 0;
  font-family: var(--font);
  color: var(--txt);
  background: radial-gradient(1100px 600px at 50% -10%, rgba(90,168,255,.16), transparent 55%),
              linear-gradient(180deg, var(--bg0), var(--bg1));
  overflow-x: hidden;
}
.dot-bg {
  position: fixed; inset: 0;
  background-image: radial-gradient(rgba(255,255,255,.05) 1px, transparent 1px);
  background-size: 38px 38px;
  opacity: .14;
  pointer-events: none;
  z-index: 0;
}
.wrap {
  position: relative;
  z-index: 1;
  max-width: 1000px;
  margin: 0 auto;
  padding: 16px 14px 44px;
}
/* Banner */
.top-banner {
  width: 100%;
  border-radius: var(--r-lg);
  overflow: hidden;
  border: 1px solid var(--stroke);
  box-shadow: var(--shadow);
  position: relative;
  background: #000;
}
.top-banner img {
  width: 100%;
  height: 210px;
  object-fit: cover;
  display: block;
}
.top-banner::after {
  content: "";
  position: absolute; inset: 0;
  background: linear-gradient(180deg, rgba(0,0,0,.04), rgba(0,0,0,.72));
  pointer-events: none;
}
.top-copy {
  position: absolute;
  left: 18px; right: 18px; bottom: 16px;
  z-index: 2;
}
/* Eyebrow */
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(255,255,255,.18);
  background: rgba(0,0,0,.32);
  backdrop-filter: blur(8px);
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: .14em;
  text-transform: uppercase;
}
/* Section title */
.section-title {
  font-weight: 900;
  letter-spacing: .10em;
  text-transform: uppercase;
  font-size: 11px;
  color: var(--muted);
  margin: 22px 0 10px;
}
/* Panel */
.panel {
  border: 1px solid var(--stroke);
  border-radius: var(--r-lg);
  background: var(--panel);
  box-shadow: var(--shadow2);
}
/* Search bar */
.search-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--panel2);
  border: 1px solid var(--stroke);
  border-radius: var(--r-md);
  padding: 12px 14px;
  box-shadow: var(--shadow2);
}
.search-bar input {
  width: 100%;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--txt);
  font-size: 14px;
  font-family: var(--font);
}
.search-bar input::placeholder {
  color: rgba(255,255,255,.32);
  font-weight: 800;
  letter-spacing: .06em;
}
/* Cards grid */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-top: 14px;
}
@media (min-width: 720px) { .cards-grid { grid-template-columns: repeat(3, 1fr); } }
/* Card base */
.card {
  border-radius: var(--r-lg);
  overflow: hidden;
  border: 1px solid var(--stroke);
  background: var(--panel2);
  box-shadow: var(--shadow2);
  transition: transform .16s ease, border-color .16s ease;
}
.card:hover { transform: translateY(-2px); border-color: var(--stroke2); }
.card .cover {
  width: 100%;
  height: 240px;
  position: relative;
  background: linear-gradient(135deg, rgba(90,168,255,.14), rgba(255,255,255,.02));
}
.card .cover img {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
}
.card .cover::after {
  content: "";
  position: absolute; inset: 0;
  background: linear-gradient(180deg, transparent 40%, rgba(0,0,0,.58));
  pointer-events: none;
}
.card .meta { padding: 13px 14px 15px; }
.card .name {
  font-weight: 900;
  letter-spacing: .04em;
  font-size: 13px;
  line-height: 1.25;
  text-transform: uppercase;
  margin: 0;
}
.card .sub {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.pill {
  border: 1px solid rgba(255,255,255,.12);
  background: rgba(255,255,255,.05);
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .10em;
  text-transform: uppercase;
  color: rgba(255,255,255,.72);
}
/* Buttons */
.btn {
  border: none;
  border-radius: var(--r-md);
  padding: 14px 18px;
  font-size: 13px;
  font-weight: 900;
  letter-spacing: .08em;
  text-transform: uppercase;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: transform .13s ease, filter .13s ease, opacity .13s ease;
  font-family: var(--font);
  text-decoration: none;
}
.btn:hover { filter: brightness(1.06); }
.btn:active { transform: scale(.982); }
.btn[disabled], .btn:disabled { opacity: .42; cursor: not-allowed; }
.btn-primary {
  background: linear-gradient(135deg, var(--accent), #3a7cf5);
  color: #fff;
  box-shadow: 0 12px 24px rgba(90,168,255,.24);
}
.btn-ghost {
  background: var(--panel);
  color: var(--txt);
  border: 1px solid var(--stroke2);
}
.btn-ok {
  background: rgba(74,222,128,.16);
  color: var(--ok);
  border: 1px solid rgba(74,222,128,.30);
}
.btn-danger {
  background: rgba(255,90,118,.16);
  color: var(--danger);
  border: 1px solid rgba(255,90,118,.30);
}
.btn-brand {
  background: linear-gradient(90deg, var(--brand), var(--brand2));
  color: #fff;
  box-shadow: 0 12px 24px rgba(255,98,0,.24);
}
.btn-full { width: 100%; }
/* Toast */
.toast {
  position: fixed;
  left: 50%; bottom: 20px;
  transform: translateX(-50%);
  max-width: 92vw;
  padding: 13px 18px;
  border-radius: var(--r-md);
  background: rgba(5,9,18,.92);
  border: 1px solid var(--stroke2);
  box-shadow: var(--shadow);
  font-size: 13px;
  font-weight: 800;
  z-index: 100;
  pointer-events: none;
  opacity: 0;
  transition: opacity .22s ease;
  white-space: pre-line;
}
.toast.show { opacity: 1; }
/* Empty state */
.empty-state {
  text-align: center;
  padding: 32px 18px;
  border: 1px dashed var(--stroke2);
  border-radius: var(--r-lg);
  color: var(--muted);
  font-weight: 700;
  margin-top: 14px;
}
/* Skeleton */
.skeleton {
  border-radius: var(--r-lg);
  background: linear-gradient(90deg, var(--panel2) 25%, var(--panel) 50%, var(--panel2) 75%);
  background-size: 200% 100%;
  animation: sk 1.3s linear infinite;
}
@keyframes sk { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
/* Tabs */
.tabs {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}
.tab {
  flex: 1;
  min-width: 120px;
  padding: 13px 10px;
  border-radius: var(--r-md);
  text-align: center;
  border: 1px solid var(--stroke);
  background: var(--panel2);
  font-weight: 900;
  letter-spacing: .08em;
  font-size: 12px;
  text-transform: uppercase;
  cursor: pointer;
  user-select: none;
  transition: background .13s ease, border-color .13s ease;
}
.tab.active { background: rgba(90,168,255,.18); border-color: rgba(90,168,255,.42); }
/* Msg/Status */
.msg {
  min-height: 20px;
  font-size: 13px;
  font-weight: 800;
  color: rgba(255,255,255,.72);
  margin-top: 12px;
  white-space: pre-wrap;
}
/* Footer */
.footer {
  margin-top: 22px;
  text-align: center;
  color: rgba(255,255,255,.30);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}
/* Back link */
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: var(--txt);
  border: 1px solid rgba(255,255,255,.16);
  background: rgba(0,0,0,.28);
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: .12em;
  text-transform: uppercase;
}
"""

def _page(title: str, body: str, extra_css: str = "", extra_js: str = "", tg_init: bool = False) -> str:
    tg_script = '<script src="https://telegram.org/js/telegram-web-app.js"></script>' if tg_init else ""
    return f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>{title}</title>
{tg_script}
<style>
{_DS_CSS}
{extra_css}
</style>
</head>
<body>
<div class="dot-bg"></div>
{body}
{extra_js}
</body>
</html>"""

# =============================================================================
# CONFIG GLOBAL
# =============================================================================
TERMS_VERSION = (os.getenv("TERMS_VERSION", "v1").strip() or "v1")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourceBaltigo").strip()
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/SourceBaltigo").strip()
TOP_BANNER_URL = os.getenv("TOP_BANNER_URL", "https://photo.chelpbot.me/AgACAgEAAxkBZzS3wWmpl9pZVvh8mUyitl-u56VSkUmPAALrC2sb1ZFIRYO5j8ewhrZJAQADAgADeQADOgQ/photo.jpg").strip()
BACKGROUND_URL = os.getenv("BACKGROUND_URL", "").strip()
EMPTY_BG_DATA_URI = "data:image/gif;base64,R0lGODlhAQABAAAAACw="

CATALOG_PATH = os.getenv("CATALOG_PATH", "data/catalogo_enriquecido.json").strip()
CATALOG_BANNER_URL = os.getenv("CATALOG_BANNER_URL", "https://photo.chelpbot.me/AgACAgEAAxkBZzeISGmpyjb2CsPEQUv3zfVD-aj7780SAAKzC2sb6qtQRVbTTJ4IyPVIAQADAgADeQADOgQ/photo.jpg").strip()
BACKGROUND_PATTERN_URL = os.getenv("BACKGROUND_PATTERN_URL", "").strip()
CATALOG_TITLE = os.getenv("CATALOG_TITLE", "CATÁLOGO GERAL").strip()
CATALOG_SUBTITLE = os.getenv("CATALOG_SUBTITLE", "TOTAL NA SEÇÃO").strip()

MANGA_CATALOG_PATH = os.getenv("MANGA_CATALOG_PATH", "data/catalogo_mangas_enriquecido.json").strip()
MANGA_CATALOG_BANNER_URL = os.getenv("MANGA_CATALOG_BANNER_URL", "https://photo.chelpbot.me/AgACAgEAAxkBZzeISGmpyjb2CsPEQUv3zfVD-aj7780SAAKzC2sb6qtQRVbTTJ4IyPVIAQADAgADeQADOgQ/photo.jpg").strip()
MANGA_BACKGROUND_PATTERN_URL = os.getenv("MANGA_BACKGROUND_PATTERN_URL", "").strip()
MANGA_CATALOG_TITLE = os.getenv("MANGA_CATALOG_TITLE", "CATÁLOGO MANGÁS").strip()
MANGA_CATALOG_SUBTITLE = os.getenv("MANGA_CATALOG_SUBTITLE", "TOTAL NA SEÇÃO").strip()

CARDS_ASSETS_PATH = os.getenv("CARDS_ASSETS_PATH", "data/personagens_anilist.txt").strip()
CARDS_TOP_BANNER_URL = os.getenv("CARDS_TOP_BANNER_URL", "https://photo.chelpbot.me/AgACAgEAAxkBZ0sajmmrHXRy1AZxkfEGC2Lx4yC6A80MAAJOC2sb1ZFYRQ5kxLI09cC2AQADAgADeQADOgQ/photo.jpg").strip()

DADO_BANNER_URL = os.getenv("DADO_BANNER_URL", TOP_BANNER_URL).strip()
CARDS_LOCAL_PATH = os.getenv("CARDS_LOCAL_PATH", "data/personagens_anilist.txt").strip()
DADO_WEB_RATE_SECONDS = float(os.getenv("DADO_WEB_RATE_SECONDS", "0.8"))

MENU_BANNER_URL = os.getenv("MENU_BANNER_URL", TOP_BANNER_URL).strip()
MENU_BACKGROUND_URL = os.getenv("MENU_BACKGROUND_URL", BACKGROUND_URL or "").strip()

SHOP_PREVIEW_IMAGE = os.getenv("SHOP_PREVIEW_IMAGE", "https://photo.chelpbot.me/AgACAgQAAxkBZqZjcmmff-LPn4H7y3EsyO0G_rk8AAHTWgACBw5rG0eL9VAWyQkpU35BaAEAAwIAA3kAAzoE/photo.jpg").strip()

CANAL_PEDIDOS = os.getenv("CANAL_PEDIDOS", "").strip()
PEDIDO_BANNER_URL = os.getenv("PEDIDO_BANNER_URL", "https://photo.chelpbot.me/AgACAgEAAxkBZ0w54WmrME4Fk9ObOXCy_CjgTb8IHF9cAAJRC2sb1ZFYRTRdgJDi4ysfAQADAgADeQADOgQ/photo.jpg").strip()

WEBHOOK_SECRET = os.getenv("CAKTO_WEBHOOK_SECRET", "").strip()

BALTIGOFLIX_PLANS = {
    "mensal":     {"code": "mensal",     "name": "Plano Mensal",     "amount_cents": 2590},
    "trimestral": {"code": "trimestral", "name": "Plano Trimestral", "amount_cents": 5990},
    "semestral":  {"code": "semestral",  "name": "Plano Semestral",  "amount_cents": 8990},
    "anual":      {"code": "anual",      "name": "Plano Anual",      "amount_cents": 12990},
}
CHECKOUT_URLS = {
    "mensal":     "https://pay.cakto.com.br/9snqsP3",
    "trimestral": "https://pay.cakto.com.br/3fsy24d",
    "semestral":  "https://pay.cakto.com.br/32ocvxm",
    "anual":      "https://pay.cakto.com.br/u9wz86m",
}

COUNTRY_OPTIONS = [
    {"code": "BR", "flag": "🇧🇷", "name": "Brasil"},
    {"code": "US", "flag": "🇺🇸", "name": "United States"},
    {"code": "ES", "flag": "🇪🇸", "name": "España"},
    {"code": "JP", "flag": "🇯🇵", "name": "日本"},
]
LANGUAGE_OPTIONS = [
    {"code": "pt", "name": "Português"},
    {"code": "en", "name": "English"},
    {"code": "es", "name": "Español"},
]

# init
create_media_request_tables()


# =============================================================================
# HELPERS GLOBAIS
# =============================================================================
def pick_lang(lang: Optional[str]) -> str:
    lang = (lang or "").lower().strip()
    if lang.startswith("pt"): return "pt"
    if lang.startswith("es"): return "es"
    return "en"

def _safe_int(v: Any, default: int = 0) -> int:
    try: return int(v)
    except Exception: return default

def _norm_text(v: Any) -> str:
    return str(v or "").strip()

def _valid_menu_nickname(nickname: str) -> bool:
    return bool(re.match(r"^[A-Z][A-Za-z0-9_]{3,16}$", (nickname or "").strip()))

# Telegram init data verify
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

def _get_tg_user(x_telegram_init_data: str) -> Dict[str, Any]:
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    username = (user.get("username") or "").strip()
    full_name = " ".join(p for p in [
        (user.get("first_name") or "").strip(),
        (user.get("last_name") or "").strip(),
    ] if p).strip()
    create_or_get_user(user_id)
    return {"user_id": user_id, "username": username, "full_name": full_name}

async def _tg_send_photo(chat_id: int, photo: str, caption: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                json={"chat_id": int(chat_id), "photo": str(photo), "caption": str(caption), "parse_mode": "HTML"},
            )
            return bool(resp.json().get("ok"))
    except Exception:
        return False

async def _telegram_send_message(chat_id: str, text: str):
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"},
        )

async def _telegram_send_photo(chat_id: str, photo: str, caption: str):
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": "HTML"},
        )

# =============================================================================
# RATE LIMITERS
# =============================================================================
_DADO_RATE: Dict[Tuple[int, str], float] = {}
_DADO_LOCAL_CACHE: Dict[str, Any] = {
    "mtime": 0.0, "loaded": False, "path": "",
    "animes_list": [], "animes_by_id": {}, "characters_by_anime": {},
}

def _dado_rate_limit(user_id: int, key: str, window: float = DADO_WEB_RATE_SECONDS) -> bool:
    now = time.time()
    k = (int(user_id), str(key))
    last = _DADO_RATE.get(k, 0.0)
    if now - last < window: return False
    _DADO_RATE[k] = now
    return True

def _shop_rate_limit(user_id: int, key: str, window: float = 1.0) -> bool:
    if not hasattr(_shop_rate_limit, "_mem"): _shop_rate_limit._mem = {}
    mem = _shop_rate_limit._mem
    now = time.time()
    k = f"{user_id}:{key}"
    last = float(mem.get(k, 0.0) or 0.0)
    if now - last < float(window): return False
    mem[k] = now
    return True

# =============================================================================
# CATALOG DATA — ANIME
# =============================================================================
_CATALOG: List[Dict[str, Any]] = []
_LETTER_COUNTS: Dict[str, int] = {}
_TOTAL: int = 0

def _normalize_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower().strip())

def _first_letter(title: str) -> str:
    t = re.sub(r"^(the|a|an)\s+", "", str(title or "").strip().lower())
    c = t[0].upper() if t else "#"
    return c if c.isalpha() else "#"

def _safe_int_opt(v: Any) -> Optional[int]:
    try:
        if v is None or isinstance(v, bool): return None
        return int(v)
    except Exception: return None

def _unwrap_records(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for k in ("items", "animes", "data", "records", "results", "entries"):
            v = data.get(k)
            if isinstance(v, list): return v
        vals = list(data.values())
        if len(vals) == 1 and isinstance(vals[0], list): return vals[0]
    return []

def _coerce_item(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    titulo = str(it.get("titulo") or it.get("title") or it.get("nome") or "").strip()
    if not titulo: return None
    anilist = it.get("anilist") or {}
    raw_id = it.get("anilist_id") or anilist.get("id")
    link_post = str(it.get("link_post") or it.get("url") or it.get("link") or "").strip()
    cover = str(
        it.get("cover_url") or it.get("cover") or anilist.get("cover_url")
        or (anilist.get("coverImage") or {}).get("large") or ""
    ).strip()
    year = _safe_int_opt(it.get("year") or anilist.get("seasonYear"))
    score = it.get("score") or anilist.get("averageScore")
    if score is not None:
        try: score = round(float(score) / 10, 1) if float(score) > 10 else round(float(score), 1)
        except Exception: score = None
    fmt = str(it.get("format") or anilist.get("format") or "").strip().upper()
    badge = str(it.get("badge") or fmt or "ANIME").strip()
    return {
        "titulo": titulo, "link_post": link_post, "cover_url": cover,
        "anilist_id": _safe_int_opt(raw_id), "year": year, "score": score,
        "format": fmt, "badge": badge,
        "_letter": _first_letter(titulo), "_norm": _normalize_title(titulo),
    }

def _load_catalog() -> Tuple[int, str]:
    global _CATALOG, _LETTER_COUNTS, _TOTAL
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        records = _unwrap_records(raw)
        items = [c for r in records for c in [_coerce_item(r)] if c]
        items.sort(key=lambda x: x["_norm"])
        lc: Dict[str, int] = {}
        for it in items:
            lc[it["_letter"]] = lc.get(it["_letter"], 0) + 1
        _CATALOG = items
        _LETTER_COUNTS = lc
        _TOTAL = len(items)
        return len(items), "ok"
    except Exception as e:
        return 0, str(e)

def _filter_catalog(q: str, letter: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    data = _CATALOG
    if letter and letter != "ALL":
        data = [x for x in data if x["_letter"] == letter]
    if q:
        qn = _normalize_title(q)
        data = [x for x in data if qn in x["_norm"]]
    total = len(data)
    return data[offset:offset + limit], total

_load_catalog()

# =============================================================================
# CATALOG DATA — MANGÁS
# =============================================================================
_MANGA_CATALOG: List[Dict[str, Any]] = []
_MANGA_LETTER_COUNTS: Dict[str, int] = {}
_MANGA_TOTAL: int = 0

def _detect_manga_badge(it: Dict[str, Any], anilist: Optional[Dict[str, Any]]) -> str:
    fmt = str(it.get("format") or (anilist or {}).get("format") or "").strip().upper()
    mapping = {"MANGA": "MANGÁ", "ONE_SHOT": "ONE-SHOT", "NOVEL": "NOVEL", "LIGHT_NOVEL": "LIGHT NOVEL"}
    return mapping.get(fmt, fmt or "MANGÁ")

def _coerce_manga_item(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    titulo = str(it.get("titulo") or it.get("title") or it.get("nome") or "").strip()
    if not titulo: return None
    anilist = it.get("anilist") or {}
    raw_id = it.get("anilist_id") or anilist.get("id")
    link_post = str(it.get("link_post") or it.get("url") or it.get("link") or "").strip()
    cover = str(
        it.get("cover_url") or it.get("cover") or anilist.get("cover_url")
        or (anilist.get("coverImage") or {}).get("large") or ""
    ).strip()
    year = _safe_int_opt(it.get("year") or anilist.get("seasonYear") or anilist.get("startDate", {}).get("year"))
    score = it.get("score") or anilist.get("averageScore")
    if score is not None:
        try: score = round(float(score) / 10, 1) if float(score) > 10 else round(float(score), 1)
        except Exception: score = None
    fmt = str(it.get("format") or anilist.get("format") or "").strip().upper()
    badge = _detect_manga_badge(it, anilist)
    chapters = _safe_int_opt(it.get("chapters") or anilist.get("chapters"))
    return {
        "titulo": titulo, "link_post": link_post, "cover_url": cover,
        "anilist_id": _safe_int_opt(raw_id), "year": year, "score": score,
        "format": fmt, "badge": badge, "chapters": chapters,
        "_letter": _first_letter(titulo), "_norm": _normalize_title(titulo),
    }

def _load_manga_catalog() -> Tuple[int, str]:
    global _MANGA_CATALOG, _MANGA_LETTER_COUNTS, _MANGA_TOTAL
    try:
        with open(MANGA_CATALOG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        records = _unwrap_records(raw)
        items = [c for r in records for c in [_coerce_manga_item(r)] if c]
        items.sort(key=lambda x: x["_norm"])
        lc: Dict[str, int] = {}
        for it in items:
            lc[it["_letter"]] = lc.get(it["_letter"], 0) + 1
        _MANGA_CATALOG = items
        _MANGA_LETTER_COUNTS = lc
        _MANGA_TOTAL = len(items)
        return len(items), "ok"
    except Exception as e:
        return 0, str(e)

def _filter_manga_catalog(q: str, letter: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    data = _MANGA_CATALOG
    if letter and letter != "ALL":
        data = [x for x in data if x["_letter"] == letter]
    if q:
        qn = _normalize_title(q)
        data = [x for x in data if qn in x["_norm"]]
    total = len(data)
    return data[offset:offset + limit], total

_load_manga_catalog()

# =============================================================================
# DADO — POOL LOCAL
# =============================================================================
def _build_cover_from_anilist(anime_id: int) -> str:
    if int(anime_id) <= 0: return DADO_BANNER_URL
    return f"https://img.anili.st/media/{anime_id}"

def _build_char_image_from_anilist(char_id: int) -> str:
    if int(char_id) <= 0: return DADO_BANNER_URL
    return f"https://img.anili.st/character/{char_id}"

def _resolve_local_cards_path() -> Optional[Path]:
    candidates = [CARDS_LOCAL_PATH, "data/personagens_anilist.txt"]
    for c in candidates:
        p = Path(c)
        if p.exists(): return p
    return None

def _repair_loose_json_text(raw: str) -> str:
    raw = re.sub(r",\s*\]", "]", raw)
    raw = re.sub(r",\s*\}", "}", raw)
    return raw

def _extract_items_from_local_file(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    try:
        data = json.loads(text)
        return _unwrap_records(data)
    except Exception:
        pass
    text2 = _repair_loose_json_text(text)
    try:
        data = json.loads(text2)
        return _unwrap_records(data)
    except Exception:
        pass
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    items = []
    for line in lines:
        try:
            obj = json.loads(line)
            if isinstance(obj, dict): items.append(obj)
        except Exception:
            pass
    return items

def _load_local_dado_pool() -> Dict[str, Any]:
    path = _resolve_local_cards_path()
    if not path:
        return {"animes_list": [], "animes_by_id": {}, "characters_by_anime": {}}
    try:
        mtime = path.stat().st_mtime
        cache = _DADO_LOCAL_CACHE
        if cache["loaded"] and cache["path"] == str(path) and abs(cache["mtime"] - mtime) < 0.5:
            return cache
        raw_items = _extract_items_from_local_file(path)
        animes_by_id: Dict[int, Dict] = {}
        characters_by_anime: Dict[int, List] = {}
        for it in raw_items:
            aid = _safe_int(it.get("anime_id") or it.get("anilist_id"))
            if not aid: continue
            if aid not in animes_by_id:
                animes_by_id[aid] = {
                    "id": aid,
                    "title": str(it.get("anime") or it.get("anime_title") or "").strip(),
                    "cover": str(it.get("anime_cover") or it.get("cover") or "").strip() or _build_cover_from_anilist(aid),
                }
            cid = _safe_int(it.get("id") or it.get("character_id"))
            if not cid: continue
            if aid not in characters_by_anime: characters_by_anime[aid] = []
            characters_by_anime[aid].append({
                "id": cid,
                "name": str(it.get("name") or "").strip(),
                "image": str(it.get("image") or "").strip() or _build_char_image_from_anilist(cid),
                "anime_cover": animes_by_id[aid]["cover"],
                "anime_title": animes_by_id[aid]["title"],
            })
        animes_list = [
            {"id": aid, "title": a["title"], "cover": a["cover"]}
            for aid, a in animes_by_id.items()
            if characters_by_anime.get(aid)
        ]
        animes_list.sort(key=lambda x: x["title"].lower())
        cache.update({
            "mtime": mtime, "loaded": True, "path": str(path),
            "animes_list": animes_list,
            "animes_by_id": animes_by_id,
            "characters_by_anime": characters_by_anime,
        })
        return cache
    except Exception:
        return {"animes_list": [], "animes_by_id": {}, "characters_by_anime": {}}

def _max_dice_value_from_local_pool(pool: Optional[List] = None) -> int:
    if pool is None: pool = _load_local_dado_pool().get("animes_list", [])
    n = len(pool)
    if n <= 0: return 0
    if n >= 6: return 6
    return n

def _pick_random_local_animes(count: int, pool: Optional[List] = None) -> List[Dict]:
    if pool is None: pool = _load_local_dado_pool().get("animes_list", [])
    if not pool: return []
    count = max(1, min(count, len(pool)))
    return random.SystemRandom().sample(pool, count)

def _pick_random_local_character(anime_id: int) -> Optional[dict]:
    data = _load_local_dado_pool()
    chars = data.get("characters_by_anime", {}).get(int(anime_id), [])
    if not chars: return None
    return random.SystemRandom().choice(chars)

def _rarity_from_roll(dice_value: int, character_id: int) -> dict:
    seed = (int(dice_value) * 31337 + int(character_id) * 7) % 100
    if dice_value >= 6:
        if seed < 8: return {"tier": "LEGENDARY", "stars": 5}
        if seed < 22: return {"tier": "EPIC", "stars": 4}
        return {"tier": "RARE", "stars": 3}
    elif dice_value >= 4:
        if seed < 12: return {"tier": "EPIC", "stars": 4}
        if seed < 38: return {"tier": "RARE", "stars": 3}
        return {"tier": "UNCOMMON", "stars": 2}
    else:
        if seed < 16: return {"tier": "RARE", "stars": 3}
        if seed < 42: return {"tier": "UNCOMMON", "stars": 2}
        return {"tier": "COMMON", "stars": 1}

# =============================================================================
# MENU HELPERS
# =============================================================================
def _menu_user_payload(uid: int) -> Dict[str, Any]:
    create_or_get_user(uid)
    user = get_user_status(uid) or {}
    progress = get_progress_row(uid) or {}
    settings = get_profile_settings(uid) or {}
    cards = get_user_card_collection(uid) or []
    favorite = None
    fav_id = settings.get("favorite_character_id")
    if fav_id:
        try:
            ch = get_character_by_id(int(fav_id))
            if ch:
                favorite = {
                    "id": int(fav_id),
                    "name": str(ch.get("name") or "").strip(),
                    "anime": str(ch.get("anime") or "").strip(),
                    "image": str(ch.get("image") or "").strip(),
                }
        except Exception:
            favorite = None
    full_name = str(user.get("full_name") or "").strip()
    username = str(user.get("username") or "").strip()
    display_name = full_name or (f"@{username}" if username else f"User {uid}")
    return {
        "ok": True,
        "profile": {
            "user_id": int(uid),
            "display_name": display_name,
            "username": username,
            "coins": int(user.get("coins") or 0),
            "level": int(progress.get("level") or 1),
            "collection_total": len(cards),
            "nickname": str(settings.get("nickname") or "").strip(),
            "favorite": favorite,
            "country_code": str(settings.get("country_code") or "BR").strip().upper(),
            "language": str(settings.get("language") or "pt").strip().lower(),
            "private_profile": bool(settings.get("private_profile")),
            "notifications_enabled": bool(settings.get("notifications_enabled", True)),
        },
        "countries": COUNTRY_OPTIONS,
        "languages": LANGUAGE_OPTIONS,
    }

def _menu_collection_characters(uid: int) -> List[Dict[str, Any]]:
    rows = get_user_card_collection(uid) or []
    out: List[Dict[str, Any]] = []
    for row in rows:
        cid = int(row.get("character_id") or 0)
        qty = int(row.get("quantity") or 0)
        if cid <= 0 or qty <= 0: continue
        try: ch = get_character_by_id(cid)
        except Exception: ch = None
        if not ch: continue
        out.append({
            "id": cid,
            "name": str(ch.get("name") or "").strip(),
            "anime": str(ch.get("anime") or "").strip(),
            "image": str(ch.get("image") or "").strip(),
            "quantity": qty,
        })
    out.sort(key=lambda x: ((x["anime"] or "").lower(), (x["name"] or "").lower(), int(x["id"])))
    return out

# =============================================================================
# SHOP HELPERS
# =============================================================================
def _shop_collection_items(user_id: int, q: str = "") -> List[Dict[str, Any]]:
    rows = get_user_card_collection(user_id) or []
    qn = (q or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for row in rows:
        cid = int(row.get("character_id") or 0)
        qty = int(row.get("quantity") or 0)
        if cid <= 0 or qty <= 0: continue
        try: ch = get_character_by_id(cid)
        except Exception: ch = None
        if not ch: continue
        name = str(ch.get("name") or "").strip()
        anime = str(ch.get("anime") or "").strip()
        image = str(ch.get("image") or "").strip()
        if qn and qn not in (name + " " + anime).lower(): continue
        out.append({
            "character_id": cid,
            "character_name": name,
            "anime_title": anime,
            "image": image,
            "quantity": qty,
            "rarity": str(ch.get("rarity") or "").strip() or None,
        })
    out.sort(key=lambda x: ((x["anime_title"] or "").lower(), (x["character_name"] or "").lower()))
    return out

# =============================================================================
# PEDIDO HELPERS
# =============================================================================
_PEDIDO_ANIME_INDEX: Dict[str, Any] = {"title_norm": set(), "anilist_ids": set()}
_PEDIDO_MANGA_INDEX: Dict[str, Any] = {"title_norm": set(), "anilist_ids": set()}

def _pedido_build_index(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    idx: Dict[str, Any] = {"title_norm": set(), "anilist_ids": set()}
    for rec in records:
        titulo = str(rec.get("titulo") or rec.get("title") or "").strip()
        if titulo:
            idx["title_norm"].add(_normalize_title(titulo))
        aid = rec.get("anilist_id") or (rec.get("anilist") or {}).get("id")
        if aid:
            try: idx["anilist_ids"].add(int(aid))
            except Exception: pass
    return idx

def _pedido_reload_indexes():
    global _PEDIDO_ANIME_INDEX, _PEDIDO_MANGA_INDEX
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            anime_records = _unwrap_records(json.load(f))
        _PEDIDO_ANIME_INDEX = _pedido_build_index(anime_records)
    except Exception:
        _PEDIDO_ANIME_INDEX = {"title_norm": set(), "anilist_ids": set()}
    try:
        with open(MANGA_CATALOG_PATH, "r", encoding="utf-8") as f:
            manga_records = _unwrap_records(json.load(f))
        _PEDIDO_MANGA_INDEX = _pedido_build_index(manga_records)
    except Exception:
        _PEDIDO_MANGA_INDEX = {"title_norm": set(), "anilist_ids": set()}

_pedido_reload_indexes()

def _pedido_catalog_contains(media_type: str, title: str, anilist_id=None) -> bool:
    idx = _PEDIDO_ANIME_INDEX if media_type == "anime" else _PEDIDO_MANGA_INDEX
    if anilist_id:
        try:
            if int(anilist_id) in idx["anilist_ids"]: return True
        except Exception: pass
    return _normalize_title(title) in idx["title_norm"]

async def _pedido_anilist_search(query_text: str, media_type: str) -> List[Dict[str, Any]]:
    gql_type = "ANIME" if media_type == "anime" else "MANGA"
    query = """
    query ($search: String, $type: MediaType) {
      Page(page: 1, perPage: 18) {
        media(search: $search, type: $type, sort: SEARCH_MATCH) {
          id title { romaji english native }
          coverImage { large }
          averageScore format status seasonYear
          episodes chapters
        }
      }
    }"""
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": {"search": query_text, "type": gql_type}},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        data = r.json()
    return (data.get("data") or {}).get("Page", {}).get("media") or []

# =============================================================================
# CAKTO HELPERS
# =============================================================================
def _extract_cakto_ids(payload: Dict[str, Any]) -> Dict[str, str]:
    data = payload.get("data") or {}
    customer = data.get("customer") or {}
    order = data.get("order") or {}
    order_id = (str(order.get("id") or "").strip()
                or str(data.get("order_id") or "").strip()
                or str(payload.get("order_id") or "").strip())
    subscription_id = (str(data.get("subscription_id") or "").strip()
                       or str(payload.get("subscription_id") or "").strip())
    external_reference = (str(data.get("external_reference") or "").strip()
                          or str(order.get("external_reference") or "").strip()
                          or str(payload.get("external_reference") or "").strip())
    customer_id = (str(customer.get("id") or "").strip()
                   or str(data.get("customer_id") or "").strip())
    return {"order_id": order_id, "subscription_id": subscription_id,
            "external_reference": external_reference, "customer_id": customer_id}


# =============================================================================
# TERMS — TEXTOS E HTML
# =============================================================================
TEXTS = {
    "pt": {
        "title": "Termos de Uso e Privacidade",
        "subtitle": f"Revisão: {TERMS_VERSION}",
        "intro": "Antes de continuar, você precisa ler e aceitar os termos abaixo.",
        "check1": "Aceito a Política de Privacidade",
        "check2": "Aceito os Termos de Uso",
        "accept": "ACEITAR E CONTINUAR",
        "decline": "Não aceito",
        "done": "✅ Aceito com sucesso. Volte ao Telegram.",
        "no": "❌ Sem aceitar os Termos, você não consegue usar a Source Baltigo.",
        "error": "Erro. Tente novamente.",
        "need_checks": "⚠️ Marque as duas opções para continuar.",
        "join_needed": "📢 Antes de continuar, entre no canal e clique em \u201cVerificar inscrição\u201d.",
        "saving": "⏳ Salvando...",
        "processing": "⏳ Processando...",
        "join_title": "CANAL OBRIGATÓRIO",
        "join_text": "Para continuar, é obrigatório entrar no nosso canal oficial.",
        "join_button": "📢 ENTRAR NO CANAL",
        "verify_button": "✅ VERIFICAR INSCRIÇÃO",
        "verify_ok": "✅ Inscrição confirmada. Você já pode continuar.",
        "verify_fail": "❌ Ainda não foi possível confirmar. Entre no canal e verifique novamente.",
        "verify_confirmed": "✅ CONFIRMADO",
    },
    "en": {
        "title": "Terms of Use & Privacy",
        "subtitle": f"Revision: {TERMS_VERSION}",
        "intro": "Before continuing, you must read and accept the terms below.",
        "check1": "I accept the Privacy Policy",
        "check2": "I accept the Terms of Use",
        "accept": "ACCEPT & CONTINUE",
        "decline": "I do not accept",
        "done": "✅ Accepted successfully. Go back to Telegram.",
        "no": "❌ Without accepting the Terms, you cannot use Source Baltigo.",
        "error": "Error. Please try again.",
        "need_checks": "⚠️ Check both boxes to continue.",
        "join_needed": "📢 Before continuing, join the channel and tap 201cVerify membership201d.",
        "saving": "⏳ Saving...",
        "processing": "⏳ Processing...",
        "join_title": "REQUIRED CHANNEL",
        "join_text": "To continue, you must join our official channel.",
        "join_button": "📢 JOIN CHANNEL",
        "verify_button": "✅ VERIFY MEMBERSHIP",
        "verify_ok": "✅ Membership confirmed. You can continue.",
        "verify_fail": "❌ Couldn't confirm yet. Join the channel and try again.",
        "verify_confirmed": "✅ CONFIRMED",
    },
    "es": {
        "title": "Términos de Uso y Privacidad",
        "subtitle": f"Revisión: {TERMS_VERSION}",
        "intro": "Antes de continuar, debes leer y aceptar los términos a continuación.",
        "check1": "Acepto la Política de Privacidad",
        "check2": "Acepto los Términos de Uso",
        "accept": "ACEPTAR Y CONTINUAR",
        "decline": "No acepto",
        "done": "✅ Aceptado con éxito. Vuelve a Telegram.",
        "no": "❌ Sin aceptar los Términos, no puedes usar Source Baltigo.",
        "error": "Error. Inténtalo de nuevo.",
        "need_checks": "⚠️ Marca ambas casillas para continuar.",
        "join_needed": "📢 Antes de continuar, entra al canal y toca 201cVerificar suscripción201d.",
        "saving": "⏳ Guardando...",
        "processing": "⏳ Procesando...",
        "join_title": "CANAL OBLIGATORIO",
        "join_text": "Para continuar, es obligatorio unirte a nuestro canal oficial.",
        "join_button": "📢 UNIRME AL CANAL",
        "verify_button": "✅ VERIFICAR SUSCRIPCIÓN",
        "verify_ok": "✅ Suscripción confirmada. Ya puedes continuar.",
        "verify_fail": "❌ Aún no se pudo confirmar. Entra al canal y vuelve a verificar.",
        "verify_confirmed": "✅ CONFIRMADO",
    },
}

TERMS_LONG = {
    "pt": """
<div class="terms-section"><div class="terms-heading">SUA PRIVACIDADE</div>
<p>Coletamos apenas o seu ID numérico do Telegram e dados necessários para o funcionamento do bot
(idioma, registro de aceite e informações de uso dentro do bot).
Não temos acesso às suas conversas privadas fora do bot.</p></div>
<div class="terms-section"><div class="terms-heading">CANAL OFICIAL (OBRIGATÓRIO)</div>
<p>Para usar o bot, é obrigatório entrar e permanecer no nosso canal oficial.
Caso você saia do canal, o acesso pode ser bloqueado até regularizar.</p></div>
<div class="terms-section"><div class="terms-heading">USO JUSTO E SEGURANÇA</div>
<p>Não é permitido spam, automação, exploração de falhas, tentativa de duplicação de recompensas
ou qualquer prática que prejudique outros usuários.</p></div>
<div class="terms-section"><div class="terms-heading">SUA RESPONSABILIDADE</div>
<p>Ao aceitar, você confirma que leu e concorda com estas regras.
As funcionalidades podem mudar para manter equilíbrio e segurança.</p></div>""",
    "en": """
<div class="terms-section"><div class="terms-heading">YOUR PRIVACY</div>
<p>We only collect your Telegram numeric ID and what is required to operate the bot
(language, acceptance record, and usage data inside the bot).
We do not access your private chats outside the bot.</p></div>
<div class="terms-section"><div class="terms-heading">OFFICIAL CHANNEL (REQUIRED)</div>
<p>To use the bot, you must join and remain in our official channel.
If you leave, access may be blocked until you rejoin.</p></div>
<div class="terms-section"><div class="terms-heading">FAIR USE & SECURITY</div>
<p>Spam, automation, exploits, reward duplication, or abusive usage is not allowed.</p></div>
<div class="terms-section"><div class="terms-heading">YOUR RESPONSIBILITY</div>
<p>By accepting, you confirm that you read and agree to these rules.
Features may change to maintain balance and security.</p></div>""",
    "es": """
<div class="terms-section"><div class="terms-heading">TU PRIVACIDAD</div>
<p>Solo recopilamos tu ID numérico de Telegram y lo necesario para operar el bot.
No accedemos a tus chats privados fuera del bot.</p></div>
<div class="terms-section"><div class="terms-heading">CANAL OFICIAL (OBLIGATORIO)</div>
<p>Para usar el bot, es obligatorio unirte y permanecer en nuestro canal oficial.</p></div>
<div class="terms-section"><div class="terms-heading">USO JUSTO Y SEGURIDAD</div>
<p>No se permite spam, automatización, explotación de fallos ni abuso de botones.</p></div>
<div class="terms-section"><div class="terms-heading">TU RESPONSABILIDAD</div>
<p>Al aceptar, confirmas que leíste y aceptas estas reglas.</p></div>""",
}

# =============================================================================
# ROUTES — ROOT
# =============================================================================
@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse("✅ Source Baltigo WebApp online.")

# =============================================================================
# ROUTES — TERMS
# =============================================================================
@app.get("/terms", response_class=HTMLResponse)
def terms_page(uid: int = Query(...), lang: str = Query("en")):
    L = pick_lang(lang)
    t = TEXTS[L]
    body = TERMS_LONG[L]
    bg = BACKGROUND_URL if BACKGROUND_URL else EMPTY_BG_DATA_URI

    terms_css = f"""
body {{
  background:
    linear-gradient(180deg, rgba(0,0,0,.60), rgba(0,0,0,.80)),
    url("{bg}") center/cover no-repeat fixed,
    radial-gradient(1200px 700px at 20% 10%, rgba(59,130,246,.16), transparent 60%),
    radial-gradient(900px 600px at 80% 30%, rgba(168,85,247,.14), transparent 60%),
    #050712;
}}
.terms-card {{
  background: rgba(12,16,28,.68);
  border: 1px solid rgba(255,255,255,.10);
  border-radius: var(--r-xl);
  overflow: hidden;
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
  max-width: 720px;
  margin: 0 auto;
}}
.terms-hero {{
  width: 100%;
  height: 180px;
  object-fit: cover;
  display: block;
  object-position: center;
}}
.terms-hero-overlay {{
  position: relative;
}}
.terms-hero-overlay::after {{
  content: "";
  position: absolute; inset: 0;
  background: linear-gradient(180deg, transparent 30%, rgba(12,16,28,.80));
  pointer-events: none;
}}
.terms-body {{
  padding: 22px 20px 28px;
}}
.lang-badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid rgba(255,255,255,.14);
  border-radius: 999px;
  background: rgba(255,255,255,.06);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 16px;
}}
.terms-title {{
  font-size: clamp(22px, 5vw, 30px);
  font-weight: 900;
  line-height: 1.15;
  letter-spacing: -.02em;
  margin: 0 0 6px;
}}
.terms-intro {{
  color: var(--muted);
  font-size: 14px;
  line-height: 1.6;
  margin: 0 0 20px;
}}
.terms-content {{
  border: 1px solid rgba(255,255,255,.08);
  border-radius: var(--r-lg);
  background: rgba(255,255,255,.03);
  padding: 18px;
  max-height: 260px;
  overflow-y: auto;
  margin-bottom: 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,.15) transparent;
}}
.terms-section {{ margin-bottom: 16px; }}
.terms-heading {{
  font-size: 11px;
  font-weight: 900;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 8px;
}}
.terms-section p {{
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.65;
}}
.channel-block {{
  border: 1px solid rgba(255,255,255,.10);
  border-radius: var(--r-lg);
  background: rgba(255,255,255,.04);
  padding: 16px;
  margin-bottom: 20px;
}}
.channel-title {{
  font-size: 11px;
  font-weight: 900;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--warn);
  margin-bottom: 8px;
}}
.channel-text {{
  font-size: 13px;
  color: var(--muted);
  margin-bottom: 14px;
  line-height: 1.5;
}}
.channel-btns {{
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}}
.checks {{
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}}
.check-label {{
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  padding: 14px 16px;
  border: 1px solid var(--stroke);
  border-radius: var(--r-md);
  background: rgba(255,255,255,.03);
  transition: border-color .14s ease;
  user-select: none;
}}
.check-label:has(input:checked) {{
  border-color: rgba(74,222,128,.38);
  background: rgba(74,222,128,.06);
}}
.check-label input[type=checkbox] {{
  width: 20px; height: 20px;
  accent-color: var(--ok);
  flex: 0 0 auto;
  cursor: pointer;
}}
.check-label span {{
  font-size: 14px;
  font-weight: 800;
  line-height: 1.4;
}}
.action-row {{
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.terms-footer {{
  text-align: center;
  padding: 14px;
  color: rgba(255,255,255,.25);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
  border-top: 1px solid rgba(255,255,255,.06);
}}
"""

    terms_js = f"""<script>
const uid = {uid};
let lang = "{L}";
let channel_ok = false;

const checkChannelBtn = document.getElementById("checkChannelBtn");
const acceptBtn = document.getElementById("acceptBtn");
const declineBtn = document.getElementById("declineBtn");
const msgEl = document.getElementById("statusMsg");
const c1 = document.getElementById("check1");
const c2 = document.getElementById("check2");

function setMsg(text, cls) {{
  msgEl.textContent = text;
  msgEl.style.display = text ? "block" : "none";
  msgEl.style.color = cls === "ok" ? "var(--ok)" : cls === "err" ? "var(--danger)" : "var(--muted)";
}}

checkChannelBtn && checkChannelBtn.addEventListener("click", async () => {{
  setMsg("{t["processing"]}", "");
  try {{
    const r = await fetch("/api/channel/check", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{uid}})
    }});
    const data = await r.json();
    if (data.ok) {{
      channel_ok = true;
      setMsg("{t["verify_ok"]}", "ok");
      checkChannelBtn.textContent = "{t["verify_confirmed"]}";
      checkChannelBtn.disabled = true;
    }} else {{
      setMsg("{t["verify_fail"]}", "err");
    }}
  }} catch(e) {{
    setMsg("❌ " + (e.message || "{t["verify_fail"]}"), "err");
  }}
}});

acceptBtn && acceptBtn.addEventListener("click", async () => {{
  if (!(c1.checked && c2.checked)) {{ setMsg("{t["need_checks"]}", "err"); return; }}
  if (!channel_ok) {{ setMsg("{t["join_needed"]}", "err"); return; }}
  setMsg("{t["saving"]}", "");
  try {{
    const r = await fetch("/api/terms/accept", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{uid, lang}})
    }});
    const data = await r.json();
    setMsg(data.message || "{t["done"]}", data.ok ? "ok" : "err");
  }} catch(e) {{
    setMsg("❌ " + (e.message || "{t["error"]}"), "err");
  }}
}});

declineBtn && declineBtn.addEventListener("click", async () => {{
  setMsg("{t["processing"]}", "");
  try {{
    const r = await fetch("/api/terms/decline", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{uid, lang}})
    }});
    const data = await r.json();
    setMsg(data.message || "{t["no"]}", "");
  }} catch(e) {{
    setMsg("❌ " + (e.message || "{t["error"]}"), "err");
  }}
}});
</script>"""

    body_html = f"""<div class="wrap" style="padding-top:20px;">
  <div class="terms-card">
    <div class="terms-hero-overlay">
      <img class="terms-hero" src="{TOP_BANNER_URL}" alt="Source Baltigo"/>
    </div>
    <div class="terms-body">
      <div class="lang-badge">🌐 {L.upper()} &nbsp;•&nbsp; {TERMS_VERSION.upper()}</div>
      <h1 class="terms-title">{t["title"]}</h1>
      <p class="terms-intro">{t["intro"]}</p>

      <div class="terms-content">{body}</div>

      <div class="channel-block">
        <div class="channel-title">📢 {t["join_title"]}</div>
        <div class="channel-text">{t["join_text"]}</div>
        <div class="channel-btns">
          <a class="btn btn-ghost" href="{REQUIRED_CHANNEL_URL}" target="_blank" rel="noopener">{t["join_button"]}</a>
          <button class="btn btn-primary" id="checkChannelBtn" type="button">{t["verify_button"]}</button>
        </div>
      </div>

      <div class="checks">
        <label class="check-label">
          <input type="checkbox" id="check1"/>
          <span>{t["check1"]}</span>
        </label>
        <label class="check-label">
          <input type="checkbox" id="check2"/>
          <span>{t["check2"]}</span>
        </label>
      </div>

      <div id="statusMsg" class="msg" style="display:none;margin-bottom:12px;"></div>

      <div class="action-row">
        <button class="btn btn-ok btn-full" id="acceptBtn" type="button">{t["accept"]}</button>
        <button class="btn btn-ghost btn-full" id="declineBtn" type="button" style="font-size:12px;">{t["decline"]}</button>
      </div>
    </div>
    <div class="terms-footer">REVISÃO • {TERMS_VERSION.upper()} • SOURCE BALTIGO</div>
  </div>
</div>"""

    return HTMLResponse(_page(t["title"], body_html, terms_css, terms_js))

@app.post("/api/terms/accept")
def api_accept(payload: dict = Body(...)):
    try:
        uid = int(payload.get("uid") or 0)
        lang = pick_lang(payload.get("lang"))
        if uid <= 0:
            return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
        create_or_get_user(uid)
        set_language(uid, lang)
        accept_terms(uid, TERMS_VERSION)
        return {"ok": True, "message": TEXTS[lang]["done"]}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "message": f"Erro interno: {type(e).__name__}"}, status_code=500)

@app.post("/api/terms/decline")
def api_decline(payload: dict = Body(...)):
    try:
        uid = int(payload.get("uid") or 0)
        lang = pick_lang(payload.get("lang"))
        if uid <= 0:
            return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
        create_or_get_user(uid)
        set_language(uid, lang)
        return {"ok": True, "message": TEXTS[lang]["no"]}
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)

@app.post("/api/channel/check")
def api_channel_check(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    if not REQUIRED_CHANNEL: return {"ok": True}
    if not BOT_TOKEN:
        return JSONResponse({"ok": False, "message": "BOT_TOKEN ausente."}, status_code=500)
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember",
                params={"chat_id": REQUIRED_CHANNEL, "user_id": uid}
            )
            data = r.json()
        if not data.get("ok"): return {"ok": False}
        result = data.get("result") or {}
        status = (result.get("status") or "").lower()
        is_member = bool(result.get("is_member", False))
        ok = (status in ("creator", "administrator", "member")) or (status == "restricted" and is_member)
        return {"ok": ok}
    except Exception as e:
        print("❌ /api/channel/check:", repr(e), flush=True)
        return {"ok": False}


# =============================================================================
# ROUTES — CATALOGO ANIME
# =============================================================================
@app.get("/api/letters")
def api_letters():
    return JSONResponse({
        "total": _TOTAL,
        "all_count": _TOTAL,
        "counts": _LETTER_COUNTS,
    })

@app.get("/api/catalogo")
def api_catalogo(
    letter: str = Query(default="ALL", max_length=2),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = _filter_catalog(q.strip(), letter.strip().upper(), limit, offset)
    return JSONResponse({"total": total, "items": items})

@app.get("/catalogo", response_class=HTMLResponse)
def catalogo_page():
    pat = BACKGROUND_PATTERN_URL if BACKGROUND_PATTERN_URL else ""
    extra_css = f"""
.catalog-pattern {{
  position: fixed; inset: 0;
  background-image: url("{pat}");
  background-size: 520px;
  background-repeat: repeat;
  opacity: .08;
  filter: grayscale(1) contrast(1.1);
  pointer-events: none;
  z-index: 0;
}}
.letters-strip {{
  margin-top: 14px;
  border: 1px solid var(--stroke);
  border-radius: var(--r-lg);
  background: var(--panel2);
  padding: 14px;
  box-shadow: var(--shadow2);
}}
.letters-grid {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}}
.letter-btn {{
  border: 1px solid var(--stroke);
  background: rgba(255,255,255,.04);
  border-radius: var(--r-sm);
  padding: 8px 10px;
  min-width: 48px;
  text-align: center;
  cursor: pointer;
  transition: background .12s ease, border-color .12s ease;
  user-select: none;
}}
.letter-btn .k {{
  font-size: 11px;
  font-weight: 900;
  letter-spacing: .10em;
  text-transform: uppercase;
}}
.letter-btn .n {{
  font-size: 10px;
  color: var(--muted);
  font-weight: 700;
  margin-top: 2px;
}}
.letter-btn.active {{
  background: var(--accent2);
  border-color: rgba(90,168,255,.42);
}}
.head-row {{
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 4px 8px;
}}
.head-row .title {{
  font-weight: 900;
  letter-spacing: .08em;
  text-transform: uppercase;
  font-size: 20px;
}}
.head-row .subtitle {{
  margin-top: 4px;
  color: var(--muted);
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
  font-size: 11px;
}}
.load-more {{
  display: block;
  width: 100%;
  max-width: 320px;
  margin: 16px auto 0;
  border: 1px solid var(--stroke);
  background: var(--panel2);
  color: var(--txt);
  border-radius: var(--r-md);
  padding: 13px 14px;
  font-weight: 900;
  letter-spacing: .10em;
  text-transform: uppercase;
  cursor: pointer;
  font-family: var(--font);
  font-size: 12px;
}}
.load-more:disabled {{ opacity: .45; cursor: not-allowed; }}
"""
    body = f"""<div class="catalog-pattern"></div>
<div class="wrap">
  <div class="top-banner">
    <img src="{CATALOG_BANNER_URL}" alt="Catálogo"/>
  </div>
  <div class="head-row">
    <div>
      <div class="title">{CATALOG_TITLE}</div>
      <div class="subtitle"><span id="totalTxt">{CATALOG_SUBTITLE}: ...</span></div>
    </div>
    <div class="search-bar" style="flex:1;min-width:200px;max-width:360px;">
      <span style="opacity:.55;font-weight:900;">🔎</span>
      <input id="q" type="text" placeholder="BUSCAR ANIME..."/>
    </div>
  </div>
  <div class="letters-strip">
    <div class="letters-grid" id="lettersGrid"></div>
  </div>
  <div class="cards-grid" id="cards"></div>
  <button class="load-more" id="btnMore">CARREGAR MAIS</button>
  <div class="footer">Source Baltigo • Catálogo Geral</div>
</div>"""

    js = """<script>
const CSUB = "__CSUB__".replace("__CSUB__","__CATALOG_SUB__");
let state = { letter:"ALL", q:"", limit:60, offset:0, total:0, loading:false };

function esc(s){ return (s||"").replace(/[&<>"']/g,(m)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m])); }

function openLink(link){
  try{ if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.openTelegramLink){ Telegram.WebApp.openTelegramLink(link); return; } }catch(e){}
  window.open(link,"_blank");
}

function makeLetterButton(key,count){
  const el=document.createElement("div");
  el.className="letter-btn"+(state.letter===key?" active":"");
  el.innerHTML=`<div class="k">${esc(key==="ALL"?"TODOS":key)}</div><div class="n">${key==="ALL"?(count>999?"999+":count):count}</div>`;
  el.onclick=()=>{ state.letter=key; state.offset=0; document.getElementById("cards").innerHTML=""; renderLetters(); loadCatalog(true); };
  return el;
}

async function renderLetters(){
  const grid=document.getElementById("lettersGrid");
  grid.innerHTML="";
  const res=await fetch("/api/letters?_ts="+Date.now());
  const data=await res.json();
  document.getElementById("totalTxt").textContent="TOTAL: "+(data.total??0);
  grid.appendChild(makeLetterButton("ALL",data.all_count||data.total||0));
  grid.appendChild(makeLetterButton("#",(data.counts&&data.counts["#"])||0));
  for(let c=65;c<=90;c++){
    const k=String.fromCharCode(c);
    grid.appendChild(makeLetterButton(k,(data.counts&&data.counts[k])||0));
  }
}

function makeCard(item){
  const card=document.createElement("div");
  card.className="card";
  card.style.cursor="pointer";
  const hasCover=item.cover_url&&item.cover_url.length>5;
  const pills=[item.year,item.score?("★ "+item.score):null,item.format].filter(Boolean).map(p=>`<span class="pill">${esc(String(p))}</span>`).join("");
  card.innerHTML=`
    <div class="cover">
      ${hasCover?`<img src="${esc(item.cover_url)}" alt="${esc(item.titulo)}" loading="lazy"/>`:``}
      <span class="pill" style="position:absolute;left:10px;bottom:10px;z-index:2;">${esc(item.badge||"ANIME")}</span>
    </div>
    <div class="meta">
      <p class="name">${esc(item.titulo)}</p>
      <div class="sub">${pills||'<span class="pill">CANAL</span>'}</div>
    </div>`;
  card.onclick=()=>openLink(item.link_post);
  return card;
}

async function loadCatalog(reset=false){
  if(state.loading)return;
  state.loading=true;
  const btn=document.getElementById("btnMore");
  btn.disabled=true; btn.textContent="CARREGANDO...";
  const params=new URLSearchParams({letter:state.letter,q:state.q,limit:state.limit,offset:state.offset,_ts:Date.now()});
  const res=await fetch("/api/catalogo?"+params);
  const data=await res.json();
  state.total=data.total||0;
  const cards=document.getElementById("cards");
  for(const it of(data.items||[])) cards.appendChild(makeCard(it));
  state.offset+=(data.items||[]).length;
  if(state.offset>=state.total){ btn.disabled=true; btn.textContent="FIM DA LISTA"; }
  else{ btn.disabled=false; btn.textContent="CARREGAR MAIS"; }
  state.loading=false;
}

function debounce(fn,ms){ let t=null; return(...a)=>{ if(t)clearTimeout(t); t=setTimeout(()=>fn(...a),ms); }; }
const onSearch=debounce(()=>{ state.q=(document.getElementById("q").value||"").trim(); state.offset=0; document.getElementById("cards").innerHTML=""; loadCatalog(true); },280);
document.getElementById("q").addEventListener("input",onSearch);
document.getElementById("btnMore").addEventListener("click",()=>loadCatalog(false));
(async()=>{ await renderLetters(); await loadCatalog(true); })();
</script>""".replace("__CATALOG_SUB__", CATALOG_SUBTITLE)

    return HTMLResponse(_page(f"{CATALOG_TITLE} — Source Baltigo", body, extra_css, js))

# =============================================================================
# ROUTES — CATALOGO MANGÁS
# =============================================================================
@app.get("/api/mangas/letters")
def api_manga_letters():
    return JSONResponse({
        "total": _MANGA_TOTAL,
        "all_count": _MANGA_TOTAL,
        "counts": _MANGA_LETTER_COUNTS,
    })

@app.get("/api/mangas/catalogo")
def api_manga_catalogo(
    letter: str = Query(default="ALL", max_length=2),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = _filter_manga_catalog(q.strip(), letter.strip().upper(), limit, offset)
    return JSONResponse({"total": total, "items": items})

@app.get("/mangas", response_class=HTMLResponse)
def mangas_page():
    pat = MANGA_BACKGROUND_PATTERN_URL if MANGA_BACKGROUND_PATTERN_URL else ""
    extra_css = f"""
.catalog-pattern {{
  position: fixed; inset: 0;
  background-image: url("{pat}");
  background-size: 520px; background-repeat: repeat;
  opacity: .08; filter: grayscale(1); pointer-events: none; z-index: 0;
}}
.letters-strip {{ margin-top:14px; border:1px solid var(--stroke); border-radius:var(--r-lg); background:var(--panel2); padding:14px; }}
.letters-grid {{ display:flex; flex-wrap:wrap; gap:6px; }}
.letter-btn {{ border:1px solid var(--stroke); background:rgba(255,255,255,.04); border-radius:var(--r-sm); padding:8px 10px; min-width:48px; text-align:center; cursor:pointer; user-select:none; }}
.letter-btn .k {{ font-size:11px; font-weight:900; letter-spacing:.10em; text-transform:uppercase; }}
.letter-btn .n {{ font-size:10px; color:var(--muted); font-weight:700; margin-top:2px; }}
.letter-btn.active {{ background:var(--accent2); border-color:rgba(90,168,255,.42); }}
.head-row {{ display:flex; align-items:flex-end; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:16px 4px 8px; }}
.head-row .title {{ font-weight:900; letter-spacing:.08em; text-transform:uppercase; font-size:20px; }}
.head-row .subtitle {{ margin-top:4px; color:var(--muted); font-weight:700; letter-spacing:.12em; text-transform:uppercase; font-size:11px; }}
.load-more {{ display:block; width:100%; max-width:320px; margin:16px auto 0; border:1px solid var(--stroke); background:var(--panel2); color:var(--txt); border-radius:var(--r-md); padding:13px 14px; font-weight:900; letter-spacing:.10em; text-transform:uppercase; cursor:pointer; font-family:var(--font); font-size:12px; }}
.load-more:disabled {{ opacity:.45; cursor:not-allowed; }}
"""
    body = f"""<div class="catalog-pattern"></div>
<div class="wrap">
  <div class="top-banner"><img src="{MANGA_CATALOG_BANNER_URL}" alt="Mangás"/></div>
  <div class="head-row">
    <div>
      <div class="title">{MANGA_CATALOG_TITLE}</div>
      <div class="subtitle"><span id="totalTxt">{MANGA_CATALOG_SUBTITLE}: ...</span></div>
    </div>
    <div class="search-bar" style="flex:1;min-width:200px;max-width:360px;">
      <span style="opacity:.55;font-weight:900;">🔎</span>
      <input id="q" type="text" placeholder="BUSCAR MANGÁ..."/>
    </div>
  </div>
  <div class="letters-strip"><div class="letters-grid" id="lettersGrid"></div></div>
  <div class="cards-grid" id="cards"></div>
  <button class="load-more" id="btnMore">CARREGAR MAIS</button>
  <div class="footer">Source Baltigo • Catálogo Mangás</div>
</div>"""

    js = """<script>
let state={letter:"ALL",q:"",limit:60,offset:0,total:0,loading:false};
function esc(s){return(s||"").replace(/[&<>"']/g,(m)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));}
function openLink(link){try{if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.openTelegramLink){Telegram.WebApp.openTelegramLink(link);return;}}catch(e){}window.open(link,"_blank");}
function makeLetterButton(key,count){const el=document.createElement("div");el.className="letter-btn"+(state.letter===key?" active":"");el.innerHTML=`<div class="k">${esc(key==="ALL"?"TODOS":key)}</div><div class="n">${key==="ALL"?(count>999?"999+":count):count}</div>`;el.onclick=()=>{state.letter=key;state.offset=0;document.getElementById("cards").innerHTML="";renderLetters();loadCatalog(true);};return el;}
async function renderLetters(){const grid=document.getElementById("lettersGrid");grid.innerHTML="";const res=await fetch("/api/mangas/letters?_ts="+Date.now());const data=await res.json();document.getElementById("totalTxt").textContent="TOTAL: "+(data.total??0);grid.appendChild(makeLetterButton("ALL",data.all_count||data.total||0));grid.appendChild(makeLetterButton("#",(data.counts&&data.counts["#"])||0));for(let c=65;c<=90;c++){const k=String.fromCharCode(c);grid.appendChild(makeLetterButton(k,(data.counts&&data.counts[k])||0));}}
function makeCard(item){const card=document.createElement("div");card.className="card";card.style.cursor="pointer";const hasCover=item.cover_url&&item.cover_url.length>5;const pills=[item.year,item.score?("★ "+item.score):null,item.chapters?(item.chapters+" caps"):null].filter(Boolean).map(p=>`<span class="pill">${esc(String(p))}</span>`).join("");card.innerHTML=`<div class="cover">${hasCover?`<img src="${esc(item.cover_url)}" alt="${esc(item.titulo)}" loading="lazy"/>`:`}`}<span class="pill" style="position:absolute;left:10px;bottom:10px;z-index:2;">${esc(item.badge||"MANGÁ")}</span></div><div class="meta"><p class="name">${esc(item.titulo)}</p><div class="sub">${pills||'<span class="pill">CANAL</span>'}</div></div>`;card.onclick=()=>openLink(item.link_post);return card;}
async function loadCatalog(reset=false){if(state.loading)return;state.loading=true;const btn=document.getElementById("btnMore");btn.disabled=true;btn.textContent="CARREGANDO...";const params=new URLSearchParams({letter:state.letter,q:state.q,limit:state.limit,offset:state.offset,_ts:Date.now()});const res=await fetch("/api/mangas/catalogo?"+params);const data=await res.json();state.total=data.total||0;const cards=document.getElementById("cards");for(const it of(data.items||[]))cards.appendChild(makeCard(it));state.offset+=(data.items||[]).length;if(state.offset>=state.total){btn.disabled=true;btn.textContent="FIM DA LISTA";}else{btn.disabled=false;btn.textContent="CARREGAR MAIS";}state.loading=false;}
function debounce(fn,ms){let t=null;return(...a)=>{if(t)clearTimeout(t);t=setTimeout(()=>fn(...a),ms);};}
const onSearch=debounce(()=>{state.q=(document.getElementById("q").value||"").trim();state.offset=0;document.getElementById("cards").innerHTML="";loadCatalog(true);},280);
document.getElementById("q").addEventListener("input",onSearch);
document.getElementById("btnMore").addEventListener("click",()=>loadCatalog(false));
(async()=>{await renderLetters();await loadCatalog(true);})();
</script>"""

    return HTMLResponse(_page(f"{MANGA_CATALOG_TITLE} — Source Baltigo", body, extra_css, js))


# =============================================================================
# ROUTES — CARDS (usa cards_service — versão completa, sem duplicatas)
# =============================================================================
@app.get("/api/cards/reload")
def api_cards_reload():
    reload_cards_cache()
    data = build_cards_final_data(force_reload=True)
    return JSONResponse({
        "ok": True,
        "total_animes": len(data["animes_list"]),
        "total_characters": len(data["characters_by_id"]),
    })

@app.get("/api/cards/animes")
def api_cards_animes(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    data = build_cards_final_data()
    items = data["animes_list"]
    qn = q.strip().lower()
    if qn:
        items = [x for x in items if qn in x["anime"].lower()]
    total = len(items)
    items = items[offset:offset + limit]
    return JSONResponse({"ok": True, "total": total, "items": items})

@app.get("/api/cards/characters")
def api_cards_characters(
    anime_id: int = Query(...),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    data = build_cards_final_data()
    anime = data["animes_by_id"].get(anime_id)
    if not anime:
        return JSONResponse({"ok": False, "anime": None, "total": 0, "items": []})
    chars = list(data["characters_by_anime"].get(anime_id, []))
    qn = q.strip().lower()
    if qn:
        chars = [x for x in chars if qn in x["name"].lower()]
    total = len(chars)
    chars = chars[offset:offset + limit]
    return JSONResponse({"ok": True, "anime": anime, "total": total, "items": chars})

@app.get("/api/cards/search")
def api_cards_search(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
):
    items = search_characters(q, limit=limit)
    return JSONResponse({"ok": True, "total": len(items), "items": items})

@app.get("/api/cards/find-anime")
def api_cards_find_anime(q: str = Query(..., min_length=1, max_length=120)):
    anime = find_anime(q)
    return JSONResponse({"ok": bool(anime), "anime": anime})

@app.get("/api/cards/subcategories")
def api_cards_subcategories():
    items = list_subcategories()
    return JSONResponse({"ok": True, "items": items})

@app.get("/api/cards/subcategory")
def api_cards_subcategory(
    name: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    data = build_cards_final_data()
    chars = list(data["characters_by_id"].values())
    name_lower = name.strip().lower()
    matching = [c for c in chars if name_lower in [s.lower() for s in (c.get("subcategories") or [])]]
    total = len(matching)
    matching = matching[offset:offset + limit]
    return JSONResponse({"ok": True, "name": name, "total": total, "items": matching})

_CARDS_CSS = """
.cards-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 14px 4px 8px;
}
.cards-stats {
  font-weight: 900;
  letter-spacing: .10em;
  text-transform: uppercase;
  font-size: 11px;
  color: var(--muted);
}
.search-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}
.subs-box {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.sub-btn {
  border: 1px solid var(--stroke);
  background: var(--panel2);
  color: var(--txt);
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: .10em;
  text-transform: uppercase;
  cursor: pointer;
  transition: background .12s ease, border-color .12s ease;
  font-family: var(--font);
}
.sub-btn:hover { background: var(--accent2); border-color: rgba(90,168,255,.42); }
.char-card .cover { height: 280px; }
.char-card .id-pill {
  position: absolute;
  left: 10px; bottom: 10px;
  z-index: 2;
}
.hero-anime {
  width: 100%;
  min-height: 220px;
  border-radius: var(--r-lg);
  overflow: hidden;
  border: 1px solid var(--stroke);
  box-shadow: var(--shadow);
  position: relative;
  background: #101827;
}
.hero-anime img {
  width: 100%;
  height: 220px;
  object-fit: cover;
  display: block;
}
.hero-anime::after {
  content: "";
  position: absolute; inset: 0;
  background: linear-gradient(180deg, rgba(0,0,0,.04), rgba(0,0,0,.74));
  pointer-events: none;
}
.hero-copy {
  position: absolute;
  left: 18px; right: 18px; bottom: 16px;
  z-index: 2;
}
"""

@app.get("/cards", response_class=HTMLResponse)
def cards_page():
    body = f"""<div class="wrap">
  <div class="top-banner">
    <img src="{CARDS_TOP_BANNER_URL}" alt="Cards banner"/>
    <div class="top-copy">
      <div class="eyebrow">🃏 Cards • Source Baltigo</div>
      <div style="margin-top:10px;font-size:22px;font-weight:900;">Coleção de Personagens</div>
      <div style="margin-top:4px;color:rgba(255,255,255,.72);font-size:13px;">Obras, subcategorias e personagens</div>
    </div>
  </div>

  <div class="cards-header">
    <div class="cards-stats" id="statsTxt">Carregando...</div>
  </div>

  <div class="search-stack">
    <div class="search-bar">
      <span style="opacity:.55;font-weight:900;">🎬</span>
      <input id="searchInput" type="text" placeholder="Buscar obra..."/>
    </div>
    <div class="search-bar">
      <span style="opacity:.55;font-weight:900;">🧍</span>
      <input id="charSearchInput" type="text" placeholder="Buscar personagem e pressionar Enter..."/>
    </div>
  </div>

  <div class="section-title">Subcategorias</div>
  <div class="subs-box" id="subsBox"><span style="color:var(--muted);font-size:12px;">Carregando...</span></div>

  <div class="section-title">Obras</div>
  <div class="cards-grid" id="cards"></div>
  <div class="empty-state" id="emptyBox" style="display:none;">Nenhuma obra encontrada.</div>

  <div class="footer">Source Baltigo • Cards</div>
</div>"""

    js = f"""<script>
const TOP = "{CARDS_TOP_BANNER_URL}";
let fullData=[], filteredData=[];
function esc(s){{return String(s||"").replace(/[&<>"']/g,(m)=>({{\"&\":\"&amp;\",\"<\":\"&lt;\",\">\":\"&gt;\",'\"':\"&quot;\",\"'\":\"&#039;\"}}[m]));}}
function pickCover(item){{if(item.cover_image&&item.cover_image.length>5)return item.cover_image;if(item.banner_image&&item.banner_image.length>5)return item.banner_image;return TOP;}}
function render(){{
  const box=document.getElementById("cards"),empty=document.getElementById("emptyBox"),stats=document.getElementById("statsTxt");
  stats.textContent="TOTAL DE OBRAS: "+filteredData.length;
  if(!filteredData.length){{box.innerHTML="";empty.style.display="block";return;}}
  empty.style.display="none";
  box.innerHTML=filteredData.map(item=>`
    <div class="card" style="cursor:pointer;" onclick="openAnime(${{item.anime_id}})">
      <div class="cover">
        <img src="${{esc(pickCover(item))}}" alt="${{esc(item.anime)}}" loading="lazy"/>
        <span class="pill" style="position:absolute;right:10px;bottom:10px;z-index:2;">${{item.characters_count||0}} chars</span>
      </div>
      <div class="meta">
        <p class="name">${{esc(item.anime)}}</p>
        <div class="sub"><span class="pill">ID ${{item.anime_id}}</span><span class="pill">CARDS</span></div>
      </div>
    </div>`).join("");
}}
function applySearch(){{
  const q=(document.getElementById("searchInput").value||"").trim().toLowerCase();
  filteredData=q?fullData.filter(x=>String(x.anime||"").toLowerCase().includes(q)):[...fullData];
  render();
}}
function openAnime(id){{window.location.href="/cards/anime?anime_id="+encodeURIComponent(id);}}
async function loadSubs(){{
  const subsBox=document.getElementById("subsBox");
  try{{
    const res=await fetch("/api/cards/subcategories?_ts="+Date.now());
    const data=await res.json();
    const items=data.items||[];
    if(!items.length){{subsBox.innerHTML='<span style="color:var(--muted);font-size:12px;">Nenhuma subcategoria.</span>';return;}}
    subsBox.innerHTML=items.map(item=>`<button class="sub-btn" onclick="openSub('${{esc(item.name)}}')">${{esc(item.name)}} (${{item.count||0}})</button>`).join("");
  }}catch(e){{subsBox.innerHTML='<span style="color:var(--muted);font-size:12px;">Erro ao carregar.</span>';}}
}}
function openSub(name){{window.location.href="/cards/subcategory?name="+encodeURIComponent(name);}}
async function load(){{
  const res=await fetch("/api/cards/animes?limit=5000&_ts="+Date.now());
  const data=await res.json();
  fullData=(data.items||[]).sort((a,b)=>String(a.anime||"").localeCompare(String(b.anime||"")));
  filteredData=[...fullData];
  render();
}}
document.getElementById("searchInput").addEventListener("input",applySearch);
document.getElementById("charSearchInput").addEventListener("keydown",function(e){{
  if(e.key!=="Enter")return;
  const q=(this.value||"").trim();
  if(!q)return;
  window.location.href="/cards/search?q="+encodeURIComponent(q);
}});
load(); loadSubs();
</script>"""

    return HTMLResponse(_page("Cards • Source Baltigo", body, _CARDS_CSS, js))

@app.get("/cards/anime", response_class=HTMLResponse)
def cards_anime_page(anime_id: int = Query(...)):
    body = f"""<div class="wrap">
  <div class="hero-anime" id="heroBox">
    <img id="heroImg" src="{CARDS_TOP_BANNER_URL}" alt="Banner"/>
    <div class="hero-copy">
      <a class="back-link" href="/cards">← Voltar</a>
      <div style="margin-top:10px;font-size:22px;font-weight:900;" id="animeTitle">Carregando...</div>
      <div style="margin-top:4px;color:rgba(255,255,255,.72);font-size:13px;" id="animeSub">Personagens</div>
    </div>
  </div>

  <div class="cards-header">
    <div class="cards-stats" id="statsTxt">Carregando...</div>
  </div>

  <div class="search-bar" style="margin-top:12px;">
    <span style="opacity:.55;font-weight:900;">🔎</span>
    <input id="searchInput" type="text" placeholder="Buscar personagem..."/>
  </div>

  <div class="cards-grid" id="cards" style="margin-top:16px;"></div>
  <div class="empty-state" id="emptyBox" style="display:none;">Nenhum personagem encontrado.</div>

  <div class="footer">Source Baltigo • Cards</div>
</div>"""

    js = f"""<script>
const animeId={anime_id};
const fallbackTop="{CARDS_TOP_BANNER_URL}";
let animeMeta=null,fullData=[],filteredData=[];
function esc(s){{return String(s||"").replace(/[&<>"']/g,(m)=>({{\"&\":\"&amp;\",\"<\":\"&lt;\",\">\":\"&gt;\",'\"':\"&quot;\",\"'\":\"&#039;\"}}[m]));}}
function pickHero(meta){{if(meta.banner_image&&meta.banner_image.length>5)return meta.banner_image;if(meta.cover_image&&meta.cover_image.length>5)return meta.cover_image;return fallbackTop;}}
function pickCharImage(item){{if(item.image&&item.image.length>5)return item.image;return fallbackTop;}}
function render(){{
  const box=document.getElementById("cards"),empty=document.getElementById("emptyBox"),stats=document.getElementById("statsTxt");
  stats.textContent="TOTAL DE PERSONAGENS: "+filteredData.length;
  if(!filteredData.length){{box.innerHTML="";empty.style.display="block";return;}}
  empty.style.display="none";
  box.innerHTML=filteredData.map(item=>`
    <div class="card char-card">
      <div class="cover" style="height:280px;">
        <img src="${{esc(pickCharImage(item))}}" alt="${{esc(item.name)}}" loading="lazy"/>
        <span class="pill id-pill">ID ${{item.id}}</span>
      </div>
      <div class="meta">
        <p class="name">${{esc(item.name)}}</p>
        <div class="sub"><span class="pill">${{esc(item.anime)}}</span><span class="pill">CARD</span></div>
      </div>
    </div>`).join("");
}}
function applySearch(){{
  const q=(document.getElementById("searchInput").value||"").trim().toLowerCase();
  filteredData=q?fullData.filter(x=>String(x.name||"").toLowerCase().includes(q)):[...fullData];
  render();
}}
async function load(){{
  const res=await fetch("/api/cards/characters?anime_id="+animeId+"&limit=5000&_ts="+Date.now());
  const data=await res.json();
  animeMeta=data.anime||null;
  fullData=(data.items||[]).sort((a,b)=>String(a.name||"").localeCompare(String(b.name||"")));
  filteredData=[...fullData];
  if(animeMeta){{
    document.getElementById("animeTitle").textContent=animeMeta.anime||"Obra";
    document.getElementById("animeSub").textContent="ID "+animeMeta.anime_id+" • "+(animeMeta.characters_count||fullData.length)+" personagens";
    document.getElementById("heroImg").src=pickHero(animeMeta);
  }}else{{
    document.getElementById("animeTitle").textContent="Obra não encontrada";
    document.getElementById("animeSub").textContent="ID inválido";
  }}
  render();
}}
document.getElementById("searchInput").addEventListener("input",applySearch);
load();
</script>"""

    return HTMLResponse(_page("Cards Anime • Source Baltigo", body, _CARDS_CSS, js))

@app.get("/cards/subcategory", response_class=HTMLResponse)
def cards_subcategory_page(name: str = Query(...)):
    safe_name = str(name).replace("\\", "\\\\").replace("'", "\\'")
    body = f"""<div class="wrap">
  <a class="back-link" href="/cards">← Voltar</a>
  <div style="margin:18px 0 6px;font-size:26px;font-weight:900;text-transform:uppercase;">Subcategoria</div>
  <div style="margin-bottom:4px;font-size:18px;font-weight:800;color:var(--accent);">{html.escape(name)}</div>
  <div id="meta" class="section-title">Carregando...</div>
  <div class="cards-grid" id="cards" style="margin-top:12px;"></div>
  <div class="footer">Source Baltigo • Cards</div>
</div>"""

    js = f"""<script>
const subName='{safe_name}';
function esc(s){{return String(s||"").replace(/[&<>"']/g,(m)=>({{\"&\":\"&amp;\",\"<\":\"&lt;\",\">\":\"&gt;\",'\"':\"&quot;\",\"'\":\"&#039;\"}}[m]));}}
const fallbackTop="{CARDS_TOP_BANNER_URL}";
async function load(){{
  const res=await fetch("/api/cards/subcategory?name="+encodeURIComponent(subName)+"&limit=5000&_ts="+Date.now());
  const data=await res.json();
  const items=data.items||[];
  document.getElementById("meta").textContent="TOTAL DE PERSONAGENS: "+items.length;
  document.getElementById("cards").innerHTML=items.map(item=>`
    <div class="card char-card">
      <div class="cover" style="height:280px;">
        <img src="${{esc(item.image||fallbackTop)}}" alt="${{esc(item.name)}}" loading="lazy"/>
      </div>
      <div class="meta">
        <p class="name">${{esc(item.name)}}</p>
        <div class="sub"><span class="pill">${{esc(item.anime)}}</span></div>
      </div>
    </div>`).join("");
}}
load();
</script>"""

    return HTMLResponse(_page("Subcategoria • Source Baltigo", body, _CARDS_CSS, js))

@app.get("/cards/search", response_class=HTMLResponse)
def cards_search_page(q: str = Query(...)):
    safe_q = str(q).replace("\\", "\\\\").replace("'", "\\'")
    body = f"""<div class="wrap">
  <a class="back-link" href="/cards">← Voltar</a>
  <div style="margin:18px 0 6px;font-size:26px;font-weight:900;text-transform:uppercase;">Busca</div>
  <div style="margin-bottom:4px;font-size:16px;font-weight:800;color:var(--accent);">"{html.escape(q)}"</div>
  <div id="meta" class="section-title">Carregando...</div>
  <div class="cards-grid" id="cards" style="margin-top:12px;"></div>
  <div class="footer">Source Baltigo • Cards</div>
</div>"""

    js = f"""<script>
const searchQ='{safe_q}';
function esc(s){{return String(s||"").replace(/[&<>"']/g,(m)=>({{\"&\":\"&amp;\",\"<\":\"&lt;\",\">\":\"&gt;\",'\"':\"&quot;\",\"'\":\"&#039;\"}}[m]));}}
const fallbackTop="{CARDS_TOP_BANNER_URL}";
async function load(){{
  const res=await fetch("/api/cards/search?q="+encodeURIComponent(searchQ)+"&limit=500&_ts="+Date.now());
  const data=await res.json();
  const items=data.items||[];
  document.getElementById("meta").textContent="TOTAL DE RESULTADOS: "+items.length;
  if(!items.length){{document.getElementById("cards").innerHTML='<div class="empty-state">Nenhum personagem encontrado para esta busca.</div>';return;}}
  document.getElementById("cards").innerHTML=items.map(item=>`
    <div class="card char-card">
      <div class="cover" style="height:280px;">
        <img src="${{esc(item.image||fallbackTop)}}" alt="${{esc(item.name)}}" loading="lazy"/>
      </div>
      <div class="meta">
        <p class="name">${{esc(item.name)}}</p>
        <div class="sub"><span class="pill">${{esc(item.anime)}}</span></div>
      </div>
    </div>`).join("");
}}
load();
</script>"""

    return HTMLResponse(_page("Busca • Source Baltigo", body, _CARDS_CSS, js))

@app.get("/cards/contrib", response_class=HTMLResponse)
async def cards_contrib_page():
    body = """<div class="wrap">
  <div style="max-width:640px;margin:0 auto;padding-top:16px;">
    <div class="eyebrow" style="margin-bottom:20px;">🖼 Central de Contribuições</div>
    <h1 style="font-size:clamp(24px,5vw,32px);font-weight:900;line-height:1.15;margin:0 0 12px;">Contribua com os Cards</h1>
    <p style="color:var(--muted);font-size:14px;line-height:1.65;margin:0 0 24px;">
      Ajude a melhorar a experiência enviando novas imagens de personagens ou sugerindo novas obras.
    </p>
    <div class="panel" style="padding:20px;display:flex;flex-direction:column;gap:12px;">
      <h2 style="margin:0 0 4px;font-size:16px;font-weight:900;text-transform:uppercase;letter-spacing:.06em;">Escolha uma opção</h2>
      <a class="btn btn-primary btn-full" href="/cards/contrib/image">🖼 Alterar foto de personagem</a>
      <a class="btn btn-ghost btn-full" href="/cards/contrib/work">🎬 Pedir nova obra para cards</a>
      <a class="btn btn-ghost btn-full" href="/cards/contrib/rules">📜 Ver regras de contribuição</a>
    </div>
    <div class="footer">Source Baltigo • Cards</div>
  </div>
</div>"""
    return HTMLResponse(_page("Contribuições • Source Baltigo", body))

@app.get("/cards/contrib/rules", response_class=HTMLResponse)
async def cards_contrib_rules_page():
    body = """<div class="wrap">
  <div style="max-width:640px;margin:0 auto;padding-top:16px;">
    <a class="back-link" href="/cards/contrib">← Voltar</a>
    <h1 style="font-size:clamp(22px,5vw,30px);font-weight:900;margin:20px 0 16px;">📜 Regras para Imagens</h1>
    <div class="panel" style="padding:20px;">
      <ul style="margin:0;padding:0 0 0 18px;display:flex;flex-direction:column;gap:12px;">
        <li style="color:var(--txt);font-size:14px;line-height:1.6;">Formato obrigatório <strong>2:3</strong> (retrato)</li>
        <li style="color:var(--txt);font-size:14px;line-height:1.6;">A imagem deve ser fiel ao personagem</li>
        <li style="color:var(--txt);font-size:14px;line-height:1.6;">Não pode conter outros personagens além do principal</li>
        <li style="color:var(--txt);font-size:14px;line-height:1.6;">Sem texto, marca d'água ou bordas estranhas</li>
        <li style="color:var(--txt);font-size:14px;line-height:1.6;">Imagem limpa, centralizada e com boa qualidade</li>
        <li style="color:var(--txt);font-size:14px;line-height:1.6;">Conteúdo impróprio será recusado automaticamente</li>
      </ul>
      <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--stroke);">
        <p style="margin:0 0 8px;color:var(--muted);font-size:13px;">Se aprovada, a nova imagem substituirá a atual em todo o sistema.</p>
        <p style="margin:0;font-size:14px;"><strong>Recompensa:</strong> <span style="color:var(--ok);">+1 coin</span> por imagem aprovada.</p>
      </div>
    </div>
    <div class="footer">Source Baltigo • Cards</div>
  </div>
</div>"""
    return HTMLResponse(_page("Regras • Source Baltigo", body))


# =============================================================================
# ROUTES — PEDIDO
# =============================================================================
@app.get("/api/pedido/limit")
def api_pedido_limit(uid: int = Query(...)):
    used = count_user_media_requests_last_24h(uid)
    remaining = max(0, 3 - used)
    return JSONResponse({"ok": True, "used": used, "remaining": remaining, "limit": 3})

@app.get("/api/pedido/search")
async def api_pedido_search(
    q: str = Query(..., min_length=1, max_length=80),
    media_type: str = Query(...)
):
    media_type = (media_type or "").strip().lower()
    if media_type not in ("anime", "manga"):
        return JSONResponse({"ok": False, "message": "media_type inválido"}, status_code=400)
    try:
        results = await _pedido_anilist_search(q.strip(), media_type)
        items = []
        for x in results:
            title = (
                ((x.get("title") or {}).get("romaji"))
                or ((x.get("title") or {}).get("english"))
                or ((x.get("title") or {}).get("native"))
                or ""
            ).strip()
            if not title: continue
            aid = x.get("id")
            items.append({
                "id": aid,
                "title": title,
                "cover": ((x.get("coverImage") or {}).get("large") or ""),
                "score": x.get("averageScore"),
                "format": x.get("format"),
                "status": x.get("status"),
                "year": x.get("seasonYear"),
                "episodes": x.get("episodes"),
                "chapters": x.get("chapters"),
                "already_exists": bool(_pedido_catalog_contains(media_type, title, aid)),
                "already_requested": bool(media_request_exists(media_type, title, aid)),
            })
        return JSONResponse({"ok": True, "items": items})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "message": "Não foi possível buscar agora."}, status_code=502)

@app.post("/api/pedido/send")
async def api_pedido_send(payload: dict = Body(...)):
    try:
        user_id = int(payload.get("user_id") or 0)
        username = str(payload.get("username") or "").strip()
        full_name = str(payload.get("full_name") or payload.get("name") or "").strip()
        media_type = str(payload.get("media_type") or "").strip().lower()
        anilist_id = payload.get("anilist_id")
        title = str(payload.get("title") or "").strip()
        cover = str(payload.get("cover") or "").strip()
        if user_id <= 0 or media_type not in ("anime", "manga") or not title:
            return JSONResponse({"ok": False, "message": "Dados inválidos."}, status_code=400)
        used = count_user_media_requests_last_24h(user_id)
        if used >= 3:
            return JSONResponse({"ok": False, "code": "limit", "message": "Você atingiu o limite de 3 pedidos nas últimas 24h."}, status_code=429)
        if _pedido_catalog_contains(media_type, title, anilist_id):
            return JSONResponse({"ok": False, "code": "exists", "message": "Esse título já está disponível no catálogo."}, status_code=409)
        if media_request_exists(media_type, title, anilist_id):
            return JSONResponse({"ok": False, "code": "requested", "message": "Esse título já foi pedido e está em análise."}, status_code=409)
        save_media_request(user_id, username, full_name, media_type, title, anilist_id, cover)
        if not CANAL_PEDIDOS or not BOT_TOKEN:
            return JSONResponse({"ok": False, "message": "CANAL_PEDIDOS ou BOT_TOKEN não configurado."}, status_code=500)
        safe_fn = html.escape(full_name or "Sem nome")
        safe_un = html.escape(username) if username else "sem_username"
        safe_title = html.escape(title)
        safe_type = html.escape(media_type.upper())
        safe_aid = html.escape(str(anilist_id or "-"))
        caption = (f"📥 <b>NOVO PEDIDO</b>\n\n"
                   f"👤 <b>Usuário:</b> {safe_fn}\n🆔 <b>ID:</b> <code>{user_id}</code>\n🔖 <b>Username:</b> @{safe_un}\n\n"
                   f"🎴 <b>Tipo:</b> {safe_type}\n📝 <b>Título:</b> <i>{safe_title}</i>\n🆔 <b>AniList ID:</b> <code>{safe_aid}</code>")
        tg_json = None
        if cover:
            try:
                resp = await _telegram_send_photo(CANAL_PEDIDOS, cover, caption)
                tg_json = resp.json()
            except Exception as e:
                tg_json = {"ok": False, "description": repr(e)}
        if not tg_json or not tg_json.get("ok"):
            text_fallback = caption + f"\n🖼 <b>Capa:</b> {html.escape(cover or '-')}"
            resp = await _telegram_send_message(CANAL_PEDIDOS, text_fallback)
            tg_json = resp.json()
            if not tg_json.get("ok"):
                return JSONResponse({"ok": False, "message": "Pedido salvo, mas Telegram recusou envio ao canal."}, status_code=502)
        return JSONResponse({"ok": True, "message": "Pedido enviado com sucesso.", "used": used + 1, "remaining": max(0, 3 - (used + 1))})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "message": "Não foi possível enviar seu pedido."}, status_code=500)

@app.post("/api/pedido/report")
async def api_pedido_report(payload: dict = Body(...)):
    try:
        user_id = int(payload.get("user_id") or 0)
        username = str(payload.get("username") or "").strip()
        full_name = str(payload.get("full_name") or payload.get("name") or "").strip()
        report_type = str(payload.get("report_type") or "Outro").strip()
        message = str(payload.get("message") or "").strip()
        if user_id <= 0 or not message:
            return JSONResponse({"ok": False, "message": "Dados inválidos."}, status_code=400)
        save_webapp_report(user_id, username, full_name, report_type, message)
        if not CANAL_PEDIDOS or not BOT_TOKEN:
            return JSONResponse({"ok": False, "message": "CANAL_PEDIDOS ou BOT_TOKEN não configurado."}, status_code=500)
        safe_fn = html.escape(full_name or "Sem nome")
        safe_un = html.escape(username) if username else "sem_username"
        text = (f"⚠️ <b>NOVO REPORT</b>\n\n"
                f"👤 <b>Usuário:</b> {safe_fn}\n🆔 <b>ID:</b> <code>{user_id}</code>\n🔖 @{safe_un}\n\n"
                f"🏷 <b>Tipo:</b> {html.escape(report_type)}\n📝 <b>Mensagem:</b>\n{html.escape(message)}")
        resp = await _telegram_send_message(CANAL_PEDIDOS, text)
        tg_json = resp.json()
        if not tg_json.get("ok"):
            return JSONResponse({"ok": False, "message": "Report salvo, mas Telegram recusou envio."}, status_code=502)
        return JSONResponse({"ok": True, "message": "Report enviado com sucesso."})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"ok": False, "message": "Não foi possível enviar o report."}, status_code=500)

@app.get("/pedido", response_class=HTMLResponse)
def pedido_page():
    pedido_css = """
.hero-pedido {
  border: 1px solid var(--stroke);
  border-radius: var(--r-lg);
  overflow: hidden;
  box-shadow: var(--shadow);
  background: var(--panel2);
}
.hero-pedido-top {
  position: relative;
  height: 190px;
  background: center/cover no-repeat;
}
.hero-pedido-top::after {
  content: "";
  position: absolute; inset: 0;
  background: linear-gradient(180deg, rgba(0,0,0,.06), rgba(0,0,0,.72));
}
.hero-pedido-copy {
  position: absolute;
  left: 16px; right: 16px; bottom: 14px;
  z-index: 2;
}
.hero-pedido-body { padding: 18px; }
.limit-box {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: var(--r-md);
  background: rgba(255,255,255,.04);
  border: 1px solid var(--stroke);
}
.limit-bar {
  height: 8px;
  width: 140px;
  border-radius: 999px;
  background: rgba(255,255,255,.08);
  overflow: hidden;
}
.limit-fill {
  height: 100%;
  width: 0;
  background: linear-gradient(90deg, var(--accent), var(--ok));
  border-radius: 999px;
  transition: width .4s ease;
}
.result-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-top: 14px;
}
@media (min-width: 720px) { .result-grid { grid-template-columns: repeat(3, 1fr); } }
.result-card {
  border-radius: var(--r-lg);
  overflow: hidden;
  border: 1px solid var(--stroke);
  background: var(--panel2);
  box-shadow: var(--shadow2);
}
.result-cover {
  height: 220px;
  position: relative;
  background: linear-gradient(135deg, rgba(90,168,255,.14), rgba(255,255,255,.02));
}
.result-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.result-cover-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(180deg, transparent 40%, rgba(0,0,0,.60));
}
.result-meta { padding: 13px 14px 15px; }
.result-title { font-weight: 900; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; margin: 0; line-height: 1.25; }
.result-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.result-status { margin-top: 10px; font-size: 11px; font-weight: 900; letter-spacing: .06em; text-transform: uppercase; }
.status-ok { color: var(--ok); }
.status-warn { color: var(--warn); }
.status-bad { color: var(--danger); }
.report-types { display: grid; grid-template-columns: repeat(2,1fr); gap: 10px; margin-top: 8px; }
.r-type {
  padding: 12px;
  border-radius: var(--r-md);
  border: 1px solid var(--stroke);
  background: var(--panel2);
  text-align: center;
  font-weight: 900;
  font-size: 12px;
  letter-spacing: .06em;
  text-transform: uppercase;
  cursor: pointer;
  user-select: none;
  transition: background .12s ease, border-color .12s ease;
}
.r-type.active { background: rgba(255,90,118,.14); border-color: rgba(255,90,118,.36); color: var(--danger); }
.report-box { margin-top: 12px; padding: 14px; border-radius: var(--r-md); border: 1px solid var(--stroke); background: var(--panel2); }
.report-box textarea { width: 100%; min-height: 120px; border: 0; outline: none; background: transparent; color: var(--txt); font-size: 14px; resize: vertical; font-family: var(--font); }
.report-box textarea::placeholder { color: rgba(255,255,255,.30); }
.toast-fixed { position: fixed; left: 50%; bottom: 20px; transform: translateX(-50%); max-width: 92vw; padding: 13px 18px; border-radius: var(--r-md); background: rgba(5,9,18,.94); border: 1px solid var(--stroke2); box-shadow: var(--shadow); font-size: 13px; font-weight: 800; z-index: 100; display: none; }
.toast-fixed.show { display: block; animation: fadeUp .22s ease; }
@keyframes fadeUp { from{opacity:0;transform:translateX(-50%) translateY(6px)} to{opacity:1;transform:translateX(-50%) translateY(0)} }
"""

    body = f"""<div class="wrap">
  <div class="hero-pedido">
    <div class="hero-pedido-top" style="background-image:linear-gradient(180deg,rgba(0,0,0,.06),rgba(0,0,0,.70)),url('{PEDIDO_BANNER_URL}')">
      <div class="hero-pedido-copy">
        <div class="eyebrow">📩 Mini App • Central unificada</div>
      </div>
    </div>
    <div class="hero-pedido-body">
      <h1 style="margin:0 0 6px;font-size:24px;font-weight:900;line-height:1.1;">Central de Pedidos</h1>
      <p style="margin:0;color:var(--muted);font-size:13px;line-height:1.55;">
        Peça <strong>animes</strong>, <strong>mangás</strong> e envie <strong>reports</strong> em um só lugar.
      </p>
      <div class="limit-box">
        <div>
          <div style="font-weight:900;letter-spacing:.08em;text-transform:uppercase;font-size:11px;color:var(--muted);">Limite diário</div>
          <div id="limitText" style="margin-top:4px;font-size:14px;font-weight:800;">Carregando...</div>
        </div>
        <div class="limit-bar"><div class="limit-fill" id="limitFill"></div></div>
      </div>
    </div>
  </div>

  <div class="tabs" style="margin-top:16px;">
    <div class="tab active" data-tab="anime">🎌 Anime</div>
    <div class="tab" data-tab="manga">📖 Mangá</div>
    <div class="tab" data-tab="report">⚠️ Report</div>
  </div>

  <div id="panel-anime" class="panel" style="margin-top:14px;padding:18px;">
    <div class="search-bar">
      <span style="opacity:.55;font-weight:900;">🔎</span>
      <input id="searchAnime" type="text" placeholder="Nome do anime..."/>
    </div>
    <button class="btn btn-primary" id="btnSearchAnime" style="width:100%;margin-top:10px;">Buscar anime</button>
    <div class="result-grid" id="animeResults"></div>
    <div class="empty-state" id="animeEmpty" style="display:none;"></div>
  </div>

  <div id="panel-manga" class="panel" style="margin-top:14px;padding:18px;display:none;">
    <div class="search-bar">
      <span style="opacity:.55;font-weight:900;">🔎</span>
      <input id="searchManga" type="text" placeholder="Nome do mangá..."/>
    </div>
    <button class="btn btn-primary" id="btnSearchManga" style="width:100%;margin-top:10px;">Buscar mangá</button>
    <div class="result-grid" id="mangaResults"></div>
    <div class="empty-state" id="mangaEmpty" style="display:none;"></div>
  </div>

  <div id="panel-report" class="panel" style="margin-top:14px;padding:18px;display:none;">
    <h3 style="margin:0 0 12px;font-size:16px;font-weight:900;text-transform:uppercase;letter-spacing:.06em;">Tipo de report</h3>
    <div class="report-types">
      <div class="r-type active" data-type="Bug">🐛 Bug</div>
      <div class="r-type" data-type="Sugestão">💡 Sugestão</div>
      <div class="r-type" data-type="Imagem">🖼 Imagem</div>
      <div class="r-type" data-type="Outro">❓ Outro</div>
    </div>
    <div class="report-box" style="margin-top:14px;">
      <textarea id="reportMessage" placeholder="Descreva o problema ou sugestão..."></textarea>
    </div>
    <button class="btn btn-danger" id="btnSendReport" style="width:100%;margin-top:12px;">Enviar report</button>
  </div>

  <div class="footer">Source Baltigo • Central de Pedidos</div>
</div>
<div class="toast-fixed" id="toast"></div>"""

    js = """<script>
const tg=window.Telegram&&window.Telegram.WebApp?window.Telegram.WebApp:null;
if(tg){try{tg.ready();tg.expand();}catch(e){}}
const currentUser={id:0,username:"",full_name:""};
if(tg&&tg.initDataUnsafe&&tg.initDataUnsafe.user){
  const u=tg.initDataUnsafe.user;
  currentUser.id=Number(u.id||0);
  currentUser.username=u.username||"";
  currentUser.full_name=[u.first_name||"",u.last_name||""].join(" ").trim();
}
let currentTab="anime", currentReportType="Bug";
const limitState={used:0,remaining:3,limit:3};

function esc(s){return(s||"").replace(/[&<>"']/g,(m)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));}

function toast(msg,ms=3200){
  const el=document.getElementById("toast");
  el.textContent=msg; el.classList.add("show");
  setTimeout(()=>el.classList.remove("show"),ms);
}

async function getJSON(url){
  const res=await fetch(url+"&_ts="+Date.now()); const data=await res.json();
  if(!res.ok||!data.ok) throw new Error((data&&data.message)||"Erro");
  return data;
}
async function postJSON(url,payload){
  const res=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await res.json();
  if(!res.ok||!data.ok) throw new Error((data&&data.message)||"Erro");
  return data;
}

function setTab(tab){
  currentTab=tab;
  document.querySelectorAll(".tab").forEach(el=>{el.classList.toggle("active",el.dataset.tab===tab);});
  ["anime","manga","report"].forEach(p=>{document.getElementById("panel-"+p).style.display=(p===tab?"block":"none");});
}

async function loadLimit(){
  if(!currentUser.id)return;
  try{
    const data=await getJSON("/api/pedido/limit?uid="+currentUser.id+"");
    limitState.used=data.used; limitState.remaining=data.remaining; limitState.limit=data.limit;
    updateLimitUI();
  }catch(e){}
}
function updateLimitUI(){
  document.getElementById("limitText").textContent=limitState.used+" de "+limitState.limit+" usados • "+limitState.remaining+" restantes";
  const pct=limitState.limit>0?(limitState.used/limitState.limit*100):0;
  document.getElementById("limitFill").style.width=Math.min(100,pct)+"%";
}

function skeletons(containerId,emptyId){
  document.getElementById(containerId).innerHTML=[1,2,3,4].map(()=>'<div class="skeleton" style="height:316px;border-radius:var(--r-lg);"></div>').join("");
  document.getElementById(emptyId).style.display="none";
}

function renderResults(containerId,emptyId,items,mediaType){
  const c=document.getElementById(containerId),e=document.getElementById(emptyId);
  c.innerHTML="";
  if(!items||!items.length){e.textContent="Nenhum resultado encontrado.";e.style.display="block";return;}
  e.style.display="none";
  for(const item of items){
    const stateText=item.already_exists?"Já está no catálogo":(item.already_requested?"Em análise":"Disponível para pedido");
    const stateClass=item.already_exists?"status-bad":(item.already_requested?"status-warn":"status-ok");
    const sub=[item.year,item.score?("★ "+item.score):null,item.format,mediaType==="anime"&&item.episodes?(item.episodes+" eps"):null,mediaType==="manga"&&item.chapters?(item.chapters+" caps"):null].filter(Boolean);
    const disabled=item.already_exists||item.already_requested||(limitState.used>=(limitState.limit||3));
    const el=document.createElement("div");
    el.className="result-card";
    el.innerHTML=`
      <div class="result-cover">
        ${item.cover?`<img src="${esc(item.cover)}" alt="${esc(item.title)}" loading="lazy"/>`:""}
        <div class="result-cover-overlay"></div>
        <span class="pill" style="position:absolute;left:10px;bottom:10px;z-index:2;">${esc(mediaType.toUpperCase())}</span>
      </div>
      <div class="result-meta">
        <div class="result-title">${esc(item.title)}</div>
        <div class="result-chips">${sub.map(x=>`<span class="pill">${esc(String(x))}</span>`).join("")}</div>
        <div class="result-status ${stateClass}">${esc(stateText)}</div>
        <button class="btn ${disabled?"btn-ghost":"btn-primary"} btn-full" style="margin-top:10px;" ${disabled?"disabled":""}>
          ${disabled?"Indisponível":"Pedir agora"}
        </button>
      </div>`;
    const btn=el.querySelector("button");
    if(!disabled) btn.addEventListener("click",()=>sendRequest(mediaType,item));
    c.appendChild(el);
  }
}

async function runSearch(mediaType){
  if(!currentUser.id){toast("Abra este Mini App dentro do Telegram.");return;}
  const inputId=mediaType==="anime"?"searchAnime":"searchManga";
  const containerId=mediaType==="anime"?"animeResults":"mangaResults";
  const emptyId=mediaType==="anime"?"animeEmpty":"mangaEmpty";
  const q=(document.getElementById(inputId).value||"").trim();
  if(!q){toast("Digite um nome para buscar.");return;}
  skeletons(containerId,emptyId);
  try{
    const data=await getJSON(`/api/pedido/search?q=${encodeURIComponent(q)}&media_type=${mediaType}`);
    renderResults(containerId,emptyId,data.items||[],mediaType);
  }catch(e){
    document.getElementById(containerId).innerHTML="";
    document.getElementById(emptyId).textContent=e.message||"Não foi possível buscar agora.";
    document.getElementById(emptyId).style.display="block";
  }
}

async function sendRequest(mediaType,item){
  if(!currentUser.id){toast("Abra este Mini App dentro do Telegram.");return;}
  try{
    const data=await postJSON("/api/pedido/send",{user_id:currentUser.id,username:currentUser.username,full_name:currentUser.full_name,media_type:mediaType,anilist_id:item.id,title:item.title,cover:item.cover||""});
    limitState.used=data.used; limitState.remaining=data.remaining;
    updateLimitUI();
    toast("✅ "+item.title+" enviado com sucesso.");
  }catch(e){toast(e.message||"Não foi possível enviar o pedido.");}
}

async function sendReport(){
  if(!currentUser.id){toast("Abra este Mini App dentro do Telegram.");return;}
  const message=(document.getElementById("reportMessage").value||"").trim();
  if(!message){toast("Descreva o problema antes de enviar.");return;}
  try{
    await postJSON("/api/pedido/report",{user_id:currentUser.id,username:currentUser.username,full_name:currentUser.full_name,report_type:currentReportType,message});
    document.getElementById("reportMessage").value="";
    toast("✅ Report enviado com sucesso.");
  }catch(e){toast(e.message||"Não foi possível enviar o report.");}
}

document.querySelectorAll(".tab").forEach(el=>el.addEventListener("click",()=>setTab(el.dataset.tab)));
document.querySelectorAll(".r-type").forEach(el=>el.addEventListener("click",()=>{
  document.querySelectorAll(".r-type").forEach(x=>x.classList.remove("active"));
  el.classList.add("active"); currentReportType=el.dataset.type;
}));
document.getElementById("btnSearchAnime").addEventListener("click",()=>runSearch("anime"));
document.getElementById("btnSearchManga").addEventListener("click",()=>runSearch("manga"));
document.getElementById("btnSendReport").addEventListener("click",sendReport);
document.getElementById("searchAnime").addEventListener("keydown",(e)=>{if(e.key==="Enter")runSearch("anime");});
document.getElementById("searchManga").addEventListener("keydown",(e)=>{if(e.key==="Enter")runSearch("manga");});
loadLimit();
</script>"""

    return HTMLResponse(_page("Central de Pedidos — Source Baltigo", body, pedido_css, js, tg_init=True))


# =============================================================================
# ROUTES — DADO / GACHA
# =============================================================================
@app.get("/api/dado/state")
def api_dado_state(x_telegram_init_data: str = Header(default="")):
    tg = _get_tg_user(x_telegram_init_data)
    user_id = int(tg["user_id"])
    try: expire_stale_dice_rolls(refund_pending=True)
    except Exception: pass
    state = get_dado_state(user_id) or {}
    recharge = get_next_dado_recharge_info(user_id) or {}
    active = get_active_dice_roll(user_id)
    roll_payload = None
    if active:
        options = active.get("options_json") or []
        dice_value = int(active.get("dice_value") or 0)
        if isinstance(options, str):
            try: options = json.loads(options)
            except Exception: options = []
        if isinstance(options, list) and options:
            roll_payload = {
                "roll_id": int(active["roll_id"]),
                "dice_value": dice_value,
                "options": options,
                "status": active.get("status"),
                "selected_anime_id": active.get("selected_anime_id"),
                "rewarded_character_id": active.get("rewarded_character_id"),
            }
    return JSONResponse({
        "ok": True,
        "balance": int(state.get("balance") or 0),
        "next_recharge_hhmm": recharge.get("next_recharge_hhmm") or "--:--",
        "next_recharge_iso": recharge.get("next_recharge_iso"),
        "timezone": recharge.get("timezone") or "America/Sao_Paulo",
        "max_balance": int(recharge.get("max_balance") or 24),
        "active_roll": roll_payload,
        "recharge_hours": ["01:00","04:00","07:00","10:00","13:00","16:00","19:00","22:00"],
    })

@app.post("/api/dado/roll")
async def api_dado_roll(x_telegram_init_data: str = Header(default="")):
    tg = _get_tg_user(x_telegram_init_data)
    user_id = int(tg["user_id"])
    if not _dado_rate_limit(user_id, "roll", 1.4):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)
    try: expire_stale_dice_rolls(refund_pending=True)
    except Exception: pass
    active = get_active_dice_roll(user_id)
    if active:
        active_options = active.get("options_json") or []
        active_dice = int(active.get("dice_value") or 0)
        if isinstance(active_options, str):
            try: active_options = json.loads(active_options)
            except Exception: active_options = []
        if isinstance(active_options, list) and active_options and len(active_options) == active_dice:
            return JSONResponse({
                "ok": True, "reused": True,
                "roll_id": int(active["roll_id"]),
                "dice_value": active_dice,
                "options": active_options,
                "status": active.get("status"),
                "balance": int((get_dado_state(user_id) or {}).get("balance") or 0),
            })
        try: cancel_dice_roll(user_id, int(active["roll_id"]), refund=True)
        except Exception: pass
    data = _load_local_dado_pool()
    anime_pool = list(data.get("animes_list") or [])
    max_dice_value = _max_dice_value_from_local_pool(anime_pool)
    if max_dice_value <= 0:
        return JSONResponse({"ok": False, "error": "anime_pool_unavailable"}, status_code=200)
    raw_value = random.SystemRandom().randint(1, max_dice_value)
    try: options = _pick_random_local_animes(raw_value, anime_pool)
    except Exception:
        return JSONResponse({"ok": False, "error": "anime_pool_unavailable"}, status_code=200)
    if not options:
        return JSONResponse({"ok": False, "error": "anime_pool_unavailable"}, status_code=200)
    dice_value = len(options)
    created = create_dice_roll(user_id, dice_value, options)
    if not created.get("ok"):
        return JSONResponse(created, status_code=200)
    roll = created["roll"]
    balance = int((get_dado_state(user_id) or {}).get("balance") or 0)
    response_options = created.get("options") or options or roll.get("options_json") or []
    if isinstance(response_options, str):
        try: response_options = json.loads(response_options)
        except Exception: response_options = []
    return JSONResponse({
        "ok": True,
        "reused": bool(created.get("reused")),
        "roll_id": int(roll["roll_id"]),
        "dice_value": int(roll["dice_value"]),
        "options": response_options,
        "status": roll.get("status"),
        "balance": balance,
    })

@app.post("/api/dado/pick")
async def api_dado_pick(payload_body: dict = Body(default={}), x_telegram_init_data: str = Header(default="")):
    tg = _get_tg_user(x_telegram_init_data)
    user_id = int(tg["user_id"])
    if not _dado_rate_limit(user_id, "pick", 1.0):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)
    roll_id = int(payload_body.get("roll_id") or 0)
    anime_id = int(payload_body.get("anime_id") or 0)
    if roll_id <= 0 or anime_id <= 0:
        raise HTTPException(status_code=400, detail="roll_id/anime_id inválidos")
    picked = pick_dice_roll_anime(user_id, roll_id, anime_id)
    if not picked.get("ok"):
        return JSONResponse(picked, status_code=200)
    roll = picked["roll"]
    char = _pick_random_local_character(anime_id)
    if not char:
        return JSONResponse({"ok": False, "error": "character_not_found"}, status_code=200)
    resolved = resolve_dice_roll(user_id, roll_id, int(char["id"]))
    if not resolved.get("ok"):
        return JSONResponse(resolved, status_code=200)
    rarity = _rarity_from_roll(int(roll["dice_value"]), int(char["id"]))
    balance = int((get_dado_state(user_id) or {}).get("balance") or 0)
    char_id = int(char["id"])
    name = str(char["name"])
    image = str(char["image"] or char["anime_cover"] or DADO_BANNER_URL)
    anime_title = str(char["anime_title"] or "Anime")
    try:
        await _tg_send_photo(
            chat_id=user_id, photo=image,
            caption=(f"🎁 <b>VOCÊ GANHOU!</b>\n\n"
                     f"🧧 <code>{char_id}</code>. <b>{name}</b>\n"
                     f"<i>{anime_title}</i>\n\n"
                     f"📦 <b>Adicionado à sua coleção!</b>"),
        )
    except Exception: pass
    return JSONResponse({
        "ok": True,
        "roll_id": int(roll_id),
        "balance": balance,
        "character": {
            "id": char_id, "name": name, "image": image,
            "anime_title": anime_title, "anime_cover": char["anime_cover"],
            "tier": rarity["tier"], "stars": rarity["stars"],
        },
    })

@app.get("/dado", response_class=HTMLResponse)
def dado_page():
    dado_css = """
.dado-banner { border-radius: var(--r-lg); overflow: hidden; border: 1px solid var(--stroke); box-shadow: var(--shadow); position: relative; background: #000; }
.dado-banner img { width: 100%; height: 210px; object-fit: cover; display: block; }
.dado-banner::after { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg,rgba(0,0,0,.06),rgba(0,0,0,.72)); }
.dado-hero { margin-top: 14px; border-radius: var(--r-lg); border: 1px solid var(--stroke); background: rgba(255,255,255,.035); box-shadow: var(--shadow); padding: 18px; }
.dado-title { font-size: 22px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }
.dado-sub { margin-top: 8px; color: var(--muted); font-size: 13px; font-weight: 700; line-height: 1.55; }
.dado-stats { margin-top: 16px; display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; }
@media (max-width: 600px) { .dado-stats { grid-template-columns: 1fr; } }
.dado-stat { border-radius: var(--r-md); background: rgba(255,255,255,.045); border: 1px solid var(--stroke); padding: 14px; }
.dado-stat .k { color: var(--muted); font-size: 11px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }
.dado-stat .v { margin-top: 8px; font-size: 22px; font-weight: 900; line-height: 1.2; }
.dice-stage { margin-top: 16px; border-radius: var(--r-lg); overflow: hidden; border: 1px solid var(--stroke); background: radial-gradient(circle at 50% 0%,rgba(255,43,214,.08),transparent 38%), radial-gradient(circle at 50% 100%,rgba(0,242,255,.08),transparent 38%), rgba(255,255,255,.025); box-shadow: var(--shadow); min-height: 360px; position: relative; }
#sceneWrap { width: 100%; height: 360px; position: relative; }
.hud { position: absolute; left: 0; right: 0; bottom: 14px; display: flex; justify-content: center; pointer-events: none; padding: 0 14px; }
.hud-tag { max-width: 100%; padding: 10px 14px; border-radius: 999px; background: rgba(0,0,0,.38); border: 1px solid rgba(255,255,255,.12); font-weight: 900; font-size: 12px; letter-spacing: .12em; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dado-actions { margin-top: 16px; display: flex; gap: 12px; flex-wrap: wrap; }
.btn-roll { flex: 1; min-width: 160px; background: linear-gradient(135deg,rgba(255,43,214,.92),rgba(0,242,255,.92)); border: 1px solid rgba(255,255,255,.18); color: #fff; }
.btn-reset { background: rgba(255,214,90,.18); border: 1px solid rgba(255,214,90,.28); color: #fff; }
.anime-grid { margin-top: 16px; display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; }
@media (max-width: 600px) { .anime-grid { grid-template-columns: 1fr; } }
.anime-card { appearance: none; width: 100%; padding: 0; border: none; border-radius: var(--r-lg); overflow: hidden; border: 1px solid rgba(255,255,255,.12); background: #0f1728; cursor: pointer; color: #fff; position: relative; min-height: 92px; text-align: left; transition: transform .16s ease, border-color .16s ease; }
.anime-card:hover { transform: translateY(-2px); border-color: rgba(0,242,255,.42); }
.anime-card[aria-disabled="true"] { opacity: .55; pointer-events: none; }
.anime-bg { position: absolute; inset: 0; background-size: cover; background-position: center; transform: scale(1.04); filter: blur(.5px) saturate(1.05); opacity: .34; }
.anime-overlay { position: absolute; inset: 0; background: linear-gradient(90deg,rgba(6,10,18,.92) 0%,rgba(6,10,18,.78) 46%,rgba(6,10,18,.62) 100%); }
.anime-meta { position: relative; z-index: 2; min-height: 92px; display: flex; flex-direction: column; justify-content: center; padding: 16px; }
.anime-title-txt { font-size: 17px; font-weight: 900; line-height: 1.22; color: #fff; word-break: break-word; }
.anime-hint { margin-top: 8px; color: rgba(255,255,255,.72); font-size: 11px; font-weight: 900; letter-spacing: .10em; text-transform: uppercase; }
.reveal-box { margin-top: 16px; border-radius: var(--r-lg); border: 1px solid var(--stroke); background: rgba(255,255,255,.035); box-shadow: var(--shadow); overflow: hidden; display: none; }
.reveal-box.show { display: block; animation: fadeUp .35s ease; }
@keyframes fadeUp { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
.reveal-img { width: 100%; height: 300px; object-fit: cover; display: block; background: #111; }
.reveal-body { padding: 16px; }
.rarity-tag { display: inline-flex; align-items: center; gap: 8px; border-radius: 999px; padding: 8px 12px; background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.12); font-size: 12px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }
.char-name { margin-top: 12px; font-size: 24px; font-weight: 900; line-height: 1.2; }
.anime-from { margin-top: 8px; color: var(--muted); font-weight: 800; font-size: 14px; }
"""
    body = f"""<div class="wrap">
  <div class="dado-banner">
    <img src="{DADO_BANNER_URL}" alt="Sistema de Dados"/>
  </div>

  <div class="dado-hero">
    <div class="dado-title">Sistema de Dados</div>
    <div class="dado-sub">Role o dado 3D, receba entre 1 e 6 opções de anime e escolha uma para revelar um personagem da sua coleção.</div>

    <div class="dado-stats">
      <div class="dado-stat"><div class="k">Dados disponíveis</div><div class="v" id="balanceTxt">...</div></div>
      <div class="dado-stat"><div class="k">Próximo dado</div><div class="v" id="nextTxt">...</div></div>
      <div class="dado-stat"><div class="k">Recargas diárias</div><div class="v" style="font-size:13px;line-height:1.6;">01h 04h 07h 10h 13h 16h 19h 22h</div></div>
    </div>

    <div class="dice-stage">
      <div id="sceneWrap"></div>
      <div class="hud"><div class="hud-tag" id="hudTxt">Pronto para rolar</div></div>
    </div>

    <div class="dado-actions">
      <button id="rollBtn" class="btn btn-roll">🎲 Rolar Dado</button>
      <button id="resetBtn" class="btn btn-ghost btn-reset" type="button">✖ Limpar</button>
    </div>

    <div class="msg" id="msg">Carregando seus dados...</div>
    <div id="animeGrid" class="anime-grid"></div>

    <div id="revealBox" class="reveal-box">
      <img id="revealImg" class="reveal-img" src="" alt="Personagem">
      <div class="reveal-body">
        <div id="rarityTxt" class="rarity-tag">REWARD</div>
        <div id="charName" class="char-name"></div>
        <div id="animeFrom" class="anime-from"></div>
      </div>
    </div>
  </div>

  <div class="footer">Source Baltigo • Dado Gacha</div>
</div>"""

    js = f"""<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
<script>
const tg=(window.Telegram&&window.Telegram.WebApp)?window.Telegram.WebApp:null;
const DADO_BANNER_FALLBACK="{DADO_BANNER_URL}";
if(tg){{try{{tg.ready();tg.expand();tg.setHeaderColor("#0b1222");tg.setBackgroundColor("#060912");}}catch(e){{}}}}

const state={{balance:0,nextRecharge:"--:--",currentRollId:0,currentDice:0,rolling:false,choosing:false,options:[]}};
const msg=document.getElementById("msg"),balanceTxt=document.getElementById("balanceTxt"),nextTxt=document.getElementById("nextTxt");
const hudTxt=document.getElementById("hudTxt"),animeGrid=document.getElementById("animeGrid");
const revealBox=document.getElementById("revealBox"),revealImg=document.getElementById("revealImg");
const rarityTxt=document.getElementById("rarityTxt"),charName=document.getElementById("charName");
const animeFrom=document.getElementById("animeFrom"),rollBtn=document.getElementById("rollBtn"),resetBtn=document.getElementById("resetBtn");

function setMsg(t){{msg.textContent=t||"";}}
function setHud(t){{hudTxt.textContent=t||"";}}
function setBalance(v){{balanceTxt.textContent=String(v??0);}}
function setNext(v){{nextTxt.textContent=String(v||"--:--");}}
function clearReveal(){{revealBox.classList.remove("show");revealImg.src="";charName.textContent="";animeFrom.textContent="";rarityTxt.textContent="REWARD";}}
function clearAnimeCards(){{animeGrid.innerHTML="";}}
function resetScreen(){{clearAnimeCards();clearReveal();state.currentRollId=0;state.currentDice=0;state.options=[];setHud("Pronto para rolar");setMsg("Tela limpa.");}}

async function apiGet(url){{
  const res=await fetch(url+"?_ts="+Date.now(),{{headers:{{"X-Telegram-Init-Data":tg?tg.initData:""}}}});
  let data={{}};try{{data=await res.json();}}catch(e){{}}
  if(!res.ok)throw new Error(data.detail||("Erro HTTP "+res.status));
  return data;
}}
async function apiPost(url,payload){{
  const res=await fetch(url+"?_ts="+Date.now(),{{method:"POST",headers:{{"Content-Type":"application/json","X-Telegram-Init-Data":tg?tg.initData:""}},body:JSON.stringify(payload||{{}})}});
  let data={{}};try{{data=await res.json();}}catch(e){{}}
  if(!res.ok)throw new Error(data.detail||("Erro HTTP "+res.status));
  return data;
}}

let renderer,scene,camera,dice,particles=[],frameHandle=0;

function createFaceTexture(value,rotateDeg=0){{
  const c=document.createElement("canvas");c.width=512;c.height=512;
  const ctx=c.getContext("2d");
  const g=ctx.createLinearGradient(0,0,512,512);g.addColorStop(0,"#1b2340");g.addColorStop(1,"#0a0f1e");
  ctx.fillStyle=g;ctx.fillRect(0,0,512,512);
  ctx.strokeStyle="rgba(255,255,255,.18)";ctx.lineWidth=12;ctx.strokeRect(18,18,476,476);
  ctx.save();ctx.translate(256,256);ctx.rotate(rotateDeg*Math.PI/180);
  ctx.shadowColor="rgba(0,242,255,.65)";ctx.shadowBlur=28;ctx.fillStyle="#ffffff";
  ctx.font="bold 250px Arial";ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillText(String(value),0,18);
  ctx.restore();
  const tex=new THREE.CanvasTexture(c);tex.needsUpdate=true;return tex;
}}

function setupScene(){{
  const el=document.getElementById("sceneWrap");const w=el.clientWidth;const h=el.clientHeight;
  renderer=new THREE.WebGLRenderer({{antialias:true,alpha:true}});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setSize(w,h);
  renderer.outputColorSpace=THREE.SRGBColorSpace;el.innerHTML="";el.appendChild(renderer.domElement);
  scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(38,w/h,0.1,100);camera.position.set(0,0.8,6.8);
  scene.add(new THREE.AmbientLight(0xffffff,1.45));
  const pt=new THREE.PointLight(0xffffff,2.0,30);pt.position.set(2.8,3.6,5.2);scene.add(pt);
  const floorGeo=new THREE.CircleGeometry(2.9,64);
  const floor=new THREE.Mesh(floorGeo,new THREE.MeshBasicMaterial({{color:0x112031,transparent:true,opacity:.36}}));
  floor.rotation.x=-Math.PI/2;floor.position.y=-1.55;scene.add(floor);
  const mats=[[2,-90],[5,90],[3,0],[4,180],[1,0],[6,180]].map(([v,r])=>new THREE.MeshStandardMaterial({{map:createFaceTexture(v,r),roughness:0.42,metalness:0.35}}));
  const geo=new THREE.BoxGeometry(2.05,2.05,2.05,1,1,1);
  dice=new THREE.Mesh(geo,mats);scene.add(dice);
  const edges=new THREE.LineSegments(new THREE.EdgesGeometry(geo),new THREE.LineBasicMaterial({{color:0x6ae7ff,transparent:true,opacity:.55}}));
  dice.add(edges);
  particles=[];for(let i=0;i<48;i++){{
    const p=new THREE.Mesh(new THREE.SphereGeometry(0.03,8,8),new THREE.MeshBasicMaterial({{color:i%2?0x00f2ff:0xff2bd6}}));
    p.position.set((Math.random()-.5)*4,(Math.random()-.5)*3,(Math.random()-.5)*3);
    p.userData={{vx:(Math.random()-.5)*.02,vy:(Math.random()-.5)*.02,vz:(Math.random()-.5)*.02}};
    scene.add(p);particles.push(p);
  }}
  cancelAnimationFrame(frameHandle);
  const tick=()=>{{
    if(!renderer||!scene||!camera||!dice)return;
    if(!state.rolling){{dice.rotation.x+=0.0022;dice.rotation.y+=0.003;}}
    particles.forEach(p=>{{
      p.position.x+=p.userData.vx;p.position.y+=p.userData.vy;p.position.z+=p.userData.vz;
      if(Math.abs(p.position.x)>3)p.userData.vx*=-1;
      if(Math.abs(p.position.y)>2)p.userData.vy*=-1;
      if(Math.abs(p.position.z)>2)p.userData.vz*=-1;
    }});
    renderer.render(scene,camera);frameHandle=requestAnimationFrame(tick);
  }};tick();
}}

function resizeScene(){{
  const el=document.getElementById("sceneWrap");if(!renderer||!camera||!el)return;
  renderer.setSize(el.clientWidth,el.clientHeight);camera.aspect=el.clientWidth/el.clientHeight;camera.updateProjectionMatrix();
}}

async function animateDiceResult(value){{
  if(!dice)return;state.rolling=true;rollBtn.disabled=true;setHud("Rolando...");
  clearAnimeCards();clearReveal();
  const targets={{1:{{x:0,y:0}},2:{{x:0,y:-Math.PI/2}},3:{{x:Math.PI/2,y:0}},4:{{x:-Math.PI/2,y:0}},5:{{x:0,y:Math.PI/2}},6:{{x:0,y:Math.PI}}}};
  const t=targets[value]||targets[1];
  const baseX=dice.rotation.x,baseY=dice.rotation.y,baseZ=dice.rotation.z;
  const endX=t.x+Math.PI*8,endY=t.y+Math.PI*9,endZ=baseZ+Math.PI*2.5;
  const duration=1850,start=performance.now();
  await new Promise(resolve=>{{
    function step(now){{
      const p=Math.min((now-start)/duration,1),ease=1-Math.pow(1-p,4);
      dice.rotation.x=baseX+(endX-baseX)*ease;dice.rotation.y=baseY+(endY-baseY)*ease;
      dice.rotation.z=baseZ+(endZ-baseZ)*(1-Math.pow(1-p,3))*.10;
      camera.position.x=Math.sin(p*Math.PI*2)*.22;camera.position.y=.8+Math.sin(p*Math.PI*5)*.08;
      camera.lookAt(0,0,0);
      if(p<1)requestAnimationFrame(step);else resolve();
    }}requestAnimationFrame(step);
  }});
  dice.rotation.x=t.x;dice.rotation.y=t.y;dice.rotation.z=0;
  camera.position.set(0,.8,6.8);camera.lookAt(0,0,0);
  setHud("Resultado: "+value);state.rolling=false;rollBtn.disabled=false;
}}

function renderAnimeOptions(options){{
  animeGrid.innerHTML="";clearReveal();
  if(!Array.isArray(options)||!options.length){{setMsg("Nenhuma opção encontrada para esta rolagem.");return;}}
  options.forEach((opt,idx)=>{{
    const title=(opt&&opt.title)?String(opt.title):("Anime "+(idx+1));
    const cover=(opt&&opt.cover)?String(opt.cover):DADO_BANNER_FALLBACK;
    const card=document.createElement("button");card.type="button";card.className="anime-card";
    card.innerHTML=`<div class="anime-bg" style="background-image:url('${{cover.replace(/'/g,"\\\\'")}}')" ></div><div class="anime-overlay"></div><div class="anime-meta"><div class="anime-title-txt">${{title}}</div><div class="anime-hint">Toque para escolher</div></div>`;
    card.addEventListener("click",()=>chooseAnime(opt));animeGrid.appendChild(card);
  }});
}}

async function chooseAnime(opt){{
  if(!state.currentRollId||state.choosing)return;state.choosing=true;
  [...animeGrid.children].forEach(el=>el.setAttribute("aria-disabled","true"));
  setMsg("Revelando personagem...");setHud("Escolha confirmada");
  try{{
    const data=await apiPost("/api/dado/pick",{{roll_id:state.currentRollId,anime_id:Number(opt.id)}});
    if(!data.ok){{
      const msgMap={{rate_limited:"Espere um instante.",character_not_found:"Nenhum personagem encontrado.",roll_not_found:"Rolagem não encontrada.",expired:"Sua rolagem expirou. Role novamente.",anime_not_in_roll:"Anime inválido para esta rolagem."}};
      throw new Error(msgMap[data.error]||data.error||"Falha ao revelar personagem.");
    }}
    const ch=data.character||{{}};
    setBalance(data.balance??state.balance);
    revealImg.src=ch.image||opt.cover||DADO_BANNER_FALLBACK;
    rarityTxt.textContent=`${{ch.tier||"COMMON"}} • ${{"\u2605".repeat(Number(ch.stars||1))}}`;
    charName.textContent=ch.name||"Personagem";
    animeFrom.textContent="Obtido de "+(ch.anime_title||opt.title||"Anime");
    revealBox.classList.add("show");setHud("Personagem revelado");setMsg("✨ Personagem obtido com sucesso.");
  }}catch(e){{
    [...animeGrid.children].forEach(el=>el.removeAttribute("aria-disabled"));
    setMsg("❌ "+(e.message||"Falha ao escolher anime."));
  }}finally{{state.choosing=false;}}
}}

async function loadState(){{
  try{{
    if(!tg||!tg.initData){{setMsg("Abra este WebApp pelo Telegram.");rollBtn.disabled=true;return;}}
    const data=await apiGet("/api/dado/state");
    setBalance(data.balance??0);setNext(data.next_recharge_hhmm||"--:--");state.balance=Number(data.balance||0);
    if(data.active_roll&&data.active_roll.roll_id){{
      state.currentRollId=Number(data.active_roll.roll_id);state.currentDice=Number(data.active_roll.dice_value||0);
      state.options=Array.isArray(data.active_roll.options)?data.active_roll.options:[];
      if(state.currentDice>0)await animateDiceResult(state.currentDice);
      if(state.options.length){{renderAnimeOptions(state.options);setMsg("Você tinha uma rolagem ativa. Continue escolhendo.");}}
      else setMsg("Você tinha uma rolagem ativa, mas sem opções visíveis. Role novamente.");
    }}else setMsg("Tudo pronto. Role o dado quando quiser.");
    rollBtn.disabled=false;
  }}catch(e){{rollBtn.disabled=true;setMsg("❌ "+(e.message||"Não consegui carregar seus dados."));}}
}}

async function rollDice(){{
  if(state.rolling||state.choosing)return;
  if(!tg||!tg.initData){{setMsg("Abra este WebApp pelo Telegram.");return;}}
  rollBtn.disabled=true;clearAnimeCards();clearReveal();setMsg("Rolando dado...");setHud("Rolando...");
  try{{
    const data=await apiPost("/api/dado/roll",{{}});
    if(!data.ok){{
      const msgMap={{no_balance:"Você está sem dados agora.",rate_limited:"Espere um instante.",anime_pool_unavailable:"Base local indisponível."}};
      throw new Error(msgMap[data.error]||data.error||"Falha ao rolar.");
    }}
    state.currentRollId=Number(data.roll_id||0);state.currentDice=Number(data.dice_value||1);
    state.options=Array.isArray(data.options)?data.options:[];
    setBalance(data.balance??0);await animateDiceResult(state.currentDice);
    if(!state.options.length)throw new Error("A rolagem veio sem opções de anime.");
    renderAnimeOptions(state.options);setMsg("Escolha um anime para revelar o personagem.");
  }}catch(e){{setMsg("❌ "+(e.message||"Erro ao rolar dado."));setHud("Falha na rolagem");}}
  finally{{rollBtn.disabled=false;}}
}}

rollBtn.addEventListener("click",rollDice);
resetBtn.addEventListener("click",resetScreen);
window.addEventListener("resize",resizeScene);
setupScene();loadState();
</script>"""

    return HTMLResponse(_page("Sistema de Dados — Source Baltigo", body, dado_css, js))


# =============================================================================
# ROUTES — MENU
# =============================================================================
@app.get("/api/menu/profile")
def api_menu_profile(uid: int = Query(...)):
    uid = int(uid or 0)
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    return JSONResponse(_menu_user_payload(uid))

@app.get("/api/menu/collection-characters")
def api_menu_collection_characters(uid: int = Query(...)):
    uid = int(uid or 0)
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    return JSONResponse({"ok": True, "items": _menu_collection_characters(uid)})

@app.post("/api/menu/nickname")
def api_menu_nickname(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    nickname = str(payload.get("nickname") or "").strip()
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    if not _valid_menu_nickname(nickname):
        return JSONResponse({"ok": False, "message": "Nickname inválido. Use 4-17 caracteres, começando com letra maiúscula."}, status_code=400)
    result = set_profile_nickname(uid, nickname)
    if not result.get("ok"):
        err = result.get("error")
        if err == "nickname_locked":
            return JSONResponse({"ok": False, "message": "Você já definiu seu nickname."}, status_code=400)
        if err == "nickname_taken":
            return JSONResponse({"ok": False, "message": "Esse nickname já está em uso."}, status_code=400)
        return JSONResponse({"ok": False, "message": "Não foi possível salvar o nickname."}, status_code=400)
    return {"ok": True}

@app.post("/api/menu/favorite")
def api_menu_favorite(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    character_id = int(payload.get("character_id") or 0)
    if uid <= 0 or character_id <= 0:
        return JSONResponse({"ok": False, "message": "Dados inválidos."}, status_code=400)
    set_profile_favorite(uid, character_id)
    return {"ok": True}

@app.post("/api/menu/country")
def api_menu_country(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    country_code = str(payload.get("country_code") or "").strip().upper()
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    set_profile_country(uid, country_code)
    return {"ok": True}

@app.post("/api/menu/language")
def api_menu_language(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    language = str(payload.get("language") or "").strip().lower()
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    if language not in ("pt", "en", "es"):
        return JSONResponse({"ok": False, "message": "Idioma inválido."}, status_code=400)
    set_profile_language(uid, language)
    return {"ok": True}

@app.post("/api/menu/privacy")
def api_menu_privacy(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    value = bool(payload.get("value"))
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    set_profile_private(uid, value)
    return {"ok": True}

@app.post("/api/menu/notifications")
def api_menu_notifications(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    value = bool(payload.get("value"))
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    set_profile_notifications(uid, value)
    return {"ok": True}

@app.post("/api/menu/delete-account")
def api_menu_delete_account(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    delete_user_account(uid)
    return {"ok": True}

@app.get("/menu", response_class=HTMLResponse)
def menu_page(uid: int = Query(...)):
    bg = MENU_BACKGROUND_URL if MENU_BACKGROUND_URL else EMPTY_BG_DATA_URI

    menu_css = f"""
body {{
  background:
    linear-gradient(180deg, rgba(0,0,0,.48), rgba(0,0,0,.78)),
    url("{bg}") center/cover no-repeat fixed,
    radial-gradient(900px 520px at 50% -10%, rgba(79,140,255,.18), transparent 55%),
    #050712;
}}
.menu-hero {{
  width: 100%;
  border-radius: var(--r-lg);
  overflow: hidden;
  border: 1px solid var(--stroke);
  background: #111;
  box-shadow: var(--shadow);
}}
.menu-hero img {{
  width: 100%; height: 190px;
  object-fit: cover; display: block; opacity: .9;
}}
.menu-hero::after {{
  content: ""; position: absolute; inset: 0;
  background: linear-gradient(180deg, rgba(0,0,0,.04), rgba(0,0,0,.74));
}}
.profile-block {{
  position: relative; z-index: 2;
  margin-top: -52px;
  display: flex; flex-direction: column; align-items: center;
}}
.avatar {{
  width: 108px; height: 108px;
  border-radius: 50%;
  border: 4px solid rgba(255,255,255,.10);
  background: #111722;
  overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  font-size: 32px; font-weight: 900;
  box-shadow: 0 12px 24px rgba(0,0,0,.40);
}}
.avatar img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.profile-name {{
  margin-top: 14px;
  font-size: 22px; font-weight: 900; line-height: 1.15; text-align: center;
}}
.profile-sub {{
  margin-top: 4px;
  color: var(--muted); font-size: 13px; font-weight: 700; text-align: center;
}}
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 22px;
}}
@media (max-width: 500px) {{ .stats-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
.stat-card {{
  border: 1px solid var(--stroke);
  border-radius: var(--r-md);
  background: var(--panel2);
  padding: 14px;
  text-align: center;
}}
.stat-card .stat-label {{
  font-size: 10px; font-weight: 900; letter-spacing: .12em;
  text-transform: uppercase; color: var(--muted);
}}
.stat-card .stat-val {{
  margin-top: 6px;
  font-size: 20px; font-weight: 900; line-height: 1.1;
}}
.list-block {{
  border: 1px solid var(--stroke);
  border-radius: var(--r-lg);
  background: var(--panel2);
  overflow: hidden;
  margin-top: 10px;
}}
.list-row {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 16px;
  border-bottom: 1px solid var(--stroke);
  flex-wrap: wrap;
}}
.list-row:last-child {{ border-bottom: none; }}
.row-left {{ flex: 1; min-width: 0; }}
.row-title {{ font-size: 14px; font-weight: 900; line-height: 1.2; }}
.row-sub {{ margin-top: 3px; font-size: 12px; color: var(--muted); font-weight: 700; line-height: 1.4; }}
.nick-box {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
.nick-box input {{
  border: 1px solid var(--stroke);
  background: rgba(255,255,255,.04);
  border-radius: var(--r-sm);
  padding: 10px 12px;
  color: var(--txt); font-size: 13px; font-family: var(--font);
  width: 140px; outline: none;
}}
.nick-box input:disabled {{ opacity: .45; }}
select {{
  border: 1px solid var(--stroke);
  background: rgba(255,255,255,.06);
  border-radius: var(--r-sm);
  padding: 10px 12px;
  color: var(--txt); font-size: 13px; font-family: var(--font);
  outline: none; cursor: pointer;
}}
.modal-wrap {{
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,.62);
  backdrop-filter: blur(4px);
  display: none;
  align-items: flex-end;
  justify-content: center;
}}
.modal {{
  width: 100%; max-width: 640px;
  max-height: 80vh;
  border: 1px solid var(--stroke);
  border-radius: var(--r-xl) var(--r-xl) 0 0;
  background: #0d1322;
  display: flex; flex-direction: column;
  overflow: hidden;
}}
.modal-head {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--stroke);
}}
.modal-title {{ font-size: 18px; font-weight: 900; }}
.modal-body {{ flex: 1; overflow-y: auto; padding: 14px 18px 24px; }}
.fav-search {{
  width: 100%;
  border: 1px solid var(--stroke);
  background: var(--panel2);
  border-radius: var(--r-md);
  padding: 12px 14px;
  color: var(--txt); font-size: 13px; font-family: var(--font);
  outline: none; margin-bottom: 14px;
}}
.fav-item {{
  border: 1px solid var(--stroke);
  background: rgba(255,255,255,.04);
  border-radius: var(--r-md);
  padding: 12px;
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 10px;
}}
.fav-thumb {{ width: 62px; height: 62px; border-radius: var(--r-sm); overflow: hidden; background: #121825; flex: 0 0 auto; }}
.fav-thumb img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.fav-meta {{ flex: 1; min-width: 0; }}
.fav-name {{ font-size: 15px; font-weight: 900; line-height: 1.2; }}
.fav-anime {{ margin-top: 3px; color: var(--muted); font-size: 12px; }}
"""

    body = f"""<div class="wrap">
  <div class="menu-hero" style="position:relative;">
    <img src="{MENU_BANNER_URL}" alt="Banner"/>
  </div>

  <div class="profile-block">
    <div class="avatar" id="avatar">SB</div>
    <div class="profile-name" id="profileName">Carregando...</div>
    <div class="profile-sub" id="profileSub">...</div>
  </div>

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-label">Coleção</div><div class="stat-val" id="collectionTotal">0</div></div>
    <div class="stat-card"><div class="stat-label">Coins</div><div class="stat-val" id="coins">0</div></div>
    <div class="stat-card"><div class="stat-label">Nível</div><div class="stat-val" id="level">1</div></div>
    <div class="stat-card"><div class="stat-label">Favorito</div><div class="stat-val" id="favoriteName" style="font-size:13px;">—</div></div>
  </div>

  <div class="section-title">Perfil</div>
  <div class="list-block">
    <div class="list-row">
      <div class="row-left">
        <div class="row-title">Nickname</div>
        <div class="row-sub">Único, começa com maiúscula. Não pode ser alterado depois.</div>
      </div>
      <div class="nick-box">
        <input id="nicknameInput" placeholder="Ex: Zoro" maxlength="17"/>
        <button class="btn btn-primary" id="saveNicknameBtn">Salvar</button>
      </div>
    </div>
    <div class="list-row">
      <div class="row-left">
        <div class="row-title">Favoritar personagem</div>
        <div class="row-sub">Só pode escolher da sua coleção.</div>
      </div>
      <button class="btn btn-ghost" id="favoriteBtn">Escolher</button>
    </div>
  </div>

  <div class="section-title">Preferências</div>
  <div class="list-block">
    <div class="list-row">
      <div class="row-left"><div class="row-title">Bandeira</div><div class="row-sub">Defina seu país.</div></div>
      <select id="countrySelect"></select>
    </div>
    <div class="list-row">
      <div class="row-left"><div class="row-title">Idioma</div><div class="row-sub">Idioma principal da conta.</div></div>
      <select id="languageSelect"></select>
    </div>
    <div class="list-row">
      <div class="row-left"><div class="row-title">Perfil privado</div><div class="row-sub">Oculta o perfil para outros usuários.</div></div>
      <button class="btn btn-ghost" id="privacyBtn">Desativado</button>
    </div>
    <div class="list-row">
      <div class="row-left"><div class="row-title">Notificações</div><div class="row-sub">Avisar quando os 24 dados acumularem.</div></div>
      <button class="btn btn-ghost" id="notificationsBtn">Ativado</button>
    </div>
  </div>

  <div class="section-title">Conta</div>
  <div class="list-block">
    <div class="list-row">
      <div class="row-left">
        <div class="row-title">Autoexcluir conta</div>
        <div class="row-sub">Apaga nickname, coleção, nível, coins e preferências.</div>
      </div>
      <button class="btn btn-danger" id="deleteBtn">Excluir conta</button>
    </div>
  </div>

  <div class="msg" id="menuMsg"></div>
  <div class="footer">Source Baltigo • Menu do usuário</div>
</div>

<div class="modal-wrap" id="favoriteModalWrap">
  <div class="modal">
    <div class="modal-head">
      <div class="modal-title">Escolher favorito</div>
      <button class="btn btn-ghost" id="closeFavoriteModalBtn" style="padding:8px 14px;font-size:12px;">Fechar</button>
    </div>
    <div class="modal-body">
      <input class="fav-search" id="favSearchInput" placeholder="Buscar personagem..."/>
      <div id="favList"></div>
    </div>
  </div>
</div>"""

    js = f"""<script>
const uid={uid};
const msgEl=document.getElementById("menuMsg");
const tg=window.Telegram&&window.Telegram.WebApp?window.Telegram.WebApp:null;
if(tg){{try{{tg.ready();}}catch(e){{}}}}
let profileData=null,favoriteCharacters=[];

function setMsg(text){{msgEl.textContent=text||"";}}

async function getJson(url){{
  const res=await fetch(url+(url.includes("?")?"&":"?")+"_ts="+Date.now());
  const data=await res.json();
  if(!res.ok||!data.ok)throw new Error((data&&data.message)||"Erro");
  return data;
}}
async function postJson(url,payload){{
  const res=await fetch(url+"?_ts="+Date.now(),{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(payload)}});
  const data=await res.json();
  if(!res.ok||!data.ok)throw new Error((data&&data.message)||"Erro");
  return data;
}}

function renderAvatar(profile){{
  const avatar=document.getElementById("avatar");
  if(profile.favorite&&profile.favorite.image){{
    avatar.innerHTML='<img src="'+profile.favorite.image+'" alt="avatar">';return;
  }}
  avatar.textContent=(profile.display_name||"SB").trim().slice(0,2).toUpperCase();
}}

function renderProfile(data){{
  profileData=data.profile||{{}};const p=profileData;
  document.getElementById("profileName").textContent=p.display_name||"User";
  document.getElementById("profileSub").textContent=p.nickname?("@"+p.nickname):"Sem nickname";
  document.getElementById("collectionTotal").textContent=String(p.collection_total||0);
  document.getElementById("coins").textContent=String(p.coins||0);
  document.getElementById("level").textContent=String(p.level||1);
  document.getElementById("favoriteName").textContent=p.favorite?p.favorite.name:"—";
  renderAvatar(p);
  const ni=document.getElementById("nicknameInput"),nb=document.getElementById("saveNicknameBtn");
  ni.value=p.nickname||"";ni.disabled=!!p.nickname;nb.disabled=!!p.nickname;
  const country=document.getElementById("countrySelect");country.innerHTML="";
  (data.countries||[]).forEach(c=>{{const opt=document.createElement("option");opt.value=c.code;opt.textContent=c.flag+" "+c.name;if(c.code===p.country_code)opt.selected=true;country.appendChild(opt);}});
  const lang=document.getElementById("languageSelect");lang.innerHTML="";
  (data.languages||[]).forEach(l=>{{const opt=document.createElement("option");opt.value=l.code;opt.textContent=l.name;if(l.code===p.language)opt.selected=true;lang.appendChild(opt);}});
  document.getElementById("privacyBtn").textContent=p.private_profile?"Ativado":"Desativado";
  document.getElementById("notificationsBtn").textContent=p.notifications_enabled?"Ativado":"Desativado";
}}

async function loadProfile(){{const data=await getJson("/api/menu/profile?uid="+uid);renderProfile(data);}}

function openFavoriteModal(){{document.getElementById("favoriteModalWrap").style.display="flex";}}
function closeFavoriteModal(){{document.getElementById("favoriteModalWrap").style.display="none";}}

function renderFavoriteList(items){{
  const wrap=document.getElementById("favList");wrap.innerHTML="";
  if(!items.length){{wrap.innerHTML='<div class="row-sub">Você ainda não tem personagens na coleção.</div>';return;}}
  for(const item of items){{
    const el=document.createElement("div");el.className="fav-item";
    el.innerHTML=`<div class="fav-thumb">${{item.image?`<img src="${{item.image}}" alt="">`:""}} </div><div class="fav-meta"><div class="fav-name">🧧 ${{item.name}}</div><div class="fav-anime">${{item.anime||""}}</div></div><button class="btn btn-primary" style="padding:10px 14px;font-size:12px;">Favoritar</button>`;
    el.querySelector("button").onclick=async()=>{{
      try{{setMsg("Salvando favorito...");await postJson("/api/menu/favorite",{{uid,character_id:item.id}});setMsg("✅ Favorito atualizado.");closeFavoriteModal();await loadProfile();}}
      catch(e){{setMsg("❌ "+e.message);}}
    }};
    wrap.appendChild(el);
  }}
}}

async function loadFavoriteCharacters(){{
  const data=await getJson("/api/menu/collection-characters?uid="+uid);
  favoriteCharacters=data.items||[];renderFavoriteList(favoriteCharacters);
}}

document.getElementById("favoriteBtn").onclick=async()=>{{
  try{{setMsg("");await loadFavoriteCharacters();openFavoriteModal();}}
  catch(e){{setMsg("❌ "+e.message);}}
}};
document.getElementById("closeFavoriteModalBtn").onclick=closeFavoriteModal;
document.getElementById("favoriteModalWrap").onclick=(e)=>{{if(e.target.id==="favoriteModalWrap")closeFavoriteModal();}};
document.getElementById("favSearchInput").addEventListener("input",(e)=>{{
  const q=(e.target.value||"").trim().toLowerCase();
  renderFavoriteList(favoriteCharacters.filter(item=>((item.name+" "+item.anime).toLowerCase()).includes(q)));
}});
document.getElementById("saveNicknameBtn").onclick=async()=>{{
  try{{const nickname=document.getElementById("nicknameInput").value.trim();setMsg("Salvando nickname...");await postJson("/api/menu/nickname",{{uid,nickname}});setMsg("✅ Nickname salvo.");await loadProfile();}}
  catch(e){{setMsg("❌ "+e.message);}}
}};
document.getElementById("countrySelect").onchange=async(e)=>{{
  try{{await postJson("/api/menu/country",{{uid,country_code:e.target.value}});setMsg("✅ Bandeira atualizada.");}}catch(e){{setMsg("❌ "+e.message);}}
}};
document.getElementById("languageSelect").onchange=async(e)=>{{
  try{{await postJson("/api/menu/language",{{uid,language:e.target.value}});setMsg("✅ Idioma atualizado.");}}catch(e){{setMsg("❌ "+e.message);}}
}};
document.getElementById("privacyBtn").onclick=async()=>{{
  try{{const current=document.getElementById("privacyBtn").textContent==="Ativado";await postJson("/api/menu/privacy",{{uid,value:!current}});setMsg("✅ Privacidade atualizada.");await loadProfile();}}catch(e){{setMsg("❌ "+e.message);}}
}};
document.getElementById("notificationsBtn").onclick=async()=>{{
  try{{const current=document.getElementById("notificationsBtn").textContent==="Ativado";await postJson("/api/menu/notifications",{{uid,value:!current}});setMsg("✅ Notificações atualizadas.");await loadProfile();}}catch(e){{setMsg("❌ "+e.message);}}
}};
document.getElementById("deleteBtn").onclick=async()=>{{
  if(!confirm("Tem certeza que deseja excluir sua conta? Esta ação é irreversível."))return;
  try{{setMsg("Excluindo conta...");await postJson("/api/menu/delete-account",{{uid}});setMsg("✅ Conta excluída.");if(tg)try{{tg.close();}}catch(e){{}}}}catch(e){{setMsg("❌ "+e.message);}}
}};
(async()=>{{try{{await loadProfile();}}catch(e){{setMsg("❌ "+e.message);}}}})();
</script>"""

    return HTMLResponse(_page("Menu — Source Baltigo", body, menu_css, js))


# =============================================================================
# ROUTES — SHOP
# =============================================================================
@app.get("/api/shop/state")
def api_shop_state(x_telegram_init_data: str = Header(default="")):
    tg = _get_tg_user(x_telegram_init_data)
    user_id = int(tg["user_id"])
    row = get_user_status(user_id) or {}
    return JSONResponse({"ok": True, "coins": int(row.get("coins") or 0), "dado_balance": int(row.get("dado_balance") or 0)})

@app.get("/api/shop/sell/all")
def api_shop_sell_all(q: str = Query(default="", max_length=120), x_telegram_init_data: str = Header(default="")):
    tg = _get_tg_user(x_telegram_init_data)
    user_id = int(tg["user_id"])
    items = _shop_collection_items(user_id, q=q)
    return JSONResponse({"ok": True, "items": items})

@app.post("/api/shop/sell/confirm")
def api_shop_sell_confirm(payload: dict = Body(...), x_telegram_init_data: str = Header(default="")):
    from database import sell_character
    tg = _get_tg_user(x_telegram_init_data)
    user_id = int(tg["user_id"])
    char_id = int(payload.get("character_id") or 0)
    if char_id <= 0:
        return JSONResponse({"ok": False, "error": "character_id inválido"}, status_code=400)
    if not _shop_rate_limit(user_id, f"sell:{char_id}", 0.9):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)
    result = sell_character(user_id, char_id)
    if not result or not result.get("ok"):
        return JSONResponse({"ok": False, "error": (result or {}).get("error") or "Não foi possível vender."}, status_code=200)
    row = get_user_status(user_id) or {}
    return JSONResponse({"ok": True, "coins": int(row.get("coins") or 0)})

@app.post("/api/shop/buy/dado")
def api_shop_buy_dado(x_telegram_init_data: str = Header(default="")):
    from database import buy_dado
    tg = _get_tg_user(x_telegram_init_data)
    user_id = int(tg["user_id"])
    if not _shop_rate_limit(user_id, "buy_dado", 0.9):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)
    result = buy_dado(user_id)
    if not result or not result.get("ok"):
        return JSONResponse({"ok": False, "error": (result or {}).get("error") or "Coins insuficientes."}, status_code=200)
    row = get_user_status(user_id) or {}
    return JSONResponse({"ok": True, "coins": int(row.get("coins") or 0), "dado_balance": int(row.get("dado_balance") or 0)})

@app.post("/api/shop/buy/nickname")
def api_shop_buy_nickname(x_telegram_init_data: str = Header(default="")):
    from database import buy_nickname_change
    tg = _get_tg_user(x_telegram_init_data)
    user_id = int(tg["user_id"])
    if not _shop_rate_limit(user_id, "buy_nick", 0.9):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)
    result = buy_nickname_change(user_id)
    if not result or not result.get("ok"):
        return JSONResponse({"ok": False, "error": (result or {}).get("error") or "Coins insuficientes."}, status_code=200)
    row = get_user_status(user_id) or {}
    return JSONResponse({"ok": True, "coins": int(row.get("coins") or 0)})

@app.get("/shop", response_class=HTMLResponse)
@app.get("/loja", response_class=HTMLResponse)
def shop_page():
    shop_css = """
.shop-stats { display: flex; gap: 10px; flex-wrap: wrap; padding: 14px 4px 6px; }
.stat-pill { border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.05); padding: 10px 14px; border-radius: 999px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; font-size: 12px; }
.sell-count-pill { position: absolute; right: 10px; bottom: 10px; z-index: 2; }
.buy-grid { display: grid; grid-template-columns: 1fr; gap: 14px; margin-top: 14px; }
@media (min-width: 600px) { .buy-grid { grid-template-columns: repeat(2,1fr); } }
.buy-card { border: 1px solid var(--stroke); border-radius: var(--r-lg); background: var(--panel2); padding: 20px; box-shadow: var(--shadow2); }
.buy-card h3 { margin: 0 0 8px; font-size: 18px; font-weight: 900; letter-spacing: .04em; text-transform: uppercase; }
.buy-card p { margin: 0 0 14px; color: var(--muted); font-size: 13px; line-height: 1.55; }
.buy-price { margin-bottom: 14px; font-weight: 900; letter-spacing: .10em; text-transform: uppercase; font-size: 12px; color: rgba(255,255,255,.80); }
.shop-toast { margin-top: 14px; border: 1px solid var(--stroke); background: var(--panel2); border-radius: var(--r-md); padding: 12px 16px; font-size: 13px; color: rgba(255,255,255,.82); font-weight: 700; min-height: 42px; }
"""
    body = f"""<div class="wrap">
  <div class="top-banner">
    <img src="{SHOP_PREVIEW_IMAGE}" alt="Shop banner"/>
    <div class="top-copy">
      <div class="eyebrow">🛒 Shop • Source Baltigo</div>
      <div style="margin-top:10px;font-size:24px;font-weight:900;">Loja Baltigo</div>
      <div style="margin-top:4px;color:rgba(255,255,255,.78);font-size:13px;">Venda personagens e compre recursos do sistema</div>
    </div>
  </div>

  <div class="shop-stats">
    <div class="stat-pill">🪙 Coins: <span id="coinsTxt">...</span></div>
    <div class="stat-pill">🎲 Dados: <span id="dadoTxt">...</span></div>
  </div>

  <div class="tabs">
    <div class="tab active" id="tabSell">📦 Vender</div>
    <div class="tab" id="tabBuy">🛒 Comprar</div>
  </div>

  <div id="sellView" style="margin-top:14px;">
    <div class="search-bar">
      <span style="opacity:.55;font-weight:900;">🔎</span>
      <input id="q" type="text" placeholder="Buscar personagem ou anime..."/>
    </div>
    <div class="cards-grid" id="sellCards" style="margin-top:14px;"></div>
    <div class="empty-state" id="sellEmpty" style="display:none;">Nada para mostrar.</div>
  </div>

  <div id="buyView" style="display:none;margin-top:14px;">
    <div class="buy-grid">
      <div class="buy-card">
        <h3>🎲 Comprar Dado</h3>
        <p>Adiciona +1 dado ao seu saldo atual.</p>
        <div class="buy-price">Preço: 2 coins</div>
        <button class="btn btn-ok btn-full" id="buyDadoBtn">Comprar dado</button>
      </div>
      <div class="buy-card">
        <h3>✏️ Alterar Nickname</h3>
        <p>Libera uma nova troca de nickname no seu perfil.</p>
        <div class="buy-price">Preço: 3 coins</div>
        <button class="btn btn-ok btn-full" id="buyNickBtn">Comprar nickname</button>
      </div>
    </div>
  </div>

  <div class="shop-toast" id="toast">Carregando loja...</div>
  <div class="footer">Source Baltigo • Shop</div>
</div>"""

    js = """<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script>
const tg=(window.Telegram&&Telegram.WebApp)?Telegram.WebApp:null;
if(tg){try{tg.ready();tg.expand();}catch(e){}}

async function fetchJson(url,options={}){
  const headers=Object.assign({},options.headers||{});
  try{const initData=tg&&tg.initData?tg.initData:"";if(initData)headers["x-telegram-init-data"]=initData;}catch(e){}
  const res=await fetch(url,Object.assign({},options,{headers}));
  const data=await res.json();return{ok:res.ok,data};
}

const state={items:[],coins:0,dado_balance:0,q:""};

function setToast(msg){document.getElementById("toast").textContent=msg;}
function syncState(){document.getElementById("coinsTxt").textContent=String(state.coins??0);document.getElementById("dadoTxt").textContent=String(state.dado_balance??0);}
function esc(s){return String(s||"").replace(/[&<>"']/g,(m)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));}

function renderSell(){
  const root=document.getElementById("sellCards"),empty=document.getElementById("sellEmpty");
  root.innerHTML="";
  const qn=state.q.trim().toLowerCase();
  const items=state.items.filter(x=>!qn||(`${x.character_id} ${x.character_name} ${x.anime_title}`).toLowerCase().includes(qn));
  if(!items.length){empty.style.display="";return;}
  empty.style.display="none";
  for(const c of items){
    const card=document.createElement("div");card.className="card";
    const cover=c.image?`<img src="${esc(c.image)}" alt="${esc(c.character_name)}" loading="lazy"/>`:`<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-weight:900;opacity:.45;">SEM IMAGEM</div>`;
    const extra=c.rarity?`<span class="pill">${esc(c.rarity)}</span>`:"";
    card.innerHTML=`
      <div class="cover">
        ${cover}
        <span class="pill sell-count-pill">x${Number(c.quantity||0)}</span>
      </div>
      <div class="meta">
        <p class="name">${esc(c.character_name)}</p>
        <div class="sub"><span class="pill">${esc(c.anime_title)}</span>${extra}</div>
        <button class="btn btn-danger btn-full" style="margin-top:12px;" data-sell="${Number(c.character_id)}">Vender +1 coin</button>
      </div>`;
    root.appendChild(card);
  }
  root.querySelectorAll("button[data-sell]").forEach(btn=>{
    btn.onclick=async()=>{
      const id=Number(btn.getAttribute("data-sell"));btn.disabled=true;setToast("Vendendo personagem...");
      const r=await fetchJson("/api/shop/sell/confirm",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({character_id:id})});
      if(!r.ok||!r.data.ok){setToast("❌ "+((r.data&&r.data.error)||"Não foi possível vender."));btn.disabled=false;return;}
      state.coins=Number(r.data.coins||state.coins||0);syncState();setToast("✅ Personagem vendido.");await loadCollection();
    };
  });
}

async function loadState(){
  const r=await fetchJson("/api/shop/state");
  if(!r.ok||!r.data.ok){setToast("❌ Falha ao carregar estado.");return false;}
  state.coins=Number(r.data.coins||0);state.dado_balance=Number(r.data.dado_balance||0);syncState();return true;
}

async function loadCollection(){
  const r=await fetchJson("/api/shop/sell/all?q="+encodeURIComponent(state.q||""));
  if(!r.ok||!r.data.ok){state.items=[];renderSell();setToast("❌ Falha ao carregar personagens.");return;}
  state.items=Array.isArray(r.data.items)?r.data.items:[];renderSell();setToast("✅ Loja Baltigo.");
}

document.getElementById("q").addEventListener("input",async(e)=>{state.q=e.target.value||"";renderSell();});
document.getElementById("tabSell").onclick=()=>{document.getElementById("tabSell").classList.add("active");document.getElementById("tabBuy").classList.remove("active");document.getElementById("sellView").style.display="";document.getElementById("buyView").style.display="none";};
document.getElementById("tabBuy").onclick=()=>{document.getElementById("tabBuy").classList.add("active");document.getElementById("tabSell").classList.remove("active");document.getElementById("buyView").style.display="";document.getElementById("sellView").style.display="none";};
document.getElementById("buyDadoBtn").onclick=async()=>{setToast("Comprando dado...");const r=await fetchJson("/api/shop/buy/dado",{method:"POST"});if(!r.ok||!r.data.ok){setToast("❌ "+((r.data&&r.data.error)||"Coins insuficientes."));return;}state.coins=Number(r.data.coins||state.coins||0);state.dado_balance=Number(r.data.dado_balance||state.dado_balance||0);syncState();setToast("✅ Dado comprado.");};
document.getElementById("buyNickBtn").onclick=async()=>{setToast("Comprando nickname...");const r=await fetchJson("/api/shop/buy/nickname",{method:"POST"});if(!r.ok||!r.data.ok){setToast("❌ "+((r.data&&r.data.error)||"Coins insuficientes."));return;}state.coins=Number(r.data.coins||state.coins||0);syncState();setToast("✅ Alteração de nickname liberada.");};
(async()=>{const ok=await loadState();if(!ok)return;await loadCollection();})();
</script>"""

    return HTMLResponse(_page("Loja • Source Baltigo", body, shop_css, js))


# =============================================================================
# ROUTES — BALTIGOFLIX
# =============================================================================
@app.post("/api/baltigoflix/create-intent")
async def baltigoflix_create_intent(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "json_invalido"}, status_code=400)
    telegram_user_id = int(body.get("telegram_user_id") or 0)
    telegram_username = str(body.get("telegram_username") or "").strip()
    telegram_full_name = str(body.get("telegram_full_name") or "").strip()
    plan_code = str(body.get("plan_code") or "").strip().lower()
    if telegram_user_id <= 0:
        return JSONResponse({"ok": False, "error": "telegram_user_id_invalido"}, status_code=400)
    plan = BALTIGOFLIX_PLANS.get(plan_code)
    if not plan:
        return JSONResponse({"ok": False, "error": "plano_invalido"}, status_code=400)
    ref = get_user_referrer(telegram_user_id) or {}
    referrer_user_id = ref.get("referrer_user_id")
    ref_code = ref.get("ref_code") or ""
    intent = create_purchase_intent(
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        telegram_full_name=telegram_full_name,
        plan_code=plan["code"],
        plan_name=plan["name"],
        amount_cents=int(plan["amount_cents"]),
        referrer_user_id=int(referrer_user_id) if referrer_user_id else None,
        ref_code=ref_code,
        metadata={"source": "miniapp", "plan_code": plan["code"]},
    )
    base_checkout_url = CHECKOUT_URLS.get(plan["code"], "").strip()
    if not base_checkout_url:
        return JSONResponse({"ok": False, "error": "checkout_nao_configurado"}, status_code=500)
    separator = "&" if "?" in base_checkout_url else "?"
    checkout_url = f"{base_checkout_url}{separator}ref={intent['intent_token']}"
    attach_checkout_data_to_purchase_intent(
        intent_id=int(intent["id"]),
        checkout_url=checkout_url,
        raw_checkout_response={"mode": "static_checkout_link"},
    )
    return JSONResponse({
        "ok": True,
        "intent_token": intent["intent_token"],
        "plan_code": plan["code"],
        "plan_name": plan["name"],
        "amount_cents": plan["amount_cents"],
        "checkout_url": checkout_url,
        "external_reference": intent.get("external_reference"),
        "message": "intenção criada com sucesso",
    })

@app.post("/api/cakto/webhook")
async def cakto_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "json_invalido"}, status_code=400)
    received_secret = (
        request.headers.get("x-webhook-secret")
        or request.headers.get("x-cakto-secret")
        or str(payload.get("secret") or "").strip()
    )
    if WEBHOOK_SECRET and received_secret != WEBHOOK_SECRET:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    event_type = str(payload.get("event") or payload.get("type") or payload.get("event_type") or "").strip()
    ids = _extract_cakto_ids(payload)
    event_row = save_cakto_webhook_event(
        event_type=event_type,
        payload=payload,
        event_id=str(payload.get("id") or payload.get("event_id") or "").strip(),
        order_id=ids["order_id"],
        subscription_id=ids["subscription_id"],
    )
    try:
        intent = None
        if ids["order_id"]:
            intent = get_purchase_intent_by_cakto_order_id(ids["order_id"])
        if not intent and ids["external_reference"]:
            intent = get_purchase_intent_by_external_reference(ids["external_reference"])
        if not intent:
            mark_cakto_webhook_event_error(event_row["id"], "purchase_intent_nao_encontrado")
            return JSONResponse({"ok": True, "ignored": True, "reason": "purchase_intent_nao_encontrado"})
        attach_checkout_data_to_purchase_intent(
            intent_id=int(intent["id"]),
            cakto_order_id=ids["order_id"],
            cakto_subscription_id=ids["subscription_id"],
            cakto_customer_id=ids["customer_id"],
            raw_checkout_response=payload,
        )
        event_type_lower = event_type.lower()
        approved_events = {"purchase_approved","compra_aprovada","payment_approved","order_paid","subscription_renewed"}
        canceled_events = {"purchase_refused","compra_recusada","subscription_canceled","subscription_cancelled","canceled","cancelled"}
        refunded_events = {"refund","refunded","reembolso","chargeback"}
        if event_type_lower in approved_events:
            mark_purchase_intent_status(intent_id=int(intent["id"]), status="paid", cakto_order_id=ids["order_id"], cakto_subscription_id=ids["subscription_id"], cakto_customer_id=ids["customer_id"])
            if intent.get("referrer_user_id"):
                create_affiliate_commission_for_purchase(
                    purchase_intent_id=int(intent["id"]), buyer_user_id=int(intent["telegram_user_id"]),
                    referrer_user_id=int(intent["referrer_user_id"]), amount_cents=int(intent["amount_cents"]),
                    metadata={"source": "cakto_webhook", "event_type": event_type},
                )
        elif event_type_lower in canceled_events:
            mark_purchase_intent_status(intent_id=int(intent["id"]), status="canceled", cakto_order_id=ids["order_id"], cakto_subscription_id=ids["subscription_id"], cakto_customer_id=ids["customer_id"])
        elif event_type_lower in refunded_events:
            mark_purchase_intent_status(intent_id=int(intent["id"]), status="refunded", cakto_order_id=ids["order_id"], cakto_subscription_id=ids["subscription_id"], cakto_customer_id=ids["customer_id"])
            reverse_affiliate_commission_by_purchase(purchase_intent_id=int(intent["id"]), reason=event_type)
        mark_cakto_webhook_event_processed(event_row["id"])
        return JSONResponse({"ok": True})
    except Exception as e:
        mark_cakto_webhook_event_error(event_row["id"], str(e))
        return JSONResponse({"ok": False, "error": "erro_processando_webhook"}, status_code=500)

@app.get("/baltigoflix/checkout-pending", response_class=HTMLResponse)
def baltigoflix_checkout_pending():
    body = """<div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;">
  <div class="panel" style="width:100%;max-width:520px;padding:32px;text-align:center;">
    <div style="font-size:48px;margin-bottom:16px;">⏳</div>
    <h1 style="margin:0 0 12px;font-size:26px;font-weight:900;">Redirecionando...</h1>
    <p style="margin:0;color:var(--muted);line-height:1.65;font-size:14px;">
      Aguarde enquanto preparamos seu checkout. Se esta tela persistir, verifique a URL configurada na intenção de compra.
    </p>
    <div style="margin-top:24px;width:40px;height:40px;border:3px solid rgba(255,255,255,.12);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;margin-left:auto;margin-right:auto;"></div>
  </div>
</div>
<style>@keyframes spin{to{transform:rotate(360deg)}}</style>"""
    return HTMLResponse(_page("BaltigoFlix • Checkout", body))

@app.get("/baltigoflix", response_class=HTMLResponse)
def baltigoflix_page():
    bflix_css = """
body {
  background:
    radial-gradient(900px 500px at 0% 0%, rgba(255,138,0,.14), transparent 60%),
    radial-gradient(1000px 500px at 100% 10%, rgba(99,168,255,.13), transparent 60%),
    radial-gradient(900px 600px at 50% 100%, rgba(255,61,0,.08), transparent 60%),
    linear-gradient(180deg, #060913, #0b1020);
}
.bflix-section { margin-top: 16px; border: 1px solid var(--stroke); border-radius: 30px; background: rgba(255,255,255,.04); box-shadow: var(--shadow); overflow: hidden; }
.bflix-inner { padding: 22px; }
.bflix-eyebrow { display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid rgba(255,255,255,.14); border-radius: 999px; background: rgba(255,255,255,.06); font-size: 12px; font-weight: 900; letter-spacing: .06em; text-transform: uppercase; }
.bflix-title { margin: 12px 0 10px; font-size: clamp(30px,6vw,58px); line-height: 1.02; font-weight: 900; letter-spacing: -.045em; }
.grad-text { background: linear-gradient(90deg,#ffe09c 0%,#ff9d22 35%,#ff5100 78%); -webkit-background-clip: text; background-clip: text; color: transparent; }
.bflix-subtitle { margin: 0; font-size: 16px; line-height: 1.65; color: var(--muted); }
.hero-grid { display: grid; grid-template-columns: 1.15fr .85fr; gap: 18px; align-items: stretch; }
@media (max-width: 700px) { .hero-grid { grid-template-columns: 1fr; } }
.hero-card { border: 1px solid var(--stroke); border-radius: var(--r-lg); background: rgba(255,255,255,.055); padding: 18px; backdrop-filter: blur(12px); }
.mini-label { color: #ffc680; font-size: 12px; text-transform: uppercase; letter-spacing: .09em; font-weight: 900; margin-bottom: 10px; }
.price-text { color: var(--muted); font-size: 15px; line-height: 1.55; }
.price-text strong { display: block; margin-top: 8px; font-size: 44px; line-height: 1; color: #fff; letter-spacing: -.04em; }
.check-list { display: grid; gap: 10px; margin-top: 16px; }
.check-item { display: flex; gap: 10px; align-items: flex-start; font-size: 14px; line-height: 1.45; }
.check-dot { width: 22px; height: 22px; flex: 0 0 22px; border-radius: 999px; display: flex; align-items: center; justify-content: center; background: rgba(39,227,138,.15); border: 1px solid rgba(39,227,138,.34); color: var(--ok); font-weight: 900; font-size: 12px; }
.bflix-stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-top: 18px; }
@media (max-width: 600px) { .bflix-stats { grid-template-columns: repeat(2,1fr); } }
.bflix-stat { border: 1px solid var(--stroke); background: rgba(255,255,255,.04); border-radius: var(--r-lg); padding: 16px; text-align: center; }
.bflix-stat strong { display: block; font-size: 24px; line-height: 1; margin-bottom: 6px; letter-spacing: -.03em; }
.bflix-stat span { color: var(--muted); font-size: 13px; }
.section-eyebrow { color: #ffc680; font-size: 12px; text-transform: uppercase; letter-spacing: .10em; font-weight: 900; margin-bottom: 8px; }
.section-heading { margin: 0 0 10px; font-size: clamp(22px,4.4vw,40px); line-height: 1.08; letter-spacing: -.03em; font-weight: 900; }
.section-text { margin: 0; color: var(--muted); line-height: 1.65; font-size: 15px; }
.logo-strip { overflow: hidden; margin-top: 16px; -webkit-mask-image: linear-gradient(to right,transparent 0%,black 14%,black 86%,transparent 100%); mask-image: linear-gradient(to right,transparent 0%,black 14%,black 86%,transparent 100%); }
.logo-track { display: flex; gap: 12px; width: max-content; animation: marquee 26s linear infinite; }
.logo-item { min-width: 110px; border: 1px solid var(--stroke); border-radius: var(--r-md); background: rgba(255,255,255,.05); padding: 12px 14px; color: rgba(255,255,255,.9); text-align: center; font-weight: 800; font-size: 12px; }
@keyframes marquee { from{transform:translateX(0)} to{transform:translateX(-50%)} }
.feature-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: 14px; margin-top: 18px; }
@media (max-width: 500px) { .feature-grid { grid-template-columns: 1fr; } }
.feature { border: 1px solid var(--stroke); border-radius: var(--r-lg); background: linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.035)); padding: 18px; }
.feature-icon { width: 46px; height: 46px; border-radius: var(--r-md); display: flex; align-items: center; justify-content: center; margin-bottom: 12px; font-size: 20px; background: rgba(255,255,255,.08); border: 1px solid var(--stroke2); }
.feature h3 { margin: 0 0 8px; font-size: 20px; line-height: 1.15; letter-spacing: -.02em; }
.feature p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.62; }
.plans-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-top: 18px; }
@media (max-width: 800px) { .plans-grid { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 450px) { .plans-grid { grid-template-columns: 1fr; } }
.plan { position: relative; border: 1px solid var(--stroke); border-radius: var(--r-lg); background: linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.035)); padding: 18px; display: flex; flex-direction: column; }
.plan.popular { border-color: rgba(255,138,0,.36); box-shadow: 0 18px 32px rgba(255,98,0,.14); }
.popular-tag { position: absolute; top: 14px; right: 14px; background: linear-gradient(90deg,var(--brand),var(--brand2)); color: #fff; border-radius: 999px; padding: 7px 10px; font-size: 11px; font-weight: 900; letter-spacing: .06em; text-transform: uppercase; }
.plan-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; font-weight: 900; margin-bottom: 8px; }
.plan h3 { margin: 0 0 10px; font-size: 26px; font-weight: 900; letter-spacing: -.03em; }
.plan-price { color: var(--muted); font-size: 14px; line-height: 1.5; margin-bottom: 14px; }
.plan-price strong { display: block; font-size: 32px; line-height: 1; color: #fff; margin-top: 6px; letter-spacing: -.04em; }
.plan ul { list-style: none; padding: 0; margin: 0 0 16px; display: grid; gap: 10px; flex: 1; }
.plan li { display: flex; gap: 10px; align-items: flex-start; font-size: 14px; line-height: 1.45; color: var(--txt); }
.plan li b { color: var(--ok); }
.faq { display: grid; gap: 10px; margin-top: 18px; }
.faq-item { border: 1px solid var(--stroke); border-radius: var(--r-md); overflow: hidden; background: rgba(255,255,255,.04); }
.faq-btn { width: 100%; text-align: left; padding: 16px 18px; background: none; border: none; color: var(--txt); font-size: 15px; font-weight: 800; cursor: pointer; font-family: var(--font); display: flex; justify-content: space-between; align-items: center; }
.faq-btn::after { content: "+"; font-size: 20px; opacity: .6; transition: transform .2s ease; }
.faq-item.active .faq-btn::after { transform: rotate(45deg); }
.faq-content { display: none; padding: 0 18px 18px; color: var(--muted); font-size: 14px; line-height: 1.65; }
.faq-item.active .faq-content { display: block; }
.guarantee-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: center; }
@media (max-width: 600px) { .guarantee-grid { grid-template-columns: 1fr; } }
.guarantee-card { border: 1px solid var(--stroke); border-radius: var(--r-lg); background: rgba(255,255,255,.045); padding: 20px; }
.proof-big { font-size: 46px; line-height: 1; font-weight: 900; letter-spacing: -.04em; margin: 0 0 8px; }
.status-box { margin-bottom: 18px; padding: 16px; border-radius: var(--r-md); border: 1px solid var(--stroke); background: rgba(255,255,255,.04); display: none; font-size: 14px; font-weight: 700; line-height: 1.6; }
.status-box.success { border-color: rgba(74,222,128,.36); background: rgba(74,222,128,.08); color: var(--ok); }
.status-box.error { border-color: rgba(255,90,118,.36); background: rgba(255,90,118,.08); color: var(--danger); }
.loading-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.62); backdrop-filter: blur(4px); z-index: 300; display: none; align-items: center; justify-content: center; }
.loading-card { border: 1px solid var(--stroke); border-radius: var(--r-xl); background: #0d1322; padding: 32px; text-align: center; max-width: 380px; width: 90%; }
.spinner { width: 42px; height: 42px; border: 3px solid rgba(255,255,255,.12); border-top-color: var(--brand); border-radius: 50%; animation: spin .8s linear infinite; margin: 0 auto 18px; }
@keyframes spin { to { transform: rotate(360deg); } }
.cta-row { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 18px; }
"""

    logos = ["Apple TV","Claro TV","Combate","Crunchyroll","Disney+","Globoplay","Max","Netflix","Premiere","Prime Video","Sky","Telecine"]
    logo_html = "".join(f'<div class="logo-item">{l}</div>' for l in logos * 2)

    body = f"""<div class="wrap">
  <div class="bflix-section">
    <div class="bflix-inner">
      <div class="bflix-eyebrow">📺 BaltigoFlix</div>
      <div class="bflix-title"><span class="grad-text">O entretenimento que você quer,</span> em um só acesso</div>
      <div class="bflix-subtitle">Canais, filmes, séries, esportes e conteúdo premium. Instalação simples, sem complicação.</div>
      <div class="hero-grid" style="margin-top:18px;">
        <div>
          <div class="cta-row">
            <a href="#planos" class="btn btn-brand">🔥 Ver planos</a>
            <button class="btn btn-ghost" id="btnSaibaMais">Saiba mais</button>
          </div>
          <div class="check-list" style="margin-top:20px;">
            <div class="check-item"><div class="check-dot">✓</div><div>Acesso a milhares de canais abertos e fechados</div></div>
            <div class="check-item"><div class="check-dot">✓</div><div>Filmes, séries e conteúdo premium sem anúncios</div></div>
            <div class="check-item"><div class="check-dot">✓</div><div>Esportes ao vivo — futebol, UFC, F1, NBA e mais</div></div>
            <div class="check-item"><div class="check-dot">✓</div><div>Instalação em Smart TV, TV Box, celular ou PC</div></div>
          </div>
        </div>
        <div class="hero-card">
          <div class="mini-label">A partir de</div>
          <div class="price-text">Plano Mensal<strong>R$ 25,90</strong></div>
          <div class="check-list" style="margin-top:14px;">
            <div class="check-item"><div class="check-dot">✓</div><div>Sem mensalidade extra por conteúdo</div></div>
            <div class="check-item"><div class="check-dot">✓</div><div>7 dias de garantia</div></div>
            <div class="check-item"><div class="check-dot">✓</div><div>Suporte via Telegram</div></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="bflix-section">
    <div class="bflix-inner">
      <div class="bflix-stats">
        <div class="bflix-stat"><strong>+1.300</strong><span>usuários ativos</span></div>
        <div class="bflix-stat"><strong>4</strong><span>planos disponíveis</span></div>
        <div class="bflix-stat"><strong>7 dias</strong><span>de garantia</span></div>
        <div class="bflix-stat"><strong>24h</strong><span>suporte ativo</span></div>
      </div>
    </div>
  </div>

  <div class="bflix-section" id="saibamais">
    <div class="bflix-inner">
      <div class="section-eyebrow">O que é a BaltigoFlix?</div>
      <h2 class="section-heading">Tudo em um lugar, sem complicação</h2>
      <p class="section-text">Em vez de pagar vários serviços separados, a BaltigoFlix concentra canais, filmes, séries, esportes e conteúdos especiais em um único acesso.</p>
      <div class="logo-strip"><div class="logo-track">{logo_html}</div></div>
    </div>
  </div>

  <div class="bflix-section">
    <div class="bflix-inner">
      <div class="section-eyebrow">Recursos</div>
      <h2 class="section-heading">Tudo que você vai encontrar no acesso</h2>
      <div class="feature-grid">
        <article class="feature"><div class="feature-icon">📺</div><h3>Milhares de canais</h3><p>Grade ampla com canais abertos e fechados para o dia a dia.</p></article>
        <article class="feature"><div class="feature-icon">🎞️</div><h3>Filmes e séries</h3><p>Catálogo robusto para quem quer maratonar sem depender de múltiplos apps.</p></article>
        <article class="feature"><div class="feature-icon">⚽</div><h3>Esportes ao vivo</h3><p>Futebol, Champions, UFC, basquete e Fórmula 1 ao vivo.</p></article>
        <article class="feature"><div class="feature-icon">🔒</div><h3>Conteúdo adulto protegido</h3><p>Área separada e protegida por senha para mais privacidade.</p></article>
        <article class="feature"><div class="feature-icon">🧩</div><h3>Instalação simples</h3><p>Passo a passo enviado ao comprador. Funciona em Smart TV, TV Box, celular ou PC.</p></article>
        <article class="feature"><div class="feature-icon">🚫</div><h3>Sem propagandas</h3><p>Assista sem anúncios e sem interrupções no meio do conteúdo.</p></article>
      </div>
    </div>
  </div>

  <div class="bflix-section">
    <div class="bflix-inner guarantee-grid">
      <div>
        <div class="section-eyebrow">Garantia</div>
        <h2 class="section-heading"><span class="grad-text">Experimente sem riscos por 7 dias</span></h2>
        <p class="section-text">Em caso de falha do sistema dentro desse período, devolvemos integralmente o valor pago. Sem letras miúdas.</p>
        <div class="cta-row"><a href="#planos" class="btn btn-brand">💎 Quero meu acesso</a></div>
      </div>
      <div class="guarantee-card">
        <div class="proof-big">+1.300</div>
        <p class="section-text">pessoas já usam e recomendam a BaltigoFlix.</p>
      </div>
    </div>
  </div>

  <div class="bflix-section">
    <div class="bflix-inner">
      <div class="section-eyebrow">Planos</div>
      <h2 class="section-heading" id="planos">Escolha o plano ideal</h2>
      <p class="section-text">Toque em um dos planos abaixo para iniciar sua compra dentro do bot.</p>
      <div id="purchaseStatus" class="status-box"></div>
      <div class="plans-grid">
        <article class="plan">
          <div class="plan-label">Plano</div><h3>Mensal</h3>
          <div class="plan-price">Ideal para começar<strong>R$ 25,90</strong></div>
          <ul><li><b>✓</b><div>Entrada rápida no serviço</div></li><li><b>✓</b><div>Bom para testar a experiência</div></li><li><b>✓</b><div>Fluxo concluído pelo bot</div></li></ul>
          <button class="btn btn-brand buy-btn btn-full" data-plan="mensal">Assinar mensal</button>
        </article>
        <article class="plan">
          <div class="plan-label">Plano</div><h3>Trimestral</h3>
          <div class="plan-price">Mais economia<strong>R$ 59,90</strong></div>
          <ul><li><b>✓</b><div>Melhor custo que o mensal</div></li><li><b>✓</b><div>Mais tranquilidade</div></li><li><b>✓</b><div>Compra simples e direta</div></li></ul>
          <button class="btn btn-brand buy-btn btn-full" data-plan="trimestral">Assinar trimestral</button>
        </article>
        <article class="plan popular">
          <div class="popular-tag">Popular</div>
          <div class="plan-label">Plano</div><h3>Semestral</h3>
          <div class="plan-price">Excelente custo-benefício<strong>R$ 89,90</strong></div>
          <ul><li><b>✓</b><div>Mais vantagem na permanência</div></li><li><b>✓</b><div>Boa relação tempo/valor</div></li><li><b>✓</b><div>Opção muito competitiva</div></li></ul>
          <button class="btn btn-brand buy-btn btn-full" data-plan="semestral">Assinar semestral</button>
        </article>
        <article class="plan">
          <div class="plan-label">Plano</div><h3>Anual</h3>
          <div class="plan-price">Maior economia<strong>R$ 129,90</strong></div>
          <ul><li><b>✓</b><div>Melhor valor entre os planos</div></li><li><b>✓</b><div>Mais tempo sem preocupação</div></li><li><b>✓</b><div>Destaque de oferta</div></li></ul>
          <button class="btn btn-brand buy-btn btn-full" data-plan="anual">Assinar anual</button>
        </article>
      </div>
    </div>
  </div>

  <div class="bflix-section">
    <div class="bflix-inner">
      <div class="section-eyebrow">Perguntas frequentes</div>
      <h2 class="section-heading">Respostas diretas</h2>
      <div class="faq">
        <div class="faq-item active"><button class="faq-btn">O que é exatamente a BaltigoFlix?</button><div class="faq-content">Uma solução para concentrar acesso a canais, filmes, séries, esportes e conteúdos especiais em uma experiência mais simples e centralizada.</div></div>
        <div class="faq-item"><button class="faq-btn">Preciso pagar mensalidade extra por conteúdo?</button><div class="faq-content">Não. Você recebe um código de acesso equivalente à assinatura, sem necessidade de pagamentos extras por conteúdo.</div></div>
        <div class="faq-item"><button class="faq-btn">Como é a instalação?</button><div class="faq-content">O passo a passo é enviado ao comprador, com instalação possível em TV Box, Smart TV, celular ou computador.</div></div>
        <div class="faq-item"><button class="faq-btn">Tem garantia?</button><div class="faq-content">Sim. Você pode experimentar por 7 dias e, em caso de falha do sistema dentro desse período, devolvemos o valor integralmente.</div></div>
        <div class="faq-item"><button class="faq-btn">O pagamento acontece aqui?</button><div class="faq-content">A compra é iniciada aqui no Mini App e a confirmação final acontece quando o sistema recebe o retorno oficial do pagamento.</div></div>
      </div>
    </div>
  </div>

  <div class="footer">Source Baltigo • BaltigoFlix</div>
</div>

<div id="loadingOverlay" class="loading-overlay">
  <div class="loading-card">
    <div class="spinner"></div>
    <div style="font-size:18px;font-weight:900;margin-bottom:8px;">Preparando sua compra...</div>
    <div style="color:var(--muted);line-height:1.6;font-size:14px;">Estamos registrando seu plano e preparando a próxima etapa.</div>
  </div>
</div>"""

    js = """<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script>
const tg=window.Telegram&&window.Telegram.WebApp?window.Telegram.WebApp:null;
if(tg){try{tg.ready();tg.expand();}catch(e){}}
const loadingOverlay=document.getElementById("loadingOverlay");
const statusBox=document.getElementById("purchaseStatus");

document.getElementById("btnSaibaMais").addEventListener("click",()=>{const el=document.getElementById("saibamais");if(el)el.scrollIntoView({behavior:"smooth",block:"start"});});
document.querySelectorAll(".faq-btn").forEach(btn=>{btn.addEventListener("click",()=>{btn.parentElement.classList.toggle("active");});});

function showLoading(){if(loadingOverlay)loadingOverlay.style.display="flex";}
function hideLoading(){if(loadingOverlay)loadingOverlay.style.display="none";}
function setStatus(message,kind=""){if(!statusBox)return;statusBox.style.display="block";statusBox.className="status-box"+(kind?" "+kind:"");statusBox.innerText=message;}
function getTelegramUser(){const u=(tg&&tg.initDataUnsafe&&tg.initDataUnsafe.user)?tg.initDataUnsafe.user:null;if(!u)return null;return{telegram_user_id:Number(u.id||0),telegram_username:u.username||"",telegram_full_name:[u.first_name||"",u.last_name||""].join(" ").trim()};}

async function createIntent(planCode){
  const user=getTelegramUser();
  if(!user||!user.telegram_user_id){setStatus("Não foi possível identificar seu usuário do Telegram.","error");return;}
  showLoading();
  try{
    const res=await fetch("/api/baltigoflix/create-intent",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({telegram_user_id:user.telegram_user_id,telegram_username:user.telegram_username,telegram_full_name:user.telegram_full_name,plan_code:planCode})});
    const data=await res.json();
    if(!res.ok||!data.ok)throw new Error(data.error||"erro_ao_criar_intent");
    setStatus("✅ Plano "+data.plan_name+" registrado. Redirecionando para o checkout...","success");
    if(tg&&tg.HapticFeedback)try{tg.HapticFeedback.notificationOccurred("success");}catch(e){}
    if(data.checkout_url)setTimeout(()=>{window.location.href=data.checkout_url;},700);
  }catch(err){
    setStatus("Erro ao iniciar sua compra: "+(err.message||"desconhecido"),"error");
    if(tg&&tg.HapticFeedback)try{tg.HapticFeedback.notificationOccurred("error");}catch(e){}
  }finally{hideLoading();}
}

document.querySelectorAll(".buy-btn").forEach(btn=>{
  btn.addEventListener("click",()=>{
    if(tg&&tg.HapticFeedback)try{tg.HapticFeedback.impactOccurred("light");}catch(e){}
    createIntent(btn.dataset.plan||"");
  });
});
</script>"""

    return HTMLResponse(_page("BaltigoFlix — Source Baltigo", body, bflix_css, js))


# =============================================================================
# COMPAT — /api/pedido (endpoint legado, redireciona para o sistema correto)
# =============================================================================
@app.post("/api/pedido")
async def api_pedido_legacy(payload: dict = Body(...)):
    """Endpoint legado — mantido para compatibilidade retroativa."""
    uid = int(payload.get("uid") or 0)
    nome = str(payload.get("nome") or payload.get("title") or "").strip()
    tipo = str(payload.get("tipo") or "anime").strip().lower()
    if uid <= 0 or not nome:
        return {"ok": False, "msg": "Dados inválidos."}
    # Delega para o sistema de pedidos via canal
    if CANAL_PEDIDOS and BOT_TOKEN:
        texto = f"📥 NOVO PEDIDO (LEGADO)\n\nUsuário: {uid}\nTipo: {tipo}\n\nPedido:\n{nome}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": CANAL_PEDIDOS, "text": texto},
                )
        except Exception:
            pass
    return {"ok": True}
