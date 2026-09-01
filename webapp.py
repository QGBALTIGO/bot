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

from aninexus_router import router as aninexus_router

from utils.image_proxy import ImageProxyError, fetch_public_image
from utils.portrait_image import PortraitCropError, crop_portrait_bytes
from utils.public_character_image import is_own_image_proxy_url
from utils.telegram_webapp_auth import TelegramWebAppAuthError, validate_telegram_init_data

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
    build_collection_page as build_collection_page_html,
    build_dado_page as build_dado_page_html,
    build_home_page as build_home_page_html,
    build_memory_page as build_memory_page_html,
    build_media_catalog_page as build_media_catalog_page_html,
    build_menu_page as build_menu_page_html,
    build_request_center_page as build_request_center_page_html,
    build_shop_page as build_shop_page_html,
)

from database import (
    create_or_get_user,
    accept_terms,
    set_language,
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
app.include_router(aninexus_router)


@app.on_event("shutdown")
async def close_aninexus_http_client() -> None:
    from utils.aninexus_client import aninexus_client

    await aninexus_client.aclose()

# =========================
# CONFIG — TERMOS
# =========================
TERMS_VERSION = (os.getenv("TERMS_VERSION", "v1").strip() or "v1")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourceBaltigo").strip()
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/SourceBaltigo").strip()

TOP_BANNER_URL = os.getenv(
    "TOP_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzS3wWmpl9pZVvh8mUyitl-u56VSkUmPAALrC2sb1ZFIRYO5j8ewhrZJAQADAgADeQADOgQ/photo.jpg",
).strip()

BACKGROUND_URL = os.getenv("BACKGROUND_URL", "").strip()  # URL pública (pode ficar vazio)
EMPTY_BG_DATA_URI = "data:image/gif;base64,R0lGODlhAQABAAAAACw="

DIRECT_IMAGE_HOSTS = {
    "s4.anilist.co",
    "img.anili.st",
}

IMAGE_PROXY_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

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


def _web_image_url(url: Any) -> str:
    value = str(url or "").strip()
    if not value:
        return ""

    if value.startswith(("data:", "/api/image-proxy?")):
        return value
    if is_own_image_proxy_url(value):
        return value

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return value

    host = (parsed.hostname or "").strip().lower()
    if host in DIRECT_IMAGE_HOSTS:
        return value

    encoded = quote(value, safe="")
    if host == "w.wallhaven.cc":
        return f"/api/image-proxy?crop=portrait&url={encoded}"
    return f"/api/image-proxy?url={encoded}"


@app.get("/api/image-proxy")
async def api_image_proxy(
    url: str = Query(..., min_length=8, max_length=2000),
    crop: str = Query("", max_length=20),
):
    target = str(url or "").strip()
    parsed = urlparse(target)
    hostname = (parsed.hostname or "").strip().lower()

    headers = {
        "User-Agent": IMAGE_PROXY_USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    try:
        content, media_type, _ = await fetch_public_image(
            target,
            headers=headers,
            timeout=httpx.Timeout(20.0, connect=10.0),
        )
    except ImageProxyError as exc:
        print(
            f"[image-proxy] rejected host={hostname or '-'} code={exc.code}",
            flush=True,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except Exception as exc:
        print(
            f"[image-proxy] fetch-failed host={hostname or '-'} error={type(exc).__name__}",
            flush=True,
        )
        raise HTTPException(status_code=502, detail="image_fetch_failed") from exc

    crop_mode = str(crop or "").strip().lower()
    if crop_mode not in {"", "portrait"}:
        raise HTTPException(status_code=400, detail="invalid_crop_mode")

    applied_crop = False
    if crop_mode == "portrait":
        try:
            content, crop_meta = crop_portrait_bytes(content)
            media_type = "image/jpeg"
            applied_crop = True
        except PortraitCropError as exc:
            print(
                f"[image-proxy] portrait-crop-failed host={hostname or '-'} code={exc}",
                flush=True,
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=604800, stale-while-revalidate=86400",
            "Access-Control-Allow-Origin": "*",
            "X-Image-Crop": "2:3" if applied_crop else "original",
        },
    )


def pick_lang(lang: Optional[str]) -> str:
    lang = (lang or "").lower().strip()
    if lang.startswith("pt"):
        return "pt"
    if lang.startswith("es"):
        return "es"
    if lang.startswith("en"):
        return "en"
    return "en"


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
        "no": "❌ Sem aceitar os Termos, você não consegue usar a Source Baltigo. Se mudar de ideia, volte e aceite para continuar sua jornada.",
        "error": "Erro. Tente novamente.",
        "need_checks": "⚠️ Marque as duas opções para continuar.",
        "join_needed": "📢 Antes de continuar, entre no canal e clique em “Verificar inscrição”.",
        "saving": "⏳ Salvando...",
        "processing": "⏳ Processando...",

        "join_title": "CANAL OBRIGATÓRIO",
        "join_text": "Para continuar, é obrigatório entrar no nosso canal oficial.",
        "join_button": "📢 ENTRAR NO CANAL",
        "verify_button": "✅ VERIFICAR INSCRIÇÃO",
        "verify_ok": "✅ Inscrição confirmada. Você já pode continuar.",
        "verify_fail": "❌ Ainda não foi possível confirmar. Entre no canal, aguarde alguns segundos e verifique novamente.",
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
        "no": "❌ Without accepting the Terms, you cannot use Source Baltigo. If you change your mind, come back and accept to continue.",
        "error": "Error. Please try again.",
        "need_checks": "⚠️ Check both boxes to continue.",
        "join_needed": "📢 Before continuing, join the channel and tap “Verify membership”.",
        "saving": "⏳ Saving...",
        "processing": "⏳ Processing...",

        "join_title": "REQUIRED CHANNEL",
        "join_text": "To continue, you must join our official channel.",
        "join_button": "📢 JOIN CHANNEL",
        "verify_button": "✅ VERIFY MEMBERSHIP",
        "verify_ok": "✅ Membership confirmed. You can continue.",
        "verify_fail": "❌ Couldn't confirm yet. Join the channel, wait a few seconds, and try again.",
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
        "no": "❌ Sin aceptar los Términos, no puedes usar Source Baltigo. Si cambias de idea, vuelve y acepta para continuar.",
        "error": "Error. Inténtalo de nuevo.",
        "need_checks": "⚠️ Marca ambas casillas para continuar.",
        "join_needed": "📢 Antes de continuar, entra al canal y toca “Verificar suscripción”.",
        "saving": "⏳ Guardando...",
        "processing": "⏳ Procesando...",

        "join_title": "CANAL OBLIGATORIO",
        "join_text": "Para continuar, es obligatorio unirte a nuestro canal oficial.",
        "join_button": "📢 UNIRME AL CANAL",
        "verify_button": "✅ VERIFICAR SUSCRIPCIÓN",
        "verify_ok": "✅ Suscripción confirmada. Ya puedes continuar.",
        "verify_fail": "❌ Aún no se pudo confirmar. Entra al canal, espera unos segundos y vuelve a verificar.",
        "verify_confirmed": "✅ CONFIRMADO",
    },
}

TERMS_LONG = {
    "pt": """
<div class="section">
  <div class="sectionTitle">SUA PRIVACIDADE</div>
  <div class="sectionText">
    Coletamos apenas o seu ID numérico do Telegram e dados necessários para o funcionamento do bot
    (ex.: idioma, registro de aceite e informações relacionadas ao uso dentro do bot).
    Não temos acesso às suas conversas privadas fora do bot.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">CANAL OFICIAL (OBRIGATÓRIO)</div>
  <div class="sectionText">
    Para usar o bot, é obrigatório entrar e permanecer no nosso canal oficial.
    Caso você saia do canal, o acesso aos comandos pode ser bloqueado até regularizar.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">USO JUSTO E SEGURANÇA</div>
  <div class="sectionText">
    Não é permitido spam, automação, exploração de falhas, tentativa de duplicação de recompensas,
    abuso de botões/callbacks ou qualquer prática que prejudique a experiência de outros usuários.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">SUA RESPONSABILIDADE</div>
  <div class="sectionText">
    Ao aceitar, você confirma que leu e concorda com estas regras.
    As funcionalidades podem mudar para manter equilíbrio e segurança.
  </div>
</div>
""",
    "en": """
<div class="section">
  <div class="sectionTitle">YOUR PRIVACY</div>
  <div class="sectionText">
    We only collect your Telegram numeric ID and what is required to operate the bot
    (e.g., language, acceptance record, and usage-related data inside the bot).
    We do not access your private chats outside the bot.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">OFFICIAL CHANNEL (REQUIRED)</div>
  <div class="sectionText">
    To use the bot, you must join and remain in our official channel.
    If you leave the channel, access to commands may be blocked until you rejoin.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">FAIR USE & SECURITY</div>
  <div class="sectionText">
    Spam, automation, exploit attempts, reward duplication, or abusive button/callback usage is not allowed.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">YOUR RESPONSIBILITY</div>
  <div class="sectionText">
    By accepting, you confirm that you read and agree to these rules.
    Features may change to maintain balance and security.
  </div>
</div>
""",
    "es": """
<div class="section">
  <div class="sectionTitle">TU PRIVACIDAD</div>
  <div class="sectionText">
    Solo recopilamos tu ID numérico de Telegram y lo necesario para operar el bot
    (por ejemplo: idioma, registro de aceptación y datos de uso dentro del bot).
    No accedemos a tus chats privados fuera del bot.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">CANAL OFICIAL (OBLIGATORIO)</div>
  <div class="sectionText">
    Para usar el bot, es obligatorio unirte y permanecer en nuestro canal oficial.
    Si sales del canal, el acceso a los comandos puede bloquearse hasta que vuelvas a unirte.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">USO JUSTO Y SEGURIDAD</div>
  <div class="sectionText">
    No se permite spam, automatización, explotación de fallos, duplicación de recompensas ni abuso de botones/callbacks.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">TU RESPONSABILIDAD</div>
  <div class="sectionText">
    Al aceptar, confirmas que leíste y aceptas estas reglas.
    Las funciones pueden cambiar para mantener equilibrio y seguridad.
  </div>
</div>
""",
}

TERMS_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
<title>__TITLE__</title>
<style>
  :root {
    --text: #e7eaf3;
    --muted: rgba(231,234,243,0.75);
    --glass: rgba(12, 16, 28, 0.62);
    --stroke: rgba(255,255,255,0.10);
    --stroke2: rgba(255,255,255,0.16);
    --okbg: #4ade80;
    --oktxt: #052e16;
  }

  body {
    margin:0;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    color:var(--text);
    background:
      linear-gradient(180deg, rgba(0,0,0,0.62), rgba(0,0,0,0.78)),
      url("__BGURL__") center/cover no-repeat fixed,
      radial-gradient(1200px 700px at 20% 10%, rgba(59,130,246,0.16), transparent 60%),
      radial-gradient(900px 600px at 80% 30%, rgba(168,85,247,0.14), transparent 60%),
      radial-gradient(900px 600px at 50% 90%, rgba(16,185,129,0.10), transparent 60%),
      #050712;
  }

  body:before{
    content:"";
    position:fixed; inset:0;
    background-image: radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px);
    background-size: 42px 42px;
    opacity:0.18;
    pointer-events:none;
  }

  .wrap { max-width:760px; margin:0 auto; padding:18px; position:relative; z-index:1; }

  .card {
    background:var(--glass);
    border:1px solid var(--stroke);
    border-radius:22px;
    overflow:hidden;
    box-shadow:0 18px 40px rgba(0,0,0,0.40);
    backdrop-filter: blur(10px);
  }

  .banner {
    width:100%;
    height:160px;
    background:
      linear-gradient(180deg, rgba(0,0,0,0.0), rgba(0,0,0,0.62)),
      url("__TOPBANNER__") center/cover no-repeat;
    position:relative;
  }
  .banner:after{
    content:"";
    position:absolute; inset:0;
    background: linear-gradient(180deg, rgba(0,0,0,0.05), rgba(0,0,0,0.80));
  }

  .content { padding:16px; }

  .top { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:14px; }
  .brand { display:flex; align-items:center; gap:10px; }
  .badge {
    width:38px; height:38px; border-radius:14px;
    background:rgba(59,130,246,0.16);
    border:1px solid rgba(59,130,246,0.26);
    display:flex; align-items:center; justify-content:center;
    font-weight:900;
  }
  .brandTitle { font-weight:900; letter-spacing:.6px; font-size:15px; line-height:1.1; }
  .brandSub { opacity:.78; font-size:12px; margin-top:2px; letter-spacing:.3px; }

  .langPill {
    display:flex; align-items:center; gap:10px;
    background:rgba(255,255,255,0.06);
    border:1px solid var(--stroke);
    padding:10px 14px; border-radius:14px;
    cursor:pointer; user-select:none;
  }
  .langIcon { font-size:13px; opacity:.9; }
  .langCode { font-size:13px; font-weight:900; letter-spacing:.4px; opacity:.95; }

  .langMenu { display:none; justify-content:flex-end; gap:10px; margin:10px 0 14px 0; }
  .langBtn {
    width:56px; text-align:center;
    background:rgba(255,255,255,0.06);
    border:1px solid var(--stroke);
    padding:10px 0; border-radius:14px;
    font-size:13px; font-weight:900;
    cursor:pointer;
  }

  h1 { font-size:20px; margin:6px 0 2px 0; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:14px; }

  .section {
    background:rgba(255,255,255,0.04);
    border:1px solid rgba(255,255,255,0.08);
    border-radius:18px;
    padding:14px;
    margin:12px 0;
  }
  .sectionTitle { font-weight:900; letter-spacing:.5px; font-size:14px; margin-bottom:8px; }
  .sectionText { color:rgba(231,234,243,0.86); line-height:1.48; font-size:13.5px; }

  .divider { height:1px; background:rgba(255,255,255,0.10); margin:14px 0; }

  label { display:flex; gap:12px; align-items:flex-start; font-size:14px; margin:12px 0; color:rgba(231,234,243,0.92); }
  input[type="checkbox"] { margin-top:3px; transform:scale(1.15); }

  .actions { display:flex; flex-direction:column; gap:10px; margin-top:14px; }
  button { border:0; border-radius:18px; padding:14px 12px; font-weight:900; cursor:pointer; letter-spacing:.6px; }

  .accept { background:var(--okbg); color:var(--oktxt); opacity:0.45; cursor:not-allowed; }
  .decline { background:rgba(255,255,255,0.06); color:var(--text); border:1px solid var(--stroke2); }

  .msg { margin-top:10px; font-size:14px; color:rgba(231,234,243,0.92); min-height:18px; }

  .colBlock {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 14px;
    margin: 12px 0;
  }
  .colTitle { font-weight: 900; letter-spacing: .5px; font-size: 14px; margin-bottom: 8px; }
  .colText { color: rgba(231,234,243,0.86); line-height: 1.48; font-size: 13.5px; margin-bottom: 12px; }
  .rowBtns { display:flex; gap: 10px; flex-wrap: wrap; }

  .smallBtn {
    border: 0;
    border-radius: 16px;
    padding: 12px 14px;
    font-weight: 900;
    cursor: pointer;
    letter-spacing: .4px;
    background: rgba(255,255,255,0.06);
    color: var(--text);
    border: 1px solid rgba(255,255,255,0.14);
    text-decoration: none;
    display:inline-flex;
    align-items:center;
    justify-content:center;
  }
  .smallBtnPrimary {
    background: rgba(74,222,128,0.18);
    border: 1px solid rgba(74,222,128,0.35);
  }
  .smallBtnOk {
    background: rgba(74,222,128,0.24);
    border: 1px solid rgba(74,222,128,0.45);
    color: rgba(231,234,243,0.98);
  }

  .footer { margin-top:14px; text-align:center; font-size:12px; color:rgba(231,234,243,0.45); letter-spacing:2px; padding-bottom:8px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="banner"></div>
    <div class="content">

      <div class="top">
        <div class="brand">
          <div class="badge">🛡️</div>
          <div>
            <div class="brandTitle">SOURCE BALTIGO</div>
            <div class="brandSub">LEGAL & PRIVACY</div>
          </div>
        </div>
        <div class="langPill" id="langPill" title="Change language">
          <span class="langIcon">文A</span>
          <span class="langCode">__LANGCODE__</span>
        </div>
      </div>

      <div class="langMenu" id="langMenu">
        <div class="langBtn" data-lang="pt">PT</div>
        <div class="langBtn" data-lang="en">EN</div>
        <div class="langBtn" data-lang="es">ES</div>
      </div>

      <h1>__TITLE__</h1>
      <div class="sub">__SUBTITLE__ • __INTRO__</div>

      __BODY__

      __JOINBLOCK__

      <div class="divider"></div>

      <label>
        <input id="c1" type="checkbox" />
        <span>__CHECK1__</span>
      </label>

      <label>
        <input id="c2" type="checkbox" />
        <span>__CHECK2__</span>
      </label>

      <div class="actions">
        <button type="button" class="accept" id="acceptBtn">__ACCEPT__</button>
        <button type="button" class="decline" id="declineBtn">__DECLINE__</button>
      </div>

      <div class="msg" id="msg"></div>
      <div class="footer">REVISÃO • __TVERSION__</div>
    </div>
  </div>
</div>

<script>
  const uid = __UID__;
  let lang = "__LANG__";
  let channel_ok = false;

  const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
  if (tg) { try { tg.ready(); } catch (e) {} }

  const langPill = document.getElementById("langPill");
  const langMenu = document.getElementById("langMenu");
  langPill.addEventListener("click", (e) => {
    e.stopPropagation();
    langMenu.style.display = (langMenu.style.display === "flex") ? "none" : "flex";
    if (langMenu.style.display === "flex") langMenu.style.justifyContent = "flex-end";
  });
  document.addEventListener("click", () => { langMenu.style.display = "none"; });
  document.querySelectorAll(".langBtn").forEach(btn => {
    btn.addEventListener("click", () => {
      const newLang = btn.getAttribute("data-lang");
      const url = new URL(window.location.href);
      url.searchParams.set("lang", newLang);
      window.location.href = url.toString();
    });
  });

  const c1 = document.getElementById("c1");
  const c2 = document.getElementById("c2");
  const acceptBtn = document.getElementById("acceptBtn");
  const declineBtn = document.getElementById("declineBtn");
  const msg = document.getElementById("msg");

  function setMsg(text) { msg.textContent = text || ""; }

  function updateAcceptButton() {
    const ok = c1.checked && c2.checked && channel_ok;
    acceptBtn.style.opacity = ok ? "1" : "0.45";
    acceptBtn.style.cursor = ok ? "pointer" : "not-allowed";
  }
  c1.addEventListener("change", updateAcceptButton);
  c2.addEventListener("change", updateAcceptButton);
  updateAcceptButton();

  async function postJson(url, payload) {
    const u = new URL(url, window.location.origin);
    u.searchParams.set("_ts", String(Date.now()));

    const headers = { "Content-Type": "application/json" };
    if (tg && tg.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    if (uid > 0) headers["X-WebApp-Uid"] = String(uid);

    const res = await fetch(u.toString(), {
      method: "POST",
      headers,
      body: JSON.stringify(payload)
    });

    let data = null;
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) {
      const m = (data && data.message) ? data.message : ("Erro HTTP " + res.status);
      throw new Error(m);
    }
    return data || {};
  }

  const checkChannelBtn = document.getElementById("checkChannelBtn");
  if (checkChannelBtn) {
    checkChannelBtn.addEventListener("click", async () => {
      setMsg("__PROCESSING__");
      try {
        const data = await postJson("/api/channel/check", { uid });
        if (data && data.ok) {
          channel_ok = true;
          updateAcceptButton();
          setMsg("__VERIFYOK__");

          checkChannelBtn.textContent = "__VERIFYCONF__";
          checkChannelBtn.classList.add("smallBtnOk");
          checkChannelBtn.disabled = true;

        } else {
          channel_ok = false;
          updateAcceptButton();
          setMsg("__VERIFYFAIL__");
        }
      } catch (e) {
        channel_ok = false;
        updateAcceptButton();
        setMsg("❌ " + (e.message || "__VERIFYFAIL__"));
      }
    });
  }

  acceptBtn.addEventListener("click", async () => {
    if (!(c1.checked && c2.checked)) { setMsg("__NEEDCHECKS__"); return; }
    if (!channel_ok) { setMsg("__JOINNEEDED__"); return; }

    setMsg("__SAVING__");
    acceptBtn.disabled = true; declineBtn.disabled = true;
    try {
      const data = await postJson("/api/terms/accept", { uid, lang });
      setMsg(data.message || "__DONE__");
      if (tg) { try { tg.close(); } catch (e) {} }
    } catch (e) {
      setMsg("❌ " + (e.message || "__ERROR__"));
      acceptBtn.disabled = false; declineBtn.disabled = false;
    }
  });

  declineBtn.addEventListener("click", async () => {
    setMsg("__PROCESSING__");
    acceptBtn.disabled = true; declineBtn.disabled = true;
    try {
      const data = await postJson("/api/terms/decline", { uid, lang });
      setMsg(data.message || "__NO__");
      if (tg) { try { tg.close(); } catch (e) {} }
    } catch (e) {
      setMsg("❌ " + (e.message || "__ERROR__"));
      acceptBtn.disabled = false; declineBtn.disabled = false;
    }
  });
</script>

</body>
</html>
"""


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


@app.get("/terms", response_class=HTMLResponse)
def terms_page(uid: int = Query(...), lang: str = Query("en")):
    L = pick_lang(lang)
    t = TEXTS[L]
    body = TERMS_LONG[L]

    joinblock = f"""
    <div class="colBlock">
      <div class="colTitle">{t["join_title"]}</div>
      <div class="colText">{t["join_text"]}</div>
      <div class="rowBtns">
        <a class="smallBtn" href="{REQUIRED_CHANNEL_URL}" target="_blank" rel="noopener noreferrer">{t["join_button"]}</a>
        <button type="button" class="smallBtn smallBtnPrimary" id="checkChannelBtn">{t["verify_button"]}</button>
      </div>
    </div>
    """

    bg = BACKGROUND_URL if BACKGROUND_URL else EMPTY_BG_DATA_URI
    html = (TERMS_HTML
        .replace("__UID__", str(uid))
        .replace("__LANG__", L)
        .replace("__LANGCODE__", L.upper())
        .replace("__TITLE__", t["title"])
        .replace("__SUBTITLE__", t["subtitle"])
        .replace("__INTRO__", t["intro"])
        .replace("__CHECK1__", t["check1"])
        .replace("__CHECK2__", t["check2"])
        .replace("__ACCEPT__", t["accept"])
        .replace("__DECLINE__", t["decline"])
        .replace("__DONE__", t["done"])
        .replace("__NO__", t["no"])
        .replace("__ERROR__", t["error"])
        .replace("__NEEDCHECKS__", t["need_checks"])
        .replace("__JOINNEEDED__", t["join_needed"])
        .replace("__SAVING__", t["saving"])
        .replace("__PROCESSING__", t["processing"])
        .replace("__VERIFYOK__", t["verify_ok"])
        .replace("__VERIFYFAIL__", t["verify_fail"])
        .replace("__VERIFYCONF__", t["verify_confirmed"])
        .replace("__TVERSION__", TERMS_VERSION.upper())
        .replace("__BODY__", body)
        .replace("__JOINBLOCK__", joinblock)
        .replace("__TOPBANNER__", TOP_BANNER_URL)
        .replace("__BGURL__", bg)
    )
    return HTMLResponse(html)


@app.post("/api/terms/accept")
def api_accept(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    try:
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            x_webapp_uid=x_webapp_uid,
            body_uid=payload.get("uid"),
        )
        user_id = int(ctx["user_id"])
        lang = pick_lang(payload.get("lang"))

        create_or_get_user(user_id)
        set_language(user_id, lang)
        accept_terms(user_id, TERMS_VERSION)
        return {"ok": True, "message": TEXTS[lang]["done"]}
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[terms] accept failed type={type(exc).__name__}", flush=True)
        traceback.print_exc()
        return JSONResponse(
            {"ok": False, "message": TEXTS[pick_lang(payload.get("lang"))]["error"]},
            status_code=500,
        )


@app.post("/api/terms/decline")
def api_decline(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    try:
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            x_webapp_uid=x_webapp_uid,
            body_uid=payload.get("uid"),
        )
        user_id = int(ctx["user_id"])
        lang = pick_lang(payload.get("lang"))

        create_or_get_user(user_id)
        set_language(user_id, lang)
        return {"ok": True, "message": TEXTS[lang]["no"]}
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[terms] decline failed type={type(exc).__name__}", flush=True)
        traceback.print_exc()
        return JSONResponse(
            {"ok": False, "message": TEXTS[pick_lang(payload.get("lang"))]["error"]},
            status_code=500,
        )


from utils.channel_verification_bridge import wait_for_verification, worker_health


@app.get("/api/channel/selftest")
def api_channel_selftest(
    x_internal_api_secret: str = Header(default=""),
):
    _require_internal_api_secret(x_internal_api_secret)
    health = worker_health()
    return JSONResponse(health, status_code=200 if health.get("ok") else 503)


@app.post("/api/channel/check")
def api_channel_check(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload or {}).get("uid"),
    )
    user_id = int(ctx["user_id"])

    if not REQUIRED_CHANNEL:
        return {"ok": True}

    try:
        result = wait_for_verification(user_id, timeout_seconds=8.0)
    except Exception as exc:
        print(
            f"[terms-membership] bridge failed user_id={user_id} type={type(exc).__name__}",
            flush=True,
        )
        return JSONResponse(
            {"ok": False, "message": "Não foi possível iniciar a verificação agora."},
            status_code=502,
        )

    if result.get("ok"):
        return {"ok": True}

    status = str(result.get("status") or "")
    if status == "not_member":
        return JSONResponse(
            {"ok": False, "message": "Você ainda não está no canal obrigatório."},
            status_code=403,
        )

    return JSONResponse(
        {"ok": False, "message": str(result.get("message") or "Falha na verificação.")},
        status_code=503 if status == "timeout" else 502,
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


@app.get("/memoria", response_class=HTMLResponse)
def memory_page(
    level: str = Query(default="medium"),
    uid: int = Query(default=0),
):
    return HTMLResponse(
        build_memory_page_html(
            uid=int(uid or 0),
            banner_url=CARDS_TOP_BANNER_URL,
            default_level=str(level or "medium"),
        )
    )


@app.get("/memory", response_class=HTMLResponse)
def memory_alias(
    level: str = Query(default="medium"),
    uid: int = Query(default=0),
):
    return memory_page(level=level, uid=uid)


@app.get("/api/memory/best")
def api_memory_best(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from database import get_memory_best_summary

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

    payload = get_memory_best_summary(user_id)
    rows = payload.get("rows") or []
    summary = payload.get("summary") or {}

    by_level = {}
    for row in rows:
        level_key = str(row.get("level") or "").strip().lower()
        if not level_key:
            continue
        by_level[level_key] = {
            "time_ms": int(row.get("best_time_ms") or 0),
            "moves": int(row.get("best_moves") or 0),
            "games_played": int(row.get("games_played") or 0),
            "completed_games": int(row.get("completed_games") or 0),
        }

    return JSONResponse({
        "ok": True,
        "by_level": by_level,
        "summary": {
            "levels_completed": int(summary.get("levels_completed") or 0),
            "avg_best_time_ms": float(summary.get("avg_best_time_ms") or 0),
            "avg_best_moves": float(summary.get("avg_best_moves") or 0),
            "completed_games": int(summary.get("completed_games") or 0),
        },
    })


@app.post("/api/memory/finish")
def api_memory_finish(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from database import save_memory_game_result

    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=payload.get("uid"),
        body_uid=payload.get("uid"),
        x_webapp_uid=x_webapp_uid,
    )
    user_id = int(ctx["user_id"])
    touch_user_identity(
        user_id,
        username=str(ctx.get("username") or "").strip(),
        full_name=str(ctx.get("full_name") or "").strip(),
    )

    level = str(payload.get("level") or "").strip().lower()
    time_ms = int(payload.get("time_ms") or 0)
    moves = int(payload.get("moves") or 0)

    if level not in {"easy", "medium", "hard", "extreme"}:
        return JSONResponse({"ok": False, "message": "Nivel invalido."}, status_code=400)
    if time_ms <= 0 or time_ms > 7_200_000:
        return JSONResponse({"ok": False, "message": "Tempo invalido."}, status_code=400)
    if moves <= 0 or moves > 10_000:
        return JSONResponse({"ok": False, "message": "Quantidade de jogadas invalida."}, status_code=400)

    try:
        result = save_memory_game_result(user_id, level, time_ms, moves)
    except ValueError as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)

    best = result.get("best") or {}
    summary = result.get("summary") or {}
    return JSONResponse({
        "ok": True,
        "new_record": bool(result.get("new_record")),
        "best": {
            "level": str(best.get("level") or level),
            "time_ms": int(best.get("best_time_ms") or time_ms),
            "moves": int(best.get("best_moves") or moves),
            "games_played": int(best.get("games_played") or 0),
            "completed_games": int(best.get("completed_games") or 0),
        },
        "summary": {
            "levels_completed": int(summary.get("levels_completed") or 0),
            "avg_best_time_ms": float(summary.get("avg_best_time_ms") or 0),
            "avg_best_moves": float(summary.get("avg_best_moves") or 0),
            "completed_games": int(summary.get("completed_games") or 0),
        },
    })




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
                ((item.get("title") or {}).get("romaji"))
                or ((item.get("title") or {}).get("english"))
                or ((item.get("title") or {}).get("native"))
                or ""
            ).strip()
            if not title:
                continue

            anilist_id = item.get("id")
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
                "already_exists": bool(_pedido_catalog_contains(media_type, title, anilist_id)),
                "already_requested": bool(media_request_exists(media_type, title, anilist_id)),
            })

        return JSONResponse({"ok": True, "items": items})
    except Exception as exc:
        print(f"[pedido] busca AniList falhou: {type(exc).__name__}", flush=True)
        traceback.print_exc()
        return JSONResponse(
            {"ok": False, "message": "Não foi possível buscar agora."},
            status_code=502,
        )


async def _telegram_send_message(chat_id: str, text: str):
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )
    return resp


async def _telegram_send_photo(chat_id: str, photo: str, caption: str):
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={
                "chat_id": chat_id,
                "photo": photo,
                "caption": caption,
                "parse_mode": "HTML",
            },
        )
    return resp


@app.post("/api/pedido/send")
async def api_pedido_send(
    payload: dict = Body(...),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    try:
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            uid=uid,
            x_webapp_uid=x_webapp_uid,
            body_uid=(payload or {}).get("uid") or (payload or {}).get("user_id"),
        )
        user_id = int(ctx["user_id"])
        username = str(ctx.get("username") or payload.get("username") or "").strip()
        full_name = str(ctx.get("full_name") or payload.get("full_name") or payload.get("name") or "").strip()
        media_type = str(payload.get("media_type") or "").strip().lower()
        anilist_id = payload.get("anilist_id")
        title = str(payload.get("title") or "").strip()
        cover = str(payload.get("cover") or "").strip()

        if user_id <= 0 or media_type not in ("anime", "manga") or not title:
            return JSONResponse({"ok": False, "message": "Dados inválidos."}, status_code=400)

        touch_user_identity(user_id, username=username, full_name=full_name)
        used = count_user_media_requests_last_24h(user_id)
        if used >= 3:
            return JSONResponse({
                "ok": False,
                "code": "limit",
                "message": "Você atingiu o limite de 3 pedidos nas últimas 24h."
            }, status_code=429)

        if _pedido_catalog_contains(media_type, title, anilist_id):
            return JSONResponse({
                "ok": False,
                "code": "exists",
                "message": "Esse título já está disponível no catálogo."
            }, status_code=409)

        if media_request_exists(media_type, title, anilist_id):
            return JSONResponse({
                "ok": False,
                "code": "requested",
                "message": "Esse título já foi pedido e está em análise."
            }, status_code=409)

        save_media_request(user_id, username, full_name, media_type, title, anilist_id, cover)

        if not CANAL_PEDIDOS or not BOT_TOKEN:
            return JSONResponse({
                "ok": False,
                "message": "CANAL_PEDIDOS ou BOT_TOKEN não configurado no webapp."
            }, status_code=500)

        safe_full_name = html.escape(full_name or "Sem nome")
        safe_username = html.escape(username) if username else "sem_username"
        safe_title = html.escape(title)
        safe_type = html.escape(media_type.upper())
        safe_anilist = html.escape(str(anilist_id or "-"))

        caption = (
            f"📥 <b>NOVO PEDIDO</b>\n\n"
            f"👤 <b>Usuário:</b> {safe_full_name}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"🔖 <b>Username:</b> @{safe_username}\n\n"
            f"🎴 <b>Tipo:</b> {safe_type}\n"
            f"📝 <b>Título:</b> <i>{safe_title}</i>\n"
            f"🆔 <b>AniList ID:</b> <code>{safe_anilist}</code>"
        )

        resp = None
        tg_json = None

        if cover:
            try:
                resp = await _telegram_send_photo(CANAL_PEDIDOS, cover, caption)
                tg_json = resp.json()
            except Exception as e:
                print("[pedido] sendPhoto exception:", repr(e), flush=True)
                tg_json = {"ok": False, "description": repr(e)}

        if not tg_json or not tg_json.get("ok"):
            text_fallback = (
                f"📥 <b>NOVO PEDIDO</b>\n\n"
                f"👤 <b>Usuário:</b> {safe_full_name}\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                f"🔖 <b>Username:</b> @{safe_username}\n\n"
                f"🎴 <b>Tipo:</b> {safe_type}\n"
                f"📝 <b>Título:</b> <i>{safe_title}</i>\n"
                f"🆔 <b>AniList ID:</b> <code>{safe_anilist}</code>\n"
                f"🖼 <b>Capa:</b> {html.escape(cover or '-')}"
            )

            resp = await _telegram_send_message(CANAL_PEDIDOS, text_fallback)
            tg_json = resp.json()

            if not tg_json.get("ok"):
                print("[pedido] telegram falhou:", tg_json, flush=True)
                return JSONResponse({
                    "ok": False,
                    "message": "O pedido foi salvo, mas o Telegram recusou o envio ao canal. Verifique se o bot está admin no canal."
                }, status_code=502)

        return JSONResponse({
            "ok": True,
            "message": "Pedido enviado com sucesso.",
            "used": used + 1,
            "remaining": max(0, 3 - (used + 1)),
        })

    except Exception as e:
        print("[pedido] falha ao enviar pedido:", repr(e), flush=True)
        traceback.print_exc()
        return JSONResponse({"ok": False, "message": "Não foi possível enviar seu pedido."}, status_code=500)


@app.post("/api/pedido/report")
async def api_pedido_report(
    payload: dict = Body(...),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    try:
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            uid=uid,
            x_webapp_uid=x_webapp_uid,
            body_uid=(payload or {}).get("uid") or (payload or {}).get("user_id"),
        )
        user_id = int(ctx["user_id"])
        username = str(ctx.get("username") or payload.get("username") or "").strip()
        full_name = str(ctx.get("full_name") or payload.get("full_name") or payload.get("name") or "").strip()
        report_type = str(payload.get("report_type") or "Outro").strip()
        message = str(payload.get("message") or "").strip()

        if user_id <= 0 or not message:
            return JSONResponse({"ok": False, "message": "Dados inválidos."}, status_code=400)

        touch_user_identity(user_id, username=username, full_name=full_name)
        save_webapp_report(user_id, username, full_name, report_type, message)

        if not CANAL_PEDIDOS or not BOT_TOKEN:
            return JSONResponse({
                "ok": False,
                "message": "CANAL_PEDIDOS ou BOT_TOKEN não configurado no webapp."
            }, status_code=500)

        safe_full_name = html.escape(full_name or "Sem nome")
        safe_username = html.escape(username) if username else "sem_username"
        safe_report_type = html.escape(report_type)
        safe_message = html.escape(message)

        text = (
            f"⚠️ <b>NOVO REPORT</b>\n\n"
            f"👤 <b>Usuário:</b> {safe_full_name}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"🔖 <b>Username:</b> @{safe_username}\n\n"
            f"🏷 <b>Tipo:</b> {safe_report_type}\n"
            f"📝 <b>Mensagem:</b>\n{safe_message}"
        )

        resp = await _telegram_send_message(CANAL_PEDIDOS, text)
        tg_json = resp.json()

        if not tg_json.get("ok"):
            print("[pedido] telegram falhou no report:", tg_json, flush=True)
            return JSONResponse({
                "ok": False,
                "message": "O report foi salvo, mas o Telegram recusou o envio ao canal."
            }, status_code=502)

        return JSONResponse({"ok": True, "message": "Report enviado com sucesso."})

    except Exception as e:
        print("[pedido] falha ao enviar report:", repr(e), flush=True)
        traceback.print_exc()
        return JSONResponse({"ok": False, "message": "Não foi possível enviar o report."}, status_code=500)


@app.get("/pedido", response_class=HTMLResponse)
def pedido_page(uid: int = Query(default=0)):
    return HTMLResponse(
        build_request_center_page_html(
            uid=int(uid or 0),
            banner_url=PEDIDO_BANNER_URL,
        )
    )


# =========================================================
# DADO / GACHA WEBAPP — BLOCO COMPLETO
# =========================================================

from pathlib import Path
from urllib.parse import parse_qsl
import hashlib
import hmac
import json
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import Body, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from database import (
    cancel_dice_roll,
    create_dice_roll,
    create_or_get_user,
    expire_stale_dice_rolls,
    get_active_dice_roll,
    get_dado_state,
    get_next_dado_recharge_info,
    pick_dice_roll_anime,
    resolve_dice_roll,
)

# =========================================================
# CONFIG — DADO / GACHA WEBAPP
# =========================================================

DADO_BANNER_URL = os.getenv(
    "DADO_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZqAk02mfJAxu6F0SV9i2MqA5qQ6fDy3PAAKhC2sbjP74RFhnKn29pt05AQADAgADeQADOgQ/photo.jpg",
).strip()

CARDS_LOCAL_PATH = os.getenv(
    "CARDS_LOCAL_PATH",
    "bot/data/personagens_anilist.txt",
).strip()

DADO_WEB_RATE_SECONDS = float(os.getenv("DADO_WEB_RATE_SECONDS", "0.8"))

_DADO_LOCAL_CACHE: Dict[str, Any] = {
    "mtime": 0.0,
    "loaded": False,
    "path": "",
    "animes_list": [],
    "animes_by_id": {},
    "characters_by_anime": {},
}


def _dado_rate_limit(user_id: int, key: str, window: float = DADO_WEB_RATE_SECONDS) -> bool:
    return _webapp_rate_limit(user_id, f"dado:{key}", window)


# =========================================================
# TELEGRAM WEBAPP AUTH
# =========================================================

def verify_telegram_init_data(init_data: str) -> dict:
    try:
        validated = validate_telegram_init_data(init_data, BOT_TOKEN)
    except TelegramWebAppAuthError as exc:
        code = str(exc) or "init_data_invalid"
        status_code = 503 if code == "bot_token_missing" else 401
        raise HTTPException(status_code=status_code, detail=code) from exc

    return {
        "user": dict(validated.get("user") or {}),
        "raw": dict(validated.get("raw") or {}),
    }


def _get_tg_user(x_telegram_init_data: str) -> Dict[str, Any]:
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]

    user_id = int(user["id"])
    username = (user.get("username") or "").strip()
    full_name = " ".join(
        p for p in [
            (user.get("first_name") or "").strip(),
            (user.get("last_name") or "").strip(),
        ] if p
    ).strip()

    create_or_get_user(user_id)
    return {
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
    }


def _coerce_positive_uid(*values: Any) -> int:
    for value in values:
        try:
            uid = int(str(value or "").strip())
        except Exception:
            continue
        if uid > 0:
            return uid
    return 0


def _build_fallback_webapp_user(user_id: int) -> Dict[str, Any]:
    from database import get_user_status

    user_id = int(user_id or 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="uid ausente")

    create_or_get_user(user_id)
    row = get_user_status(user_id) or {}

    return {
        "user_id": int(user_id),
        "username": str(row.get("username") or "").strip(),
        "full_name": str(row.get("full_name") or "").strip(),
        "auth_mode": "uid_fallback",
    }


def _resolve_webapp_user(
    *,
    x_telegram_init_data: str = "",
    uid: Any = None,
    x_webapp_uid: Any = None,
    body_uid: Any = None,
) -> Dict[str, Any]:
    fallback_uid = _coerce_positive_uid(body_uid, uid, x_webapp_uid)

    if x_telegram_init_data:
        data = _get_tg_user(x_telegram_init_data)
        signed_user_id = int(data["user_id"])
        if fallback_uid > 0 and fallback_uid != signed_user_id:
            raise HTTPException(status_code=403, detail="uid_divergente")
        data["auth_mode"] = "telegram_init_data"
        return data

    allow_insecure_fallback = os.getenv(
        "ALLOW_INSECURE_WEBAPP_UID_FALLBACK",
        "",
    ).strip().lower() in {"1", "true", "yes", "on"}
    if allow_insecure_fallback and fallback_uid > 0:
        return _build_fallback_webapp_user(fallback_uid)

    raise HTTPException(status_code=401, detail="telegram_init_data_required")


@app.get("/api/webapp/context")
def api_webapp_context(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    from database import (
        get_progress_row,
        get_profile_settings,
        get_user_status,
        get_user_xcard_collection,
    )

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

    user = get_user_status(user_id) or {}
    progress = get_progress_row(user_id) or {}
    settings = get_profile_settings(user_id) or {}
    cards_data, qty_by_char, subcategory_map = _collection_snapshot(user_id)
    cards = _collection_cards_from_snapshot(cards_data, qty_by_char, subcategory_map)
    xcards = get_user_xcard_collection(user_id) or []

    display_name = (
        str(settings.get("nickname") or "").strip()
        or str(ctx.get("full_name") or "").strip()
        or (f"@{ctx.get('username')}" if str(ctx.get("username") or "").strip() else f"User {user_id}")
    )

    return JSONResponse({
        "ok": True,
        "profile": {
            "user_id": user_id,
            "username": str(ctx.get("username") or user.get("username") or "").strip(),
            "full_name": str(ctx.get("full_name") or user.get("full_name") or "").strip(),
            "display_name": display_name,
            "nickname": str(settings.get("nickname") or "").strip(),
            "coins": int(user.get("coins") or 0),
            "dado_balance": int(user.get("dado_balance") or 0),
            "level": int(progress.get("level") or 1),
            "collection_total": len(cards),
            "xcollection_total": len(xcards),
            "xcollection_copies": sum(int(item.get("quantity") or 0) for item in xcards),
            "auth_mode": str(ctx.get("auth_mode") or ""),
        },
    })


async def _tg_send_photo(chat_id: int, photo: str, caption: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                json={
                    "chat_id": int(chat_id),
                    "photo": str(photo),
                    "caption": str(caption),
                    "parse_mode": "HTML",
                },
            )
            data = resp.json()
            return bool(data.get("ok"))
    except Exception:
        return False


# =========================================================
# DADO — BASE LOCAL
# =========================================================

def _dado_safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _norm_text(v: Any) -> str:
    return str(v or "").strip()


def _build_cover_from_anilist(anime_id: int) -> str:
    anime_id = int(anime_id)
    if anime_id <= 0:
        return DADO_BANNER_URL
    return f"https://img.anili.st/media/{anime_id}"


def _build_char_image_from_anilist(char_id: int) -> str:
    char_id = int(char_id)
    if char_id <= 0:
        return DADO_BANNER_URL
    return f"https://img.anili.st/character/{char_id}"


def _resolve_local_cards_path() -> Optional[Path]:
    candidates = [
        CARDS_LOCAL_PATH,
        "bot/data/personagens_anilist.txt",
        "data/personagens_anilist.txt",
        "/app/bot/data/personagens_anilist.txt",
        "/app/data/personagens_anilist.txt",
    ]

    seen = set()
    for cand in candidates:
        cand = str(cand or "").strip()
        if not cand or cand in seen:
            continue
        seen.add(cand)

        p = Path(cand)
        if p.exists() and p.is_file():
            return p

    return None


def _repair_loose_json_text(raw: str) -> str:
    if not raw:
        return "[]"

    lines = raw.splitlines()
    fixed: List[str] = []

    key_start_re = re.compile(r'^\s*"[^"]+"\s*:')
    prev_can_need_comma_re = re.compile(r'["\}\]0-9]$')

    for line in lines:
        stripped = line.strip()

        if fixed:
            prev = fixed[-1].rstrip()
            prev_stripped = prev.strip()

            if (
                stripped
                and key_start_re.match(stripped)
                and prev_stripped
                and not prev_stripped.endswith((",", "{", "[", ":"))
                and prev_can_need_comma_re.search(prev_stripped)
            ):
                fixed[-1] = prev + ","

        fixed.append(line)

    txt = "\n".join(fixed)
    txt = re.sub(r",(\s*[\]\}])", r"\1", txt)
    return txt


def _extract_items_from_local_file(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not raw:
        return []

    attempts = [
        raw,
        _repair_loose_json_text(raw),
    ]

    for candidate in attempts:
        try:
            parsed = json.loads(candidate)
            items = parsed.get("items") if isinstance(parsed, dict) else parsed
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
        except Exception:
            continue

    return []


def _load_local_dado_pool() -> Dict[str, Any]:
    global _DADO_LOCAL_CACHE

    path = _resolve_local_cards_path()
    if path is None:
        return {
            "animes_list": [],
            "animes_by_id": {},
            "characters_by_anime": {},
        }

    mtime = float(path.stat().st_mtime or 0.0)
    if (
        _DADO_LOCAL_CACHE["loaded"]
        and _DADO_LOCAL_CACHE["mtime"] == mtime
        and _DADO_LOCAL_CACHE["path"] == str(path)
    ):
        return {
            "animes_list": _DADO_LOCAL_CACHE["animes_list"],
            "animes_by_id": _DADO_LOCAL_CACHE["animes_by_id"],
            "characters_by_anime": _DADO_LOCAL_CACHE["characters_by_anime"],
        }

    raw_items = _extract_items_from_local_file(path)

    animes_by_id: Dict[int, Dict[str, Any]] = {}
    characters_by_anime: Dict[int, List[Dict[str, Any]]] = {}

    for item in raw_items:
        anime_id = _dado_safe_int(item.get("anime_id"), 0)
        anime_name = _norm_text(item.get("anime"))
        banner_image = _norm_text(item.get("banner_image"))
        cover_image = _norm_text(item.get("cover_image") or item.get("imagem_de_capa"))
        chars_raw = item.get("characters") or item.get("personagens") or []

        if anime_id <= 0 or not anime_name:
            continue

        if anime_id not in animes_by_id:
            animes_by_id[anime_id] = {
                "anime_id": anime_id,
                "anime": anime_name,
                "cover_image": cover_image or banner_image or _build_cover_from_anilist(anime_id),
                "banner_image": banner_image or cover_image or _build_cover_from_anilist(anime_id),
                "characters_count": 0,
            }
            characters_by_anime[anime_id] = []

        if isinstance(chars_raw, list):
            for c in chars_raw:
                if not isinstance(c, dict):
                    continue

                cid = _dado_safe_int(c.get("id"), 0)
                cname = _norm_text(c.get("name") or c.get("nome"))
                canime = _norm_text(c.get("anime") or anime_name)
                cimg = _norm_text(c.get("image") or c.get("imagem"))

                if cid <= 0 or not cname:
                    continue

                characters_by_anime[anime_id].append({
                    "id": cid,
                    "name": cname,
                    "anime": canime or anime_name,
                    "image": cimg or _build_char_image_from_anilist(cid),
                })

    animes_list: List[Dict[str, Any]] = []

    for anime_id, meta in animes_by_id.items():
        chars = characters_by_anime.get(anime_id, [])
        seen_ids = set()
        clean_chars = []

        for c in chars:
            cid = int(c["id"])
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            clean_chars.append(c)

        clean_chars.sort(key=lambda x: (x["name"] or "").lower())
        characters_by_anime[anime_id] = clean_chars
        meta["characters_count"] = len(clean_chars)

        if clean_chars:
            animes_list.append(meta)

    animes_list.sort(key=lambda x: (x.get("anime") or "").lower())

    _DADO_LOCAL_CACHE = {
        "mtime": mtime,
        "loaded": True,
        "path": str(path),
        "animes_list": animes_list,
        "animes_by_id": animes_by_id,
        "characters_by_anime": characters_by_anime,
    }

    return {
        "animes_list": animes_list,
        "animes_by_id": animes_by_id,
        "characters_by_anime": characters_by_anime,
    }


def _max_dice_value_from_local_pool(pool: Optional[List[Dict[str, Any]]] = None) -> int:
    if pool is None:
        data = _load_local_dado_pool()
        pool = list(data.get("animes_list") or [])
    return min(6, len(pool))


def _pick_random_local_animes(
    n: int,
    pool: Optional[List[Dict[str, Any]]] = None,
) -> List[dict]:
    if pool is None:
        data = _load_local_dado_pool()
        pool = list(data.get("animes_list") or [])
    else:
        pool = list(pool or [])

    if not pool:
        return []

    max_allowed = min(6, len(pool))
    qty = max(1, min(int(n), max_allowed))

    picks = random.sample(pool, qty)
    return [
        {
            "id": int(item["anime_id"]),
            "title": str(item["anime"]),
            "cover": str(item.get("cover_image") or item.get("banner_image") or DADO_BANNER_URL),
        }
        for item in picks
    ]


def _pick_random_local_character(anime_id: int) -> Optional[dict]:
    data = _load_local_dado_pool()
    chars = list((data["characters_by_anime"].get(int(anime_id)) or []))
    if not chars:
        return None

    random.shuffle(chars)
    c = chars[0]

    return {
        "id": int(c["id"]),
        "name": str(c["name"]),
        "image": str(c.get("image") or DADO_BANNER_URL),
        "anime_title": str(c.get("anime") or "Anime"),
        "anime_cover": _build_cover_from_anilist(int(anime_id)),
    }


def _find_local_dado_character(anime_id: int, character_id: int) -> Optional[dict]:
    data = _load_local_dado_pool()
    characters = list(data["characters_by_anime"].get(int(anime_id)) or [])
    for character in characters:
        if int(character.get("id") or 0) != int(character_id):
            continue
        return {
            "id": int(character["id"]),
            "name": str(character.get("name") or "Personagem"),
            "image": str(character.get("image") or DADO_BANNER_URL),
            "anime_title": str(character.get("anime") or "Anime"),
            "anime_cover": _build_cover_from_anilist(int(anime_id)),
        }
    return None


def _hydrate_dado_character(anime_id: int, character_id: int) -> Optional[dict]:
    character = _find_local_dado_character(anime_id, character_id)

    try:
        from cards_service import get_character_by_id

        global_character = get_character_by_id(int(character_id))
    except Exception as exc:
        print(f"[dado] falha ao consultar personagem global: {type(exc).__name__}", flush=True)
        global_character = None

    if character is None and global_character:
        character = {
            "id": int(global_character.get("id") or character_id),
            "name": str(global_character.get("name") or "Personagem"),
            "image": str(global_character.get("image") or DADO_BANNER_URL),
            "anime_title": str(global_character.get("anime") or "Anime"),
            "anime_cover": _build_cover_from_anilist(
                int(global_character.get("anime_id") or anime_id)
            ),
        }
    elif character is not None and global_character:
        global_image = str(global_character.get("image") or "").strip()
        if global_image:
            character["image"] = global_image

    return character


def _rarity_from_roll(dice_value: int, character_id: int) -> dict:
    seed = ((int(character_id) * 1103515245) + (int(dice_value) * 12345)) & 0xFFFFFFFF
    r = seed % 1000

    if r < 30:
        return {"tier": "MYTHIC", "stars": 5}
    if r < 150:
        return {"tier": "LEGENDARY", "stars": 4}
    if r < 420:
        return {"tier": "EPIC", "stars": 3}
    if r < 760:
        return {"tier": "RARE", "stars": 2}
    return {"tier": "COMMON", "stars": 1}


# =========================================================
# API — DADO
# =========================================================

@app.get("/api/dado/state")
def api_dado_state(
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

    try:
        expire_stale_dice_rolls(refund_pending=True)
    except Exception:
        pass

    state = get_dado_state(user_id) or {}
    recharge = get_next_dado_recharge_info(user_id) or {}
    active = get_active_dice_roll(user_id)

    roll_payload = None
    if active:
        options = active.get("options_json") or []
        dice_value = int(active.get("dice_value") or 0)

        if isinstance(options, str):
            try:
                options = json.loads(options)
            except Exception:
                options = []

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
        "recharge_hours": ["01:00", "04:00", "07:00", "10:00", "13:00", "16:00", "19:00", "22:00"],
    })


@app.post("/api/dado/roll")
async def api_dado_roll(
    payload_body: dict = Body(default={}),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    tg = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload_body or {}).get("uid"),
    )
    user_id = int(tg["user_id"])

    if not _dado_rate_limit(user_id, "roll", 1.4):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=200)

    try:
        expire_stale_dice_rolls(refund_pending=True)
    except Exception:
        pass

    active = get_active_dice_roll(user_id)
    if active:
        active_options = active.get("options_json") or []
        active_dice = int(active.get("dice_value") or 0)

        if isinstance(active_options, str):
            try:
                active_options = json.loads(active_options)
            except Exception:
                active_options = []

        if isinstance(active_options, list) and active_options and len(active_options) == active_dice:
            return JSONResponse({
                "ok": True,
                "reused": True,
                "roll_id": int(active["roll_id"]),
                "dice_value": active_dice,
                "options": active_options,
                "status": active.get("status"),
                "balance": int((get_dado_state(user_id) or {}).get("balance") or 0),
            })

        try:
            cancel_dice_roll(user_id, int(active["roll_id"]), refund=True)
        except Exception:
            pass

    data = _load_local_dado_pool()
    anime_pool = list(data.get("animes_list") or [])
    max_dice_value = _max_dice_value_from_local_pool(anime_pool)

    if max_dice_value <= 0:
        return JSONResponse({
            "ok": False,
            "error": "anime_pool_unavailable",
        }, status_code=200)

    raw_value = random.SystemRandom().randint(1, max_dice_value)

    try:
        options = _pick_random_local_animes(raw_value, anime_pool)
    except Exception:
        return JSONResponse({
            "ok": False,
            "error": "anime_pool_unavailable",
        }, status_code=200)

    if not options:
        return JSONResponse({
            "ok": False,
            "error": "anime_pool_unavailable",
        }, status_code=200)

    dice_value = len(options)

    created = create_dice_roll(user_id, dice_value, options)
    if not created.get("ok"):
        return JSONResponse(created, status_code=200)

    roll = created["roll"]
    balance = int((get_dado_state(user_id) or {}).get("balance") or 0)

    response_options = created.get("options") or options or roll.get("options_json") or []

    if isinstance(response_options, str):
        try:
            response_options = json.loads(response_options)
        except Exception:
            response_options = []

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
async def api_dado_pick(
    payload_body: dict = Body(default={}),
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    tg = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload_body or {}).get("uid"),
    )
    user_id = int(tg["user_id"])

    if not _dado_rate_limit(user_id, "pick", 1.0):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=429)

    try:
        roll_id = int(payload_body.get("roll_id") or 0)
        anime_id = int(payload_body.get("anime_id") or 0)
    except (TypeError, ValueError):
        roll_id = 0
        anime_id = 0

    if roll_id <= 0 or anime_id <= 0:
        raise HTTPException(status_code=400, detail="roll_id/anime_id inválidos")

    picked = await asyncio.to_thread(pick_dice_roll_anime, user_id, roll_id, anime_id)
    if not picked.get("ok"):
        return JSONResponse(picked, status_code=409)

    roll = dict(picked.get("roll") or {})
    already_done = bool(picked.get("already_done"))

    if already_done:
        rewarded_character_id = int(roll.get("rewarded_character_id") or 0)
        selected_anime_id = int(roll.get("selected_anime_id") or anime_id)
        character = await asyncio.to_thread(
            _hydrate_dado_character,
            selected_anime_id,
            rewarded_character_id,
        )
        if rewarded_character_id <= 0 or not character:
            return JSONResponse(
                {"ok": False, "error": "resolved_reward_unavailable"},
                status_code=409,
            )
    else:
        character = await asyncio.to_thread(_pick_random_local_character, anime_id)
        if not character:
            await asyncio.to_thread(cancel_dice_roll, user_id, roll_id, True)
            return JSONResponse(
                {"ok": False, "error": "character_not_found", "refunded": True},
                status_code=409,
            )

        try:
            resolved = await asyncio.to_thread(
                resolve_dice_roll,
                user_id,
                roll_id,
                int(character["id"]),
            )
        except Exception as exc:
            print(f"[dado] falha ao resolver rolagem: {type(exc).__name__}", flush=True)
            await asyncio.to_thread(cancel_dice_roll, user_id, roll_id, True)
            return JSONResponse(
                {"ok": False, "error": "resolve_failed", "refunded": True},
                status_code=500,
            )

        if not resolved.get("ok"):
            await asyncio.to_thread(cancel_dice_roll, user_id, roll_id, True)
            return JSONResponse(
                {**resolved, "refunded": True},
                status_code=409,
            )

        character = await asyncio.to_thread(
            _hydrate_dado_character,
            anime_id,
            int(character["id"]),
        ) or character
        roll = dict(resolved.get("roll") or roll)

    char_id = int(character["id"])
    name = str(character.get("name") or "Personagem")
    image = str(character.get("image") or DADO_BANNER_URL)
    anime_title = str(character.get("anime_title") or "Anime")
    rarity = _rarity_from_roll(int(roll.get("dice_value") or 1), char_id)
    balance = int((await asyncio.to_thread(get_dado_state, user_id) or {}).get("balance") or 0)

    reward_caption = (
        "🎁 <b>VOCÊ GANHOU!</b>\n\n"
        f"🧧 <code>{char_id}</code>. <b>{name}</b>\n"
        f"<i>{anime_title}</i>\n\n"
        "📦 <b>Adicionado à sua coleção!</b>"
    )

    try:
        from utils.telegram_outbox import enqueue_photo

        await asyncio.to_thread(
            enqueue_photo,
            dedupe_key=f"dado:{user_id}:{roll_id}",
            chat_id=user_id,
            photo=image,
            caption=reward_caption,
            parse_mode="HTML",
        )
    except Exception as exc:
        print(f"[dado] falha ao enfileirar entrega no chat: {type(exc).__name__}", flush=True)
        try:
            await _tg_send_photo(chat_id=user_id, photo=image, caption=reward_caption)
        except Exception as send_exc:
            print(f"[dado] falha no fallback de entrega: {type(send_exc).__name__}", flush=True)

    return JSONResponse({
        "ok": True,
        "already_done": already_done,
        "roll_id": roll_id,
        "balance": balance,
        "character": {
            "id": char_id,
            "name": name,
            "image": image,
            "anime_title": anime_title,
            "anime_cover": character.get("anime_cover") or _build_cover_from_anilist(anime_id),
            "tier": rarity["tier"],
            "stars": rarity["stars"],
        },
    })


# =========================================================
# PAGE — /dado
# =========================================================

@app.get("/dado", response_class=HTMLResponse)
def dado_page(uid: int = Query(default=0)):
    return HTMLResponse(
        build_dado_page_html(
            uid=int(uid or 0),
            banner_url=DADO_BANNER_URL,
        )
    )


# =========================================================
# MENU WEBAPP — BLOCO COMPLETO
# Cole no seu webapp.py
# =========================================================

from database import (
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
)

from cards_service import get_character_by_id


MENU_BANNER_URL = os.getenv(
    "MENU_BANNER_URL",
    TOP_BANNER_URL,
).strip()

MENU_BACKGROUND_URL = os.getenv(
    "MENU_BACKGROUND_URL",
    BACKGROUND_URL or "",
).strip()

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


def _valid_menu_nickname(nickname: str) -> bool:
    nickname = (nickname or "").strip()
    return bool(re.match(r"^[A-Z][A-Za-z0-9_]{3,16}$", nickname))


def _menu_user_payload(uid: int) -> Dict[str, Any]:
    create_or_get_user(uid)

    user = get_user_status(uid) or {}
    progress = get_progress_row(uid) or {}
    settings = get_profile_settings(uid) or {}
    cards_data, qty_by_char, subcategory_map = _collection_snapshot(uid)
    cards = _collection_cards_from_snapshot(cards_data, qty_by_char, subcategory_map)

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
                    "image": _web_image_url(ch.get("image")),
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
        if cid <= 0 or qty <= 0:
            continue

        try:
            ch = get_character_by_id(cid)
        except Exception:
            ch = None

        if not ch:
            continue

        out.append({
            "id": cid,
            "name": str(ch.get("name") or "").strip(),
            "anime": str(ch.get("anime") or "").strip(),
            "image": _web_image_url(ch.get("image")),
            "quantity": qty,
        })

    out.sort(key=lambda x: ((x["anime"] or "").lower(), (x["name"] or "").lower(), int(x["id"])))
    return out


MENU_HTML = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
<title>Menu</title>
<style>
  :root{
    --bg:#050712;
    --card:rgba(255,255,255,0.05);
    --stroke:rgba(255,255,255,0.10);
    --stroke2:rgba(255,255,255,0.18);
    --txt:rgba(255,255,255,0.94);
    --muted:rgba(255,255,255,0.58);
    --accent:#4f8cff;
    --danger:#ff5f57;
    --ok:#4ade80;
    --shadow:0 18px 36px rgba(0,0,0,.42);
  }

  *{box-sizing:border-box}
  html,body{height:100%}
  body{
    margin:0;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    color:var(--txt);
    background:
      linear-gradient(180deg, rgba(0,0,0,.48), rgba(0,0,0,.78)),
      url("__MENU_BG__") center/cover no-repeat fixed,
      radial-gradient(900px 520px at 50% -10%, rgba(79,140,255,.18), transparent 55%),
      #050712;
    overflow-x:hidden;
  }

  body:before{
    content:"";
    position:fixed; inset:0;
    background-image: radial-gradient(rgba(255,255,255,0.05) 1px, transparent 1px);
    background-size:42px 42px;
    opacity:.12;
    pointer-events:none;
  }

  .wrap{
    position:relative;
    z-index:1;
    max-width:860px;
    margin:0 auto;
    padding:16px 14px 40px;
  }

  .hero{
    position:relative;
    width:100%;
    border-radius:28px;
    overflow:hidden;
    border:1px solid var(--stroke);
    background:#111;
    box-shadow:var(--shadow);
  }

  .hero img{
    width:100%;
    height:190px;
    object-fit:cover;
    display:block;
    opacity:.9;
  }

  .hero:after{
    content:"";
    position:absolute; inset:0;
    background:linear-gradient(180deg, rgba(0,0,0,.04), rgba(0,0,0,.74));
  }

  .profile{
    position:relative;
    z-index:2;
    margin-top:-48px;
    display:flex;
    flex-direction:column;
    align-items:center;
  }

  .avatar{
    width:106px; height:106px;
    border-radius:50%;
    border:4px solid rgba(255,255,255,.08);
    background:#111722;
    overflow:hidden;
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:34px;
    font-weight:900;
    box-shadow:0 18px 34px rgba(0,0,0,.38);
  }

  .avatar img{
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
  }

  .name{
    margin-top:14px;
    font-size:30px;
    font-weight:900;
    line-height:1.1;
    text-align:center;
  }

  .sub{
    margin-top:6px;
    color:var(--muted);
    font-size:15px;
    text-align:center;
  }

  .stats{
    margin-top:22px;
    display:grid;
    grid-template-columns:repeat(2,1fr);
    gap:12px;
  }

  .stat{
    border:1px solid var(--stroke);
    background:var(--card);
    border-radius:24px;
    padding:18px;
    box-shadow:var(--shadow);
  }

  .statLabel{
    color:var(--muted);
    font-size:13px;
    letter-spacing:.08em;
    text-transform:uppercase;
    font-weight:800;
  }

  .statValue{
    margin-top:8px;
    font-size:24px;
    font-weight:900;
  }

  .sectionTitle{
    margin:28px 4px 12px;
    font-size:18px;
    font-weight:900;
    letter-spacing:.02em;
  }

  .list{
    display:flex;
    flex-direction:column;
    gap:12px;
  }

  .row{
    border:1px solid var(--stroke);
    background:var(--card);
    border-radius:24px;
    padding:18px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:14px;
    box-shadow:var(--shadow);
  }

  .rowLeft{
    display:flex;
    flex-direction:column;
    gap:6px;
    min-width:0;
  }

  .rowTitle{
    font-size:18px;
    font-weight:800;
    line-height:1.15;
  }

  .rowSub{
    color:var(--muted);
    font-size:14px;
    line-height:1.35;
  }

  .btn,
  select,
  input{
    border:1px solid var(--stroke);
    background:rgba(255,255,255,.06);
    color:var(--txt);
    border-radius:16px;
    padding:12px 14px;
    font-weight:800;
    outline:none;
  }

  .btn{
    cursor:pointer;
    min-width:118px;
  }

  .btn:hover{
    border-color:var(--stroke2);
  }

  .btnDanger{
    border-color:rgba(255,95,87,.32);
    background:rgba(255,95,87,.12);
    color:#ffd8d6;
  }

  .btnAccent{
    border-color:rgba(79,140,255,.30);
    background:rgba(79,140,255,.14);
  }

  .nicknameBox{
    display:flex;
    gap:10px;
    flex-wrap:wrap;
    justify-content:flex-end;
    width:100%;
    max-width:340px;
  }

  .nicknameBox input{
    flex:1;
    min-width:180px;
  }

  .msg{
    margin-top:14px;
    min-height:20px;
    color:var(--muted);
    font-size:14px;
  }

  .modalWrap{
    position:fixed;
    inset:0;
    display:none;
    align-items:flex-end;
    justify-content:center;
    background:rgba(0,0,0,.52);
    z-index:9999;
    padding:16px;
  }

  .modal{
    width:100%;
    max-width:760px;
    max-height:78vh;
    overflow:hidden;
    border:1px solid var(--stroke);
    background:#0d1320;
    border-radius:26px;
    box-shadow:0 24px 48px rgba(0,0,0,.52);
    display:flex;
    flex-direction:column;
  }

  .modalHead{
    padding:16px;
    border-bottom:1px solid var(--stroke);
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:10px;
  }

  .modalTitle{
    font-size:18px;
    font-weight:900;
  }

  .modalBody{
    padding:14px;
    overflow:auto;
  }

  .favSearch{
    width:100%;
    margin-bottom:12px;
  }

  .favList{
    display:flex;
    flex-direction:column;
    gap:10px;
  }

  .favItem{
    border:1px solid var(--stroke);
    background:rgba(255,255,255,.04);
    border-radius:20px;
    padding:12px;
    display:flex;
    align-items:center;
    gap:12px;
  }

  .favThumb{
    width:62px;
    height:62px;
    border-radius:16px;
    overflow:hidden;
    background:#121825;
    flex:0 0 auto;
  }

  .favThumb img{
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
  }

  .favMeta{
    min-width:0;
    flex:1;
  }

  .favName{
    font-size:16px;
    font-weight:900;
    line-height:1.15;
  }

  .favAnime{
    margin-top:4px;
    color:var(--muted);
    font-size:13px;
  }

  .footer{
    margin-top:18px;
    text-align:center;
    color:rgba(255,255,255,.42);
    font-size:12px;
    font-weight:700;
    letter-spacing:.08em;
  }

  @media (max-width: 720px){
    .stats{ grid-template-columns:1fr 1fr; }
    .row{ flex-direction:column; align-items:stretch; }
    .nicknameBox{ max-width:none; }
    .btn, select, input{ width:100%; }
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <img src="__MENU_BANNER__" alt="Banner">
  </div>

  <div class="profile">
    <div class="avatar" id="avatar">SB</div>
    <div class="name" id="name">Carregando...</div>
    <div class="sub" id="subtitle">...</div>
  </div>

  <div class="stats">
    <div class="stat">
      <div class="statLabel">Coleção</div>
      <div class="statValue" id="collectionTotal">0</div>
    </div>
    <div class="stat">
      <div class="statLabel">Coins</div>
      <div class="statValue" id="coins">0</div>
    </div>
    <div class="stat">
      <div class="statLabel">Nível</div>
      <div class="statValue" id="level">1</div>
    </div>
    <div class="stat">
      <div class="statLabel">Favorito</div>
      <div class="statValue" id="favoriteName">—</div>
    </div>
  </div>

  <div class="sectionTitle">Perfil</div>
  <div class="list">
    <div class="row">
      <div class="rowLeft">
        <div class="rowTitle">Nickname</div>
        <div class="rowSub">Único, começa com maiúscula e não pode ser alterado depois.</div>
      </div>
      <div class="nicknameBox">
        <input id="nicknameInput" placeholder="Ex: Zoro" maxlength="17" />
        <button class="btn btnAccent" id="saveNicknameBtn">Salvar</button>
      </div>
    </div>

    <div class="row">
      <div class="rowLeft">
        <div class="rowTitle">Favoritar personagem</div>
        <div class="rowSub">Só pode escolher personagens da sua própria coleção.</div>
      </div>
      <button class="btn" id="favoriteBtn">Escolher</button>
    </div>
  </div>

  <div class="sectionTitle">Preferências</div>
  <div class="list">
    <div class="row">
      <div class="rowLeft">
        <div class="rowTitle">Bandeira</div>
        <div class="rowSub">Defina seu país.</div>
      </div>
      <select id="countrySelect"></select>
    </div>

    <div class="row">
      <div class="rowLeft">
        <div class="rowTitle">Idioma</div>
        <div class="rowSub">Idioma principal da conta.</div>
      </div>
      <select id="languageSelect"></select>
    </div>

    <div class="row">
      <div class="rowLeft">
        <div class="rowTitle">Perfil privado</div>
        <div class="rowSub">Oculta o perfil para outros usuários.</div>
      </div>
      <button class="btn" id="privacyBtn">Desativado</button>
    </div>

    <div class="row">
      <div class="rowLeft">
        <div class="rowTitle">Notificações</div>
        <div class="rowSub">Avisar quando os 24 dados acumularem.</div>
      </div>
      <button class="btn" id="notificationsBtn">Ativado</button>
    </div>
  </div>

  <div class="sectionTitle">Conta</div>
  <div class="list">
    <div class="row">
      <div class="rowLeft">
        <div class="rowTitle">Autoexcluir conta</div>
        <div class="rowSub">Apaga nickname, coleção, nível, coins e preferências.</div>
      </div>
      <button class="btn btnDanger" id="deleteBtn">Excluir conta</button>
    </div>
  </div>

  <div class="msg" id="msg"></div>
  <div class="footer">Source Baltigo • Menu do usuário</div>
</div>

<div class="modalWrap" id="favoriteModalWrap">
  <div class="modal">
    <div class="modalHead">
      <div class="modalTitle">Escolher favorito</div>
      <button class="btn" id="closeFavoriteModalBtn">Fechar</button>
    </div>
    <div class="modalBody">
      <input class="favSearch" id="favSearchInput" placeholder="Buscar personagem..." />
      <div class="favList" id="favList"></div>
    </div>
  </div>
</div>

<script>
const uid = __UID__;
const msg = document.getElementById("msg");
const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
if (tg) { try { tg.ready(); } catch(e) {} }

let profileData = null;
let favoriteCharacters = [];

function setMsg(text) {
  msg.textContent = text || "";
}

async function getJson(url) {
  const res = await fetch(url + (url.includes("?") ? "&" : "?") + "_ts=" + Date.now());
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error((data && data.message) || "Erro");
  }
  return data;
}

async function postJson(url, payload) {
  const res = await fetch(url + "?_ts=" + Date.now(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error((data && data.message) || "Erro");
  }
  return data;
}

function renderAvatar(profile) {
  const avatar = document.getElementById("avatar");
  if (profile.favorite && profile.favorite.image) {
    avatar.innerHTML = '<img src="' + profile.favorite.image + '" alt="avatar">';
    return;
  }
  const name = (profile.display_name || "SB").trim();
  const initials = name.slice(0, 2).toUpperCase();
  avatar.textContent = initials;
}

function renderProfile(data) {
  profileData = data.profile || {};
  const p = profileData;

  document.getElementById("name").textContent = p.display_name || "User";
  document.getElementById("subtitle").textContent = p.nickname ? ("@" + p.nickname) : "Sem nickname";
  document.getElementById("collectionTotal").textContent = String(p.collection_total || 0);
  document.getElementById("coins").textContent = String(p.coins || 0);
  document.getElementById("level").textContent = String(p.level || 1);
  document.getElementById("favoriteName").textContent = p.favorite ? p.favorite.name : "—";

  renderAvatar(p);

  const nickInput = document.getElementById("nicknameInput");
  const nickBtn = document.getElementById("saveNicknameBtn");

  nickInput.value = p.nickname || "";
  nickInput.disabled = !!p.nickname;
  nickBtn.disabled = !!p.nickname;

  const country = document.getElementById("countrySelect");
  country.innerHTML = "";
  (data.countries || []).forEach(c => {
    const opt = document.createElement("option");
    opt.value = c.code;
    opt.textContent = c.flag + " " + c.name;
    if (c.code === p.country_code) opt.selected = true;
    country.appendChild(opt);
  });

  const lang = document.getElementById("languageSelect");
  lang.innerHTML = "";
  (data.languages || []).forEach(l => {
    const opt = document.createElement("option");
    opt.value = l.code;
    opt.textContent = l.name;
    if (l.code === p.language) opt.selected = true;
    lang.appendChild(opt);
  });

  document.getElementById("privacyBtn").textContent = p.private_profile ? "Ativado" : "Desativado";
  document.getElementById("notificationsBtn").textContent = p.notifications_enabled ? "Ativado" : "Desativado";
}

async function loadProfile() {
  const data = await getJson("/api/menu/profile?uid=" + uid);
  renderProfile(data);
}

function openFavoriteModal() {
  document.getElementById("favoriteModalWrap").style.display = "flex";
}

function closeFavoriteModal() {
  document.getElementById("favoriteModalWrap").style.display = "none";
}

function renderFavoriteList(items) {
  const wrap = document.getElementById("favList");
  wrap.innerHTML = "";

  if (!items.length) {
    wrap.innerHTML = '<div class="rowSub">Você ainda não tem personagens na coleção.</div>';
    return;
  }

  for (const item of items) {
    const el = document.createElement("div");
    el.className = "favItem";

    el.innerHTML = `
      <div class="favThumb">${item.image ? `<img src="${item.image}" alt="">` : ""}</div>
      <div class="favMeta">
        <div class="favName">🧧 ${item.name}</div>
        <div class="favAnime">${item.anime || ""}</div>
      </div>
      <button class="btn btnAccent">Favoritar</button>
    `;

    el.querySelector("button").onclick = async () => {
      try {
        setMsg("Salvando favorito...");
        await postJson("/api/menu/favorite", { uid, character_id: item.id });
        setMsg("✅ Favorito atualizado.");
        closeFavoriteModal();
        await loadProfile();
      } catch (e) {
        setMsg("❌ " + e.message);
      }
    };

    wrap.appendChild(el);
  }
}

async function loadFavoriteCharacters() {
  const data = await getJson("/api/menu/collection-characters?uid=" + uid);
  favoriteCharacters = data.items || [];
  renderFavoriteList(favoriteCharacters);
}

document.getElementById("favoriteBtn").onclick = async () => {
  try {
    setMsg("");
    await loadFavoriteCharacters();
    openFavoriteModal();
  } catch (e) {
    setMsg("❌ " + e.message);
  }
};

document.getElementById("closeFavoriteModalBtn").onclick = closeFavoriteModal;
document.getElementById("favoriteModalWrap").onclick = (e) => {
  if (e.target.id === "favoriteModalWrap") closeFavoriteModal();
};

document.getElementById("favSearchInput").addEventListener("input", (e) => {
  const q = (e.target.value || "").trim().toLowerCase();
  const filtered = favoriteCharacters.filter(item => {
    const hay = (item.name + " " + item.anime).toLowerCase();
    return hay.includes(q);
  });
  renderFavoriteList(filtered);
});

document.getElementById("saveNicknameBtn").onclick = async () => {
  try {
    const nickname = document.getElementById("nicknameInput").value.trim();
    setMsg("Salvando nickname...");
    await postJson("/api/menu/nickname", { uid, nickname });
    setMsg("✅ Nickname salvo com sucesso.");
    await loadProfile();
  } catch (e) {
    setMsg("❌ " + e.message);
  }
};

document.getElementById("countrySelect").onchange = async (e) => {
  try {
    await postJson("/api/menu/country", { uid, country_code: e.target.value });
    setMsg("✅ Bandeira atualizada.");
  } catch (e) {
    setMsg("❌ " + e.message);
  }
};

document.getElementById("languageSelect").onchange = async (e) => {
  try {
    await postJson("/api/menu/language", { uid, language: e.target.value });
    setMsg("✅ Idioma atualizado.");
  } catch (e) {
    setMsg("❌ " + e.message);
  }
};

document.getElementById("privacyBtn").onclick = async () => {
  try {
    const current = document.getElementById("privacyBtn").textContent === "Ativado";
    await postJson("/api/menu/privacy", { uid, value: !current });
    setMsg("✅ Privacidade atualizada.");
    await loadProfile();
  } catch (e) {
    setMsg("❌ " + e.message);
  }
};

document.getElementById("notificationsBtn").onclick = async () => {
  try {
    const current = document.getElementById("notificationsBtn").textContent === "Ativado";
    await postJson("/api/menu/notifications", { uid, value: !current });
    setMsg("✅ Notificações atualizadas.");
    await loadProfile();
  } catch (e) {
    setMsg("❌ " + e.message);
  }
};

document.getElementById("deleteBtn").onclick = async () => {
  const ok = confirm("Tem certeza que deseja excluir sua conta? Essa ação é irreversível.");
  if (!ok) return;

  try {
    setMsg("Excluindo conta...");
    await postJson("/api/menu/delete-account", { uid });
    setMsg("✅ Conta excluída com sucesso.");
    if (tg) {
      try { tg.close(); } catch (e) {}
    }
  } catch (e) {
    setMsg("❌ " + e.message);
  }
};

(async () => {
  try {
    await loadProfile();
  } catch (e) {
    setMsg("❌ " + e.message);
  }
})();
</script>
</body>
</html>
"""


@app.get("/menu", response_class=HTMLResponse)
def menu_page(uid: int = Query(...)):
    return HTMLResponse(
        build_menu_page_html(
            uid=int(uid),
            menu_banner_url=MENU_BANNER_URL,
        )
    )


@app.get("/api/menu/profile")
def api_menu_profile(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    return JSONResponse(_menu_user_payload(int(ctx["user_id"])))


@app.get("/api/menu/collection-characters")
def api_menu_collection_characters(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    return JSONResponse({
        "ok": True,
        "items": _menu_collection_characters(int(ctx["user_id"])),
    })


@app.post("/api/menu/nickname")
def api_menu_nickname(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    user_id = int(ctx["user_id"])
    nickname = str(payload.get("nickname") or "").strip()

    if not _valid_menu_nickname(nickname):
        return JSONResponse({
            "ok": False,
            "message": "Nickname inválido. Use 4-17 caracteres, começando com letra maiúscula.",
        }, status_code=400)

    result = set_profile_nickname(user_id, nickname)
    if not result.get("ok"):
        error = result.get("error")
        if error == "nickname_locked":
            return JSONResponse({"ok": False, "message": "Você já definiu seu nickname."}, status_code=400)
        if error == "nickname_taken":
            return JSONResponse({"ok": False, "message": "Esse nickname já está em uso."}, status_code=409)
        return JSONResponse({"ok": False, "message": "Não foi possível salvar o nickname."}, status_code=400)

    return {"ok": True}


@app.post("/api/menu/favorite")
def api_menu_favorite(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    user_id = int(ctx["user_id"])
    try:
        character_id = int(payload.get("character_id") or 0)
    except (TypeError, ValueError):
        character_id = 0
    if character_id <= 0:
        return JSONResponse({"ok": False, "message": "Personagem inválido."}, status_code=400)

    owned_ids = {int(item["id"]) for item in _menu_collection_characters(user_id)}
    if character_id not in owned_ids:
        return JSONResponse({
            "ok": False,
            "message": "Você só pode favoritar personagens da sua coleção.",
        }, status_code=403)

    set_profile_favorite(user_id, character_id)
    return {"ok": True}


@app.post("/api/menu/country")
def api_menu_country(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    user_id = int(ctx["user_id"])
    country_code = str(payload.get("country_code") or "BR").strip().upper()

    if country_code not in {country["code"] for country in COUNTRY_OPTIONS}:
        return JSONResponse({"ok": False, "message": "País inválido."}, status_code=400)

    set_profile_country(user_id, country_code)
    return {"ok": True}


@app.post("/api/menu/language")
def api_menu_language(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    user_id = int(ctx["user_id"])
    language = str(payload.get("language") or "pt").strip().lower()

    if language not in {"pt", "en", "es"}:
        return JSONResponse({"ok": False, "message": "Idioma inválido."}, status_code=400)

    set_profile_language(user_id, language)
    return {"ok": True}


@app.post("/api/menu/privacy")
def api_menu_privacy(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    value = payload.get("value")
    if not isinstance(value, bool):
        return JSONResponse({"ok": False, "message": "Valor de privacidade inválido."}, status_code=400)

    set_profile_private(int(ctx["user_id"]), value)
    return {"ok": True}


@app.post("/api/menu/notifications")
def api_menu_notifications(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    value = payload.get("value")
    if not isinstance(value, bool):
        return JSONResponse({"ok": False, "message": "Valor de notificação inválido."}, status_code=400)

    set_profile_notifications(int(ctx["user_id"]), value)
    return {"ok": True}


@app.post("/api/menu/delete-account")
def api_menu_delete_account(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    delete_user_account(int(ctx["user_id"]))
    return {"ok": True}

# =========================================================
# SHOP — HELPERS
# =========================================================

SHOP_PREVIEW_IMAGE = "https://photo.chelpbot.me/AgACAgQAAxkBZqZjcmmff-LPn4H7y3EsyO0G_rk8AAHTWgACBw5rG0eL9VAWyQkpU35BaAEAAwIAA3kAAzoE/photo.jpg"


def _shop_rate_limit(user_id: int, key: str, window: float = 1.0) -> bool:
    return _webapp_rate_limit(user_id, f"shop:{key}", window)


def _shop_collection_items(user_id: int, q: str = "") -> List[Dict[str, Any]]:
    from database import get_user_card_collection
    from cards_service import build_cards_final_data

    raw_rows = get_user_card_collection(int(user_id)) or []
    data = build_cards_final_data()
    chars_by_id = data.get("characters_by_id") or {}

    qn = (q or "").strip().lower()
    out: List[Dict[str, Any]] = []

    for row in raw_rows:
        char_id = int(row.get("character_id") or 0)
        qty = int(row.get("quantity") or 0)
        if char_id <= 0 or qty <= 0:
            continue

        meta = chars_by_id.get(char_id) or {}

        name = str(meta.get("name") or f"Personagem {char_id}")
        anime = str(meta.get("anime") or "Sem anime")
        image = _web_image_url(meta.get("image"))
        rarity = str(meta.get("subcategory") or meta.get("role") or "").strip().upper()

        if qn:
            joined = f"{char_id} {name} {anime}".lower()
            if qn not in joined:
                continue

        out.append({
            "character_id": char_id,
            "character_name": name,
            "anime_title": anime,
            "image": image,
            "quantity": qty,
            "rarity": rarity,
        })

    out.sort(key=lambda x: (x["anime_title"].lower(), x["character_name"].lower(), x["character_id"]))
    return out


def _shop_parse_bp_value(card: Dict[str, Any]) -> int:
    raw_value = card.get("bp_value")
    try:
        if raw_value is not None and str(raw_value).strip() != "":
            return int(raw_value)
    except Exception:
        pass

    text = str(
        ((card.get("pt_br") or {}).get("pa"))
        or card.get("bp")
        or ""
    ).strip()
    match = re.search(r"\d+", text.replace(".", "").replace(",", ""))
    if not match:
        return 0
    try:
        return int(match.group(0))
    except Exception:
        return 0


def _shop_serialize_xcard_offer(
    offer: Dict[str, Any],
    purchase_map: Dict[str, Dict[str, Any]],
    current_level: int,
) -> Dict[str, Any]:
    from xcards_service import get_xcard_by_id

    slot_code = str(offer.get("slot_code") or "").strip()
    slot_group = str(offer.get("slot_group") or "normal").strip().lower()
    card = get_xcard_by_id(int(offer.get("card_id") or 0)) or {}
    pt_br = card.get("pt_br") if isinstance(card.get("pt_br"), dict) else {}
    rarity = str(card.get("rarity") or "").strip().upper()
    is_alt_art = bool(card.get("alt_art"))
    purchased = purchase_map.get(slot_code.lower()) or {}
    purchased_at = purchased.get("purchased_at")
    if purchased_at is None:
        purchased_at_iso = ""
    elif hasattr(purchased_at, "isoformat"):
        purchased_at_iso = purchased_at.isoformat()
    else:
        purchased_at_iso = str(purchased_at).strip()
    level_required = int(offer.get("level_required") or 1)
    price = int(offer.get("price") or 0)
    bp_value = _shop_parse_bp_value(card)
    generated_energy = [
        str(item or "").strip()
        for item in (pt_br.get("energia_gerada") or card.get("generated_energy") or [])
        if str(item or "").strip()
    ]
    affinities = [
        str(item or "").strip()
        for item in (pt_br.get("afinidades") or card.get("affinities") or [])
        if str(item or "").strip()
    ]
    effect_keywords = [
        str(item or "").strip()
        for item in (pt_br.get("keywords_efeito") or card.get("effect_keywords") or [])
        if str(item or "").strip()
    ]
    trigger_keywords = [
        str(item or "").strip()
        for item in (pt_br.get("keywords_acionar") or card.get("trigger_keywords") or [])
        if str(item or "").strip()
    ]

    return {
        "slot_code": slot_code,
        "slot_group": slot_group,
        "slot_group_label": {
            "normal": "Normal",
            "rare": "Raro",
            "special": "Especial",
        }.get(slot_group, "Normal"),
        "display_order": int(offer.get("display_order") or 0),
        "price": price,
        "level_required": level_required,
        "locked": int(current_level or 1) < level_required,
        "purchased": bool(purchased),
        "purchased_at": purchased_at_iso,
        "price_paid": int(purchased.get("price_paid") or 0),
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


def _collection_character_subcategory_map(data: Dict[str, Any]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for raw_name, chars in (data.get("subcategories") or {}).items():
        label = str(raw_name or "").strip()
        if not label:
            continue
        for char in chars or []:
            try:
                cid = int((char or {}).get("id") or 0)
            except Exception:
                cid = 0
            if cid > 0 and cid not in out:
                out[cid] = label
    return out


def _collection_snapshot(user_id: int) -> Tuple[Dict[str, Any], Dict[int, int], Dict[int, str]]:
    from database import get_user_card_collection
    from cards_service import build_cards_final_data

    data = build_cards_final_data()
    raw_rows = get_user_card_collection(int(user_id)) or []
    qty_by_char: Dict[int, int] = {}

    for row in raw_rows:
        try:
            cid = int(row.get("character_id") or 0)
            qty = int(row.get("quantity") or 0)
        except Exception:
            continue
        if cid <= 0 or qty <= 0:
            continue
        qty_by_char[cid] = qty_by_char.get(cid, 0) + qty

    return data, qty_by_char, _collection_character_subcategory_map(data)


def _collection_profile_payload(user_id: int, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = _menu_user_payload(int(user_id))
    profile = dict((data or {}).get("profile") or {})

    username = str((ctx or {}).get("username") or profile.get("username") or "").strip()
    full_name = str((ctx or {}).get("full_name") or "").strip()
    display_name = str(profile.get("display_name") or "").strip()

    if not display_name:
        display_name = full_name or (f"@{username}" if username else f"User {user_id}")

    profile["user_id"] = int(user_id)
    profile["username"] = username
    profile["full_name"] = full_name
    profile["display_name"] = display_name
    return profile


def _collection_cards_from_snapshot(
    data: Dict[str, Any],
    qty_by_char: Dict[int, int],
    subcategory_map: Dict[int, str],
) -> List[Dict[str, Any]]:
    chars_by_id = data.get("characters_by_id") or {}
    items: List[Dict[str, Any]] = []

    for cid, qty in qty_by_char.items():
        meta = chars_by_id.get(int(cid)) or {}
        if not meta:
            continue

        items.append({
            "character_id": int(cid),
            "quantity": int(qty),
            "name": str(meta.get("name") or f"Personagem {cid}"),
            "anime_id": int(meta.get("anime_id") or 0),
            "anime": str(meta.get("anime") or "Obra desconhecida"),
            "image": _web_image_url(meta.get("image")),
            "subcategory": str(subcategory_map.get(int(cid)) or "").strip(),
        })

    items.sort(key=lambda x: (x["anime"].lower(), x["name"].lower(), int(x["character_id"])))
    return items


def _collection_animes_from_snapshot(
    data: Dict[str, Any],
    qty_by_char: Dict[int, int],
) -> List[Dict[str, Any]]:
    chars_by_anime = data.get("characters_by_anime") or {}
    animes_by_id = data.get("animes_by_id") or {}
    anime_owned: Dict[int, set] = {}

    for cid, qty in qty_by_char.items():
        if qty <= 0:
            continue
        meta = (data.get("characters_by_id") or {}).get(int(cid)) or {}
        anime_id = int(meta.get("anime_id") or 0)
        if anime_id <= 0:
            continue
        anime_owned.setdefault(anime_id, set()).add(int(cid))

    items: List[Dict[str, Any]] = []
    for anime_id, owned_ids in anime_owned.items():
        chars = list(chars_by_anime.get(int(anime_id)) or [])
        if not chars:
            continue

        anime_meta = dict(animes_by_id.get(int(anime_id)) or {})
        anime_name = str(anime_meta.get("anime") or chars[0].get("anime") or f"Obra {anime_id}")
        total_count = len(chars)
        owned_count = len(owned_ids)
        missing_count = max(0, total_count - owned_count)
        completion_pct = int(round((owned_count / total_count) * 100)) if total_count else 0

        items.append({
            "anime_id": int(anime_id),
            "anime": anime_name,
            "owned_count": int(owned_count),
            "total_count": int(total_count),
            "missing_count": int(missing_count),
            "completion_pct": int(completion_pct),
            "cover_image": _web_image_url(anime_meta.get("cover_image") or anime_meta.get("banner_image")),
            "banner_image": _web_image_url(anime_meta.get("banner_image") or anime_meta.get("cover_image")),
        })

    items.sort(key=lambda x: (x["anime"].lower(), int(x["anime_id"])))
    return items


def _collection_detail_from_snapshot(
    data: Dict[str, Any],
    qty_by_char: Dict[int, int],
    subcategory_map: Dict[int, str],
    anime_id: int,
    mode: str,
) -> Optional[Dict[str, Any]]:
    anime_id = int(anime_id or 0)
    if anime_id <= 0:
        return None

    chars = list((data.get("characters_by_anime") or {}).get(anime_id) or [])
    if not chars:
        return None

    anime_meta = dict((data.get("animes_by_id") or {}).get(anime_id) or {})
    anime_name = str(anime_meta.get("anime") or chars[0].get("anime") or f"Obra {anime_id}")

    gallery_items: List[Dict[str, Any]] = []
    owned_items: List[Dict[str, Any]] = []
    missing_items: List[Dict[str, Any]] = []

    for meta in chars:
        cid = int(meta.get("id") or 0)
        qty = int(qty_by_char.get(cid) or 0)
        base = {
            "id": cid,
            "character_id": cid,
            "name": str(meta.get("name") or f"Personagem {cid}"),
            "anime_id": anime_id,
            "anime": anime_name,
            "image": _web_image_url(meta.get("image")),
            "subcategory": str(subcategory_map.get(cid) or "").strip(),
            "quantity": qty,
            "owned": qty > 0,
        }
        gallery_items.append(base)
        if qty > 0:
            owned_items.append(base)
        else:
            missing_items.append(base)

    gallery_items.sort(key=lambda x: (x["name"].lower(), int(x["id"])))
    owned_items.sort(key=lambda x: (x["name"].lower(), int(x["id"])))
    missing_items.sort(key=lambda x: (x["name"].lower(), int(x["id"])))

    mode_key = str(mode or "owned").strip().lower()
    if mode_key not in {"owned", "missing", "gallery"}:
        mode_key = "owned"

    items_map = {
        "owned": owned_items,
        "missing": missing_items,
        "gallery": gallery_items,
    }

    return {
        "anime": {
            "anime_id": anime_id,
            "anime": anime_name,
            "cover_image": _web_image_url(anime_meta.get("cover_image") or anime_meta.get("banner_image")),
            "banner_image": _web_image_url(anime_meta.get("banner_image") or anime_meta.get("cover_image")),
        },
        "mode": mode_key,
        "items": items_map[mode_key],
        "owned_count": len(owned_items),
        "total_count": len(gallery_items),
        "missing_count": len(missing_items),
        "completion_pct": int(round((len(owned_items) / len(gallery_items)) * 100)) if gallery_items else 0,
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


@app.get("/api/collection/state")
def api_collection_state(
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

    data, qty_by_char, subcategory_map = _collection_snapshot(user_id)
    cards_items = _collection_cards_from_snapshot(data, qty_by_char, subcategory_map)
    anime_items = _collection_animes_from_snapshot(data, qty_by_char)
    profile = _collection_profile_payload(user_id, ctx=ctx)
    profile["collection_total"] = len(cards_items)

    return JSONResponse({
        "ok": True,
        "profile": profile,
        "stats": {
            "unique_cards": len(cards_items),
            "total_copies": sum(int(item.get("quantity") or 0) for item in cards_items),
            "completed_animes": sum(
                1
                for item in anime_items
                if int(item.get("total_count") or 0) > 0 and int(item.get("missing_count") or 0) <= 0
            ),
            "active_animes": len(anime_items),
            "favorite_name": str(((profile.get("favorite") or {}).get("name") or "")).strip() or "--",
        },
    })


@app.get("/api/collection/cards")
def api_collection_cards(
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

    data, qty_by_char, subcategory_map = _collection_snapshot(user_id)
    return JSONResponse({
        "ok": True,
        "items": _collection_cards_from_snapshot(data, qty_by_char, subcategory_map),
    })


@app.get("/api/collection/animes")
def api_collection_animes(
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

    data, qty_by_char, _ = _collection_snapshot(user_id)
    return JSONResponse({
        "ok": True,
        "items": _collection_animes_from_snapshot(data, qty_by_char),
    })


@app.get("/api/collection/anime")
def api_collection_anime(
    anime_id: int = Query(..., ge=1),
    mode: str = Query(default="owned"),
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

    data, qty_by_char, subcategory_map = _collection_snapshot(user_id)
    payload = _collection_detail_from_snapshot(
        data,
        qty_by_char,
        subcategory_map,
        anime_id=anime_id,
        mode=mode,
    )
    if not payload:
        return JSONResponse({"ok": False, "message": "Obra nao encontrada."}, status_code=404)
    return JSONResponse({"ok": True, **payload})


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


@app.get("/cccolecao", response_class=HTMLResponse)
def collection_webapp_page(uid: int = Query(default=0)):
    return HTMLResponse(
        build_collection_page_html(
            uid=int(uid or 0),
            banner_url=CARDS_TOP_BANNER_URL,
        )
    )


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
