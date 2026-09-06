Warning: truncated output (original token count: 29459)
Total output lines: 3879

import os
import json
import re
import traceback
import asyncio
import time
import threading
import httpx
import random
import hashlib
import hmac
import ipaddress
from urllib.parse import parse_qsl, quote, urlparse
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Query, Body, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

from utils.image_proxy import ImageProxyError, fetch_public_image
from utils.portrait_image import PortraitCropError, crop_portrait_bytes
from utils.public_character_image import is_own_image_proxy_url
from utils.web_image_url import web_image_url as _web_image_url
from utils.card_media_type import card_media_emoji
from utils.profile_options import COUNTRY_OPTIONS, LANGUAGE_OPTIONS
from webapp_services.profile_collection import menu_collection_characters as _menu_collection_characters
from webapp_services.terms import TERMS_VERSION
from utils.webapp_identity import (
    build_fallback_webapp_user as _build_fallback_webapp_user,
    coerce_positive_uid as _coerce_positive_uid,
    get_tg_user as _get_tg_user,
    resolve_webapp_user as _resolve_webapp_user,
    verify_telegram_init_data,
)

from premium_webapp_ui import (
    build_baltigoflix_page as build_baltigoflix_page_html,
    build_cards_anime_page as build_cards_anime_page_html,
    build_cards_contrib_image_page as build_cards_contrib_image_page_html,
    build_cards_contrib_page as build_cards_contrib_page_html,
    build_cards_contrib_rules_page as build_cards_contrib_rules_page_html,
    build_cards_contrib_work_page as build_cards_contrib_work_page_html,
    build_cards_home_page as build_cards_home_page_html,
    build_cards_search_page as build_cards_search_page_html,
    build_cards_subcategory_page as build_cards_subcategory_page_html,
    build_dado_page as build_dado_page_html,
    build_home_page as build_home_page_html,
    build_media_catalog_page as build_media_catalog_page_html,
    build_request_center_page as build_request_center_page_html,
    build_shop_page as build_shop_page_html,
)

from database import (
    create_or_get_user,
    get_dado_state,
    get_next_dado_recharge_info,
    expire_stale_dice_rolls,
    get_active_dice_roll,
    create_dice_roll,
    pick_dice_roll_anime,
    resolve_dice_roll,
)

from database import (
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
)

app = FastAPI()

# =========================
# CONFIG — TERMOS
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourceBaltigo").strip()
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/SourceBaltigo").strip()

TOP_BANNER_URL = os.getenv(
    "TOP_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzS3wWmpl9pZVvh8mUyitl-u56VSkUmPAALrC2sb1ZFIRYO5j8ewhrZJAQADAgADeQADOgQ/photo.jpg",
).strip()

BACKGROUND_URL = os.getenv("BACKGROUND_URL", "").strip()  # URL pública (pode ficar vazio)
EMPTY_BG_DATA_URI = "data:image/gif;base64,R0lGODlhAQABAAAAACw="



INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "").strip()
_WEBAPP_RATE_LOCK = threading.Lock()
_WEBAPP_RATE: Dict[Tuple[int, str], float] = {}
_WEBAPP_RATE_PRUNE_THRESHOLD = 4096


def _require_internal_api_secret(provided: str) -> None:
    if not INTERNAL_API_SECRET:
        raise HTTPException(status_code=503, detail="internal_api_secret_not_configured")
    value = str(provided or "").strip()
    if not value or not hmac.compare_digest(value, INTERNAL_API_SECRET):
        raise HTTPException(status_code=401, detail="unauthorized")


def _webapp_rate_limit(user_id: int, key: str, window_seconds: float) -> bool:
    now = time.monotonic()
    reset_at = now + max(0.05, float(window_seconds))
    rate_key = (int(user_id), str(key))

    with _WEBAPP_RATE_LOCK:
        current_reset = float(_WEBAPP_RATE.get(rate_key, 0.0) or 0.0)
        if now < current_reset:
            return False
        _WEBAPP_RATE[rate_key] = reset_at

        if len(_WEBAPP_RATE) >= _WEBAPP_RATE_PRUNE_THRESHOLD:
            expired = [item for item, expiry in _WEBAPP_RATE.items() if expiry <= now]
            for item in expired:
                _WEBAPP_RATE.pop(item, None)

    return True


def _is_blocked_image_host(hostname: str) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host:
        return True

    if host in {"localhost"} or host.endswith(".local"):
        return True

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def _guess_image_media_type(url: str) -> str:
    path = (urlparse(url).path or "").lower()
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    if path.endswith(".gif"):
        return "image/gif"
    if path.endswith(".avif"):
        return "image/avif"
    return "image/jpeg"











@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(
        build_home_page_html(
            top_banner_url=TOP_BANNER_URL,
            catalog_banner_url=CATALOG_BANNER_URL,
            manga_banner_url=MANGA_CATALOG_BANNER_URL,
            cards_banner_url=CARDS_TOP_BANNER_URL,
            shop_banner_url=SHOP_PREVIEW_IMAGE,
        )
    )









# =========================
# CONFIG — CATÁLOGO
# =========================
CATALOG_PATH = os.getenv("CATALOG_PATH", "data/catalogo_enriquecido.json").strip()

CATALOG_BANNER_URL = os.getenv(
    "CATALOG_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzeISGmpyjb2CsPEQUv3zfVD-aj7780SAAKzC2sb6qtQRVbTTJ4IyPVIAQADAgADeQADOgQ/photo.jpg",
).strip()

BACKGROUND_PATTERN_URL = os.getenv("BACKGROUND_PATTERN_URL", "").strip()
CATALOG_TITLE = os.getenv("CATALOG_TITLE", "CATÁLOGO GERAL").strip()
CATALOG_SUBTITLE = os.getenv("CATALOG_SUBTITLE", "TOTAL NA SEÇÃO").strip()

_CATALOG: List[Dict[str, Any]] = []
_LETTER_COUNTS: Dict[str, int] = {}
_TOTAL: int = 0


def _normalize_title(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _first_letter(title: str) -> str:
    if not title:
        return "#"
    ch = title.strip()[0].upper()
    if "A" <= ch <= "Z":
        return ch
    if ch.isdigit():
        return "#"
    return "#"


def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        if isinstance(v, bool):
            return None
        return int(v)
    except Exception:
        return None


def _unwrap_records(data: Any) -> List[Dict[str, Any]]:
    """
    Aceita:
      - list[dict]
      - {"records": list[dict], ...}
      - {"items": list[dict], ...}
      - {"data": list[dict], ...}
    """
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]

    if isinstance(data, dict):
        for key in ("records", "items", "data", "animes", "catalogo", "results"):
            v = data.get(key)
            if isinstance(v, list):
                return [d for d in v if isinstance(d, dict)]
        for v in data.values():
            if isinstance(v, list):
                return [d for d in v if isinstance(d, dict)]

    return []


def _coerce_item(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title_raw = _normalize_title(str(it.get("title_raw") or it.get("titulo") or it.get("title") or ""))
    post_url = str(it.get("post_url") or it.get("link_post") or it.get("link") or "").strip()

    if not title_raw:
        raw_text = str(it.get("raw_text") or "").strip()
        if raw_text:
            title_raw = _normalize_title(raw_text.splitlines()[0])

    if not title_raw or not post_url:
        return None

    anilist = it.get("anilist")
    if not isinstance(anilist, dict):
        anilist = None

    title_display = title_raw
    cover = ""
    fmt = ""
    score = None
    year = None

    if anilist:
        if anilist.get("title_display"):
            title_display = str(anilist.get("title_display")).strip() or title_display
        cover = str(anilist.get("cover") or "").strip()
        fmt = str(anilist.get("format") or "").strip()
        score = anilist.get("averageScore")
        year = anilist.get("seasonYear")

    if year is None:
        year = it.get("year_post")

    badge = fmt.upper() if fmt else "ANIME"

    status_post = str(it.get("status_post") or "").strip()
    if status_post.lower() == "restrito":
        return None

    return {
        "message_id": _safe_int(it.get("message_id")),
        "titulo": _normalize_title(title_display),
        "letter": _first_letter(title_display),
        "link_post": post_url,
        "cover_url": cover,
        "format": fmt,
        "badge": badge,
        "score": score,
        "year": year,
    }


def _load_catalog() -> Tuple[int, str]:
    global _CATALOG, _LETTER_COUNTS, _TOTAL

    _CATALOG = []
    _LETTER_COUNTS = {}
    _TOTAL = 0

    path = CATALOG_PATH
    if not path:
        print("[catalog] CATALOG_PATH vazio. Catálogo ficará vazio.", flush=True)
        return 0, "CATALOG_PATH vazio"

    candidates = [path]
    if not os.path.isabs(path):
        candidates.append(os.path.join(os.getcwd(), path))
        candidates.append(os.path.join("/app", path))

    real_path = None
    for c in candidates:
        if os.path.exists(c):
            real_path = c
            break

    if not real_path:
        print(f"[catalog] Arquivo não encontrado: {path} (testados: {candidates})", flush=True)
        return 0, "arquivo não encontrado"

    try:
        with open(real_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = _unwrap_records(data)
        if not records:
            print(f"[catalog] Nenhum registro encontrado. Tipo JSON: {type(data).__name__}", flush=True)
            return 0, "sem registros"

        items: List[Dict[str, Any]] = []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            coerced = _coerce_item(rec)
            if coerced:
                items.append(coerced)

        items.sort(key=lambda x: x["titulo"].lower())

        counts: Dict[str, int] = {}
        for x in items:
            counts[x["letter"]] = counts.get(x["letter"], 0) + 1

        _CATALOG = items
        _LETTER_COUNTS = counts
        _TOTAL = len(items)

        print(f"[catalog] Carregado OK: {_TOTAL} itens (de {real_path})", flush=True)
        return _TOTAL, "ok"

    except Exception as e:
        print(f"[catalog] Falha ao carregar catálogo ({real_path}): {repr(e)}", flush=True)
        traceback.print_exc()
        return 0, f"erro: {type(e).__name__}"


def _filter_catalog(q: str, letter: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    q = (q or "").strip().lower()
    letter = (letter or "").strip().upper()

    data = _CATALOG

    if letter and letter != "ALL":
        data = [x for x in data if x["letter"] == letter]

    if q:
        data = [x for x in data if q in x["titulo"].lower()]

    total = len(data)

    if offset < 0:
        offset = 0
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    return data[offset : offset + limit], total


# carrega no boot (sem crash)
try:
    _load_catalog()
except Exception as e:
    print("[catalog] ERRO inesperado no startup:", repr(e), flush=True)


@app.get("/api/letters")
def api_letters():
    letters = ["ALL", "#"] + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    payload = {
        "total": _TOTAL,
        "counts": {k: _LETTER_COUNTS.get(k, 0) for k in letters if k not in ("ALL")},
        "all_count": _TOTAL,
    }
    return JSONResponse(payload)


@app.get("/api/catalogo")
def api_catalogo(
    q: str = Query(default="", max_length=80),
    letter: str = Query(default="ALL", max_length=3),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = _filter_catalog(q=q, letter=letter, limit=limit, offset=offset)
    return JSONResponse({"total": total, "items": items})


@app.get("/catalogo", response_class=HTMLResponse)
def catalogo_page():
    return HTMLResponse(
        build_media_catalog_page_html(
            page_title=f"{CATALOG_TITLE} - Source Baltigo",
            hero_tag="Anime catalog",
            hero_title=CATALOG_TITLE,
            hero_copy="Biblioteca com visual mais premium, hierarquia melhor e navegacao mais gostosa para mobile.",
            banner_url=CATALOG_BANNER_URL,
            api_letters="/api/letters",
            api_catalog="/api/catalogo",
            search_placeholder="Buscar anime...",
            footer_label="Source Baltigo . Catalogo",
            default_badge="Anime",
        )
    )

    # IMPORTANTE: aqui NÃO usa f-string com ${} do JS.
    # A gente usa placeholders e replace, pra nunca mais quebrar.


# =========================
# CONFIG — CATÁLOGO (MANGÁS)
# =========================

MANGA_CATALOG_PATH = os.getenv("MANGA_CATALOG_PATH", "data/catalogo_mangas_enriquecido.json").strip()

MANGA_CATALOG_BANNER_URL = os.getenv(
    "MANGA_CATALOG_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzguBWmp1rAsEzc6la-5rpAwuyD7vdm0AAL8C2sb1ZFIRYepX3uNQGYyAQADAgADeQADOgQ/photo.jpg",
).strip()

MANGA_BACKGROUND_PATTERN_URL = os.getenv("MANGA_BACKGROUND_PATTERN_URL", "").strip()
MANGA_CATALOG_TITLE = os.getenv("MANGA_CATALOG_TITLE", "CATÁLOGO MANGÁS").strip()
MANGA_CATALOG_SUBTITLE = os.getenv("MANGA_CATALOG_SUBTITLE", "TOTAL NA SEÇÃO").strip()

_MANGA_CATALOG: List[Dict[str, Any]] = []
_MANGA_LETTER_COUNTS: Dict[str, int] = {}
_MANGA_TOTAL: int = 0


def _detect_manga_badge(it: Dict[str, Any], anilist: Optional[Dict[str, Any]]) -> str:
    """
    Decide o badge do card:
    - se vier format do AniList (MANGA/NOVEL/ONE_SHOT etc), usa isso
    - tenta detectar pelo raw_text: "Formato: Manhwa/Manhua/Mangá"
    - fallback: MANGA
    """
    if anilist and isinstance(anilist, dict):
        fmt = str(anilist.get("format") or "").strip()
        if fmt:
            # aniList costuma ser MANGA / NOVEL / ONE_SHOT
            if fmt.upper() == "MANGA":
                return "MANGA"
            if fmt.upper() == "NOVEL":
                return "NOVEL"
            if fmt.upper() == "ONE_SHOT":
                return "ONE-SHOT"
            return fmt.upper()

    raw = str(it.get("raw_text") or "").lower()

    # procura por "formato:"
    if "formato" in raw:
        # heurística simples
        if "manhwa" in raw:
            return "MANHWA"
        if "manhua" in raw:
            return "MANHUA"
        if "mangá" in raw or "manga" in raw:
            return "MANGA"

    # fallback
    return "MANGA"


def _coerce_manga_item(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title_raw = _normalize_title(str(it.get("title_raw") or it.get("titulo") or it.get("title") or ""))
    post_url = str(it.get("post_url") or it.get("link_post") or it.get("link") or "").strip()

    if not title_raw:
        raw_text = str(it.get("raw_text") or "").strip()
        if raw_text:
            title_raw = _normalize_title(raw_text.splitlines()[0])

    if not title_raw or not post_url:
        return None

    anilist = it.get("anilist")
    if not isinstance(anilist, dict):
        anilist = None

    title_display = title_raw
    cover = ""
    fmt = ""
    score = None
    year = None

    if anilist:
        if anilist.get("title_display"):
            title_display = str(anilist.get("title_display")).strip() or title_display
        cover = str(anilist.get("cover") or "").strip()
        fmt = str(anilist.get("format") or "").strip()
        score = anilist.get("averageScore")
        year = anilist.get("seasonYear")

    if year is None:
        year = it.get("year_post")

    badge = _detect_manga_badge(it, anilist)

    status_post = str(it.get("status_post") or "").strip()
    if status_post.lower() == "restrito":
        return None

    return {
        "message_id": _safe_int(it.get("message_id")),
        "titulo": _normalize_title(title_display),
        "letter": _first_letter(title_display),
        "link_post": post_url,         # abre o post do canal
        "cover_url": cover,
        "format": fmt,
        "badge": badge,
        "score": score,
        "year": year,
    }


def _load_manga_catalog() -> Tuple[int, str]:
    global _MANGA_CATALOG, _MANGA_LETTER_COUNTS, _MANGA_TOTAL

    _MANGA_CATALOG = []
    _MANGA_LETTER_COUNTS = {}
    _MANGA_TOTAL = 0

    path = MANGA_CATALOG_PATH
    if not path:
        print("[mangas] MANGA_CATALOG_PATH vazio. Catálogo ficará vazio.", flush=True)
        return 0, "MANGA_CATALOG_PATH vazio"

    candidates = [path]
    if not os.path.isabs(path):
        candidates.append(os.path.join(os.getcwd(), path))
        candidates.append(os.path.join("/app", path))

    real_path = None
    for c in candidates:
        if os.path.exists(c):
            real_path = c
            break

    if not real_path:
        print(f"[mangas] Arquivo não encontrado: {path} (testados: {candidates})", flush=True)
        return 0, "arquivo não encontrado"

    try:
        with open(real_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = _unwrap_records(data)
        if not records:
            print(f"[mangas] Nenhum registro encontrado. Tipo JSON: {type(data).__name__}", flush=True)
            return 0, "sem registros"

        items: List[Dict[str, Any]] = []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            coerced = _coerce_manga_item(rec)
            if coerced:
                items.append(coerced)

        items.sort(key=lambda x: x["titulo"].lower())

        counts: Dict[str, int] = {}
        for x in items:
            counts[x["letter"]] = counts.get(x["letter"], 0) + 1

        _MANGA_CATALOG = items
        _MANGA_LETTER_COUNTS = counts
        _MANGA_TOTAL = len(items)

        print(f"[mangas] Carregado OK: {_MANGA_TOTAL} itens (de {real_path})", flush=True)
        return _MANGA_TOTAL, "ok"

    except Exception as e:
        print(f"[mangas] Falha ao carregar catálogo ({real_path}): {repr(e)}", flush=True)
        traceback.print_exc()
        return 0, f"erro: {type(e).__name__}"


def _filter_manga_catalog(q: str, letter: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    q = (q or "").strip().lower()
    letter = (letter or "").strip().upper()

    data = _MANGA_CATALOG

    if letter and letter != "ALL":
        data = [x for x in data if x["letter"] == letter]

    if q:
        data = [x for x in data if q in x["titulo"].lower()]

    total = len(data)

    if offset < 0:
        offset = 0
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    return data[offset : offset + limit], total


# carrega no boot (sem crash)
try:
    _load_manga_catalog()
except Exception as e:
    print("[mangas] ERRO inesperado no startup:", repr(e), flush=True)


@app.get("/api/mangas/letters")
def api_mangas_letters():
    letters = ["ALL", "#"] + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    payload = {
        "total": _MANGA_TOTAL,
        "counts": {k: _MANGA_LETTER_COUNTS.get(k, 0) for k in letters if k not in ("ALL")},
        "all_count": _MANGA_TOTAL,
    }
    return JSONResponse(payload)


@app.get("/api/mangas/catalogo")
def api_mangas_catalogo(
    q: str = Query(default="", max_length=80),
    letter: str = Query(default="ALL", max_length=3),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = _filter_manga_catalog(q=q, letter=letter, limit=limit, offset=offset)
    return JSONResponse({"total": total, "items": items})


@app.get("/mangas", response_class=HTMLResponse)
def mangas_page():
    return HTMLResponse(
        build_media_catalog_page_html(
            page_title=f"{MANGA_CATALOG_TITLE} - Source Baltigo",
            hero_tag="Manga catalog",
            hero_title=MANGA_CATALOG_TITLE,
            hero_copy="Uma vitrine mais cinematografica para explorar mangas com foco em legibilidade, contraste e ritmo visual.",
            banner_url=MANGA_CATALOG_BANNER_URL,
            api_letters="/api/mangas/letters",
            api_catalog="/api/mangas/catalogo",
            search_placeholder="Buscar manga...",
            footer_label="Source Baltigo . Mangas",
            default_badge="Manga",
        )
    )


# =========================================================
# CARDS SYSTEM — JSON ASSETS
# Lê: data/cards_assets.json
# =========================================================

import json
import os
from typing import Any, Dict, List
from fastapi import Query
from fastapi.responses import HTMLResponse, JSONResponse
from cards_service import build_cards_final_data, reload_cards_cache

CARDS_ASSETS_PATH = os.getenv("CARDS_ASSETS_PATH", "data/personagens_anilist.txt").strip()
CARDS_TOP_BANNER_URL = os.getenv(
    "CARDS_TOP_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZ0sajmmrHXRy1AZxkfEGC2Lx4yC6A80MAAJOC2sb1ZFYRQ5kxLI09cC2AQADAgADeQADOgQ/photo.jpg",
).strip()

_CARDS_DATA: List[Dict[str, Any]] = []
_CARDS_INDEX: Dict[int, Dict[str, Any]] = {}
_CARDS_TOTAL: int = 0


def _load_cards_assets() -> int:
    global _CARDS_DATA, _CARDS_INDEX, _CARDS_TOTAL

    _CARDS_DATA = []
    _CARDS_INDEX = {}
    _CARDS_TOTAL = 0

    path = CARDS_ASSETS_PATH
    candidates = [path]

    if not os.path.isabs(path):
        candidates.append(os.path.join(os.getcwd(), path))
        candidates.append(os.path.join("/app", path))

    real_path = None
    for c in candidates:
        if os.path.exists(c):
            real_path = c
            break

    if not real_path:
        print(f"[cards] Arquivo não encontrado: {path} | testados: {candidates}", flush=True)
        return 0

    try:
        with open(real_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        items = raw.get("items") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            print(f"[cards] Formato inválido em {real_path}", flush=True)
            return 0

        cleaned: List[Dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            anime_id = item.get("anime_id")
            anime = str(item.get("anime") or "").strip()
            banner_image = str(item.get("banner_image") or "").strip()
            cover_image = str(item.get("cover_image") or "").strip()
            chars_raw = item.get("characters") or []

            try:
                anime_id = int(anime_id)
            except Exception:
                continue

            if not anime:
                continue

            chars: List[Dict[str, Any]] = []
            seen_char_ids = set()

            if isinstance(chars_raw, list):
                for c in chars_raw:
                    if not isinstance(c, dict):
                        continue

                    cid = c.get("id")
                    cname = str(c.get("name") or "").strip()
                    canime = str(c.get("anime") or anime).strip()
                    cimg = str(c.get("image") or "").strip()

                    try:
                        cid = int(cid)
                    except Exception:
                        continue

                    if not cname or cid in seen_char_ids:
                        continue

                    seen_char_ids.add(cid)

                    chars.append({
                        "id": cid,
                        "name": cname,
                        "anime": canime or anime,
                        "image": cimg,
                    })

            chars.sort(key=lambda x: x["name"].lower())

            payload = {
                "anime_id": anime_id,
                "anime": anime,
                "banner_image": banner_image,
                "cover_image": cover_image,
                "characters": chars,
                "characters_count": len(chars),
            }

            cleaned.append(payload)
            _CARDS_INDEX[anime_id] = payload

        cleaned.sort(key=lambda x: x["anime"].lower())

        _CARDS_DATA = cleaned
        _CARDS_TOTAL = len(cleaned)

        print(f"[cards] Assets carregados: {_CARDS_TOTAL} obras", flush=True)
        return _CARDS_TOTAL

    except Exception as e:
        print(f"[cards] Erro ao carregar assets: {repr(e)}", flush=True)
        return 0


def _ensure_cards_loaded():
    if not _CARDS_DATA:
        _load_cards_assets()


# carrega no boot sem derrubar app
try:
    _load_cards_assets()
except Exception as e:
    print(f"[cards] erro inesperado no startup: {repr(e)}", flush=True)


def _cards_api_reload():
    return _cards_api_reload()

    # Mantem as rotas antigas, mas usa a mesma fonte central
    # do /card e dos comandos admin para refletir setfoto/overrides.


def _cards_api_animes(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    return _cards_api_animes(q=q, limit=limit, offset=offset)



def _cards_api_characters(
    anime_id: int = Query(...),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    return _cards_api_characters(
        anime_id=anime_id,
        q=q,
        limit=limit,
        offset=offset,
    )



def _cards_home_page():
    return _cards_home_page()



@app.get("/cards/anime", response_class=HTMLResponse)
def cards_anime_page(anime_id: int = Query(...)):
    return _cards_anime_page(anime_id=anime_id)




# =========================
# SISTEMA DE PEDIDOS (WEBAPP)
# =========================
import time

MAX_PEDIDOS = 3
WINDOW_PEDIDOS = 24 * 60 * 60
_PEDIDOS_CACHE = {}

def _pode_pedir(uid:int):
    now = int(time.time())
    lst = _PEDIDOS_CACHE.get(uid, [])
    lst = [t for t in lst if now - t < WINDOW_PEDIDOS]
    _PEDIDOS_CACHE[uid] = lst
    return len(lst) < MAX_PEDIDOS

def _registrar_pedido(uid:int):
    _PEDIDOS_CACHE.setdefault(uid, []).append(int(time.time()))

@app.post("/api/pedido")
async def api_pedido(payload: dict = Body(default={})):
    del payload
    return JSONResponse(
        {
            "ok": False,
            "msg": "Endpoint antigo desativado. Use /api/pedido/send.",
            "error": "endpoint_deprecated",
        },
        status_code=410,
    )


# =========================================================
# CARDS SYSTEM — WEBAPP FINAL
# Base: data/personagens_anilist.txt
# Overrides: data/cards_overrides.json
# =========================================================

from fastapi import Query
from fastapi.responses import HTMLResponse, JSONResponse

from cards_service import (
    build_cards_final_data,
    find_anime,
    list_subcategories,
    reload_cards_cache,
    search_characters,
)

CARDS_TOP_BANNER_URL = "https://photo.chelpbot.me/AgACAgEAAxkBZ0sajmmrHXRy1AZxkfEGC2Lx4yC6A80MAAJOC2sb1ZFYRQ5kxLI09cC2AQADAgADeQADOgQ/photo.jpg"


@app.get("/api/cards/reload")
def api_cards_reload(
    x_internal_api_secret: str = Header(default=""),
):
    _require_internal_api_secret(x_internal_api_secret)
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
    items = list(data["animes_list"])

    qn = q.strip().lower()
    if qn:
        items = [x for x in items if qn in x["anime"].lower()]

    total = len(items)
    payload_items = []
    for item in items[offset: offset + limit]:
        payload = dict(item)
        payload["banner_image"] = _web_image_url(item.get("banner_image"))
        payload["cover_image"] = _web_image_url(item.get("cover_image"))
        payload_items.append(payload)

    return JSONResponse({
        "ok": True,
        "total": total,
        "items": payload_items,
    })


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
        return JSONResponse({
            "ok": False,
            "anime": None,
            "total": 0,
            "items": [],
        })

    chars = list(data["characters_by_anime"].get(anime_id, []))

    qn = q.strip().lower()
    if qn:
        chars = [x for x in chars if qn in x["name"].lower()]

    total = len(chars)
    items = []
    for item in chars[offset: offset + limit]:
        payload = dict(item)
        payload["image"] = _web_image_url(item.get("image"))
        items.append(payload)

    anime_payload = dict(anime)
    anime_payload["banner_image"] = _web_image_url(anime.get("banner_image"))
    anime_payload["cover_image"] = _web_image_url(anime.get("cover_image"))

    return JSONResponse({
        "ok": True,
        "anime": anime_payload,
        "total": total,
        "items": items,
    })


@app.get("/api/cards/search")
def api_cards_search(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
):
    items = []
    for item in search_characters(q, limit=limit):
        payload = dict(item)
        payload["image"] = _web_image_url(item.get("image"))
        items.append(payload)
    return JSONResponse({
        "ok": True,
        "total": len(items),
        "items": items,
    })


@app.get("/api/cards/find-anime")
def api_cards_find_anime(q: str = Query(..., min_length=1, max_length=120)):
    anime = find_anime(q)
    return JSONResponse({
        "ok": bool(anime),
        "anime": anime,
    })


@app.get("/api/cards/subcategories")
def api_cards_subcategories():
    return JSONResponse({
        "ok": True,
        "items": list_subcategories(),
    })


@app.get("/api/cards/subcategory")
def api_cards_subcategory(
    name: str = Query(..., min_length=1, max_length=120),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    data = build_cards_final_data()
    chars = list(data["subcategories"].get(name, []))

    qn = q.strip().lower()
    if qn:
        chars = [x for x in chars if qn in x["name"].lower()]

    total = len(chars)
    items = []
    for item in chars[offset: offset + limit]:
        payload = dict(item)
        payload["image"] = _web_image_url(item.get("image"))
        items.append(payload)

    return JSONResponse({
        "ok": True,
        "subcategory": name,
        "total": total,
        "items": items,
    })


@app.get("/cards", response_class=HTMLResponse)
def cards_page():
    return HTMLResponse(build_cards_home_page_html(top_banner_url=CARDS_TOP_BANNER_URL))












def _cards_anime_page(anime_id: int):
    return HTMLResponse(
        build_cards_anime_page_html(
            anime_id=anime_id,
            top_banner_url=CARDS_TOP_BANNER_URL,
        )
    )



@app.get("/cards/subcategory", response_class=HTMLResponse)
def cards_subcategory_page(name: str = Query(...)):
    return HTMLResponse(
        build_cards_subcategory_page_html(
            name=str(name),
            top_banner_url=CARDS_TOP_BANNER_URL,
        )
    )



@app.get("/cards/search", response_class=HTMLResponse)
def cards_search_page(q: str = Query(...)):
    return HTMLResponse(
        build_cards_search_page_html(
            query=str(q),
            top_banner_url=CARDS_TOP_BANNER_URL,
        )
    )


# =========================
# CONFIG — PEDIDOS / REPORTS
# =========================
import html
import traceback
import httpx

from fastapi import Body, Query
from fastapi.responses import HTMLResponse, JSONResponse

from database import (
    create_media_request_tables,
    count_user_media_requests_last_24h,
    media_request_exists,
    save_media_request,
    save_webapp_report,
    normalize_media_title,
)

CANAL_PEDIDOS = os.getenv("CANAL_PEDIDOS", "").strip()
PEDIDO_BANNER_URL = os.getenv(
    "PEDIDO_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZ0w54WmrME4Fk9ObOXCy_CjgTb8IHF9cAAJRC2sb1ZFYRTRdgJDi4ysfAQADAgADeQADOgQ/photo.jpg",
).strip()

create_media_request_tables()

_PEDIDO_ANIME_INDEX = {"title_norm": set(), "anilist_ids": set()}
_PEDIDO_MANGA_INDEX = {"title_norm": set(), "anilist_ids": set()}


def _pedido_build_index(records: List[Dict[str, Any]]):
    idx = {"title_norm": set(), "anilist_ids": set()}

    for rec in records:
        try:
            if not isinstance(rec, dict):
                continue

            title = str(
                rec.get("title_raw")
                or rec.get("titulo")
                or rec.get("title")
                or ""
            ).strip()

            anilist_id = None
            anilist = rec.get("anilist")
            if isinstance(anilist, dict):
                title = str(anilist.get("title_display") or title).strip()
                anilist_id = anilist.get("anilist_id") or anilist.get("id")

            if title:
                idx["title_norm"].add(normalize_media_title(title))

            if anilist_id:
                try:
                    idx["anilist_ids"].add(int(anilist_id))
                except Exception:
                    pass

        except Exception:
            continue

    return idx


def _pedido_load_json(path: str):
    raw_path = str(path or "").strip()
    if not raw_path:
        raise FileNotFoundError("empty path")

    candidates = [raw_path]
    if not os.path.isabs(raw_path):
        candidates.extend([
            os.path.join(os.getcwd(), raw_path),
            os.path.join("/app", raw_path),
        ])

    seen = set()
    for candidate in candidates:
        candidate = os.path.normpath(candidate)
        if candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as handle:
                return json.load(handle)

    raise FileNotFoundError(raw_path)


def _pedido_reload_indexes():
    global _PEDIDO_ANIME_INDEX, _PEDIDO_MANGA_INDEX

    try:
        anime_records = _unwrap_records(_pedido_load_json(CATALOG_PATH))
    except Exception:
        anime_records = []

    try:
        manga_records = _unwrap_records(_pedido_load_json(MANGA_CATALOG_PATH))
    except Exception:
        manga_records = []

    _PEDIDO_ANIME_INDEX = _pedido_build_index(anime_records)
    _PEDIDO_MANGA_INDEX = _pedido_build_index(manga_records)


try:
    _pedido_reload_indexes()
except Exception as e:
    print("[pedido] falha ao montar índices:", repr(e), flush=True)


def _pedido_catalog_contains(media_type: str, title: str, anilist_id=None) -> bool:
    media_type = (media_type or "").strip().lower()
    idx = _PEDIDO_ANIME_INDEX if media_type == "anime" else _PEDIDO_MANGA_INDEX

    if anilist_id:
        try:
            if int(anilist_id) in idx["anilist_ids"]:
                return True
        except Exception:
            pass

    return normalize_media_title(title) in idx["title_norm"]


async def _pedido_anilist_search(query_text: str, media_type: str):
    gql = """
    query ($search: String, $type: MediaType) {
      Page(page: 1, perPage: 12) {
        media(search: $search, type: $type, sort: POPULARITY_DESC) {
          id
          title { romaji english native }
          coverImage { large }
          averageScore
          format
          status
          seasonYear
          episodes
          chapters
        }
      }
    }
    """

    variables = {
        "search": query_text,
        "type": "ANIME" if media_type == "anime" else "MANGA",
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "SourceBaltigo/1.0",
    }

    last_error = None

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://graphql.anilist.co",
                    headers=headers,
                    json={"query": gql, "variables": variables},
                )

            if response.status_code >= 400:
                print(
                    f"[pedido] AniList HTTP {response.status_code} attempt={attempt + 1}",
                    flush=True,
                )
                last_error = RuntimeError(f"AniList HTTP {response.status_code}")
                continue

            data = response.json()
            if not isinstance(data, dict):
                last_error = RuntimeError("Resposta inválida do AniList")
                continue

            if data.get("errors"):
                print("[pedido] AniList errors:", data.get("errors"), flush=True)
                last_error = RuntimeError("AniList retornou erro")
                continue

            return ((data.get("data") or {}).get("Page") or {}).get("media", []) or []

        except Exception as e:
            last_error = e
            print("[pedido] erro AniList:", repr(e), flush=True)

    raise last_error or RuntimeError("Falha ao buscar no AniList")


@app.get("/api/pedido/limit")
def api_pedido_limit(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    user_id = int(ctx["user_id"])
    touch_user_identity(
        user_id,
        username=str(ctx.get("username") or "").strip(),
        full_name=str(ctx.get("full_name") or "").strip(),
    )

    used = count_user_media_requests_last_24h(user_id)
    remaining = max(0, 3 - used)
    return JSONResponse({
        "ok": True,
        "user_id": user_id,
        "used": used,
        "remaining": remaining,
        "limit": 3
    })


@app.get("/api/pedido/search")
async def api_pedido_search(
    q: str = Query(..., min_length=2, max_length=80),
    media_type: str = Query(..., max_length=10),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    user_id = int(ctx["user_id"])
    if not _webapp_rate_limit(user_id, "pedido-search", 0.35):
        return JSONResponse(
            {"ok": False, "message": "Aguarde um instante antes de buscar novamente."},
            status_code=429,
        )

    media_type = (media_type or "").strip().lower()
    if media_type not in ("anime", "manga"):
        return JSONResponse({"ok": False, "message": "media_type inválido"}, status_code=400)

    try:
        results = await _pedido_anilist_search(q.strip(), media_type)
        items = []

        for item in results:
            title = (
         …9459 tokens truncated…urchased.get("price_paid") or 0),
        "card": {
            "id": int(card.get("id") or 0),
            "character_id": int(card.get("character_id") or 0),
            "card_no": str(card.get("card_no") or "").strip(),
            "base_card_no": str(card.get("base_card_no") or "").strip(),
            "name": str(card.get("name") or "").strip() or "XCard",
            "anime": str(pt_br.get("anime") or card.get("title") or "").strip(),
            "title": str(card.get("title") or "").strip(),
            "product_name": str(pt_br.get("produto") or card.get("product_name") or "").strip(),
            "image": _web_image_url(card.get("image")),
            "rarity": rarity,
            "rarity_label": str(pt_br.get("raridade") or rarity).strip(),
            "alt_art": is_alt_art,
            "required_energy": str(pt_br.get("energia_necessaria") or card.get("required_energy") or "").strip(),
            "ap_cost": str(pt_br.get("custo_ap") or card.get("ap_cost") or "").strip(),
            "card_type": str(pt_br.get("tipo_de_cartao") or card.get("card_type") or "").strip(),
            "bp": str(pt_br.get("pa") or card.get("bp") or "").strip(),
            "bp_value": bp_value,
            "affinity": str(pt_br.get("afinidade") or card.get("affinity") or "").strip(),
            "affinities": affinities,
            "generated_energy": generated_energy,
            "effect": str(pt_br.get("efeito") or card.get("effect") or "").strip(),
            "effect_keywords": effect_keywords,
            "trigger": str(pt_br.get("acionar") or card.get("trigger") or "").strip(),
            "trigger_keywords": trigger_keywords,
            "cosmetic_only": is_alt_art,
        },
    }














def _shop_css() -> str:
    return r"""
:root{
  --bg0:#070b12;
  --bg1:#0a1220;
  --txt:rgba(255,255,255,.94);
  --muted:rgba(255,255,255,.58);
  --stroke:rgba(255,255,255,.10);
  --stroke2:rgba(255,255,255,.16);
  --glass:rgba(255,255,255,.04);
  --shadow:0 16px 30px rgba(0,0,0,.44);
  --ok:#4ade80;
  --danger:#ff4d6d;
}

*{ box-sizing:border-box; }
html,body{ height:100%; }

body{
  margin:0;
  color:var(--txt);
  font-family:-apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  background:
    radial-gradient(1100px 600px at 50% -10%, rgba(90,168,255,.18), transparent 55%),
    linear-gradient(180deg,var(--bg0),var(--bg1));
  overflow-x:hidden;
}

.bg{
  position:fixed; inset:0;
  background-image: radial-gradient(rgba(255,255,255,.05) 1px, transparent 1px);
  background-size:36px 36px;
  opacity:.16;
  pointer-events:none;
  z-index:0;
}

.wrap{
  position:relative;
  z-index:1;
  max-width:980px;
  margin:0 auto;
  padding:18px 14px 42px;
}

.top-banner{
  width:100%;
  border-radius:26px;
  overflow:hidden;
  border:1px solid var(--stroke);
  box-shadow:var(--shadow);
  position:relative;
  background:#000;
  min-height:220px;
}

.top-banner img{
  width:100%;
  height:220px;
  object-fit:cover;
  display:block;
}

.top-banner:after{
  content:"";
  position:absolute; inset:0;
  background:linear-gradient(180deg, rgba(0,0,0,.12), rgba(0,0,0,.72));
  pointer-events:none;
}

.top-copy{
  position:absolute;
  left:18px;
  right:18px;
  bottom:16px;
  z-index:2;
}

.eyebrow{
  display:inline-flex;
  align-items:center;
  gap:8px;
  border:1px solid rgba(255,255,255,.16);
  background:rgba(0,0,0,.26);
  backdrop-filter: blur(8px);
  border-radius:999px;
  padding:8px 12px;
  font-size:11px;
  font-weight:900;
  letter-spacing:.14em;
  text-transform:uppercase;
}

.title{
  margin-top:12px;
  font-size:28px;
  line-height:1.05;
  font-weight:900;
  letter-spacing:.05em;
  text-transform:uppercase;
  text-shadow:0 6px 20px rgba(0,0,0,.45);
}

.subtitle{
  margin-top:8px;
  color:rgba(255,255,255,.78);
  font-weight:700;
  letter-spacing:.10em;
  text-transform:uppercase;
  font-size:12px;
}

.head{
  padding:18px 4px 8px;
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap:12px;
  flex-wrap:wrap;
}

.stats{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
}

.stat-pill{
  border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.04);
  padding:10px 12px;
  border-radius:999px;
  font-weight:900;
  letter-spacing:.08em;
  text-transform:uppercase;
  font-size:12px;
}

.tabs{
  margin-top:12px;
  display:grid;
  grid-template-columns:repeat(2,1fr);
  gap:12px;
}

.tab{
  user-select:none;
  cursor:pointer;
  border-radius:18px;
  padding:14px 12px;
  text-align:center;
  border:1px solid var(--stroke);
  background:rgba(255,255,255,.03);
  transition:transform .08s ease, border-color .12s ease, background .12s ease;
  font-weight:900;
  letter-spacing:.10em;
  text-transform:uppercase;
  font-size:13px;
}

.tab:hover{ transform:translateY(-1px); border-color:var(--stroke2); }
.tab.active{ background:rgba(90,168,255,.18); border-color:rgba(90,168,255,.42); }

.search{
  margin-top:16px;
  display:flex;
  align-items:center;
  gap:10px;
  background:var(--glass);
  border:1px solid var(--stroke);
  border-radius:18px;
  padding:13px 14px;
  box-shadow:0 10px 18px rgba(0,0,0,.32);
}

.search input{
  width:100%;
  border:0;
  outline:none;
  background:transparent;
  color:var(--txt);
  font-size:14px;
}

.search input::placeholder{
  color:rgba(255,255,255,.38);
  font-weight:800;
  letter-spacing:.06em;
  text-transform:uppercase;
}

.cards{
  margin-top:16px;
  display:grid;
  grid-template-columns:repeat(2,1fr);
  gap:12px;
}

@media (min-width:720px){
  .top-banner img{ height:250px; }
  .cards{ grid-template-columns:repeat(3,1fr); }
  .tabs{ grid-template-columns:repeat(2,220px); justify-content:flex-start; }
}

.card{
  border-radius:24px;
  overflow:hidden;
  border:1px solid var(--stroke);
  background:rgba(255,255,255,.03);
  box-shadow:0 18px 30px rgba(0,0,0,.42);
  position:relative;
}

.cover{
  width:100%;
  height:250px;
  position:relative;
  background:linear-gradient(135deg, rgba(90,168,255,.18), rgba(255,255,255,.03));
}

.cover img{
  width:100%;
  height:100%;
  object-fit:cover;
  display:block;
}

.cover:after{
  content:"";
  position:absolute; inset:0;
  background:linear-gradient(180deg, rgba(0,0,0,.00), rgba(0,0,0,.56));
  pointer-events:none;
}

.count-pill{
  position:absolute;
  right:12px;
  bottom:12px;
  z-index:2;
  border-radius:999px;
  padding:8px 10px;
  font-size:11px;
  font-weight:900;
  letter-spacing:.12em;
  text-transform:uppercase;
  color:rgba(255,255,255,.95);
  background:rgba(0,0,0,.32);
  border:1px solid rgba(255,255,255,.18);
  backdrop-filter:blur(8px);
}

.meta{
  padding:13px 14px 15px;
}

.name{
  font-weight:900;
  letter-spacing:.04em;
  font-size:14px;
  line-height:1.2;
  text-transform:uppercase;
  margin:0;
}

.sub{
  margin-top:8px;
  color:rgba(255,255,255,.52);
  font-weight:800;
  letter-spacing:.12em;
  font-size:11px;
  text-transform:uppercase;
  display:flex;
  gap:8px;
  flex-wrap:wrap;
}

.pill{
  border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.04);
  padding:6px 10px;
  border-radius:999px;
}

.actions{
  margin-top:12px;
}

.btn{
  width:100%;
  border:1px solid transparent;
  border-radius:16px;
  padding:12px 14px;
  font-weight:900;
  letter-spacing:.10em;
  text-transform:uppercase;
  cursor:pointer;
}

.btn-danger{
  background:rgba(255,77,109,.18);
  border-color:rgba(255,77,109,.34);
  color:#fff;
}

.btn-buy{
  background:rgba(74,222,128,.18);
  border-color:rgba(74,222,128,.34);
  color:#fff;
}

.buy-grid{
  margin-top:16px;
  display:grid;
  grid-template-columns:1fr;
  gap:12px;
}

@media (min-width:720px){
  .buy-grid{ grid-template-columns:repeat(2,1fr); }
}

.buy-card{
  border-radius:22px;
  border:1px solid var(--stroke);
  background:rgba(255,255,255,.03);
  box-shadow:0 18px 30px rgba(0,0,0,.42);
  padding:16px;
}

.buy-card h3{
  margin:0;
  font-size:16px;
  font-weight:900;
  letter-spacing:.05em;
  text-transform:uppercase;
}

.buy-card p{
  margin:10px 0 14px;
  color:rgba(255,255,255,.68);
  font-size:13px;
  line-height:1.45;
}

.price{
  margin-bottom:12px;
  font-weight:900;
  letter-spacing:.10em;
  text-transform:uppercase;
  font-size:12px;
  color:rgba(255,255,255,.82);
}

.empty{
  margin-top:16px;
  border:1px solid var(--stroke);
  background:rgba(255,255,255,.03);
  border-radius:22px;
  padding:18px;
  color:rgba(255,255,255,.70);
  font-weight:700;
  text-align:center;
}

.toast{
  margin-top:14px;
  border:1px solid var(--stroke);
  background:rgba(255,255,255,.03);
  border-radius:18px;
  padding:12px 14px;
  font-size:13px;
  color:rgba(255,255,255,.84);
  font-weight:700;
}

.footer{
  margin-top:16px;
  color:rgba(255,255,255,.40);
  font-size:12px;
  font-weight:700;
  letter-spacing:.08em;
  text-align:center;
}
"""


# =========================================================
# API — SHOP
# =========================================================

@app.get("/api/shop/state")
def api_shop_state(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from database import (
        get_daily_xcard_shop_refresh_info,
        get_progress_row,
        get_user_status,
        get_user_xcard_collection,
    )

    tg = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    user_id = int(tg["user_id"])

    row = get_user_status(user_id) or {}
    progress = get_progress_row(user_id) or {}
    refresh = get_daily_xcard_shop_refresh_info()
    xcards = get_user_xcard_collection(user_id) or []
    return JSONResponse({
        "ok": True,
        "coins": int(row.get("coins") or 0),
        "dado_balance": int(row.get("dado_balance") or 0),
        "level": int(progress.get("level") or 1),
        "xcollection_total": len(xcards),
        "refresh": refresh,
    })


@app.get("/api/shop/sell/all")
def api_shop_sell_all(
    q: str = Query(default="", max_length=120),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    tg = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    user_id = int(tg["user_id"])
    items = _shop_collection_items(user_id, q=q)

    return JSONResponse({
        "ok": True,
        "items": items,
    })


@app.post("/api/shop/sell/confirm")
def api_shop_sell_confirm(
    payload: dict = Body(...),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from database import sell_character, get_user_status

    tg = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload or {}).get("uid"),
    )
    user_id = int(tg["user_id"])

    char_id = int(payload.get("character_id") or 0)
    if char_id <= 0:
        return JSONResponse({"ok": False, "error": "character_id inválido"}, status_code=400)

    if not _shop_rate_limit(user_id, f"sell:{char_id}", 0.9):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)

    result = sell_character(user_id, char_id)
    if not result or not result.get("ok"):
        return JSONResponse({
            "ok": False,
            "error": (result or {}).get("error") or "Não foi possível vender agora.",
        }, status_code=200)

    row = get_user_status(user_id) or {}
    return JSONResponse({
        "ok": True,
        "coins": int(row.get("coins") or 0),
    })










@app.post("/api/shop/buy/dado")
def api_shop_buy_dado(
    payload: dict = Body(default={}),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from database import buy_dado, get_user_status

    tg = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload or {}).get("uid"),
    )
    user_id = int(tg["user_id"])

    if not _shop_rate_limit(user_id, "buy_dado", 0.9):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)

    result = buy_dado(user_id)
    if not result or not result.get("ok"):
        return JSONResponse({
            "ok": False,
            "error": (result or {}).get("error") or "Coins insuficientes.",
        }, status_code=200)

    row = get_user_status(user_id) or {}
    return JSONResponse({
        "ok": True,
        "coins": int(row.get("coins") or 0),
        "dado_balance": int(row.get("dado_balance") or 0),
    })


@app.post("/api/shop/buy/nickname")
def api_shop_buy_nickname(
    payload: dict = Body(default={}),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from database import buy_nickname_change, get_user_status

    tg = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload or {}).get("uid"),
    )
    user_id = int(tg["user_id"])

    if not _shop_rate_limit(user_id, "buy_nick", 0.9):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)

    result = buy_nickname_change(user_id)
    if not result or not result.get("ok"):
        return JSONResponse({
            "ok": False,
            "error": (result or {}).get("error") or "Coins insuficientes.",
        }, status_code=200)

    row = get_user_status(user_id) or {}
    return JSONResponse({
        "ok": True,
        "coins": int(row.get("coins") or 0),
    })


# =========================================================
# PAGE — /shop
# =========================================================

@app.get("/api/shop/xcards/daily")
def api_shop_xcards_daily(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from database import (
        get_daily_xcard_shop_refresh_info,
        get_or_create_daily_xcard_shop_offers,
        get_progress_row,
        get_user_daily_xcard_shop_purchase_map,
        get_user_status,
        get_user_xcard_collection,
    )

    tg = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    user_id = int(tg["user_id"])

    row = get_user_status(user_id) or {}
    progress = get_progress_row(user_id) or {}
    current_level = int(progress.get("level") or 1)
    refresh = get_daily_xcard_shop_refresh_info()
    offers = get_or_create_daily_xcard_shop_offers()
    purchase_map = get_user_daily_xcard_shop_purchase_map(user_id)
    xcards = get_user_xcard_collection(user_id) or []
    serialized = [
        _shop_serialize_xcard_offer(offer, purchase_map, current_level)
        for offer in offers
    ]

    groups = {
        "normal": [item for item in serialized if item.get("slot_group") == "normal"],
        "rare": [item for item in serialized if item.get("slot_group") == "rare"],
        "special": [item for item in serialized if item.get("slot_group") == "special"],
    }

    return JSONResponse({
        "ok": True,
        "coins": int(row.get("coins") or 0),
        "level": current_level,
        "xcollection_total": len(xcards),
        "xcollection_copies": sum(int(item.get("quantity") or 0) for item in xcards),
        "refresh": refresh,
        "groups": groups,
        "offers": serialized,
    })


@app.post("/api/shop/xcards/buy")
def api_shop_xcards_buy(
    payload: dict = Body(default={}),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from database import (
        buy_daily_xcard_shop_offer,
        get_progress_row,
        get_user_status,
        get_user_xcard_collection,
    )
    from xcards_service import get_xcard_by_id

    tg = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload or {}).get("uid"),
    )
    user_id = int(tg["user_id"])

    slot_code = str((payload or {}).get("slot_code") or "").strip().lower()
    if not slot_code:
        return JSONResponse(
            {"ok": False, "error": "slot_code inv\u00e1lido", "error_code": "invalid_slot"},
            status_code=400,
        )

    if not _shop_rate_limit(user_id, f"buy_xcard:{slot_code}", 0.9):
        return JSONResponse({"ok": False, "error": "rate_limited", "error_code": "rate_limited"}, status_code=200)

    result = buy_daily_xcard_shop_offer(user_id, slot_code)
    if not result or not result.get("ok"):
        error_code = str((result or {}).get("error") or "buy_failed").strip().lower()
        current_level = int((result or {}).get("current_level") or 1)
        required_level = int((result or {}).get("required_level") or 0)
        price = int((result or {}).get("price") or 0)
        current_coins = int((result or {}).get("coins") or 0)
        error_map = {
            "invalid_slot": "Oferta inv\u00e1lida.",
            "offer_not_found": "Essa oferta n\u00e3o est\u00e1 dispon\u00edvel agora.",
            "already_bought": "Voc\u00ea j\u00e1 comprou esse slot hoje.",
            "level_locked": f"Seu n\u00edvel atual \u00e9 {current_level}. Esta compra exige n\u00edvel {required_level}.",
            "no_coins": f"Voc\u00ea precisa de {price} coins, mas tem {current_coins}.",
            "buy_failed": "N\u00e3o foi poss\u00edvel concluir a compra agora.",
        }
        return JSONResponse({
            "ok": False,
            "error": error_map.get(error_code, "N\u00e3o foi poss\u00edvel concluir a compra agora."),
            "error_code": error_code,
            "required_level": required_level,
            "current_level": current_level,
            "price": price,
            "coins": current_coins,
        }, status_code=200)

    row = get_user_status(user_id) or {}
    progress = get_progress_row(user_id) or {}
    xcards = get_user_xcard_collection(user_id) or []
    card = get_xcard_by_id(int(result.get("card_id") or 0)) or {}
    pt_br = card.get("pt_br") if isinstance(card.get("pt_br"), dict) else {}

    return JSONResponse({
        "ok": True,
        "coins": int(row.get("coins") or 0),
        "level": int(progress.get("level") or 1),
        "xcollection_total": len(xcards),
        "xcollection_copies": sum(int(item.get("quantity") or 0) for item in xcards),
        "purchase": {
            "slot_code": slot_code,
            "card_id": int(result.get("card_id") or 0),
            "card_no": str(result.get("card_no") or "").strip(),
            "card_name": str(result.get("card_name") or "").strip(),
            "anime": str(pt_br.get("anime") or card.get("title") or "").strip(),
            "image": _web_image_url(card.get("image")),
            "price": int(result.get("price") or 0),
            "required_level": int(result.get("required_level") or 1),
        },
    })


@app.get("/shop", response_class=HTMLResponse)
def shop_page(uid: int = Query(default=0)):
    return HTMLResponse(
        build_shop_page_html(
            uid=int(uid or 0),
            shop_banner_url=SHOP_PREVIEW_IMAGE,
        )
    )



# Alias opcional
@app.get("/loja", response_class=HTMLResponse)
def loja_alias(uid: int = Query(default=0)):
    return shop_page(uid=uid)




@app.get("/api/cards/contrib/work/search")
async def api_cards_contrib_work_search(
    q: str = Query(..., min_length=2, max_length=80),
    media_type: str = Query(..., max_length=10),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from cards_service import build_cards_final_data
    from database import card_work_request_exists, normalize_media_title

    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    user_id = int(ctx["user_id"])
    if not _webapp_rate_limit(user_id, "card-work-search", 0.35):
        return JSONResponse(
            {"ok": False, "message": "Aguarde um instante antes de buscar novamente."},
            status_code=429,
        )

    media_type = str(media_type or "").strip().lower()
    if media_type not in ("anime", "manga"):
        return JSONResponse({"ok": False, "message": "media_type invalido"}, status_code=400)

    try:
        results = await _pedido_anilist_search(q.strip(), media_type)
        cards_data = build_cards_final_data()
        animes_by_id = cards_data.get("animes_by_id") or {}
        existing_titles = {
            normalize_media_title(item.get("anime"))
            for item in (cards_data.get("animes_list") or [])
            if str(item.get("anime") or "").strip()
        }
        items = []

        for item in results:
            title = (
                ((item.get("title") or {}).get("romaji"))
                or ((item.get("title") or {}).get("english"))
                or ((item.get("title") or {}).get("native"))
                or ""
            ).strip()
            if not title:
                continue

            anilist_id = int(item.get("id") or 0)
            title_norm = normalize_media_title(title)
            exists_catalog = bool(
                (anilist_id > 0 and animes_by_id.get(anilist_id))
                or (title_norm and title_norm in existing_titles)
            )
            items.append({
                "id": anilist_id,
                "title": title,
                "cover": ((item.get("coverImage") or {}).get("large") or ""),
                "score": item.get("averageScore"),
                "format": item.get("format"),
                "status": item.get("status"),
                "year": item.get("seasonYear"),
                "episodes": item.get("episodes"),
                "chapters": item.get("chapters"),
                "already_exists": exists_catalog,
                "already_requested": bool(card_work_request_exists(media_type, title, anilist_id)),
            })

        return JSONResponse({"ok": True, "items": items})
    except Exception as exc:
        print(f"[cards-contrib] busca de obra falhou: {type(exc).__name__}", flush=True)
        traceback.print_exc()
        return JSONResponse(
            {"ok": False, "message": "Nao foi possivel buscar agora."},
            status_code=502,
        )


@app.post("/api/cards/contrib/image")
def api_cards_contrib_image_submit(
    payload: dict = Body(default={}),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from cards_service import get_character_by_id
    from database import create_card_image_suggestion

    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload or {}).get("uid"),
    )
    user_id = int(ctx["user_id"])
    username = str(ctx.get("username") or "").strip()
    full_name = str(ctx.get("full_name") or "").strip()
    touch_user_identity(user_id, username=username, full_name=full_name)

    character_id = int((payload or {}).get("character_id") or 0)
    suggested_image_url = str((payload or {}).get("suggested_image_url") or "").strip()
    note = str((payload or {}).get("note") or "").strip()[:1000]

    parsed = urlparse(suggested_image_url)
    host = str(parsed.hostname or "").strip()
    if character_id <= 0 or parsed.scheme not in {"http", "https"} or not host or _is_blocked_image_host(host):
        return JSONResponse({"ok": False, "message": "Envie uma URL publica valida."}, status_code=400)

    character = get_character_by_id(character_id)
    if not character:
        return JSONResponse({"ok": False, "message": "Personagem nao encontrado."}, status_code=404)

    old_image_url = str(character.get("image") or "").strip()
    if old_image_url and old_image_url == suggested_image_url:
        return JSONResponse({"ok": False, "message": "A nova imagem precisa ser diferente da atual."}, status_code=409)

    row = create_card_image_suggestion({
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "character_id": character_id,
        "character_name": str(character.get("name") or "").strip(),
        "anime_id": int(character.get("anime_id") or 0) or None,
        "anime_title": str(character.get("anime") or "").strip(),
        "old_image_url": old_image_url,
        "suggested_image_url": suggested_image_url,
        "telegram_file_id": "",
        "telegram_file_unique_id": "",
        "note": note,
    })

    return JSONResponse({
        "ok": True,
        "id": int((row or {}).get("id") or 0),
        "message": "Sugestao de foto enviada com sucesso.",
    })


@app.post("/api/cards/contrib/work")
def api_cards_contrib_work_submit(
    payload: dict = Body(default={}),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from cards_service import build_cards_final_data
    from database import card_work_request_exists, create_card_work_request, normalize_media_title

    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload or {}).get("uid"),
    )
    user_id = int(ctx["user_id"])
    username = str(ctx.get("username") or "").strip()
    full_name = str(ctx.get("full_name") or "").strip()
    touch_user_identity(user_id, username=username, full_name=full_name)

    media_type = str((payload or {}).get("media_type") or "").strip().lower()
    anilist_id = int((payload or {}).get("anilist_id") or 0)
    title = str((payload or {}).get("title") or "").strip()
    cover_url = str((payload or {}).get("cover_url") or "").strip()

    if media_type not in {"anime", "manga"} or not title:
        return JSONResponse({"ok": False, "message": "Dados invalidos para o pedido de obra."}, status_code=400)

    cards_data = build_cards_final_data()
    title_norm = normalize_media_title(title)
    existing_titles = {
        normalize_media_title(item.get("anime"))
        for item in (cards_data.get("animes_list") or [])
        if str(item.get("anime") or "").strip()
    }
    already_exists = bool(
        (anilist_id > 0 and (cards_data.get("animes_by_id") or {}).get(anilist_id))
        or (title_norm and title_norm in existing_titles)
    )
    if already_exists:
        return JSONResponse({"ok": False, "message": "Essa obra ja existe no sistema de cards."}, status_code=409)

    if card_work_request_exists(media_type, title, anilist_id):
        return JSONResponse({"ok": False, "message": "Essa obra ja foi sugerida e esta em analise."}, status_code=409)

    row = create_card_work_request({
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "media_type": media_type,
        "anilist_id": anilist_id or None,
        "title": title,
        "cover_url": cover_url,
    })

    return JSONResponse({
        "ok": True,
        "id": int((row or {}).get("id") or 0),
        "message": "Pedido de obra enviado com sucesso.",
    })


@app.get("/cards/contrib/image", response_class=HTMLResponse)
async def cards_contrib_image_page(uid: int = Query(default=0)):
    return HTMLResponse(
        build_cards_contrib_image_page_html(
            uid=int(uid or 0),
            banner_url=CARDS_TOP_BANNER_URL,
        )
    )


@app.get("/cards/contrib/work", response_class=HTMLResponse)
async def cards_contrib_work_page(uid: int = Query(default=0)):
    return HTMLResponse(
        build_cards_contrib_work_page_html(
            uid=int(uid or 0),
            banner_url=CARDS_TOP_BANNER_URL,
        )
    )

# =========================================================
# PAGE — /pedidos-fotos
# =========================================================

@app.get("/cards/contrib", response_class=HTMLResponse)
async def cards_contrib_page(uid: int = Query(default=0)):
    return HTMLResponse(
        build_cards_contrib_page_html(
            uid=int(uid or 0),
            banner_url=CARDS_TOP_BANNER_URL,
        )
    )



@app.get("/cards/contrib/rules", response_class=HTMLResponse)
async def cards_contrib_rules_page():
    return HTMLResponse(
        build_cards_contrib_rules_page_html(
            banner_url=CARDS_TOP_BANNER_URL,
        )
    )


import os
from typing import Any, Dict

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse


WEBHOOK_SECRET = os.getenv("CAKTO_WEBHOOK_SECRET", "").strip()

BALTIGOFLIX_PLANS = {
    "mensal": {
        "code": "mensal",
        "name": "Plano Mensal",
        "amount_cents": 2590,
    },
    "trimestral": {
        "code": "trimestral",
        "name": "Plano Trimestral",
        "amount_cents": 5990,
    },
    "semestral": {
        "code": "semestral",
        "name": "Plano Semestral",
        "amount_cents": 8990,
    },
    "anual": {
        "code": "anual",
        "name": "Plano Anual",
        "amount_cents": 12990,
    },
}

CHECKOUT_URLS = {
    "mensal": "https://pay.cakto.com.br/9snqsP3",
    "trimestral": "https://pay.cakto.com.br/3fsy24d",
    "semestral": "https://pay.cakto.com.br/32ocvxm",
    "anual": "https://pay.cakto.com.br/u9wz86m",
}


def _extract_cakto_ids(payload: Dict[str, Any]) -> Dict[str, str]:
    data = payload.get("data") or {}
    customer = data.get("customer") or {}
    order = data.get("order") or {}

    order_id = (
        str(order.get("id") or "").strip()
        or str(data.get("order_id") or "").strip()
        or str(payload.get("order_id") or "").strip()
    )

    subscription_id = (
        str(data.get("subscription_id") or "").strip()
        or str(payload.get("subscription_id") or "").strip()
    )

    external_reference = (
        str(data.get("external_reference") or "").strip()
        or str(order.get("external_reference") or "").strip()
        or str(payload.get("external_reference") or "").strip()
    )

    customer_id = (
        str(customer.get("id") or "").strip()
        or str(data.get("customer_id") or "").strip()
    )

    return {
        "order_id": order_id,
        "subscription_id": subscription_id,
        "external_reference": external_reference,
        "customer_id": customer_id,
    }


@app.post("/api/baltigoflix/create-intent")
async def baltigoflix_create_intent(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "json_invalido"}, status_code=400)

    ctx = _resolve_webapp_user(
        x_telegram_init_data=str(request.headers.get("x-telegram-init-data") or ""),
        uid=request.query_params.get("uid"),
        x_webapp_uid=request.headers.get("x-webapp-uid"),
        body_uid=(body or {}).get("uid") or (body or {}).get("telegram_user_id"),
    )
    telegram_user_id = int(ctx["user_id"])
    telegram_username = str(ctx.get("username") or body.get("telegram_username") or "").strip()
    telegram_full_name = str(ctx.get("full_name") or body.get("telegram_full_name") or "").strip()
    plan_code = str(body.get("plan_code") or "").strip().lower()

    if telegram_user_id <= 0:
        return JSONResponse({"ok": False, "error": "telegram_user_id_invalido"}, status_code=400)

    touch_user_identity(telegram_user_id, username=telegram_username, full_name=telegram_full_name)

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
        metadata={
            "source": "miniapp",
            "plan_code": plan["code"],
        },
    )

    base_checkout_url = CHECKOUT_URLS.get(plan["code"], "").strip()
    if not base_checkout_url:
        return JSONResponse({"ok": False, "error": "checkout_nao_configurado"}, status_code=500)

    separator = "&" if "?" in base_checkout_url else "?"
    checkout_url = f"{base_checkout_url}{separator}ref={intent['intent_token']}"

    attach_checkout_data_to_purchase_intent(
        intent_id=int(intent["id"]),
        checkout_url=checkout_url,
        raw_checkout_response={
            "mode": "static_checkout_link",
            "message": "checkout via link pronto da Cakto",
        },
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

    received_secret = str(
        request.headers.get("x-webhook-secret")
        or request.headers.get("x-cakto-secret")
        or payload.get("secret")
        or ""
    ).strip()

    if not WEBHOOK_SECRET:
        return JSONResponse({"ok": False, "error": "webhook_not_configured"}, status_code=503)
    if not received_secret or not hmac.compare_digest(received_secret, WEBHOOK_SECRET):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    payload = dict(payload)
    payload.pop("secret", None)

    event_type = str(
        payload.get("event")
        or payload.get("type")
        or payload.get("event_type")
        or ""
    ).strip()

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

        approved_events = {
            "purchase_approved",
            "compra_aprovada",
            "payment_approved",
            "order_paid",
            "subscription_renewed",
        }

        canceled_events = {
            "purchase_refused",
            "compra_recusada",
            "subscription_canceled",
            "subscription_cancelled",
            "canceled",
            "cancelled",
        }

        refunded_events = {
            "refund",
            "refunded",
            "reembolso",
            "chargeback",
        }

        if event_type_lower in approved_events:
            mark_purchase_intent_status(
                intent_id=int(intent["id"]),
                status="paid",
                cakto_order_id=ids["order_id"],
                cakto_subscription_id=ids["subscription_id"],
                cakto_customer_id=ids["customer_id"],
            )

            if intent.get("referrer_user_id"):
                create_affiliate_commission_for_purchase(
                    purchase_intent_id=int(intent["id"]),
                    buyer_user_id=int(intent["telegram_user_id"]),
                    referrer_user_id=int(intent["referrer_user_id"]),
                    amount_cents=int(intent["amount_cents"]),
                    metadata={
                        "source": "cakto_webhook",
                        "event_type": event_type,
                    },
                )

        elif event_type_lower in canceled_events:
            mark_purchase_intent_status(
                intent_id=int(intent["id"]),
                status="canceled",
                cakto_order_id=ids["order_id"],
                cakto_subscription_id=ids["subscription_id"],
                cakto_customer_id=ids["customer_id"],
            )

        elif event_type_lower in refunded_events:
            mark_purchase_intent_status(
                intent_id=int(intent["id"]),
                status="refunded",
                cakto_order_id=ids["order_id"],
                cakto_subscription_id=ids["subscription_id"],
                cakto_customer_id=ids["customer_id"],
            )
            reverse_affiliate_commission_by_purchase(
                purchase_intent_id=int(intent["id"]),
                reason=event_type,
            )

        mark_cakto_webhook_event_processed(event_row["id"])
        return JSONResponse({"ok": True})

    except Exception as e:
        mark_cakto_webhook_event_error(event_row["id"], str(e))
        return JSONResponse({"ok": False, "error": "erro_processando_webhook"}, status_code=500)


@app.get("/baltigoflix/checkout-pending", response_class=HTMLResponse)
def baltigoflix_checkout_pending():
    return HTMLResponse("""
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>BaltigoFlix • Checkout</title>
  <style>
    body{
      margin:0;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
      background:#060913;
      color:#f4f7ff;
      display:flex;
      align-items:center;
      justify-content:center;
      min-height:100vh;
      padding:24px;
    }
    .card{
      width:100%;
      max-width:560px;
      border:1px solid rgba(255,255,255,.10);
      border-radius:24px;
      padding:24px;
      background:rgba(255,255,255,.04);
    }
    h1{margin:0 0 10px;font-size:28px}
    p{margin:0 0 12px;line-height:1.6;color:rgba(244,247,255,.75)}
  </style>
</head>
<body>
  <div class="card">
    <h1>Redirecionando para o checkout...</h1>
    <p>Se você estiver vendo esta tela, revise a URL do checkout retornada na criação da intenção.</p>
  </div>
</body>
</html>
""")


BALTIGOFLIX_BANNER_URL = os.getenv(
    "BALTIGOFLIX_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBaDfI-2m66g4WQ-Jj6FZRPjNKhpCO_4kNAAIXrzEbj2ehRbC9NWdU_qoOAQADAgADeQADOgQ/photo.jpg",
).strip()


@app.get("/baltigoflix", response_class=HTMLResponse)
def baltigoflix_page(uid: int = Query(default=0)):
    return HTMLResponse(
        build_baltigoflix_page_html(
            uid=int(uid or 0),
            banner_url=BALTIGOFLIX_BANNER_URL,
        )
    )


# System diagnostics: aggregate Wallhaven curator status.
from utils.wallhaven_curator_status import router as wallhaven_curator_status_router
app.include_router(wallhaven_curator_status_router)
