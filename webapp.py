# webapp.py — (SUBSTITUIR TUDO)
# MiniApp Termos (PT/EN/ES) + verificação de canal (sem requests)
# + MiniApp Catálogo do canal (cards A–Z) baseado em catalogo_enriquecido.json
#
# Requisitos: fastapi, uvicorn, httpx
#
# ENV:
#   TERMS_VERSION="v1"
#   BOT_TOKEN="xxxxx"                      (obrigatório p/ verificar canal)
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
# Rotas:
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

# =========================
# CONFIG — CARDS (PERSONAGENS)
# =========================

CHARACTERS_FILE = "data/personagens_anilist.txt"


def load_characters():
    animes = {}

    try:
        with open(CHARACTERS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split("|")
                if len(parts) < 4:
                    continue

                char_id = parts[0]
                name = parts[1]
                anime = parts[2]
                anime_id = parts[3]

                if anime_id not in animes:
                    animes[anime_id] = {
                        "anime": anime,
                        "anime_id": anime_id,
                        "characters": []
                    }

                animes[anime_id]["characters"].append({
                    "id": int(char_id),
                    "name": name,
                    "anime": anime
                })

    except Exception as e:
        print("Erro ao carregar personagens:", e)

    return list(animes.values())


# =========================
# API — LISTAR ANIMES
# =========================

@app.get("/api/cards/animes")
def api_cards_animes():
    return JSONResponse(load_characters())


# =========================
# API — PERSONAGENS DO ANIME
# =========================

@app.get("/api/cards/characters")
def api_cards_characters(anime_id: str):

    data = load_characters()

    for anime in data:
        if anime["anime_id"] == anime_id:
            return JSONResponse(anime["characters"])

    return JSONResponse([])


# =========================
# MINI APP — CARDS
# =========================

@app.get("/cards", response_class=HTMLResponse)
def cards_page():

    html = """
<!doctype html>
<html>
<head>

<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>

<style>

body{
background: radial-gradient(900px 500px at 50% -10%, rgba(90,168,255,0.18), transparent 55%),
linear-gradient(180deg,#070b12,#0a1220);
font-family: -apple-system,system-ui,Segoe UI,Roboto,Arial;
margin:0;
padding:20px;
color:white;
}

.title{
font-weight:900;
letter-spacing:.08em;
font-size:22px;
margin-bottom:16px;
}

.grid{
display:grid;
grid-template-columns:repeat(2,1fr);
gap:12px;
}

.card{
background:rgba(255,255,255,0.04);
border:1px solid rgba(255,255,255,0.1);
border-radius:18px;
padding:14px;
cursor:pointer;
transition:.15s;
font-weight:800;
letter-spacing:.04em;
}

.card:hover{
transform:translateY(-2px);
border-color:rgba(255,255,255,0.2);
}

</style>

</head>

<body>

<div class="title">🃏 COLEÇÃO DE PERSONAGENS</div>

<div id="grid" class="grid"></div>

<script>

async function load(){

let r = await fetch("/api/cards/animes")
let data = await r.json()

let html=""

data.forEach(a=>{
html+=`
<div class="card" onclick="openAnime('${a.anime_id}')">
${a.anime}
</div>
`
})

document.getElementById("grid").innerHTML=html

}

function openAnime(id){
window.location="/cards/anime?anime="+id
}

load()

</script>

</body>
</html>
"""

    return HTMLResponse(html)


# =========================
# MINI APP — PERSONAGENS
# =========================

@app.get("/cards/anime", response_class=HTMLResponse)
def cards_anime_page(anime: str):

    html = """
<!doctype html>
<html>
<head>

<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>

<style>

body{
background:#070b12;
font-family:system-ui;
color:white;
margin:0;
padding:20px;
}

.title{
font-size:20px;
font-weight:900;
margin-bottom:16px;
}

.grid{
display:grid;
grid-template-columns:repeat(2,1fr);
gap:14px;
}

.card{
background:rgba(255,255,255,0.04);
border:1px solid rgba(255,255,255,0.1);
border-radius:20px;
overflow:hidden;
}

.card img{
width:100%;
height:220px;
object-fit:cover;
}

.name{
padding:10px;
font-weight:800;
font-size:14px;
}

</style>

</head>

<body>

<div class="title">PERSONAGENS</div>

<div id="grid" class="grid"></div>

<script>

const anime="__ANIME__"

async function load(){

let r = await fetch("/api/cards/characters?anime_id="+anime)
let data = await r.json()

let html=""

data.forEach(c=>{

let img="https://img.anili.st/media/"+c.id

html+=`
<div class="card">
<img src="${img}">
<div class="name">${c.name}</div>
</div>
`

})

document.getElementById("grid").innerHTML=html

}

load()

</script>

</body>
</html>
"""

    html = html.replace("__ANIME__", anime)

    return HTMLResponse(html)
