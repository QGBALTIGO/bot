# webapp.py — (SUBSTITUIR TUDO)
# MiniApp Termos (PT/EN/ES) verificação de canal (sem requests)
# + MiniApp Catálogo do canal (cards A–Z) baseado em catalogo_enriquecido.json
#
# Requisitos: fastapi, uvicorn, httpx
#
# ENV:
#   TERMS_VERSION="v1"
#   BOT_TOKEN="xxxxx"                      (obrigatório verificar canal)
#   REQUIRED_CHANNEL="@SourcerBaltigo"     (ou -100xxxxxxxxxx)
#   REQUIRED_CHANNEL_URL="https://t.me/SourcerBaltigo"
#   TOP_BANNER_URL="https://..."           (banner do termos)
#   BACKGROUND_URL="https://..."           (fundo do termos)
#
#   CATALOG_PATH="catalogo_enriquecido.json"
#   CATALOG_BANNER_URL="https://..."       (banner do catálogo)
#   BACKGROUND_PATTERN_URL="https://..."   (pattern do catálogo)
#   CATALOG_TITLE="CATÁLOGO"
#   CATALOG_SUBTITLE="TOTAL"
#
# Rotas
#   GET  /                  -> health
#   GET  /terms             -> MiniApp (Termos)
#   POST /api/channel/check -> verifica inscrição no canal
#   POST /api/terms/accept  -> aceita termos
#   POST /api/terms/decline -> recusa termos
#
#   GET  /catalogo          -> MiniApp (Catálogo)
#   GET  /api/letters       -> contagem por letra
#   GET  /api/catalogo      -> lista filtrada (q, letter, limit, offset)

import os
import json
import re
import traceback
import asyncio
import time
import httpx
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse

from database import create_or_get_user, accept_terms, set_language


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

    bg = BACKGROUND_URL if BACKGROUND_URL else ""
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
CATALOG_PATH = os.getenv("CATALOG_PATH", "catalogo_enriquecido.json").strip()

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
    pattern = BACKGROUND_PATTERN_URL if BACKGROUND_PATTERN_URL else ""
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

    pattern = MANGA_BACKGROUND_PATTERN_URL if MANGA_BACKGROUND_PATTERN_URL else ""
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
    "https://photo.chelpbot.me/AgACAgEAAxkBZxImgmmnL7d9nYjTFd0KNTThxz9KJ6uCAAK7C2sbxrE5RXkd0eZ9Eoc4AQADAgADeQADOgQ/photo.jpg",
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
    "https://photo.chelpbot.me/AgACAgEAAxkBZxImgmmnL7d9nYjTFd0KNTThxz9KJ6uCAAK7C2sbxrE5RXkd0eZ9Eoc4AQADAgADeQADOgQ/photo.jpg",
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
# CONFIG — PEDIDOS / REPORTS
# =========================
CANAL_PEDIDOS = os.getenv("CANAL_PEDIDOS", "").strip()
PEDIDO_BANNER_URL = os.getenv(
    "PEDIDO_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzeISGmpyjb2CsPEQUv3zfVD-aj7780SAAKzC2sb6qtQRVbTTJ4IyPVIAQADAgADeQADOgQ/photo.jpg",
).strip()

from database import (
    create_media_request_tables,
    count_user_media_requests_last_24h,
    media_request_exists,
    save_media_request,
    save_webapp_report,
    normalize_media_title,
)

create_media_request_tables()

_PEDIDO_ANIME_INDEX = {"title_norm": set(), "anilist_ids": set()}
_PEDIDO_MANGA_INDEX = {"title_norm": set(), "anilist_ids": set()}


def _pedido_build_index(records: List[Dict[str, Any]], media_type: str):
    idx = {"title_norm": set(), "anilist_ids": set()}
    for rec in records:
        try:
            title = ""
            anilist_id = None
            if isinstance(rec, dict):
                title = str(rec.get("title_raw") or rec.get("titulo") or rec.get("title") or "").strip()
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
    _PEDIDO_ANIME_INDEX = _pedido_build_index(_unwrap_records(load_json(CATALOG_PATH)), "anime")
    _PEDIDO_MANGA_INDEX = _pedido_build_index(_unwrap_records(load_json(MANGA_CATALOG_PATH)), "manga")


try:
    _pedido_reload_indexes()
except Exception as e:
    print("[pedido] falha ao montar índices:", repr(e), flush=True)


def _pedido_catalog_contains(media_type: str, title: str, anilist_id=None) -> bool:
    idx = _PEDIDO_ANIME_INDEX if media_type == "anime" else _PEDIDO_MANGA_INDEX
    if anilist_id:
        try:
            if int(anilist_id) in idx["anilist_ids"]:
                return True
        except Exception:
            pass
    return normalize_media_title(title) in idx["title_norm"]


async def _pedido_anilist_search(query_text: str, media_type: str):
    media_type = "ANIME" if media_type == "anime" else "MANGA"
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

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://graphql.anilist.co",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json={"query": gql, "variables": {"search": query_text, "type": media_type}},
        )
        response.raise_for_status()
        data = response.json()

    return ((data or {}).get("data") or {}).get("Page", {}).get("media", []) or []


@app.get("/api/pedido/limit")
def api_pedido_limit(uid: int = Query(...)):
    used = count_user_media_requests_last_24h(uid)
    remaining = max(0, 3 - used)
    return JSONResponse({"ok": True, "used": used, "remaining": remaining, "limit": 3})


@app.get("/api/pedido/search")
async def api_pedido_search(q: str = Query(..., min_length=1, max_length=80), media_type: str = Query(...)):
    media_type = (media_type or "").strip().lower()
    if media_type not in ("anime", "manga"):
        return JSONResponse({"ok": False, "message": "media_type inválido"}, status_code=400)

    try:
        results = await _pedido_anilist_search(q.strip(), media_type)
        items = []
        for x in results:
            title = ((x.get("title") or {}).get("romaji") or (x.get("title") or {}).get("english") or (x.get("title") or {}).get("native") or "").strip()
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

        if CANAL_PEDIDOS and BOT_TOKEN:
            caption = (
                f"📥 <b>NOVO PEDIDO</b>\n\n"
                f"👤 <b>Usuário:</b> {full_name or 'Sem nome'}\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                f"🔖 <b>Username:</b> @{username if username else 'sem_username'}\n\n"
                f"🎴 <b>Tipo:</b> {media_type.upper()}\n"
                f"📝 <b>Título:</b> <i>{title}</i>\n"
                f"🆔 <b>AniList ID:</b> <code>{anilist_id or '-'}</code>"
            )
            async with httpx.AsyncClient(timeout=20.0) as client:
                if cover:
                    await client.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                        data={
                            "chat_id": CANAL_PEDIDOS,
                            "photo": cover,
                            "caption": caption,
                            "parse_mode": "HTML",
                        },
                    )
                else:
                    await client.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        data={
                            "chat_id": CANAL_PEDIDOS,
                            "text": caption,
                            "parse_mode": "HTML",
                        },
                    )

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

        if CANAL_PEDIDOS and BOT_TOKEN:
            text = (
                f"⚠️ <b>NOVO REPORT</b>\n\n"
                f"👤 <b>Usuário:</b> {full_name or 'Sem nome'}\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                f"🔖 <b>Username:</b> @{username if username else 'sem_username'}\n\n"
                f"🏷 <b>Tipo:</b> {report_type}\n"
                f"📝 <b>Mensagem:</b>\n{message}"
            )
            async with httpx.AsyncClient(timeout=20.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    data={
                        "chat_id": CANAL_PEDIDOS,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                )

        return JSONResponse({"ok": True, "message": "Report enviado com sucesso."})

    except Exception as e:
        print("[pedido] falha ao enviar report:", repr(e), flush=True)
        traceback.print_exc()
        return JSONResponse({"ok": False, "message": "Não foi possível enviar o report."}, status_code=500)


@app.get("/pedido", response_class=HTMLResponse)
def pedido_webapp():
    html = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://telegram.org/js/telegram-web-app.js"></script>

<style>
body{
background:#0b1320;
font-family:sans-serif;
color:white;
padding:20px;
}

.container{
max-width:600px;
margin:auto;
}

.tabs{
display:flex;
gap:10px;
margin-bottom:20px;
}

.tab{
flex:1;
padding:12px;
border-radius:12px;
background:#1a2742;
text-align:center;
cursor:pointer;
}

.tab.active{
background:#3a66ff;
}

input{
width:100%;
padding:14px;
border-radius:12px;
border:none;
background:#18233c;
color:white;
margin-bottom:10px;
}

button{
padding:12px 20px;
border:none;
border-radius:10px;
background:#3a66ff;
color:white;
cursor:pointer;
}

.result{
margin-top:20px;
}
</style>
</head>

<body>

<div class="container">

<h2>📥 Central de Pedidos</h2>

<div class="tabs">
<div class="tab active" onclick="setTab('anime')" id="t_anime">Anime</div>
<div class="tab" onclick="setTab('manga')" id="t_manga">Mangá</div>
<div class="tab" onclick="setTab('erro')" id="t_erro">Erro</div>
</div>

<div id="anime">
<input id="animeInput" placeholder="Buscar anime...">
<button onclick="buscarAnime()">Buscar</button>
<div id="animeResult" class="result"></div>
</div>

<div id="manga" style="display:none">
<input id="mangaInput" placeholder="Buscar mangá...">
<button onclick="buscarManga()">Buscar</button>
<div id="mangaResult" class="result"></div>
</div>

<div id="erro" style="display:none">
<input id="erroInput" placeholder="Descreva o erro">
<button onclick="reportarErro()">Enviar</button>
</div>

</div>

<script>

const tg = window.Telegram.WebApp;
tg.ready();

let user = tg.initDataUnsafe?.user || null;

function setTab(tab){

document.getElementById("anime").style.display="none"
document.getElementById("manga").style.display="none"
document.getElementById("erro").style.display="none"

document.getElementById(tab).style.display="block"

document.querySelectorAll(".tab").forEach(e=>e.classList.remove("active"))
document.getElementById("t_"+tab).classList.add("active")
}

async function buscarAnime(){

let q = document.getElementById("animeInput").value

let r = await fetch("/api/pedido/anime?q="+encodeURIComponent(q))
let data = await r.json()

let html=""

data.forEach(a=>{
html+=`
<div style="margin-top:10px">
<b>${a.title}</b>
<button onclick="pedir('anime','${a.title}')">Pedir</button>
</div>`
})

document.getElementById("animeResult").innerHTML=html
}

async function buscarManga(){

let q = document.getElementById("mangaInput").value

let r = await fetch("/api/pedido/manga?q="+encodeURIComponent(q))
let data = await r.json()

let html=""

data.forEach(a=>{
html+=`
<div style="margin-top:10px">
<b>${a.title}</b>
<button onclick="pedir('manga','${a.title}')">Pedir</button>
</div>`
})

document.getElementById("mangaResult").innerHTML=html
}

async function pedir(tipo,titulo){

let r = await fetch("/api/pedido/enviar",{
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({
user_id:user?.id,
username:user?.username,
tipo:tipo,
titulo:titulo
})
})

let res = await r.json()
alert(res.msg)
}

async function reportarErro(){

let texto = document.getElementById("erroInput").value

await fetch("/api/pedido/report",{
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({
user_id:user?.id,
texto:texto
})
})

alert("Erro enviado")
}

</script>

</body>
</html>
"""
    return html

@app.get("/api/pedido/anime")
async def pedido_anime(q: str):

    url = "https://graphql.anilist.co"

    query = """
    query ($search: String) {
      Page(perPage:5) {
        media(search:$search,type:ANIME){
          title{romaji}
        }
      }
    }
    """

    async with aiohttp.ClientSession() as s:
        async with s.post(url,json={"query":query,"variables":{"search":q}}) as r:
            j = await r.json()

    return [{"title":m["title"]["romaji"]} for m in j["data"]["Page"]["media"]]

    @app.get("/api/pedido/manga")
async def pedido_manga(q: str):

    url = "https://graphql.anilist.co"

    query = """
    query ($search: String) {
      Page(perPage:5) {
        media(search:$search,type:MANGA){
          title{romaji}
        }
      }
    }
    """

    async with aiohttp.ClientSession() as s:
        async with s.post(url,json={"query":query,"variables":{"search":q}}) as r:
            j = await r.json()

    return [{"title":m["title"]["romaji"]} for m in j["data"]["Page"]["media"]]

    @app.post("/api/pedido/enviar")
async def pedido_enviar(data: dict):

    user_id = data.get("user_id")
    titulo = data.get("titulo")
    tipo = data.get("tipo")

    msg = f"""
📥 NOVO PEDIDO

👤 ID: {user_id}
🎬 Tipo: {tipo}
📌 Título: {titulo}
"""

    await bot.send_message(
        chat_id=CANAL_PEDIDOS,
        text=msg
    )

    return {"msg":"Pedido enviado!"}

    @app.post("/api/pedido/report")
async def pedido_report(data: dict):

    msg = f"""
⚠️ REPORT DE ERRO

👤 ID: {data.get("user_id")}

📝 {data.get("texto")}
"""

    await bot.send_message(
        chat_id=CANAL_PEDIDOS,
        text=msg
    )

    return {"ok":True}
