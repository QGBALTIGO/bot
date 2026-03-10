import os
import json
import re
import traceback
import asyncio
import time
import httpx
import random
import hashlib
import hmac
from urllib.parse import parse_qsl
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Query, Body, Header, HTTPException
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
    pick_dice_roll_anime,
    resolve_dice_roll,
)

app = FastAPI()

# =========================
# CONFIG — TERMOS
# =========================
TERMS_VERSION = (os.getenv("TERMS_VERSION", "v1").strip() or "v1")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourcerBaltigo").strip()
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/SourcerBaltigo").strip()

TOP_BANNER_URL = os.getenv(
    "TOP_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzS3wWmpl9pZVvh8mUyitl-u56VSkUmPAALrC2sb1ZFIRYO5j8ewhrZJAQADAgADeQADOgQ/photo.jpg",
).strip()

BACKGROUND_URL = os.getenv("BACKGROUND_URL", "").strip()  # URL pública (pode ficar vazio)
EMPTY_BG_DATA_URI = "data:image/gif;base64,R0lGODlhAQABAAAAACw="


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
    u.searchParams.set("_ts", String(Date.now())); // cache-buster forte

    const res = await fetch(u.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
    return HTMLResponse("OK - WebApp online. Use /terms e /catalogo")


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
        print("❌ ERROR /api/terms/accept:", repr(e), flush=True)
        traceback.print_exc()
        return JSONResponse(
            {"ok": False, "message": f"Erro interno: {type(e).__name__}: {e}"},
            status_code=500
        )


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
        print("❌ ERROR /api/terms/decline:", repr(e), flush=True)
        traceback.print_exc()
        return JSONResponse(
            {"ok": False, "message": f"Erro interno: {type(e).__name__}: {e}"},
            status_code=500
        )


@app.post("/api/channel/check")
def api_channel_check(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)

    if not REQUIRED_CHANNEL:
        return {"ok": True}

    if not BOT_TOKEN:
        return JSONResponse({"ok": False, "message": "BOT_TOKEN ausente para verificação."}, status_code=500)

    # Verificação via Telegram Bot API (sem requests)
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        params = {"chat_id": REQUIRED_CHANNEL, "user_id": uid}

        with httpx.Client(timeout=8.0) as client:
            r = client.get(url, params=params)
            data = r.json()

        if not data.get("ok"):
            return {"ok": False}

        result = data.get("result") or {}
        status = (result.get("status") or "").lower()
        is_member = bool(result.get("is_member", False))
        ok = (status in ("creator", "administrator", "member")) or (status == "restricted" and is_member)
        return {"ok": ok}

    except Exception as e:
        print("❌ ERROR /api/channel/check:", repr(e), flush=True)
        return {"ok": False}


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
    # IMPORTANTE: aqui NÃO usa f-string com ${} do JS.
    # A gente usa placeholders e replace, pra nunca mais quebrar.
    html = """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>__CTITLE__ — Source Baltigo</title>

  <style>
    :root {
      --bg0: #070b12;
      --bg1: #0a1220;
      --stroke: rgba(255,255,255,0.10);
      --stroke2: rgba(255,255,255,0.16);
      --txt: rgba(255,255,255,0.92);
      --muted: rgba(255,255,255,0.58);
      --shadow: 0 14px 30px rgba(0,0,0,0.55);
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: -apple-system, system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      color: var(--txt);
      background: radial-gradient(1200px 600px at 50% -10%, rgba(90,168,255,0.18), transparent 55%),
                  linear-gradient(180deg, var(--bg0), var(--bg1));
      overflow-x: hidden;
    }

    .bg-pattern {
      position: fixed;
      inset: 0;
      background-image: url("__BPATTERN__");
      background-size: 520px;
      background-repeat: repeat;
      opacity: 0.10;
      filter: grayscale(1) contrast(1.1);
      pointer-events: none;
      z-index: 0;
    }

    .wrap {
      position: relative;
      z-index: 1;
      max-width: 980px;
      margin: 0 auto;
      padding: 18px 14px 40px;
    }

    .top-banner {
      width: 100%;
      border-radius: 24px;
      overflow: hidden;
      border: 1px solid var(--stroke);
      box-shadow: var(--shadow);
      position: relative;
      background: #000;
    }
    .top-banner img {
      width: 100%;
      height: 190px;
      object-fit: cover;
      object-position: center;
      display: block;
    }
    .top-banner::after{
      content:"";
      position:absolute; inset:0;
      background: linear-gradient(180deg, rgba(0,0,0,0.05), rgba(0,0,0,0.68));
      pointer-events:none;
    }

    .head {
      padding: 16px 10px 8px;
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .title {
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 22px;
      line-height: 1.15;
    }
    .subtitle {
      margin-top: 6px;
      color: var(--muted);
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 12px;
    }

    .search {
      flex: 1;
      min-width: 220px;
      max-width: 420px;
      display: flex;
      align-items: center;
      gap: 10px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--stroke);
      border-radius: 18px;
      padding: 12px 14px;
      box-shadow: 0 10px 18px rgba(0,0,0,0.35);
    }
    .search input {
      width: 100%;
      border: 0;
      outline: none;
      background: transparent;
      color: var(--txt);
      font-size: 14px;
    }
    .search input::placeholder{
      color: rgba(255,255,255,0.35);
      font-weight: 700;
      letter-spacing: 0.06em;
    }

    .letters {
      margin-top: 14px;
      background: rgba(255,255,255,0.035);
      border: 1px solid var(--stroke);
      border-radius: 26px;
      padding: 14px;
      box-shadow: 0 16px 26px rgba(0,0,0,0.36);
    }
    .letters-grid {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 10px;
    }
    @media (min-width: 720px){
      .letters-grid { grid-template-columns: repeat(10, 1fr); }
      .top-banner img { height: 220px; }
    }

    .letter {
      user-select: none;
      cursor: pointer;
      border-radius: 16px;
      padding: 12px 10px;
      text-align: center;
      border: 1px solid var(--stroke);
      background: rgba(255,255,255,0.03);
      transition: transform .08s ease, border-color .12s ease, background .12s ease;
    }
    .letter:hover { transform: translateY(-1px); border-color: var(--stroke2); }
    .letter .k { font-weight: 900; letter-spacing: 0.10em; font-size: 13px; text-transform: uppercase; }
    .letter .n { margin-top: 6px; font-size: 12px; color: rgba(255,255,255,0.55); font-weight: 800; letter-spacing: 0.08em; }
    .letter.active { background: rgba(90,168,255,0.18); border-color: rgba(90,168,255,0.42); }

    .cards {
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }
    @media (min-width: 720px){
      .cards { grid-template-columns: repeat(3, 1fr); }
    }

    .card {
      cursor: pointer;
      border-radius: 26px;
      overflow: hidden;
      border: 1px solid var(--stroke);
      background: rgba(255,255,255,0.03);
      box-shadow: 0 18px 30px rgba(0,0,0,0.44);
      transition: transform .10s ease, border-color .12s ease;
      position: relative;
    }
    .card:hover { transform: translateY(-2px); border-color: var(--stroke2); }

    .cover {
      width: 100%;
      height: 220px;
      background: linear-gradient(135deg, rgba(90,168,255,0.18), rgba(255,255,255,0.03));
      position: relative;
    }
    .cover img { width: 100%; height: 100%; object-fit: cover; display: block; }

    .badge {
      position: absolute;
      left: 12px;
      bottom: 12px;
      background: rgba(90,168,255,0.24);
      border: 1px solid rgba(90,168,255,0.40);
      color: rgba(255,255,255,0.90);
      font-weight: 900;
      letter-spacing: 0.12em;
      font-size: 11px;
      padding: 8px 10px;
      border-radius: 14px;
      backdrop-filter: blur(10px);
      text-transform: uppercase;
    }

    .meta { padding: 12px 14px 14px; }
    .meta .name {
      font-weight: 900;
      letter-spacing: 0.04em;
      font-size: 14px;
      text-transform: uppercase;
      line-height: 1.2;
      margin: 0;
    }
    .meta .sub {
      margin-top: 8px;
      color: rgba(255,255,255,0.50);
      font-weight: 800;
      letter-spacing: 0.12em;
      font-size: 11px;
      text-transform: uppercase;
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .pill {
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.04);
      padding: 6px 10px;
      border-radius: 999px;
    }

    .footer {
      margin-top: 14px;
      color: rgba(255,255,255,0.40);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-align: center;
    }

    .loadmore {
      margin: 14px auto 0;
      width: 100%;
      max-width: 320px;
      border: 1px solid var(--stroke);
      background: rgba(255,255,255,0.04);
      color: rgba(255,255,255,0.86);
      border-radius: 16px;
      padding: 12px 14px;
      font-weight: 900;
      letter-spacing: 0.10em;
      text-transform: uppercase;
      cursor: pointer;
      box-shadow: 0 14px 24px rgba(0,0,0,0.35);
    }
    .loadmore:disabled { opacity: 0.5; cursor: not-allowed; }
  </style>
</head>

<body>
  <div class="bg-pattern"></div>

  <div class="wrap">
    <div class="top-banner">
      <img src="__CBANNER__" alt="Banner"/>
    </div>

    <div class="head">
      <div>
        <div class="title">__CTITLE__</div>
        <div class="subtitle"><span id="totalTxt">__CSUB__: ...</span></div>
      </div>

      <div class="search" title="Buscar anime">
        <span style="opacity:.6;font-weight:900;">🔎</span>
        <input id="q" type="text" placeholder="BUSCAR ANIME..." />
      </div>
    </div>

    <div class="letters">
      <div class="letters-grid" id="lettersGrid"></div>
    </div>

    <div class="cards" id="cards"></div>
    <button class="loadmore" id="btnMore">CARREGAR MAIS</button>

    <div class="footer">Source Baltigo • Catálogo do canal</div>
  </div>

  <script>
    const apiLetters = "/api/letters";
    const apiCatalogo = "/api/catalogo";

    let state = {
      letter: "ALL",
      q: "",
      limit: 60,
      offset: 0,
      total: 0,
      loading: false,
    };

    function esc(s) {
      return (s || "").replace(/[&<>"']/g, (m) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[m]));
    }

    function openLink(link) {
      try {
        if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openTelegramLink) {
          Telegram.WebApp.openTelegramLink(link);
          return;
        }
      } catch (e) {}
      window.open(link, "_blank");
    }

    function makeLetterButton(key, count) {
      const el = document.createElement("div");
      el.className = "letter" + (state.letter === key ? " active" : "");
      el.innerHTML = `
        <div class="k">${esc(key === "ALL" ? "TODOS" : key)}</div>
        <div class="n">${key === "ALL" ? (count > 999 ? "999+" : count) : count}</div>
      `;
      el.onclick = () => {
        state.letter = key;
        state.offset = 0;
        document.getElementById("cards").innerHTML = "";
        renderLetters();
        loadCatalog(true);
      };
      return el;
    }

    async function renderLetters() {
      const grid = document.getElementById("lettersGrid");
      grid.innerHTML = "";

      const res = await fetch(apiLetters + "?_ts=" + Date.now());
      const data = await res.json();

      document.getElementById("totalTxt").textContent = "__CSUB__: " + (data.total ?? 0);

      grid.appendChild(makeLetterButton("ALL", data.all_count || data.total || 0));
      grid.appendChild(makeLetterButton("#", (data.counts && data.counts["#"]) ? data.counts["#"] : 0));

      for (let c = 65; c <= 90; c++) {
        const k = String.fromCharCode(c);
        const n = (data.counts && data.counts[k]) ? data.counts[k] : 0;
        grid.appendChild(makeLetterButton(k, n));
      }
    }

    function badgeText(item) {
      const b = (item.badge || item.format || "").toString().trim();
      return b ? b.toUpperCase() : "ANIME";
    }

    function pillLine(item) {
      let parts = [];
      if (item.year) parts.push(String(item.year));
      if (item.score) parts.push("★ " + String(item.score));
      if (item.format) parts.push(String(item.format).toUpperCase());
      return parts;
    }

    function makeCard(item) {
      const card = document.createElement("div");
      card.className = "card";

      const hasCover = item.cover_url && item.cover_url.length > 5;
      const coverHtml = hasCover ? `<img src="${esc(item.cover_url)}" alt="${esc(item.titulo)}"/>` : ``;
      const pills = pillLine(item).map(p => `<span class="pill">${esc(p)}</span>`).join("");

      card.innerHTML = `
        <div class="cover">
          ${coverHtml}
          <div class="badge">${esc(badgeText(item))}</div>
        </div>
        <div class="meta">
          <p class="name">${esc(item.titulo)}</p>
          <div class="sub">
            <span class="pill">CANAL</span>
            ${pills}
          </div>
        </div>
      `;

      card.onclick = () => openLink(item.link_post);
      return card;
    }

    async function loadCatalog(reset=false) {
      if (state.loading) return;
      state.loading = true;

      const btn = document.getElementById("btnMore");
      btn.disabled = true;
      btn.textContent = "CARREGANDO...";

      const params = new URLSearchParams();
      params.set("letter", state.letter);
      params.set("q", state.q);
      params.set("limit", state.limit);
      params.set("offset", state.offset);
      params.set("_ts", String(Date.now()));

      const res = await fetch(apiCatalogo + "?" + params.toString());
      const data = await res.json();

      state.total = data.total || 0;

      const cards = document.getElementById("cards");
      for (const it of (data.items || [])) {
        cards.appendChild(makeCard(it));
      }

      state.offset += (data.items || []).length;

      if (state.offset >= state.total) {
        btn.disabled = true;
        btn.textContent = "FIM DA LISTA";
      } else {
        btn.disabled = false;
        btn.textContent = "CARREGAR MAIS";
      }

      state.loading = false;
    }

    function debounce(fn, ms) {
      let t = null;
      return (...args) => {
        if (t) clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
      };
    }

    const onSearch = debounce(() => {
      state.q = (document.getElementById("q").value || "").trim();
      state.offset = 0;
      document.getElementById("cards").innerHTML = "";
      loadCatalog(true);
    }, 250);

    document.getElementById("q").addEventListener("input", onSearch);
    document.getElementById("btnMore").addEventListener("click", () => loadCatalog(false));

    (async () => {
      await renderLetters();
      await loadCatalog(true);
    })();
  </script>
</body>
</html>
"""

    # Placeholders
    pattern = BACKGROUND_PATTERN_URL if BACKGROUND_PATTERN_URL else EMPTY_BG_DATA_URI
    html = (html
        .replace("__CBANNER__", CATALOG_BANNER_URL)
        .replace("__BPATTERN__", pattern)
        .replace("__CTITLE__", CATALOG_TITLE)
        .replace("__CSUB__", CATALOG_SUBTITLE)
    )
    return HTMLResponse(html)


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
    html = """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>__CTITLE__ — Source Baltigo</title>

  <style>
    :root {
      --bg0: #070b12;
      --bg1: #0a1220;
      --stroke: rgba(255,255,255,0.10);
      --stroke2: rgba(255,255,255,0.16);
      --txt: rgba(255,255,255,0.92);
      --muted: rgba(255,255,255,0.58);
      --shadow: 0 14px 30px rgba(0,0,0,0.55);
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: -apple-system, system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      color: var(--txt);
      background: radial-gradient(1200px 600px at 50% -10%, rgba(90,168,255,0.18), transparent 55%),
                  linear-gradient(180deg, var(--bg0), var(--bg1));
      overflow-x: hidden;
    }

    .bg-pattern {
      position: fixed;
      inset: 0;
      background-image: url("__BPATTERN__");
      background-size: 520px;
      background-repeat: repeat;
      opacity: 0.10;
      filter: grayscale(1) contrast(1.1);
      pointer-events: none;
      z-index: 0;
    }

    .wrap {
      position: relative;
      z-index: 1;
      max-width: 980px;
      margin: 0 auto;
      padding: 18px 14px 40px;
    }

    .top-banner {
      width: 100%;
      border-radius: 24px;
      overflow: hidden;
      border: 1px solid var(--stroke);
      box-shadow: var(--shadow);
      position: relative;
      background: #000;
    }
    .top-banner img {
      width: 100%;
      height: 190px;
      object-fit: cover;
      object-position: center;
      display: block;
    }
    .top-banner::after{
      content:"";
      position:absolute; inset:0;
      background: linear-gradient(180deg, rgba(0,0,0,0.05), rgba(0,0,0,0.68));
      pointer-events:none;
    }

    .head {
      padding: 16px 10px 8px;
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .title {
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 22px;
      line-height: 1.15;
    }
    .subtitle {
      margin-top: 6px;
      color: var(--muted);
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 12px;
    }

    .search {
      flex: 1;
      min-width: 220px;
      max-width: 420px;
      display: flex;
      align-items: center;
      gap: 10px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--stroke);
      border-radius: 18px;
      padding: 12px 14px;
      box-shadow: 0 10px 18px rgba(0,0,0,0.35);
    }
    .search input {
      width: 100%;
      border: 0;
      outline: none;
      background: transparent;
      color: var(--txt);
      font-size: 14px;
    }
    .search input::placeholder{
      color: rgba(255,255,255,0.35);
      font-weight: 700;
      letter-spacing: 0.06em;
    }

    .letters {
      margin-top: 14px;
      background: rgba(255,255,255,0.035);
      border: 1px solid var(--stroke);
      border-radius: 26px;
      padding: 14px;
      box-shadow: 0 16px 26px rgba(0,0,0,0.36);
    }
    .letters-grid {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 10px;
    }
    @media (min-width: 720px){
      .letters-grid { grid-template-columns: repeat(10, 1fr); }
      .top-banner img { height: 220px; }
    }

    .letter {
      user-select: none;
      cursor: pointer;
      border-radius: 16px;
      padding: 12px 10px;
      text-align: center;
      border: 1px solid var(--stroke);
      background: rgba(255,255,255,0.03);
      transition: transform .08s ease, border-color .12s ease, background .12s ease;
    }
    .letter:hover { transform: translateY(-1px); border-color: var(--stroke2); }
    .letter .k { font-weight: 900; letter-spacing: 0.10em; font-size: 13px; text-transform: uppercase; }
    .letter .n { margin-top: 6px; font-size: 12px; color: rgba(255,255,255,0.55); font-weight: 800; letter-spacing: 0.08em; }
    .letter.active { background: rgba(90,168,255,0.18); border-color: rgba(90,168,255,0.42); }

    .cards {
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }
    @media (min-width: 720px){
      .cards { grid-template-columns: repeat(3, 1fr); }
    }

    .card {
      cursor: pointer;
      border-radius: 26px;
      overflow: hidden;
      border: 1px solid var(--stroke);
      background: rgba(255,255,255,0.03);
      box-shadow: 0 18px 30px rgba(0,0,0,0.44);
      transition: transform .10s ease, border-color .12s ease;
      position: relative;
    }
    .card:hover { transform: translateY(-2px); border-color: var(--stroke2); }

    .cover {
      width: 100%;
      height: 220px;
      background: linear-gradient(135deg, rgba(90,168,255,0.18), rgba(255,255,255,0.03));
      position: relative;
    }
    .cover img { width: 100%; height: 100%; object-fit: cover; display: block; }

    .badge {
      position: absolute;
      left: 12px;
      bottom: 12px;
      background: rgba(90,168,255,0.24);
      border: 1px solid rgba(90,168,255,0.40);
      color: rgba(255,255,255,0.90);
      font-weight: 900;
      letter-spacing: 0.12em;
      font-size: 11px;
      padding: 8px 10px;
      border-radius: 14px;
      backdrop-filter: blur(10px);
      text-transform: uppercase;
    }

    .meta { padding: 12px 14px 14px; }
    .meta .name {
      font-weight: 900;
      letter-spacing: 0.04em;
      font-size: 14px;
      text-transform: uppercase;
      line-height: 1.2;
      margin: 0;
    }
    .meta .sub {
      margin-top: 8px;
      color: rgba(255,255,255,0.50);
      font-weight: 800;
      letter-spacing: 0.12em;
      font-size: 11px;
      text-transform: uppercase;
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .pill {
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.04);
      padding: 6px 10px;
      border-radius: 999px;
    }

    .footer {
      margin-top: 14px;
      color: rgba(255,255,255,0.40);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-align: center;
    }

    .loadmore {
      margin: 14px auto 0;
      width: 100%;
      max-width: 320px;
      border: 1px solid var(--stroke);
      background: rgba(255,255,255,0.04);
      color: rgba(255,255,255,0.86);
      border-radius: 16px;
      padding: 12px 14px;
      font-weight: 900;
      letter-spacing: 0.10em;
      text-transform: uppercase;
      cursor: pointer;
      box-shadow: 0 14px 24px rgba(0,0,0,0.35);
    }
    .loadmore:disabled { opacity: 0.5; cursor: not-allowed; }
  </style>
</head>

<body>
  <div class="bg-pattern"></div>

  <div class="wrap">
    <div class="top-banner">
      <img src="__CBANNER__" alt="Banner"/>
    </div>

    <div class="head">
      <div>
        <div class="title">__CTITLE__</div>
        <div class="subtitle"><span id="totalTxt">__CSUB__: ...</span></div>
      </div>

      <div class="search" title="Buscar mangá">
        <span style="opacity:.6;font-weight:900;">🔎</span>
        <input id="q" type="text" placeholder="BUSCAR MANGÁ..." />
      </div>
    </div>

    <div class="letters">
      <div class="letters-grid" id="lettersGrid"></div>
    </div>

    <div class="cards" id="cards"></div>
    <button class="loadmore" id="btnMore">CARREGAR MAIS</button>

    <div class="footer">Source Baltigo • Catálogo do canal</div>
  </div>

  <script>
    const apiLetters = "/api/mangas/letters";
    const apiCatalogo = "/api/mangas/catalogo";

    let state = {
      letter: "ALL",
      q: "",
      limit: 60,
      offset: 0,
      total: 0,
      loading: false,
    };

    function esc(s) {
      return (s || "").replace(/[&<>"']/g, (m) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[m]));
    }

    function openLink(link) {
      try {
        if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openTelegramLink) {
          Telegram.WebApp.openTelegramLink(link);
          return;
        }
      } catch (e) {}
      window.open(link, "_blank");
    }

    function makeLetterButton(key, count) {
      const el = document.createElement("div");
      el.className = "letter" + (state.letter === key ? " active" : "");
      el.innerHTML = `
        <div class="k">${esc(key === "ALL" ? "TODOS" : key)}</div>
        <div class="n">${key === "ALL" ? (count > 999 ? "999+" : count) : count}</div>
      `;
      el.onclick = () => {
        state.letter = key;
        state.offset = 0;
        document.getElementById("cards").innerHTML = "";
        renderLetters();
        loadCatalog(true);
      };
      return el;
    }

    async function renderLetters() {
      const grid = document.getElementById("lettersGrid");
      grid.innerHTML = "";

      const res = await fetch(apiLetters + "?_ts=" + Date.now());
      const data = await res.json();

      document.getElementById("totalTxt").textContent = "__CSUB__: " + (data.total ?? 0);

      grid.appendChild(makeLetterButton("ALL", data.all_count || data.total || 0));
      grid.appendChild(makeLetterButton("#", (data.counts && data.counts["#"]) ? data.counts["#"] : 0));

      for (let c = 65; c <= 90; c++) {
        const k = String.fromCharCode(c);
        const n = (data.counts && data.counts[k]) ? data.counts[k] : 0;
        grid.appendChild(makeLetterButton(k, n));
      }
    }

    function badgeText(item) {
      const b = (item.badge || item.format || "").toString().trim();
      return b ? b.toUpperCase() : "MANGA";
    }

    function pillLine(item) {
      let parts = [];
      if (item.year) parts.push(String(item.year));
      if (item.score) parts.push("★ " + String(item.score));
      if (item.format) parts.push(String(item.format).toUpperCase());
      return parts;
    }

    function makeCard(item) {
      const card = document.createElement("div");
      card.className = "card";

      const hasCover = item.cover_url && item.cover_url.length > 5;
      const coverHtml = hasCover ? `<img src="${esc(item.cover_url)}" alt="${esc(item.titulo)}"/>` : ``;
      const pills = pillLine(item).map(p => `<span class="pill">${esc(p)}</span>`).join("");

      card.innerHTML = `
        <div class="cover">
          ${coverHtml}
          <div class="badge">${esc(badgeText(item))}</div>
        </div>
        <div class="meta">
          <p class="name">${esc(item.titulo)}</p>
          <div class="sub">
            <span class="pill">CANAL</span>
            ${pills}
          </div>
        </div>
      `;

      card.onclick = () => openLink(item.link_post);
      return card;
    }

    async function loadCatalog(reset=false) {
      if (state.loading) return;
      state.loading = true;

      const btn = document.getElementById("btnMore");
      btn.disabled = true;
      btn.textContent = "CARREGANDO...";

      const params = new URLSearchParams();
      params.set("letter", state.letter);
      params.set("q", state.q);
      params.set("limit", state.limit);
      params.set("offset", state.offset);
      params.set("_ts", String(Date.now()));

      const res = await fetch(apiCatalogo + "?" + params.toString());
      const data = await res.json();

      state.total = data.total || 0;

      const cards = document.getElementById("cards");
      for (const it of (data.items || [])) {
        cards.appendChild(makeCard(it));
      }

      state.offset += (data.items || []).length;

      if (state.offset >= state.total) {
        btn.disabled = true;
        btn.textContent = "FIM DA LISTA";
      } else {
        btn.disabled = false;
        btn.textContent = "CARREGAR MAIS";
      }

      state.loading = false;
    }

    function debounce(fn, ms) {
      let t = null;
      return (...args) => {
        if (t) clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
      };
    }

    const onSearch = debounce(() => {
      state.q = (document.getElementById("q").value || "").trim();
      state.offset = 0;
      document.getElementById("cards").innerHTML = "";
      loadCatalog(true);
    }, 250);

    document.getElementById("q").addEventListener("input", onSearch);
    document.getElementById("btnMore").addEventListener("click", () => loadCatalog(false));

    (async () => {
      await renderLetters();
      await loadCatalog(true);
    })();
  </script>
</body>
</html>
"""

    pattern = MANGA_BACKGROUND_PATTERN_URL if MANGA_BACKGROUND_PATTERN_URL else EMPTY_BG_DATA_URI
    html = (html
        .replace("__CBANNER__", MANGA_CATALOG_BANNER_URL)
        .replace("__BPATTERN__", pattern)
        .replace("__CTITLE__", MANGA_CATALOG_TITLE)
        .replace("__CSUB__", MANGA_CATALOG_SUBTITLE)
    )
    return HTMLResponse(html)

# =========================================================
# CARDS SYSTEM — JSON ASSETS
# Lê: data/cards_assets.json
# =========================================================

import json
import os
from typing import Any, Dict, List
from fastapi import Query
from fastapi.responses import HTMLResponse, JSONResponse

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


@app.get("/api/cards/reload")
def api_cards_reload():
    total = _load_cards_assets()
    return JSONResponse({"ok": True, "total": total})


@app.get("/api/cards/animes")
def api_cards_animes(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    _ensure_cards_loaded()

    q = (q or "").strip().lower()
    data = _CARDS_DATA

    if q:
        data = [x for x in data if q in x["anime"].lower()]

    total = len(data)
    items = data[offset: offset + limit]

    payload = []
    for a in items:
        payload.append({
            "anime_id": a["anime_id"],
            "anime": a["anime"],
            "banner_image": a["banner_image"],
            "cover_image": a["cover_image"],
            "characters_count": a["characters_count"],
        })

    return JSONResponse({
        "total": total,
        "items": payload,
    })


@app.get("/api/cards/characters")
def api_cards_characters(
    anime_id: int = Query(...),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    _ensure_cards_loaded()

    anime = _CARDS_INDEX.get(anime_id)
    if not anime:
        return JSONResponse({
            "ok": False,
            "anime": None,
            "total": 0,
            "items": [],
        })

    chars = anime["characters"]
    q = (q or "").strip().lower()

    if q:
        chars = [c for c in chars if q in c["name"].lower()]

    total = len(chars)
    items = chars[offset: offset + limit]

    return JSONResponse({
        "ok": True,
        "anime": {
            "anime_id": anime["anime_id"],
            "anime": anime["anime"],
            "banner_image": anime["banner_image"],
            "cover_image": anime["cover_image"],
            "characters_count": anime["characters_count"],
        },
        "total": total,
        "items": items,
    })


@app.get("/cards", response_class=HTMLResponse)
def cards_page():
    html = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>Cards • Source Baltigo</title>

<style>
  :root{
    --bg0:#070b12;
    --bg1:#0a1220;
    --txt:rgba(255,255,255,.94);
    --muted:rgba(255,255,255,.58);
    --stroke:rgba(255,255,255,.10);
    --stroke2:rgba(255,255,255,.16);
    --glass:rgba(255,255,255,.04);
    --shadow:0 16px 30px rgba(0,0,0,.44);
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
    background-size: 36px 36px;
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
    color:var(--muted);
    font-weight:800;
    letter-spacing:.12em;
    text-transform:uppercase;
    font-size:12px;
  }

  .search{
    width:100%;
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
  }

  .card{
    cursor:pointer;
    border-radius:24px;
    overflow:hidden;
    border:1px solid var(--stroke);
    background:rgba(255,255,255,.03);
    box-shadow:0 18px 30px rgba(0,0,0,.42);
    transition:transform .10s ease, border-color .12s ease, box-shadow .12s ease;
    position:relative;
  }

  .card:hover{
    transform:translateY(-2px);
    border-color:var(--stroke2);
    box-shadow:0 20px 34px rgba(0,0,0,.5);
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

  .footer{
    margin-top:16px;
    color:rgba(255,255,255,.40);
    font-size:12px;
    font-weight:700;
    letter-spacing:.08em;
    text-align:center;
  }
</style>
</head>
<body>
<div class="bg"></div>

<div class="wrap">

  <div class="top-banner">
    <img src="__TOP_BANNER__" alt="Cards banner"/>
    <div class="top-copy">
      <div class="eyebrow">🃏 Cards • Source Baltigo</div>
      <div class="title">Coleção de Personagens</div>
      <div class="subtitle">Obras, personagens e artes já preparadas</div>
    </div>
  </div>

  <div class="head">
    <div class="stats" id="statsTxt">Carregando...</div>
  </div>

  <div class="search">
    <span style="opacity:.62;font-weight:900;">🔎</span>
    <input id="searchInput" type="text" placeholder="Buscar obra..." />
  </div>

  <div class="cards" id="cards"></div>
  <div class="empty" id="emptyBox" style="display:none;">Nenhuma obra encontrada.</div>

  <div class="footer">Source Baltigo • Cards</div>
</div>

<script>
  const api = "/api/cards/animes";
  let fullData = [];
  let filteredData = [];

  function esc(s){
    return (s || "").replace(/[&<>\"']/g, (m) => ({
      "&":"&amp;",
      "<":"&lt;",
      ">":"&gt;",
      '"':"&quot;",
      "'":"&#039;"
    }[m]));
  }

  function pickCover(item){
    if (item.cover_image && item.cover_image.length > 5) return item.cover_image;
    if (item.banner_image && item.banner_image.length > 5) return item.banner_image;
    return "__TOP_BANNER__";
  }

  function render(){
    const box = document.getElementById("cards");
    const empty = document.getElementById("emptyBox");
    const stats = document.getElementById("statsTxt");

    stats.textContent = "TOTAL DE OBRAS: " + filteredData.length;

    if (!filteredData.length){
      box.innerHTML = "";
      empty.style.display = "block";
      return;
    }

    empty.style.display = "none";

    let html = "";
    for (const item of filteredData){
      html += `
        <div class="card" onclick="openAnime(${item.anime_id})">
          <div class="cover">
            <img src="${esc(pickCover(item))}" alt="${esc(item.anime)}" loading="lazy"/>
            <div class="count-pill">${item.characters_count || 0} chars</div>
          </div>
          <div class="meta">
            <p class="name">${esc(item.anime)}</p>
            <div class="sub">
              <span class="pill">ID ${item.anime_id}</span>
              <span class="pill">CARDS</span>
            </div>
          </div>
        </div>
      `;
    }

    box.innerHTML = html;
  }

  function applySearch(){
    const q = (document.getElementById("searchInput").value || "").trim().toLowerCase();

    if (!q){
      filteredData = [...fullData];
      render();
      return;
    }

    filteredData = fullData.filter(x => x.anime.toLowerCase().includes(q));
    render();
  }

  function openAnime(id){
    window.location.href = "/cards/anime?anime_id=" + encodeURIComponent(id);
  }

  async function load(){
    const res = await fetch(api + "?limit=5000&_ts=" + Date.now());
    const data = await res.json();
    fullData = (data.items || []).sort((a,b) => a.anime.localeCompare(b.anime));
    filteredData = [...fullData];
    render();
  }

  document.getElementById("searchInput").addEventListener("input", applySearch);
  load();
</script>
</body>
</html>
"""
    html = html.replace("__TOP_BANNER__", CARDS_TOP_BANNER_URL)
    return HTMLResponse(html)


@app.get("/cards/anime", response_class=HTMLResponse)
def cards_anime_page(anime_id: int = Query(...)):
    html = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>Cards Anime • Source Baltigo</title>

<style>
  :root{
    --bg0:#070b12;
    --bg1:#0a1220;
    --txt:rgba(255,255,255,.94);
    --muted:rgba(255,255,255,.58);
    --stroke:rgba(255,255,255,.10);
    --stroke2:rgba(255,255,255,.16);
    --glass:rgba(255,255,255,.04);
    --shadow:0 16px 30px rgba(0,0,0,.44);
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
    background-size: 36px 36px;
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

  .hero{
    width:100%;
    min-height:230px;
    border-radius:26px;
    overflow:hidden;
    border:1px solid var(--stroke);
    box-shadow:var(--shadow);
    position:relative;
    background:#101827;
  }

  .hero img{
    width:100%;
    height:230px;
    object-fit:cover;
    display:block;
  }

  .hero:after{
    content:"";
    position:absolute; inset:0;
    background:linear-gradient(180deg, rgba(0,0,0,.08), rgba(0,0,0,.80));
    pointer-events:none;
  }

  .hero-copy{
    position:absolute;
    left:18px;
    right:18px;
    bottom:16px;
    z-index:2;
  }

  .back{
    display:inline-flex;
    align-items:center;
    gap:8px;
    border:1px solid rgba(255,255,255,.16);
    background:rgba(0,0,0,.28);
    color:rgba(255,255,255,.95);
    text-decoration:none;
    backdrop-filter:blur(8px);
    border-radius:999px;
    padding:8px 12px;
    font-size:11px;
    font-weight:900;
    letter-spacing:.12em;
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
  }

  .stats{
    color:var(--muted);
    font-weight:800;
    letter-spacing:.12em;
    text-transform:uppercase;
    font-size:12px;
  }

  .search{
    width:100%;
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
    .hero img{ height:260px; }
    .cards{ grid-template-columns:repeat(3,1fr); }
  }

  .card{
    border-radius:24px;
    overflow:hidden;
    border:1px solid var(--stroke);
    background:rgba(255,255,255,.03);
    box-shadow:0 18px 30px rgba(0,0,0,.42);
    transition:transform .10s ease, border-color .12s ease;
    position:relative;
  }

  .card:hover{
    transform:translateY(-2px);
    border-color:var(--stroke2);
  }

  .char-image{
    width:100%;
    height:280px;
    position:relative;
    background:linear-gradient(135deg, rgba(90,168,255,.18), rgba(255,255,255,.03));
  }

  .char-image img{
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
  }

  .char-image:after{
    content:"";
    position:absolute; inset:0;
    background:linear-gradient(180deg, rgba(0,0,0,.00), rgba(0,0,0,.58));
    pointer-events:none;
  }

  .id-pill{
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

  .footer{
    margin-top:16px;
    color:rgba(255,255,255,.40);
    font-size:12px;
    font-weight:700;
    letter-spacing:.08em;
    text-align:center;
  }
</style>
</head>
<body>
<div class="bg"></div>

<div class="wrap">

  <div class="hero" id="heroBox">
    <img id="heroImg" src="" alt="Banner"/>
    <div class="hero-copy">
      <a class="back" href="/cards">← Voltar</a>
      <div class="title" id="animeTitle">Carregando...</div>
      <div class="subtitle" id="animeSub">Personagens</div>
    </div>
  </div>

  <div class="head">
    <div class="stats" id="statsTxt">Carregando...</div>
  </div>

  <div class="search">
    <span style="opacity:.62;font-weight:900;">🔎</span>
    <input id="searchInput" type="text" placeholder="Buscar personagem..." />
  </div>

  <div class="cards" id="cards"></div>
  <div class="empty" id="emptyBox" style="display:none;">Nenhum personagem encontrado.</div>

  <div class="footer">Source Baltigo • Cards</div>
</div>

<script>
  const animeId = __ANIME_ID__;
  const api = "/api/cards/characters?anime_id=" + animeId + "&limit=5000";
  const fallbackTop = "__TOP_BANNER__";

  let animeMeta = null;
  let fullData = [];
  let filteredData = [];

  function esc(s){
    return (s || "").replace(/[&<>\"']/g, (m) => ({
      "&":"&amp;",
      "<":"&lt;",
      ">":"&gt;",
      '"':"&quot;",
      "'":"&#039;"
    }[m]));
  }

  function pickHero(meta){
    if (meta.banner_image && meta.banner_image.length > 5) return meta.banner_image;
    if (meta.cover_image && meta.cover_image.length > 5) return meta.cover_image;
    return fallbackTop;
  }

  function pickCharImage(item){
    if (item.image && item.image.length > 5) return item.image;
    return fallbackTop;
  }

  function render(){
    const box = document.getElementById("cards");
    const empty = document.getElementById("emptyBox");
    const stats = document.getElementById("statsTxt");

    stats.textContent = "TOTAL DE PERSONAGENS: " + filteredData.length;

    if (!filteredData.length){
      box.innerHTML = "";
      empty.style.display = "block";
      return;
    }

    empty.style.display = "none";

    let html = "";
    for (const item of filteredData){
      html += `
        <div class="card">
          <div class="char-image">
            <img src="${esc(pickCharImage(item))}" alt="${esc(item.name)}" loading="lazy"/>
            <div class="id-pill">ID ${item.id}</div>
          </div>
          <div class="meta">
            <p class="name">${esc(item.name)}</p>
            <div class="sub">
              <span class="pill">${esc(item.anime)}</span>
              <span class="pill">CARD</span>
            </div>
          </div>
        </div>
      `;
    }

    box.innerHTML = html;
  }

  function applySearch(){
    const q = (document.getElementById("searchInput").value || "").trim().toLowerCase();

    if (!q){
      filteredData = [...fullData];
      render();
      return;
    }

    filteredData = fullData.filter(x => x.name.toLowerCase().includes(q));
    render();
  }

  async function load(){
    const res = await fetch(api + "&_ts=" + Date.now());
    const data = await res.json();

    animeMeta = data.anime || null;
    fullData = (data.items || []).sort((a,b) => a.name.localeCompare(b.name));
    filteredData = [...fullData];

    if (animeMeta){
      document.getElementById("animeTitle").textContent = animeMeta.anime || "Obra";
      document.getElementById("animeSub").textContent = "ID " + animeMeta.anime_id + " • " + (animeMeta.characters_count || fullData.length) + " personagens";
      document.getElementById("heroImg").src = pickHero(animeMeta);
    }

    render();
  }

  document.getElementById("searchInput").addEventListener("input", applySearch);
  load();
</script>
</body>
</html>
"""
    html = html.replace("__ANIME_ID__", str(anime_id)).replace("__TOP_BANNER__", CARDS_TOP_BANNER_URL)
    return HTMLResponse(html)



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
async def api_pedido(payload: dict = Body(...)):
    try:
        uid = int(payload.get("uid") or 0)
        nome = str(payload.get("nome") or "").strip()
        tipo = str(payload.get("tipo") or "anime")

        if uid <= 0 or not nome:
            return {"ok": False, "msg": "Dados inválidos."}

        if not _pode_pedir(uid):
            return {"ok": False, "msg": "Limite de 3 pedidos a cada 24h."}

        _registrar_pedido(uid)

        canal = os.getenv("CANAL_PEDIDOS")
        if canal and BOT_TOKEN:
            texto = f"""📥 NOVO PEDIDO

Usuário: {uid}
Tipo: {tipo}

Pedido:
{nome}
"""

            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={
                    "chat_id": canal,
                    "text": texto
                })

        return {"ok": True}

    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


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
    items = list(data["animes_list"])

    qn = q.strip().lower()
    if qn:
        items = [x for x in items if qn in x["anime"].lower()]

    total = len(items)
    items = items[offset: offset + limit]

    return JSONResponse({
        "ok": True,
        "total": total,
        "items": items,
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
    items = chars[offset: offset + limit]

    return JSONResponse({
        "ok": True,
        "anime": anime,
        "total": total,
        "items": items,
    })


@app.get("/api/cards/search")
def api_cards_search(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
):
    items = search_characters(q, limit=limit)
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
    items = chars[offset: offset + limit]

    return JSONResponse({
        "ok": True,
        "subcategory": name,
        "total": total,
        "items": items,
    })


@app.get("/cards", response_class=HTMLResponse)
def cards_page():
    html = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>Cards • Source Baltigo</title>

<style>
  :root{
    --bg0:#070b12;
    --bg1:#0a1220;
    --txt:rgba(255,255,255,.94);
    --muted:rgba(255,255,255,.58);
    --stroke:rgba(255,255,255,.10);
    --stroke2:rgba(255,255,255,.16);
    --glass:rgba(255,255,255,.04);
    --shadow:0 16px 30px rgba(0,0,0,.44);
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
    background-size: 36px 36px;
    opacity:.16;
    pointer-events:none;
    z-index:0;
  }

  .wrap{
    position:relative;
    z-index:1;
    max-width:1080px;
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
    color:var(--muted);
    font-weight:800;
    letter-spacing:.12em;
    text-transform:uppercase;
    font-size:12px;
  }

  .search-stack{
    display:grid;
    gap:12px;
    margin-top:2px;
  }

  .search{
    width:100%;
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

  .section-title{
    margin-top:22px;
    margin-bottom:10px;
    font-size:15px;
    font-weight:900;
    letter-spacing:.10em;
    text-transform:uppercase;
    color:rgba(255,255,255,.78);
  }

  .subs{
    display:flex;
    gap:10px;
    flex-wrap:wrap;
  }

  .sub-btn{
    border:1px solid rgba(255,255,255,.12);
    background:rgba(255,255,255,.04);
    color:#fff;
    padding:10px 14px;
    border-radius:999px;
    cursor:pointer;
    font-size:12px;
    font-weight:800;
    letter-spacing:.06em;
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
  }

  .card{
    cursor:pointer;
    border-radius:24px;
    overflow:hidden;
    border:1px solid var(--stroke);
    background:rgba(255,255,255,.03);
    box-shadow:0 18px 30px rgba(0,0,0,.42);
    transition:transform .10s ease, border-color .12s ease, box-shadow .12s ease;
    position:relative;
  }

  .card:hover{
    transform:translateY(-2px);
    border-color:var(--stroke2);
    box-shadow:0 20px 34px rgba(0,0,0,.5);
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

  .footer{
    margin-top:16px;
    color:rgba(255,255,255,.40);
    font-size:12px;
    font-weight:700;
    letter-spacing:.08em;
    text-align:center;
  }
</style>
</head>
<body>
<div class="bg"></div>

<div class="wrap">

  <div class="top-banner">
    <img src="__TOP_BANNER__" alt="Cards banner"/>
    <div class="top-copy">
      <div class="eyebrow">🃏 Cards • Source Baltigo</div>
      <div class="title">Coleção de Personagens</div>
      <div class="subtitle">Obras, subcategorias e personagens</div>
    </div>
  </div>

  <div class="head">
    <div class="stats" id="statsTxt">Carregando...</div>
  </div>

  <div class="search-stack">
    <div class="search">
      <span style="opacity:.62;font-weight:900;">🎬</span>
      <input id="searchInput" type="text" placeholder="Buscar obra..." />
    </div>

    <div class="search">
      <span style="opacity:.62;font-weight:900;">🧍</span>
      <input id="charSearchInput" type="text" placeholder="Buscar personagem e apertar Enter..." />
    </div>
  </div>

  <div class="section-title">Subcategorias</div>
  <div class="subs" id="subsBox"></div>

  <div class="section-title">Obras</div>
  <div class="cards" id="cards"></div>
  <div class="empty" id="emptyBox" style="display:none;">Nenhuma obra encontrada.</div>

  <div class="footer">Source Baltigo • Cards</div>
</div>

<script>
  const api = "/api/cards/animes";
  let fullData = [];
  let filteredData = [];

  function esc(s){
    return String(s || "").replace(/[&<>"']/g, (m) => ({
      "&":"&amp;",
      "<":"&lt;",
      ">":"&gt;",
      '"':"&quot;",
      "'":"&#039;"
    }[m]));
  }

  function pickCover(item){
    if (item.cover_image && item.cover_image.length > 5) return item.cover_image;
    if (item.banner_image && item.banner_image.length > 5) return item.banner_image;
    return "__TOP_BANNER__";
  }

  function render(){
    const box = document.getElementById("cards");
    const empty = document.getElementById("emptyBox");
    const stats = document.getElementById("statsTxt");

    stats.textContent = "TOTAL DE OBRAS: " + filteredData.length;

    if (!filteredData.length){
      box.innerHTML = "";
      empty.style.display = "block";
      return;
    }

    empty.style.display = "none";

    let html = "";
    for (const item of filteredData){
      html += `
        <div class="card" onclick="openAnime(${item.anime_id})">
          <div class="cover">
            <img src="${esc(pickCover(item))}" alt="${esc(item.anime)}" loading="lazy"/>
            <div class="count-pill">${item.characters_count || 0} chars</div>
          </div>
          <div class="meta">
            <p class="name">${esc(item.anime)}</p>
            <div class="sub">
              <span class="pill">ID ${item.anime_id}</span>
              <span class="pill">CARDS</span>
            </div>
          </div>
        </div>
      `;
    }

    box.innerHTML = html;
  }

  function applySearch(){
    const q = (document.getElementById("searchInput").value || "").trim().toLowerCase();

    if (!q){
      filteredData = [...fullData];
      render();
      return;
    }

    filteredData = fullData.filter(x => String(x.anime || "").toLowerCase().includes(q));
    render();
  }

  function openAnime(id){
    window.location.href = "/cards/anime?anime_id=" + encodeURIComponent(id);
  }

  async function loadSubs(){
    const subsBox = document.getElementById("subsBox");
    const res = await fetch("/api/cards/subcategories?_ts=" + Date.now());
    const data = await res.json();
    const items = data.items || [];

    if (!items.length){
      subsBox.innerHTML = '<div style="color:rgba(255,255,255,.45);font-weight:700;">Nenhuma subcategoria criada.</div>';
      return;
    }

    let html = "";
    for (const item of items){
      html += `<button class="sub-btn" onclick="openSubcategory('${esc(item.name)}')">${esc(item.name)} (${item.count || 0})</button>`;
    }
    subsBox.innerHTML = html;
  }

  function openSubcategory(name){
    window.location.href = "/cards/subcategory?name=" + encodeURIComponent(name);
  }

  async function load(){
    const res = await fetch(api + "?limit=5000&_ts=" + Date.now());
    const data = await res.json();
    fullData = (data.items || []).sort((a,b) => String(a.anime || "").localeCompare(String(b.anime || "")));
    filteredData = [...fullData];
    render();
  }

  document.getElementById("searchInput").addEventListener("input", applySearch);

  document.getElementById("charSearchInput").addEventListener("keydown", function(e){
    if (e.key !== "Enter") return;
    const q = (this.value || "").trim();
    if (!q) return;
    window.location.href = "/cards/search?q=" + encodeURIComponent(q);
  });

  load();
  loadSubs();
</script>
</body>
</html>
"""
    html = html.replace("__TOP_BANNER__", CARDS_TOP_BANNER_URL)
    return HTMLResponse(html)


@app.get("/cards/anime", response_class=HTMLResponse)
def cards_anime_page(anime_id: int = Query(...)):
    html = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>Cards Anime • Source Baltigo</title>

<style>
  :root{
    --bg0:#070b12;
    --bg1:#0a1220;
    --txt:rgba(255,255,255,.94);
    --muted:rgba(255,255,255,.58);
    --stroke:rgba(255,255,255,.10);
    --stroke2:rgba(255,255,255,.16);
    --glass:rgba(255,255,255,.04);
    --shadow:0 16px 30px rgba(0,0,0,.44);
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
    background-size: 36px 36px;
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

  .hero{
    width:100%;
    min-height:230px;
    border-radius:26px;
    overflow:hidden;
    border:1px solid var(--stroke);
    box-shadow:var(--shadow);
    position:relative;
    background:#101827;
  }

  .hero img{
    width:100%;
    height:230px;
    object-fit:cover;
    display:block;
  }

  .hero:after{
    content:"";
    position:absolute; inset:0;
    background:linear-gradient(180deg, rgba(0,0,0,.08), rgba(0,0,0,.80));
    pointer-events:none;
  }

  .hero-copy{
    position:absolute;
    left:18px;
    right:18px;
    bottom:16px;
    z-index:2;
  }

  .back{
    display:inline-flex;
    align-items:center;
    gap:8px;
    border:1px solid rgba(255,255,255,.16);
    background:rgba(0,0,0,.28);
    color:rgba(255,255,255,.95);
    text-decoration:none;
    backdrop-filter:blur(8px);
    border-radius:999px;
    padding:8px 12px;
    font-size:11px;
    font-weight:900;
    letter-spacing:.12em;
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
  }

  .stats{
    color:var(--muted);
    font-weight:800;
    letter-spacing:.12em;
    text-transform:uppercase;
    font-size:12px;
  }

  .search{
    width:100%;
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
    .hero img{ height:260px; }
    .cards{ grid-template-columns:repeat(3,1fr); }
  }

  .card{
    border-radius:24px;
    overflow:hidden;
    border:1px solid var(--stroke);
    background:rgba(255,255,255,.03);
    box-shadow:0 18px 30px rgba(0,0,0,.42);
    transition:transform .10s ease, border-color .12s ease;
    position:relative;
  }

  .card:hover{
    transform:translateY(-2px);
    border-color:var(--stroke2);
  }

  .char-image{
    width:100%;
    height:280px;
    position:relative;
    background:linear-gradient(135deg, rgba(90,168,255,.18), rgba(255,255,255,.03));
  }

  .char-image img{
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
  }

  .char-image:after{
    content:"";
    position:absolute; inset:0;
    background:linear-gradient(180deg, rgba(0,0,0,.00), rgba(0,0,0,.58));
    pointer-events:none;
  }

  .id-pill{
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

  .footer{
    margin-top:16px;
    color:rgba(255,255,255,.40);
    font-size:12px;
    font-weight:700;
    letter-spacing:.08em;
    text-align:center;
  }
</style>
</head>
<body>
<div class="bg"></div>

<div class="wrap">

  <div class="hero" id="heroBox">
    <img id="heroImg" src="" alt="Banner"/>
    <div class="hero-copy">
      <a class="back" href="/cards">← Voltar</a>
      <div class="title" id="animeTitle">Carregando...</div>
      <div class="subtitle" id="animeSub">Personagens</div>
    </div>
  </div>

  <div class="head">
    <div class="stats" id="statsTxt">Carregando...</div>
  </div>

  <div class="search">
    <span style="opacity:.62;font-weight:900;">🔎</span>
    <input id="searchInput" type="text" placeholder="Buscar personagem..." />
  </div>

  <div class="cards" id="cards"></div>
  <div class="empty" id="emptyBox" style="display:none;">Nenhum personagem encontrado.</div>

  <div class="footer">Source Baltigo • Cards</div>
</div>

<script>
  const animeId = __ANIME_ID__;
  const api = "/api/cards/characters?anime_id=" + animeId + "&limit=5000";
  const fallbackTop = "__TOP_BANNER__";

  let animeMeta = null;
  let fullData = [];
  let filteredData = [];

  function esc(s){
    return String(s || "").replace(/[&<>"']/g, (m) => ({
      "&":"&amp;",
      "<":"&lt;",
      ">":"&gt;",
      '"':"&quot;",
      "'":"&#039;"
    }[m]));
  }

  function pickHero(meta){
    if (meta.banner_image && meta.banner_image.length > 5) return meta.banner_image;
    if (meta.cover_image && meta.cover_image.length > 5) return meta.cover_image;
    return fallbackTop;
  }

  function pickCharImage(item){
    if (item.image && item.image.length > 5) return item.image;
    return fallbackTop;
  }

  function render(){
    const box = document.getElementById("cards");
    const empty = document.getElementById("emptyBox");
    const stats = document.getElementById("statsTxt");

    stats.textContent = "TOTAL DE PERSONAGENS: " + filteredData.length;

    if (!filteredData.length){
      box.innerHTML = "";
      empty.style.display = "block";
      return;
    }

    empty.style.display = "none";

    let html = "";
    for (const item of filteredData){
      html += `
        <div class="card">
          <div class="char-image">
            <img src="${esc(pickCharImage(item))}" alt="${esc(item.name)}" loading="lazy"/>
            <div class="id-pill">ID ${item.id}</div>
          </div>
          <div class="meta">
            <p class="name">${esc(item.name)}</p>
            <div class="sub">
              <span class="pill">${esc(item.anime)}</span>
              <span class="pill">CARD</span>
            </div>
          </div>
        </div>
      `;
    }

    box.innerHTML = html;
  }

  function applySearch(){
    const q = (document.getElementById("searchInput").value || "").trim().toLowerCase();

    if (!q){
      filteredData = [...fullData];
      render();
      return;
    }

    filteredData = fullData.filter(x => String(x.name || "").toLowerCase().includes(q));
    render();
  }

  async function load(){
    const res = await fetch(api + "&_ts=" + Date.now());
    const data = await res.json();

    animeMeta = data.anime || null;
    fullData = (data.items || []).sort((a,b) => String(a.name || "").localeCompare(String(b.name || "")));
    filteredData = [...fullData];

    if (animeMeta){
      document.getElementById("animeTitle").textContent = animeMeta.anime || "Obra";
      document.getElementById("animeSub").textContent = "ID " + animeMeta.anime_id + " • " + (animeMeta.characters_count || fullData.length) + " personagens";
      document.getElementById("heroImg").src = pickHero(animeMeta);
    } else {
      document.getElementById("animeTitle").textContent = "Obra não encontrada";
      document.getElementById("animeSub").textContent = "Verifique o anime_id";
      document.getElementById("heroImg").src = fallbackTop;
    }

    render();
  }

  document.getElementById("searchInput").addEventListener("input", applySearch);
  load();
</script>
</body>
</html>
"""
    html = html.replace("__ANIME_ID__", str(anime_id)).replace("__TOP_BANNER__", CARDS_TOP_BANNER_URL)
    return HTMLResponse(html)


@app.get("/cards/subcategory", response_class=HTMLResponse)
def cards_subcategory_page(name: str = Query(...)):
    safe_name = str(name).replace("\\", "\\\\").replace("'", "\\'")
    html = f"""
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>Subcategoria • Source Baltigo</title>

<style>
  :root{{
    --bg0:#070b12;
    --bg1:#0a1220;
    --txt:rgba(255,255,255,.94);
    --muted:rgba(255,255,255,.58);
    --stroke:rgba(255,255,255,.10);
    --stroke2:rgba(255,255,255,.16);
    --shadow:0 16px 30px rgba(0,0,0,.44);
  }}
  *{{ box-sizing:border-box; }}
  body{{
    margin:0;
    color:var(--txt);
    font-family:-apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
    background:
      radial-gradient(1100px 600px at 50% -10%, rgba(90,168,255,.18), transparent 55%),
      linear-gradient(180deg,var(--bg0),var(--bg1));
  }}
  .wrap{{max-width:980px;margin:0 auto;padding:18px 14px 42px;}}
  .back{{
    display:inline-flex;align-items:center;gap:8px;text-decoration:none;color:#fff;
    border:1px solid rgba(255,255,255,.16);background:rgba(0,0,0,.28);
    border-radius:999px;padding:8px 12px;font-size:11px;font-weight:900;
    letter-spacing:.12em;text-transform:uppercase;
  }}
  .title{{margin:18px 0 8px;font-size:28px;font-weight:900;text-transform:uppercase;}}
  .meta{{color:var(--muted);font-weight:800;letter-spacing:.10em;text-transform:uppercase;font-size:12px;margin-bottom:16px;}}
  .cards{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;}}
  @media (min-width:720px){{ .cards{{grid-template-columns:repeat(3,1fr);}} }}
  .card{{border-radius:24px;overflow:hidden;border:1px solid var(--stroke);background:rgba(255,255,255,.03);}}
  .char-image{{width:100%;height:280px;background:#111;}}
  .char-image img{{width:100%;height:100%;object-fit:cover;display:block;}}
  .meta2{{padding:13px 14px 15px;}}
  .name{{font-weight:900;font-size:14px;text-transform:uppercase;margin:0;}}
  .sub{{margin-top:8px;color:rgba(255,255,255,.52);font-weight:800;letter-spacing:.12em;font-size:11px;text-transform:uppercase;}}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/cards">← Voltar</a>
  <div class="title">Subcategoria: {name}</div>
  <div id="meta" class="meta">Carregando...</div>
  <div id="cards" class="cards"></div>
</div>

<script>
const subName = '{safe_name}';
const cards = document.getElementById("cards");
const meta = document.getElementById("meta");
const fallbackTop = "{CARDS_TOP_BANNER_URL}";

function esc(s){{
  return String(s || "").replace(/[&<>"']/g, (m) => ({{
    "&":"&amp;",
    "<":"&lt;",
    ">":"&gt;",
    '"':"&quot;",
    "'":"&#039;"
  }})[m]);
}}

async function load(){{
  const res = await fetch("/api/cards/subcategory?name=" + encodeURIComponent(subName) + "&limit=5000&_ts=" + Date.now());
  const data = await res.json();
  const items = data.items || [];
  meta.textContent = "TOTAL DE PERSONAGENS: " + items.length;

  let html = "";
  for (const item of items){{
    html += `
      <div class="card">
        <div class="char-image">
          <img src="${{esc(item.image || fallbackTop)}}" alt="${{esc(item.name)}}" loading="lazy"/>
        </div>
        <div class="meta2">
          <p class="name">${{esc(item.name)}}</p>
          <div class="sub">${{esc(item.anime)}}</div>
        </div>
      </div>
    `;
  }}
  cards.innerHTML = html;
}}

load();
</script>
</body>
</html>
"""
    return HTMLResponse(html)


@app.get("/cards/search", response_class=HTMLResponse)
def cards_search_page(q: str = Query(...)):
    safe_q = str(q).replace("\\", "\\\\").replace("'", "\\'")
    html = f"""
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>Busca • Source Baltigo</title>

<style>
  :root{{
    --bg0:#070b12;
    --bg1:#0a1220;
    --txt:rgba(255,255,255,.94);
    --muted:rgba(255,255,255,.58);
    --stroke:rgba(255,255,255,.10);
  }}
  *{{ box-sizing:border-box; }}
  body{{
    margin:0;
    color:var(--txt);
    font-family:-apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
    background:
      radial-gradient(1100px 600px at 50% -10%, rgba(90,168,255,.18), transparent 55%),
      linear-gradient(180deg,var(--bg0),var(--bg1));
  }}
  .wrap{{max-width:980px;margin:0 auto;padding:18px 14px 42px;}}
  .back{{
    display:inline-flex;align-items:center;gap:8px;text-decoration:none;color:#fff;
    border:1px solid rgba(255,255,255,.16);background:rgba(0,0,0,.28);
    border-radius:999px;padding:8px 12px;font-size:11px;font-weight:900;
    letter-spacing:.12em;text-transform:uppercase;
  }}
  .title{{margin:18px 0 8px;font-size:28px;font-weight:900;text-transform:uppercase;}}
  .meta{{color:var(--muted);font-weight:800;letter-spacing:.10em;text-transform:uppercase;font-size:12px;margin-bottom:16px;}}
  .cards{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;}}
  @media (min-width:720px){{ .cards{{grid-template-columns:repeat(3,1fr);}} }}
  .card{{border-radius:24px;overflow:hidden;border:1px solid var(--stroke);background:rgba(255,255,255,.03);}}
  .char-image{{width:100%;height:280px;background:#111;}}
  .char-image img{{width:100%;height:100%;object-fit:cover;display:block;}}
  .meta2{{padding:13px 14px 15px;}}
  .name{{font-weight:900;font-size:14px;text-transform:uppercase;margin:0;}}
  .sub{{margin-top:8px;color:rgba(255,255,255,.52);font-weight:800;letter-spacing:.12em;font-size:11px;text-transform:uppercase;}}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/cards">← Voltar</a>
  <div class="title">Busca: {q}</div>
  <div id="meta" class="meta">Carregando...</div>
  <div id="cards" class="cards"></div>
</div>

<script>
const searchQ = '{safe_q}';
const cards = document.getElementById("cards");
const meta = document.getElementById("meta");
const fallbackTop = "{CARDS_TOP_BANNER_URL}";

function esc(s){{
  return String(s || "").replace(/[&<>"']/g, (m) => ({{
    "&":"&amp;",
    "<":"&lt;",
    ">":"&gt;",
    '"':"&quot;",
    "'":"&#039;"
  }})[m]);
}}

async function load(){{
  const res = await fetch("/api/cards/search?q=" + encodeURIComponent(searchQ) + "&limit=500&_ts=" + Date.now());
  const data = await res.json();
  const items = data.items || [];
  meta.textContent = "TOTAL DE RESULTADOS: " + items.length;

  let html = "";
  for (const item of items){{
    html += `
      <div class="card">
        <div class="char-image">
          <img src="${{esc(item.image || fallbackTop)}}" alt="${{esc(item.name)}}" loading="lazy"/>
        </div>
        <div class="meta2">
          <p class="name">${{esc(item.name)}}</p>
          <div class="sub">${{esc(item.anime)}}</div>
        </div>
      </div>
    `;
  }}
  cards.innerHTML = html;
}}

load();
</script>
</body>
</html>
"""
    return HTMLResponse(html)

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


def _pedido_reload_indexes():
    global _PEDIDO_ANIME_INDEX, _PEDIDO_MANGA_INDEX

    try:
        anime_records = _unwrap_records(load_json(CATALOG_PATH))
    except Exception:
        anime_records = []

    try:
        manga_records = _unwrap_records(load_json(MANGA_CATALOG_PATH))
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
def api_pedido_limit(uid: int = Query(...)):
    used = count_user_media_requests_last_24h(uid)
    remaining = max(0, 3 - used)
    return JSONResponse({
        "ok": True,
        "used": used,
        "remaining": remaining,
        "limit": 3
    })


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

            if not title:
                continue

            aid = x.get("id")
            exists_catalog = _pedido_catalog_contains(media_type, title, aid)
            exists_request = media_request_exists(media_type, title, aid)

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
                "already_exists": bool(exists_catalog),
                "already_requested": bool(exists_request),
            })

        return JSONResponse({"ok": True, "items": items})

    except Exception as e:
        print("[pedido] busca AniList falhou:", repr(e), flush=True)
        traceback.print_exc()
        return JSONResponse(
            {"ok": False, "message": "Não foi possível buscar agora."},
            status_code=502
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
def pedido_page():
    html = """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Central de Pedidos — Source Baltigo</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      --bg0:#060b14; --bg1:#0c1627; --card:rgba(255,255,255,.05); --stroke:rgba(255,255,255,.10);
      --stroke2:rgba(255,255,255,.18); --txt:rgba(255,255,255,.94); --muted:rgba(255,255,255,.58);
      --blue:rgba(79,139,255,.30); --blue2:#5da7ff; --green:#45e58d; --red:#ff6565; --yellow:#ffcf5a;
      --shadow:0 20px 40px rgba(0,0,0,.45);
    }
    *{box-sizing:border-box} html,body{height:100%} body{margin:0;font-family:-apple-system,system-ui,Segoe UI,Roboto,Arial,sans-serif;color:var(--txt);background:
      radial-gradient(1000px 500px at 10% 0%, rgba(60,130,246,.18), transparent 60%),
      radial-gradient(900px 500px at 100% 20%, rgba(168,85,247,.14), transparent 60%),
      linear-gradient(180deg,var(--bg0),var(--bg1));}
    .wrap{max-width:960px;margin:0 auto;padding:16px 14px 40px}.hero{border:1px solid var(--stroke);border-radius:28px;overflow:hidden;box-shadow:var(--shadow);background:rgba(255,255,255,.03)}
    .heroTop{position:relative;height:190px;background:linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.70)), url('__PEDIDO_BANNER__') center/cover no-repeat}
    .heroBody{padding:18px}.eyebrow{display:inline-flex;gap:8px;align-items:center;padding:8px 12px;border-radius:999px;border:1px solid rgba(93,167,255,.35);background:rgba(93,167,255,.12);font-size:12px;font-weight:900;letter-spacing:.10em;text-transform:uppercase}
    h1{margin:14px 0 6px;font-size:26px;line-height:1.1}.sub{color:var(--muted);font-size:14px;line-height:1.45}.limitBox{margin-top:16px;display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;padding:14px 16px;border-radius:20px;background:rgba(255,255,255,.04);border:1px solid var(--stroke)}
    .limitBar{height:10px;width:160px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden}.limitFill{height:100%;width:0;background:linear-gradient(90deg,#4f8bff,#45e58d)}
    .tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:18px}.tab{padding:14px 10px;border-radius:18px;text-align:center;border:1px solid var(--stroke);background:rgba(255,255,255,.04);font-weight:900;letter-spacing:.06em;cursor:pointer;user-select:none}.tab.active{background:var(--blue);border-color:rgba(93,167,255,.45)}
    .panel{margin-top:16px;padding:16px;border-radius:24px;border:1px solid var(--stroke);background:rgba(255,255,255,.03);box-shadow:var(--shadow)}
    .searchRow{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.searchWrap{flex:1;min-width:220px;display:flex;gap:10px;align-items:center;padding:14px 14px;border-radius:18px;border:1px solid var(--stroke);background:rgba(255,255,255,.04)}
    .searchWrap input,.reportBox textarea{width:100%;border:0;outline:none;background:transparent;color:var(--txt);font-size:14px}.searchWrap input::placeholder,.reportBox textarea::placeholder{color:rgba(255,255,255,.35)}
    .btn{border:0;border-radius:18px;padding:14px 16px;font-weight:900;letter-spacing:.06em;cursor:pointer}.btnPrimary{background:#5da7ff;color:#08111f}.btnGhost{background:rgba(255,255,255,.06);color:var(--txt);border:1px solid var(--stroke)}
    .hint{margin-top:10px;color:var(--muted);font-size:13px}.results{margin-top:16px;display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.empty{padding:26px 14px;text-align:center;color:var(--muted);border:1px dashed var(--stroke);border-radius:20px;margin-top:16px}
    .card{border-radius:22px;overflow:hidden;border:1px solid var(--stroke);background:rgba(255,255,255,.04);box-shadow:0 16px 28px rgba(0,0,0,.35)}
    .cover{height:220px;background:linear-gradient(135deg,rgba(93,167,255,.16),rgba(255,255,255,.03));position:relative}.cover img{width:100%;height:100%;object-fit:cover;display:block}.badge{position:absolute;left:12px;bottom:12px;padding:8px 10px;border-radius:14px;background:rgba(0,0,0,.45);backdrop-filter:blur(10px);font-size:11px;font-weight:900;letter-spacing:.10em;text-transform:uppercase;border:1px solid rgba(255,255,255,.14)}
    .meta{padding:14px}.title{font-size:14px;font-weight:900;line-height:1.22;letter-spacing:.03em;text-transform:uppercase}.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.chip{padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.10);font-size:11px;font-weight:800;color:rgba(255,255,255,.76)}
    .state{margin-top:12px;font-size:12px;font-weight:900;letter-spacing:.05em}.ok{color:var(--green)} .warn{color:var(--yellow)} .bad{color:#ff8b8b}
    .card .btn{width:100%;margin-top:12px}.reportTypes{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:6px}.rType{padding:12px 10px;border-radius:16px;border:1px solid var(--stroke);background:rgba(255,255,255,.04);text-align:center;font-weight:800;cursor:pointer}.rType.active{background:rgba(255,101,101,.16);border-color:rgba(255,101,101,.38)}
    .reportBox{margin-top:12px;padding:14px;border-radius:18px;border:1px solid var(--stroke);background:rgba(255,255,255,.04)} .reportBox textarea{min-height:130px;resize:vertical}
    .toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);max-width:92vw;padding:14px 16px;border-radius:16px;background:rgba(7,11,20,.92);border:1px solid var(--stroke2);box-shadow:var(--shadow);display:none;z-index:50}.toast.show{display:block}
    .skeleton{height:316px;border-radius:22px;background:linear-gradient(90deg,rgba(255,255,255,.05),rgba(255,255,255,.09),rgba(255,255,255,.05));background-size:200% 100%;animation:sh 1.2s linear infinite} @keyframes sh{0%{background-position:200% 0}100%{background-position:-200% 0}}
    @media (min-width: 760px){.results{grid-template-columns:repeat(3,1fr)}.heroTop{height:240px}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="heroTop"></div>
      <div class="heroBody">
        <div class="eyebrow">📩 Mini App • Central unificada</div>
        <h1>Central de Pedidos</h1>
        <div class="sub">Peça <b>animes</b>, <b>mangás</b> e envie <b>reports</b> em um só lugar, com o mesmo padrão dos outros miniapps do bot.</div>
        <div class="limitBox">
          <div>
            <div style="font-weight:900;letter-spacing:.06em;text-transform:uppercase;font-size:12px">Limite diário</div>
            <div id="limitText" class="sub" style="margin-top:6px">Carregando...</div>
          </div>
          <div class="limitBar"><div class="limitFill" id="limitFill"></div></div>
        </div>
        <div class="tabs">
          <div class="tab active" data-tab="anime">🎬 Anime</div>
          <div class="tab" data-tab="manga">📚 Mangá</div>
          <div class="tab" data-tab="report">⚠️ Reportar erro</div>
        </div>

        <div id="panelAnime" class="panel">
          <div class="searchRow">
            <div class="searchWrap"><span>🔎</span><input id="searchAnime" placeholder="Busque um anime no AniList..."></div>
            <button class="btn btnPrimary" id="btnSearchAnime">Buscar</button>
          </div>
          <div class="hint">Dica: pesquise pelo nome mais conhecido para encontrar mais rápido.</div>
          <div id="animeResults" class="results"></div>
          <div id="animeEmpty" class="empty">Pesquise um anime para começar.</div>
        </div>

        <div id="panelManga" class="panel" style="display:none">
          <div class="searchRow">
            <div class="searchWrap"><span>🔎</span><input id="searchManga" placeholder="Busque um mangá no AniList..."></div>
            <button class="btn btnPrimary" id="btnSearchManga">Buscar</button>
          </div>
          <div class="hint">Você pode pedir mangás, manhwas e novels que apareçam no AniList.</div>
          <div id="mangaResults" class="results"></div>
          <div id="mangaEmpty" class="empty">Pesquise um mangá para começar.</div>
        </div>

        <div id="panelReport" class="panel" style="display:none">
          <div style="font-weight:900;text-transform:uppercase;letter-spacing:.06em;font-size:13px;margin-bottom:12px">Tipo do report</div>
          <div class="reportTypes" id="reportTypes">
            <div class="rType active" data-type="Bug visual">Bug visual</div>
            <div class="rType" data-type="Erro ao abrir">Erro ao abrir</div>
            <div class="rType" data-type="Anime faltando">Anime faltando</div>
            <div class="rType" data-type="Mangá faltando">Mangá faltando</div>
            <div class="rType" data-type="Card errado">Card errado</div>
            <div class="rType" data-type="Outro">Outro</div>
          </div>
          <div class="reportBox"><textarea id="reportMessage" placeholder="Descreva o problema com o máximo de detalhe possível..."></textarea></div>
          <div class="hint">O report é enviado para o mesmo canal privado de pedidos.</div>
          <button class="btn btnPrimary" id="btnSendReport" style="margin-top:12px;width:100%">Enviar report</button>
        </div>
      </div>
    </div>
  </div>

  <div class="toast" id="toast"></div>

<script>
const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
if (tg) {
  try {
    tg.ready();
    tg.expand();
  } catch (e) {}
}

const user = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) ? tg.initDataUnsafe.user : null;
const currentUser = {
  id: user && user.id ? Number(user.id) : 0,
  username: user && user.username ? user.username : '',
  full_name: user ? [user.first_name || '', user.last_name || ''].join(' ').trim() : ''
};

let currentTab = 'anime';
let currentReportType = 'Bug visual';
let limitState = {limit:3, used:0, remaining:3};

function toast(msg){
  const el=document.getElementById('toast');
  el.textContent=msg;
  el.classList.add('show');
  clearTimeout(window.__toastT);
  window.__toastT=setTimeout(()=>el.classList.remove('show'), 3400);
}

function esc(s){
  return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
}

function setTab(tab){
  currentTab=tab;
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active', x.dataset.tab===tab));
  document.getElementById('panelAnime').style.display = tab==='anime'?'block':'none';
  document.getElementById('panelManga').style.display = tab==='manga'?'block':'none';
  document.getElementById('panelReport').style.display = tab==='report'?'block':'none';
}

async function getJSON(url){
  const r=await fetch(url);
  const d=await r.json();
  if(!r.ok || d.ok===false) throw new Error(d.message || 'Erro');
  return d;
}

async function postJSON(url,payload){
  const r=await fetch(url,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)
  });
  const d=await r.json();
  if(!r.ok || d.ok===false) throw new Error(d.message || 'Erro');
  return d;
}

function updateLimitUI(){
  const used=limitState.used||0;
  const limit=limitState.limit||3;
  const remaining=Math.max(0, limit-used);
  document.getElementById('limitText').textContent = `Pedidos restantes hoje: ${remaining}/${limit}`;
  document.getElementById('limitFill').style.width = `${Math.min(100,(used/limit)*100)}%`;
}

async function loadLimit(){
  if(!currentUser.id){
    document.getElementById('limitText').textContent='Abra este Mini App pelo Telegram.';
    return;
  }
  try{
    limitState = await getJSON(`/api/pedido/limit?uid=${currentUser.id}`);
    updateLimitUI();
  }catch(e){
    document.getElementById('limitText').textContent='Não foi possível carregar o limite.';
  }
}

function skeletons(containerId, emptyId){
  document.getElementById(emptyId).style.display='none';
  const c=document.getElementById(containerId);
  c.innerHTML='';
  for(let i=0;i<6;i++){
    const d=document.createElement('div');
    d.className='skeleton';
    c.appendChild(d);
  }
}

function renderResults(containerId, emptyId, items, mediaType){
  const c=document.getElementById(containerId);
  const e=document.getElementById(emptyId);
  c.innerHTML='';

  if(!items || !items.length){
    e.textContent='Nenhum resultado encontrado.';
    e.style.display='block';
    return;
  }

  e.style.display='none';

  for(const item of items){
    const stateText = item.already_exists
      ? 'Já está disponível no catálogo'
      : (item.already_requested
          ? 'Já foi pedido e está em análise'
          : 'Disponível para pedido');

    const stateClass = item.already_exists ? 'bad' : (item.already_requested ? 'warn' : 'ok');

    const sub = [];
    if(item.year) sub.push(item.year);
    if(item.score) sub.push('★ '+item.score);
    if(item.format) sub.push(item.format);
    if(mediaType==='anime' && item.episodes) sub.push(item.episodes+' eps');
    if(mediaType==='manga' && item.chapters) sub.push(item.chapters+' caps');

    const disabled = item.already_exists || item.already_requested || (limitState.used >= (limitState.limit||3));

    const el=document.createElement('div');
    el.className='card';
    el.innerHTML = `
      <div class="cover">
        ${item.cover ? `<img src="${esc(item.cover)}" alt="${esc(item.title)}">` : ''}
        <div class="badge">${esc(mediaType.toUpperCase())}</div>
      </div>
      <div class="meta">
        <div class="title">${esc(item.title)}</div>
        <div class="chips">${sub.map(x=>`<span class="chip">${esc(x)}</span>`).join('')}</div>
        <div class="state ${stateClass}">${esc(stateText)}</div>
        <button class="btn ${disabled ? 'btnGhost' : 'btnPrimary'}" ${disabled ? 'disabled' : ''}>
          ${disabled ? 'Indisponível' : 'Pedir agora'}
        </button>
      </div>
    `;

    const btn = el.querySelector('button');
    if(!disabled){
      btn.addEventListener('click', ()=>sendRequest(mediaType, item));
    }

    c.appendChild(el);
  }
}

async function runSearch(mediaType){
  if(!currentUser.id){
    toast('Abra este Mini App dentro do Telegram.');
    return;
  }

  const inputId = mediaType==='anime' ? 'searchAnime' : 'searchManga';
  const containerId = mediaType==='anime' ? 'animeResults' : 'mangaResults';
  const emptyId = mediaType==='anime' ? 'animeEmpty' : 'mangaEmpty';
  const q=(document.getElementById(inputId).value||'').trim();

  if(!q){
    toast('Digite um nome para buscar.');
    return;
  }

  skeletons(containerId, emptyId);

  try{
    const data = await getJSON(`/api/pedido/search?q=${encodeURIComponent(q)}&media_type=${mediaType}`);
    renderResults(containerId, emptyId, data.items||[], mediaType);
  }catch(e){
    document.getElementById(containerId).innerHTML='';
    document.getElementById(emptyId).textContent=e.message || 'Não foi possível buscar agora.';
    document.getElementById(emptyId).style.display='block';
  }
}

async function sendRequest(mediaType, item){
  if(!currentUser.id){
    toast('Abra este Mini App dentro do Telegram.');
    return;
  }

  try{
    const data = await postJSON('/api/pedido/send', {
      user_id: currentUser.id,
      username: currentUser.username,
      full_name: currentUser.full_name,
      media_type: mediaType,
      anilist_id: item.id,
      title: item.title,
      cover: item.cover || ''
    });

    limitState.used = data.used;
    limitState.remaining = data.remaining;
    updateLimitUI();
    toast(`✅ ${item.title} enviado com sucesso.`);
  }catch(e){
    toast(e.message || 'Não foi possível enviar o pedido.');
  }
}

async function sendReport(){
  if(!currentUser.id){
    toast('Abra este Mini App dentro do Telegram.');
    return;
  }

  const message=(document.getElementById('reportMessage').value||'').trim();
  if(!message){
    toast('Descreva o problema antes de enviar.');
    return;
  }

  try{
    await postJSON('/api/pedido/report', {
      user_id: currentUser.id,
      username: currentUser.username,
      full_name: currentUser.full_name,
      report_type: currentReportType,
      message
    });
    document.getElementById('reportMessage').value='';
    toast('✅ Report enviado com sucesso.');
  }catch(e){
    toast(e.message || 'Não foi possível enviar o report.');
  }
}

document.querySelectorAll('.tab').forEach(el=>el.addEventListener('click',()=>setTab(el.dataset.tab)));
document.querySelectorAll('.rType').forEach(el=>el.addEventListener('click',()=>{
  document.querySelectorAll('.rType').forEach(x=>x.classList.remove('active'));
  el.classList.add('active');
  currentReportType=el.dataset.type;
}));
document.getElementById('btnSearchAnime').addEventListener('click',()=>runSearch('anime'));
document.getElementById('btnSearchManga').addEventListener('click',()=>runSearch('manga'));
document.getElementById('btnSendReport').addEventListener('click',sendReport);
document.getElementById('searchAnime').addEventListener('keydown',(e)=>{ if(e.key==='Enter') runSearch('anime'); });
document.getElementById('searchManga').addEventListener('keydown',(e)=>{ if(e.key==='Enter') runSearch('manga'); });

loadLimit();
</script>
</body>
</html>
"""
    return HTMLResponse(html.replace("__PEDIDO_BANNER__", PEDIDO_BANNER_URL))

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

_DADO_RATE: Dict[Tuple[int, str], float] = {}
_DADO_LOCAL_CACHE: Dict[str, Any] = {
    "mtime": 0.0,
    "loaded": False,
    "path": "",
    "animes_list": [],
    "animes_by_id": {},
    "characters_by_anime": {},
}


def _dado_rate_limit(user_id: int, key: str, window: float = DADO_WEB_RATE_SECONDS) -> bool:
    now = time.time()
    k = (int(user_id), str(key))
    last = _DADO_RATE.get(k, 0.0)
    if now - last < window:
        return False
    _DADO_RATE[k] = now
    return True


# =========================================================
# TELEGRAM WEBAPP AUTH
# =========================================================

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

def _safe_int(v: Any, default: int = 0) -> int:
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
        anime_id = _safe_int(item.get("anime_id"), 0)
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

                cid = _safe_int(c.get("id"), 0)
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
def api_dado_state(x_telegram_init_data: str = Header(default="")):
    tg = _get_tg_user(x_telegram_init_data)
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
async def api_dado_roll(x_telegram_init_data: str = Header(default="")):
    tg = _get_tg_user(x_telegram_init_data)
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
            chat_id=user_id,
            photo=image,
            caption=(
                "🎁 <b>VOCÊ GANHOU!</b>\n\n"
                f"🧧 <code>{char_id}</code>. <b>{name}</b>\n"
                f"<i>{anime_title}</i>\n\n"
                "📦 <b>Adicionado à sua coleção!</b>"
            ),
        )
    except Exception:
        pass

    return JSONResponse({
        "ok": True,
        "roll_id": int(roll_id),
        "balance": balance,
        "character": {
            "id": char_id,
            "name": name,
            "image": image,
            "anime_title": anime_title,
            "anime_cover": char["anime_cover"],
            "tier": rarity["tier"],
            "stars": rarity["stars"],
        },
    })


# =========================================================
# PAGE — /dado
# =========================================================

@app.get("/dado", response_class=HTMLResponse)
def dado_page():
    html = """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Sistema de Dados — Source Baltigo</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>

  <style>
    :root{
      --bg0:#050913;
      --bg1:#0b1222;
      --panel:rgba(255,255,255,.045);
      --panel2:rgba(255,255,255,.03);
      --stroke:rgba(255,255,255,.11);
      --txt:rgba(255,255,255,.96);
      --muted:rgba(255,255,255,.62);
      --pink:#ff2bd6;
      --cyan:#00f2ff;
      --gold:#ffd65a;
      --ok:#63ffa8;
      --shadow:0 18px 38px rgba(0,0,0,.48);
      --shadow2:0 12px 24px rgba(0,0,0,.30);
    }

    *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
    html,body{height:100%}
    body{
      margin:0;
      font-family:-apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
      color:var(--txt);
      background:
        radial-gradient(1200px 700px at 50% -10%, rgba(0,242,255,.12), transparent 55%),
        radial-gradient(900px 500px at 20% 20%, rgba(255,43,214,.10), transparent 50%),
        linear-gradient(180deg,var(--bg0),var(--bg1));
      overflow-x:hidden;
    }

    .wrap{
      max-width:980px;
      margin:0 auto;
      padding:14px 14px 34px;
    }

    .banner{
      border-radius:24px;
      overflow:hidden;
      border:1px solid var(--stroke);
      box-shadow:var(--shadow);
      position:relative;
      background:#000;
    }

    .banner img{
      width:100%;
      height:220px;
      object-fit:cover;
      display:block;
    }

    .banner:after{
      content:"";
      position:absolute; inset:0;
      background:linear-gradient(180deg,rgba(0,0,0,.06),rgba(0,0,0,.72));
    }

    .hero{
      margin-top:14px;
      border-radius:24px;
      border:1px solid var(--stroke);
      background:rgba(255,255,255,.035);
      box-shadow:var(--shadow);
      padding:16px;
      backdrop-filter:blur(8px);
    }

    .title{
      font-size:24px;
      font-weight:1000;
      letter-spacing:.08em;
      text-transform:uppercase;
    }

    .sub{
      margin-top:8px;
      color:var(--muted);
      font-size:14px;
      font-weight:700;
      line-height:1.5;
    }

    .stats{
      margin-top:16px;
      display:grid;
      grid-template-columns:repeat(3,1fr);
      gap:12px;
    }

    @media (max-width:760px){
      .stats{grid-template-columns:1fr}
    }

    .stat{
      border-radius:20px;
      background:var(--panel);
      border:1px solid var(--stroke);
      padding:16px;
      box-shadow:var(--shadow2);
    }

    .stat .k{
      color:var(--muted);
      font-size:12px;
      font-weight:900;
      letter-spacing:.12em;
      text-transform:uppercase;
    }

    .stat .v{
      margin-top:8px;
      font-size:24px;
      font-weight:1000;
      line-height:1.2;
    }

    .diceStage{
      margin-top:16px;
      border-radius:24px;
      overflow:hidden;
      border:1px solid var(--stroke);
      background:
        radial-gradient(circle at 50% 0%, rgba(255,43,214,.08), transparent 38%),
        radial-gradient(circle at 50% 100%, rgba(0,242,255,.08), transparent 38%),
        rgba(255,255,255,.025);
      box-shadow:var(--shadow);
      min-height:360px;
      position:relative;
    }

    #sceneWrap{
      width:100%;
      height:360px;
      position:relative;
    }

    .hud{
      position:absolute;
      left:0; right:0; bottom:14px;
      display:flex;
      justify-content:center;
      pointer-events:none;
      padding:0 14px;
    }

    .hudTag{
      max-width:100%;
      padding:10px 14px;
      border-radius:999px;
      background:rgba(0,0,0,.38);
      border:1px solid rgba(255,255,255,.12);
      font-weight:900;
      font-size:12px;
      letter-spacing:.12em;
      text-transform:uppercase;
      box-shadow:0 8px 18px rgba(0,0,0,.28);
      white-space:nowrap;
      overflow:hidden;
      text-overflow:ellipsis;
    }

    .actions{
      margin-top:16px;
      display:flex;
      gap:12px;
      flex-wrap:wrap;
    }

    .btn{
      flex:1;
      min-width:180px;
      border:none;
      border-radius:18px;
      padding:16px 14px;
      color:#fff;
      font-weight:1000;
      letter-spacing:.1em;
      text-transform:uppercase;
      cursor:pointer;
      box-shadow:0 18px 30px rgba(0,0,0,.3);
      transition:transform .15s ease, opacity .15s ease, filter .15s ease;
    }

    .btn:hover{filter:brightness(1.05)}
    .btn:active{transform:scale(.985)}
    .btn[disabled]{opacity:.45;cursor:not-allowed}

    .btnRoll{
      background:linear-gradient(135deg, rgba(255,43,214,.92), rgba(0,242,255,.92));
      border:1px solid rgba(255,255,255,.18);
    }

    .btnReset{
      background:linear-gradient(135deg, rgba(255,214,90,.30), rgba(255,214,90,.18));
      border:1px solid rgba(255,214,90,.28);
    }

    .msg{
      margin-top:14px;
      min-height:20px;
      color:rgba(255,255,255,.76);
      font-size:13px;
      font-weight:800;
      white-space:pre-wrap;
    }

    .animeGrid{
      margin-top:18px;
      display:grid;
      grid-template-columns:repeat(2,minmax(0,1fr));
      gap:12px;
    }

    @media (max-width:720px){
      .animeGrid{grid-template-columns:1fr}
    }

    .animeCard{
      appearance:none;
      width:100%;
      padding:0;
      border:none;
      border-radius:18px;
      overflow:hidden;
      border:1px solid rgba(255,255,255,.12);
      background:#0f1728;
      box-shadow:0 14px 28px rgba(0,0,0,.28);
      cursor:pointer;
      transition:transform .16s ease, border-color .16s ease, filter .16s ease;
      text-align:left;
      color:#fff;
      position:relative;
      min-height:92px;
    }

    .animeCard:hover{
      transform:translateY(-2px);
      border-color:rgba(0,242,255,.42);
      filter:brightness(1.02);
    }

    .animeCard[aria-disabled="true"]{
      opacity:.55;
      pointer-events:none;
    }

    .animeBg{
      position:absolute;
      inset:0;
      background-size:cover;
      background-position:center;
      transform:scale(1.04);
      filter:blur(.5px) saturate(1.05);
      opacity:.34;
    }

    .animeOverlay{
      position:absolute;
      inset:0;
      background:
        linear-gradient(90deg, rgba(6,10,18,.92) 0%, rgba(6,10,18,.78) 46%, rgba(6,10,18,.62) 100%),
        linear-gradient(180deg, rgba(255,43,214,.08), rgba(0,242,255,.06));
    }

    .animeMeta{
      position:relative;
      z-index:2;
      min-height:92px;
      display:flex;
      flex-direction:column;
      justify-content:center;
      padding:16px;
    }

    .animeTitle{
      font-size:18px;
      font-weight:1000;
      line-height:1.22;
      color:#fff;
      text-shadow:0 2px 10px rgba(0,0,0,.38);
      word-break:break-word;
    }

    .animeHint{
      margin-top:8px;
      color:rgba(255,255,255,.72);
      font-size:12px;
      font-weight:900;
      letter-spacing:.10em;
      text-transform:uppercase;
    }

    .reveal{
      margin-top:18px;
      border-radius:24px;
      border:1px solid var(--stroke);
      background:rgba(255,255,255,.035);
      box-shadow:var(--shadow);
      overflow:hidden;
      display:none;
    }

    .reveal.show{
      display:block;
      animation:fadeUp .35s ease;
    }

    .revealImg{
      width:100%;
      height:300px;
      object-fit:cover;
      display:block;
      background:#111;
    }

    .revealBody{padding:16px}

    .rarity{
      display:inline-flex;
      align-items:center;
      gap:8px;
      border-radius:999px;
      padding:8px 12px;
      background:rgba(255,255,255,.05);
      border:1px solid rgba(255,255,255,.12);
      font-size:12px;
      font-weight:1000;
      letter-spacing:.12em;
      text-transform:uppercase;
    }

    .charName{
      margin-top:12px;
      font-size:24px;
      font-weight:1000;
      line-height:1.2;
    }

    .animeFrom{
      margin-top:8px;
      color:var(--muted);
      font-weight:800;
      font-size:14px;
    }

    .footer{
      margin-top:16px;
      text-align:center;
      color:rgba(255,255,255,.38);
      font-size:12px;
      font-weight:800;
      letter-spacing:.08em;
    }

    @keyframes fadeUp{
      from{opacity:0;transform:translateY(10px)}
      to{opacity:1;transform:translateY(0)}
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="banner">
      <img src="__DADO_BANNER_URL__" alt="Sistema de Dados">
    </div>

    <div class="hero">
      <div class="title">Sistema de Dados</div>
      <div class="sub">
        Role o dado 3D, receba entre 1 e 6 opções de anime e escolha uma para revelar um personagem da sua coleção.
      </div>

      <div class="stats">
        <div class="stat">
          <div class="k">Dados disponíveis</div>
          <div class="v" id="balanceTxt">...</div>
        </div>
        <div class="stat">
          <div class="k">Próximo dado</div>
          <div class="v" id="nextTxt">...</div>
        </div>
        <div class="stat">
          <div class="k">Recargas</div>
          <div class="v" style="font-size:16px;line-height:1.5">01h, 04h, 07h, 10h, 13h, 16h, 19h e 22h</div>
        </div>
      </div>

      <div class="diceStage">
        <div id="sceneWrap"></div>
        <div class="hud"><div class="hudTag" id="hudTxt">Pronto para rolar</div></div>
      </div>

      <div class="actions">
        <button id="rollBtn" class="btn btnRoll">Rolar Dado</button>
        <button id="resetBtn" class="btn btnReset" type="button">Limpar tela</button>
      </div>

      <div class="msg" id="msg">Carregando seus dados...</div>

      <div id="animeGrid" class="animeGrid"></div>

      <div id="revealBox" class="reveal">
        <img id="revealImg" class="revealImg" src="" alt="Personagem">
        <div class="revealBody">
          <div id="rarityTxt" class="rarity">REWARD</div>
          <div id="charName" class="charName"></div>
          <div id="animeFrom" class="animeFrom"></div>
        </div>
      </div>
    </div>

    <div class="footer">Source Baltigo • Dado Gacha</div>
  </div>

  <script>
    const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
    const DADO_BANNER_FALLBACK = "__DADO_BANNER_URL__";

    if (tg) {
      try {
        tg.ready();
        tg.expand();
        tg.setHeaderColor("#0b1222");
        tg.setBackgroundColor("#060912");
      } catch(e) {}
    }

    const state = {
      balance: 0,
      nextRecharge: "--:--",
      currentRollId: 0,
      currentDice: 0,
      rolling: false,
      choosing: false,
      options: [],
    };

    const msg = document.getElementById("msg");
    const balanceTxt = document.getElementById("balanceTxt");
    const nextTxt = document.getElementById("nextTxt");
    const hudTxt = document.getElementById("hudTxt");
    const animeGrid = document.getElementById("animeGrid");
    const revealBox = document.getElementById("revealBox");
    const revealImg = document.getElementById("revealImg");
    const rarityTxt = document.getElementById("rarityTxt");
    const charName = document.getElementById("charName");
    const animeFrom = document.getElementById("animeFrom");
    const rollBtn = document.getElementById("rollBtn");
    const resetBtn = document.getElementById("resetBtn");

    function setMsg(text){ msg.textContent = text || ""; }
    function setHud(text){ hudTxt.textContent = text || ""; }
    function setBalance(v){ balanceTxt.textContent = String(v ?? 0); }
    function setNext(v){ nextTxt.textContent = String(v || "--:--"); }

    function clearReveal(){
      revealBox.classList.remove("show");
      revealImg.src = "";
      charName.textContent = "";
      animeFrom.textContent = "";
      rarityTxt.textContent = "REWARD";
    }

    function clearAnimeCards(){
      animeGrid.innerHTML = "";
    }

    function resetScreen(){
      clearAnimeCards();
      clearReveal();
      state.currentRollId = 0;
      state.currentDice = 0;
      state.options = [];
      setHud("Pronto para rolar");
      setMsg("Tela limpa.");
    }

    async function apiGet(url){
      const res = await fetch(url + "?_ts=" + Date.now(), {
        headers: {"X-Telegram-Init-Data": tg ? tg.initData : ""}
      });
      let data = {};
      try { data = await res.json(); } catch(e) {}
      if (!res.ok) {
        throw new Error(data.detail || ("Erro HTTP " + res.status));
      }
      return data;
    }

    async function apiPost(url, payload){
      const res = await fetch(url + "?_ts=" + Date.now(), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": tg ? tg.initData : ""
        },
        body: JSON.stringify(payload || {})
      });
      let data = {};
      try { data = await res.json(); } catch(e) {}
      if (!res.ok) {
        throw new Error(data.detail || ("Erro HTTP " + res.status));
      }
      return data;
    }

    let renderer, scene, camera, dice, particles = [];
    let ambient, point, frameHandle = 0;

    function createFaceTexture(value, rotateDeg = 0){
      const c = document.createElement("canvas");
      c.width = 512;
      c.height = 512;
      const ctx = c.getContext("2d");

      const g = ctx.createLinearGradient(0, 0, 512, 512);
      g.addColorStop(0, "#1b2340");
      g.addColorStop(1, "#0a0f1e");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, 512, 512);

      ctx.strokeStyle = "rgba(255,255,255,.18)";
      ctx.lineWidth = 12;
      ctx.strokeRect(18, 18, 476, 476);

      ctx.save();
      ctx.translate(256, 256);
      ctx.rotate((rotateDeg * Math.PI) / 180);

      ctx.shadowColor = "rgba(0,242,255,.65)";
      ctx.shadowBlur = 28;
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 250px Arial";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(value), 0, 18);

      ctx.restore();

      const tex = new THREE.CanvasTexture(c);
      tex.needsUpdate = true;
      return tex;
    }

    function setupScene(){
      const el = document.getElementById("sceneWrap");
      const w = el.clientWidth;
      const h = el.clientHeight;

      renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(w, h);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      el.innerHTML = "";
      el.appendChild(renderer.domElement);

      scene = new THREE.Scene();
      camera = new THREE.PerspectiveCamera(38, w / h, 0.1, 100);
      camera.position.set(0, 0.8, 6.8);

      ambient = new THREE.AmbientLight(0xffffff, 1.45);
      scene.add(ambient);

      point = new THREE.PointLight(0xffffff, 2.0, 30);
      point.position.set(2.8, 3.6, 5.2);
      scene.add(point);

      const floorGeo = new THREE.CircleGeometry(2.9, 64);
      const floorMat = new THREE.MeshBasicMaterial({
        color: 0x112031,
        transparent: true,
        opacity: .36
      });
      const floor = new THREE.Mesh(floorGeo, floorMat);
      floor.rotation.x = -Math.PI / 2;
      floor.position.y = -1.55;
      scene.add(floor);

      const mats = [
        new THREE.MeshStandardMaterial({ map: createFaceTexture(2, -90), roughness: 0.42, metalness: 0.35 }),
        new THREE.MeshStandardMaterial({ map: createFaceTexture(5,  90), roughness: 0.42, metalness: 0.35 }),
        new THREE.MeshStandardMaterial({ map: createFaceTexture(3,   0), roughness: 0.42, metalness: 0.35 }),
        new THREE.MeshStandardMaterial({ map: createFaceTexture(4, 180), roughness: 0.42, metalness: 0.35 }),
        new THREE.MeshStandardMaterial({ map: createFaceTexture(1,   0), roughness: 0.42, metalness: 0.35 }),
        new THREE.MeshStandardMaterial({ map: createFaceTexture(6, 180), roughness: 0.42, metalness: 0.35 }),
      ];

      const geo = new THREE.BoxGeometry(2.05, 2.05, 2.05, 1, 1, 1);
      dice = new THREE.Mesh(geo, mats);
      scene.add(dice);

      const edgeGeo = new THREE.EdgesGeometry(geo);
      const edgeMat = new THREE.LineBasicMaterial({color: 0x6ae7ff, transparent:true, opacity:.55});
      const edges = new THREE.LineSegments(edgeGeo, edgeMat);
      dice.add(edges);

      particles = [];
      for (let i = 0; i < 48; i++) {
        const pGeo = new THREE.SphereGeometry(0.03, 8, 8);
        const pMat = new THREE.MeshBasicMaterial({color: (i % 2 ? 0x00f2ff : 0xff2bd6)});
        const p = new THREE.Mesh(pGeo, pMat);
        p.position.set(
          (Math.random() - .5) * 4,
          (Math.random() - .5) * 3,
          (Math.random() - .5) * 3
        );
        p.userData = {
          vx: (Math.random() - .5) * 0.02,
          vy: (Math.random() - .5) * 0.02,
          vz: (Math.random() - .5) * 0.02,
        };
        scene.add(p);
        particles.push(p);
      }

      cancelAnimationFrame(frameHandle);
      const tick = () => {
        if (!renderer || !scene || !camera || !dice) return;
        if (!state.rolling) {
          dice.rotation.x += 0.0022;
          dice.rotation.y += 0.003;
        }
        particles.forEach(p => {
          p.position.x += p.userData.vx;
          p.position.y += p.userData.vy;
          p.position.z += p.userData.vz;
          if (Math.abs(p.position.x) > 3) p.userData.vx *= -1;
          if (Math.abs(p.position.y) > 2) p.userData.vy *= -1;
          if (Math.abs(p.position.z) > 2) p.userData.vz *= -1;
        });
        renderer.render(scene, camera);
        frameHandle = requestAnimationFrame(tick);
      };
      tick();
    }

    function resizeScene(){
      const el = document.getElementById("sceneWrap");
      if (!renderer || !camera || !el) return;
      const w = el.clientWidth;
      const h = el.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }

    async function animateDiceResult(value){
      if (!dice) return;

      state.rolling = true;
      rollBtn.disabled = true;
      setHud("Rolando...");
      clearAnimeCards();
      clearReveal();

      const targets = {
        1: { x: 0, y: 0 },
        2: { x: 0, y: -Math.PI / 2 },
        3: { x: Math.PI / 2, y: 0 },
        4: { x: -Math.PI / 2, y: 0 },
        5: { x: 0, y: Math.PI / 2 },
        6: { x: 0, y: Math.PI },
      };

      const t = targets[value] || targets[1];

      const baseX = dice.rotation.x;
      const baseY = dice.rotation.y;
      const baseZ = dice.rotation.z;

      const endX = t.x + (Math.PI * 8);
      const endY = t.y + (Math.PI * 9);
      const endZ = baseZ + (Math.PI * 2.5);

      const duration = 1850;
      const start = performance.now();

      await new Promise(resolve => {
        function step(now){
          const p = Math.min((now - start) / duration, 1);
          const ease = 1 - Math.pow(1 - p, 4);

          dice.rotation.x = baseX + (endX - baseX) * ease;
          dice.rotation.y = baseY + (endY - baseY) * ease;
          dice.rotation.z = baseZ + (endZ - baseZ) * (1 - Math.pow(1 - p, 3)) * 0.10;

          camera.position.x = Math.sin(p * Math.PI * 2) * 0.22;
          camera.position.y = 0.8 + Math.sin(p * Math.PI * 5) * 0.08;
          camera.lookAt(0, 0, 0);

          if (p < 1) {
            requestAnimationFrame(step);
          } else {
            resolve();
          }
        }
        requestAnimationFrame(step);
      });

      dice.rotation.x = t.x;
      dice.rotation.y = t.y;
      dice.rotation.z = 0;

      camera.position.set(0, 0.8, 6.8);
      camera.lookAt(0, 0, 0);

      setHud("Resultado: " + value);
      state.rolling = false;
      rollBtn.disabled = false;
    }

    function renderAnimeOptions(options){
      animeGrid.innerHTML = "";
      clearReveal();

      if (!Array.isArray(options) || !options.length) {
        setMsg("Nenhuma opção encontrada para esta rolagem.");
        return;
      }

      options.forEach((opt, idx) => {
        const title = (opt && opt.title) ? String(opt.title) : ("Anime " + (idx + 1));
        const cover = (opt && opt.cover) ? String(opt.cover) : DADO_BANNER_FALLBACK;

        const card = document.createElement("button");
        card.type = "button";
        card.className = "animeCard";
        card.innerHTML = `
          <div class="animeBg" style="background-image:url('${cover.replace(/'/g, "\\'")}')"></div>
          <div class="animeOverlay"></div>
          <div class="animeMeta">
            <div class="animeTitle">${title}</div>
            <div class="animeHint">Toque para escolher</div>
          </div>
        `;
        card.addEventListener("click", () => chooseAnime(opt));
        animeGrid.appendChild(card);
      });
    }

    async function chooseAnime(opt){
      if (!state.currentRollId || state.choosing) return;
      state.choosing = true;

      [...animeGrid.children].forEach(el => el.setAttribute("aria-disabled", "true"));
      setMsg("Revelando personagem...");
      setHud("Escolha confirmada");

      try {
        const data = await apiPost("/api/dado/pick", {
          roll_id: state.currentRollId,
          anime_id: Number(opt.id),
        });

        if (!data.ok) {
          const msgMap = {
            rate_limited: "Espere um instante antes de escolher novamente.",
            character_not_found: "Nenhum personagem válido foi encontrado para este anime.",
            roll_not_found: "Essa rolagem não foi encontrada.",
            expired: "Sua rolagem expirou. Role novamente.",
            anime_not_in_roll: "Esse anime não pertence à rolagem atual.",
            roll_invalid: "A rolagem ficou inválida e foi cancelada. Role novamente.",
          };
          throw new Error(msgMap[data.error] || data.error || "Falha ao revelar personagem.");
        }

        const ch = data.character || {};
        setBalance(data.balance ?? state.balance);

        revealImg.src = ch.image || opt.cover || DADO_BANNER_FALLBACK;
        rarityTxt.textContent = `${ch.tier || "COMMON"} • ${"★".repeat(Number(ch.stars || 1))}`;
        charName.textContent = ch.name || "Personagem";
        animeFrom.textContent = "Obtido de " + (ch.anime_title || opt.title || "Anime");
        revealBox.classList.add("show");

        setHud("Personagem revelado");
        setMsg("✨ Personagem obtido com sucesso.");
      } catch (e) {
        [...animeGrid.children].forEach(el => el.removeAttribute("aria-disabled"));
        setMsg("❌ " + (e.message || "Falha ao escolher anime."));
      } finally {
        state.choosing = false;
      }
    }

    async function loadState(){
      try {
        if (!tg || !tg.initData) {
          setMsg("Abra este WebApp pelo Telegram.");
          rollBtn.disabled = true;
          return;
        }

        const data = await apiGet("/api/dado/state");
        setBalance(data.balance ?? 0);
        setNext(data.next_recharge_hhmm || "--:--");
        state.balance = Number(data.balance || 0);

        if (data.active_roll && data.active_roll.roll_id) {
          state.currentRollId = Number(data.active_roll.roll_id);
          state.currentDice = Number(data.active_roll.dice_value || 0);
          state.options = Array.isArray(data.active_roll.options) ? data.active_roll.options : [];

          if (state.currentDice > 0) {
            await animateDiceResult(state.currentDice);
          }

          if (state.options.length) {
            renderAnimeOptions(state.options);
            setMsg("Você tinha uma rolagem ativa. Continue escolhendo.");
          } else {
            setMsg("Você tinha uma rolagem ativa, mas sem opções visíveis. Role novamente se necessário.");
          }
        } else {
          setMsg("Tudo pronto. Role o dado quando quiser.");
        }

        rollBtn.disabled = false;
      } catch (e) {
        rollBtn.disabled = true;
        setMsg("❌ " + (e.message || "Não consegui carregar seus dados."));
      }
    }

    async function rollDice(){
      if (state.rolling || state.choosing) return;
      if (!tg || !tg.initData) {
        setMsg("Abra este WebApp pelo Telegram.");
        return;
      }

      rollBtn.disabled = true;
      clearAnimeCards();
      clearReveal();
      setMsg("Rolando dado...");
      setHud("Rolando...");

      try {
        const data = await apiPost("/api/dado/roll", {});

        if (!data.ok) {
          const msgMap = {
            no_balance: "Você está sem dados agora.",
            rate_limited: "Espere um instante antes de rolar novamente.",
            anime_pool_unavailable: "A base local de animes não está disponível no momento.",
          };
          throw new Error(msgMap[data.error] || data.error || "Falha ao rolar.");
        }

        state.currentRollId = Number(data.roll_id || 0);
        state.currentDice = Number(data.dice_value || 1);
        state.options = Array.isArray(data.options) ? data.options : [];
        setBalance(data.balance ?? 0);

        await animateDiceResult(state.currentDice);

        if (!state.options.length) {
          throw new Error("A rolagem veio sem opções de anime.");
        }

        renderAnimeOptions(state.options);
        setMsg("Escolha um anime para revelar o personagem.");
      } catch (e) {
        setMsg("❌ " + (e.message || "Erro ao rolar dado."));
        setHud("Falha na rolagem");
      } finally {
        rollBtn.disabled = false;
      }
    }

    rollBtn.addEventListener("click", rollDice);
    resetBtn.addEventListener("click", resetScreen);
    window.addEventListener("resize", resizeScene);

    setupScene();
    loadState();
  </script>
</body>
</html>
"""
    html = html.replace("__DADO_BANNER_URL__", DADO_BANNER_URL)
    return HTMLResponse(html)

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
            "image": str(ch.get("image") or "").strip(),
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
        <input id="nicknameInput" placeholder="Ex: Kayky" maxlength="17" />
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
    bg = MENU_BACKGROUND_URL if MENU_BACKGROUND_URL else EMPTY_BG_DATA_URI

    html = (
        MENU_HTML
        .replace("__UID__", str(int(uid)))
        .replace("__MENU_BANNER__", MENU_BANNER_URL)
        .replace("__MENU_BG__", bg)
    )
    return HTMLResponse(html)


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

    return JSONResponse({
        "ok": True,
        "items": _menu_collection_characters(uid),
    })


@app.post("/api/menu/nickname")
def api_menu_nickname(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    nickname = str(payload.get("nickname") or "").strip()

    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)

    if not _valid_menu_nickname(nickname):
        return JSONResponse({
            "ok": False,
            "message": "Nickname inválido. Use 4-17 caracteres, começando com letra maiúscula."
        }, status_code=400)

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

    items = _menu_collection_characters(uid)
    owned_ids = {int(item["id"]) for item in items}

    if character_id not in owned_ids:
        return JSONResponse({
            "ok": False,
            "message": "Você só pode favoritar personagens da sua coleção."
        }, status_code=400)

    set_profile_favorite(uid, character_id)
    return {"ok": True}


@app.post("/api/menu/country")
def api_menu_country(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    country_code = str(payload.get("country_code") or "BR").strip().upper()

    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)

    valid = {c["code"] for c in COUNTRY_OPTIONS}
    if country_code not in valid:
        return JSONResponse({"ok": False, "message": "País inválido."}, status_code=400)

    set_profile_country(uid, country_code)
    return {"ok": True}


@app.post("/api/menu/language")
def api_menu_language(payload: dict = Body(...)):
    uid = int(payload.get("uid") or 0)
    language = str(payload.get("language") or "pt").strip().lower()

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

# =========================
# UI: /shop — Loja
# =========================
@app.get("/shop", response_class=HTMLResponse)
def miniapp_shop():

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1, viewport-fit=cover'>"
        "<title>Baltigo • Loja</title>"
        "<style>" + _theme_css() + r"""

/* =========================
LOJA
========================= */

.search{margin:10px 0 14px;}

.actions{
  display:flex;
  gap:10px;
  margin-top:10px;
}

.buyGrid{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:12px;
  margin-top:12px;
}

.shopCard{
  border-radius:22px;
  padding:14px;
  position:relative;
  overflow:hidden;
}

.shopCard h3{
  margin:0;
  font-size:14px;
  font-weight:1000;
}

.shopCard p{
  margin:8px 0 12px;
  font-size:12px;
  color:rgba(255,255,255,.72);
}

.price{
  font-weight:1000;
  font-size:12px;
}

.smallBtn{
  width:100%;
  padding:12px;
  border-radius:16px;
  font-weight:1000;
  font-size:14px;
}

.smallBtn.primary{
  background: linear-gradient(90deg, rgba(255,43,74,.92), rgba(176,108,255,.70));
  border:0;
  color:#fff;
}

.smallBtn.ghost{
  border:1px solid rgba(255,255,255,.14);
  background:rgba(255,255,255,.05);
  color:#fff;
}

""" + "</style></head><body>"
        "<canvas id='fx'></canvas>"
        "<div class='wrap'>"

        "<div class='top'>"
        "<div class='title'><h1>🛒 Loja</h1><div class='sub'>Venda personagens ou compre recursos</div></div>"
        "<div class='pills'><div class='pill'>🪙 <span id='coins'>-</span></div><div class='sep'></div>"
        "<div class='pill'>🎡 <span id='giros'>-</span></div></div>"
        "</div>"

        "<div class='tabs glass'>"
        "<button class='tab active' id='tab_sell'>📦 Vender</button>"
        "<button class='tab' id='tab_buy'>🎲 Comprar</button>"
        "</div>"

        "<div class='toast' id='toast'>Carregando...</div>"

        "<div id='sellView'>"
        "<div class='search'><input class='input glass' id='q' placeholder='Buscar personagem ou anime...' /></div>"
        "<div id='sellSections' class='grid'></div>"
        "</div>"

        "<div id='buyView' style='display:none;'>"

        "<div class='buyGrid'>"

        "<div class='shopCard glass'>"
        "<h3>🎲 Comprar Dado</h3>"
        "<p>Use coins para comprar dados extras.</p>"
        "<div class='price'>Preço: 2 coins</div>"
        "<button class='smallBtn primary' id='buyDice'>Comprar</button>"
        "</div>"

        "<div class='shopCard glass'>"
        "<h3>✏️ Trocar Nickname</h3>"
        "<p>Permite alterar seu nome novamente.</p>"
        "<div class='price'>Preço: 3 coins</div>"
        "<button class='smallBtn primary' id='buyNick'>Comprar</button>"
        "</div>"

        "</div>"
        "</div>"

        + _tg_js_init()
        + r"""

<script>

let coins=0
let giros=0
let allItems=[]

function setToast(t){
 document.getElementById("toast").textContent=t
}

async function loadState(){

const r = await apiGet("/api/shop/state")

coins = r.data.coins
giros = r.data.giros

document.getElementById("coins").textContent=coins
document.getElementById("giros").textContent=giros

}

async function loadSell(){

const r = await apiGet("/api/shop/sell/all")

allItems=r.data.items||[]

renderSell()

}

function renderSell(){

const root=document.getElementById("sellSections")
root.innerHTML=""

for(const c of allItems){

const img=c.image||""

const card=document.createElement("div")
card.className="card"

card.innerHTML=`

<div class="shine"></div>

<img src="${img}">

<div class="pillTag">x${c.quantity} • ID ${c.character_id}</div>

<div class="overlay">

<div class="name">${c.character_name}</div>

<div class="meta">${c.anime_title}</div>

<div class="actions">

<button class="smallBtn primary" onclick="sell(${c.character_id})">
Vender +1 coin
</button>

</div>

</div>

`

root.appendChild(card)

}

}

async function sell(id){

const r = await apiPost("/api/shop/sell/confirm",{character_id:id})

coins=r.data.coins

document.getElementById("coins").textContent=coins

await loadSell()

}

document.getElementById("buyDice").onclick=async()=>{

await apiPost("/api/shop/buy/giro")

await loadState()

}

document.getElementById("buyNick").onclick=async()=>{

await apiPost("/api/shop/buy/nickname")

await loadState()

}

document.getElementById("tab_sell").onclick=()=>{
document.getElementById("sellView").style.display=""
document.getElementById("buyView").style.display="none"
}

document.getElementById("tab_buy").onclick=()=>{
document.getElementById("sellView").style.display="none"
document.getElementById("buyView").style.display=""
}

(async()=>{
await loadState()
await loadSell()
})()

</script>

""" + _fx_js() + "</div></body></html>"
    )

    return HTMLResponse(content=html)


# =========================
# Alias /loja
# =========================
@app.get("/loja", response_class=HTMLResponse)
def loja_alias():
    return miniapp_shop()
