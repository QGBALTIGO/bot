import os
import traceback
from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse

from database import create_or_get_user, accept_terms, set_language

app = FastAPI()

# ===== CONFIG =====
TERMS_VERSION = (os.getenv("TERMS_VERSION", "v1").strip() or "v1")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@SourcerBaltigo").strip()
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/SourcerBaltigo").strip()

TOP_BANNER_URL = os.getenv(
    "TOP_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzS3wWmpl9pZVvh8mUyitl-u56VSkUmPAALrC2sb1ZFIRYO5j8ewhrZJAQADAgADeQADOgQ/photo.jpg"
).strip()

BACKGROUND_URL = os.getenv("BACKGROUND_URL", "").strip()  # precisa ser URL pública


def pick_lang(lang: str | None) -> str:
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

HTML_TEMPLATE = """<!doctype html>
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
    height:140px;
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
    return HTMLResponse("OK - WebApp online. Use /terms?uid=123&lang=pt")

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

    html = (HTML_TEMPLATE
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
        print("❌ ERROR /api/terms/accept:", repr(e))
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
        print("❌ ERROR /api/terms/decline:", repr(e))
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

    try:
        import requests
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember",
            params={"chat_id": REQUIRED_CHANNEL, "user_id": uid},
            timeout=8,
        )
        data = r.json()
        if not data.get("ok"):
            return {"ok": False}

        result = data.get("result") or {}
        status = (result.get("status") or "").lower()
        is_member = bool(result.get("is_member", False))

        ok = (status in ("creator", "administrator", "member")) or (status == "restricted" and is_member)
        return {"ok": ok}

    except Exception:
        return {"ok": False}

        import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

# ========= CONFIG VISUAL =========
CATALOG_BANNER_URL = os.getenv(
    "CATALOG_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBZzS3wWmpl9pZVvh8mUyitl-u56VSkUmPAALrC2sb1ZFIRYO5j8ewhrZJAQADAgADeQADOgQ/photo.jpg",
).strip()

BACKGROUND_PATTERN_URL = os.getenv(
    "BACKGROUND_PATTERN_URL",
    # sua imagem de fundo "fundão" (pattern)
    "https://i.imgur.com/0Z8FQ0y.png",
).strip()

# ========= DADOS =========
DATA_DIR = Path(__file__).resolve().parent / "data"
CATALOG_PATH = DATA_DIR / "catalogo_animes.json"

# cache em memória (rápido)
_CATALOG: List[Dict[str, Any]] = []
_LETTER_COUNTS: Dict[str, int] = {}
_TOTAL: int = 0


def _normalize_title(t: str) -> str:
    t = (t or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _first_letter(title: str) -> str:
    if not title:
        return "#"
    ch = title.strip()[0].upper()
    if "A" <= ch <= "Z":
        return ch
    if ch.isdigit():
        return "#"
    return "#"


def _load_catalog() -> None:
    global _CATALOG, _LETTER_COUNTS, _TOTAL

    if not CATALOG_PATH.exists():
        _CATALOG = []
        _LETTER_COUNTS = {}
        _TOTAL = 0
        return

    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    # Esperado:
    # [{"titulo": "...", "mensagem_id": 123, "link_post": "https://t.me/..."}, ...]
    items: List[Dict[str, Any]] = []
    for it in raw:
        title = _normalize_title(it.get("titulo") or it.get("title") or "")
        link = (it.get("link_post") or it.get("link") or "").strip()
        mid = it.get("mensagem_id") or it.get("message_id")

        if not title or not link:
            continue

        letter = _first_letter(title)

        items.append(
            {
                "titulo": title,
                "letter": letter,
                "link_post": link,
                "mensagem_id": mid,
                # futuro: "cover_url", "year", "genres", "score", etc.
                "cover_url": it.get("cover_url") or "",
                "year": it.get("year"),
                "score": it.get("score"),
                "format": it.get("format"),
            }
        )

    # ordenação base A-Z
    items.sort(key=lambda x: x["titulo"].lower())

    counts: Dict[str, int] = {}
    for x in items:
        counts[x["letter"]] = counts.get(x["letter"], 0) + 1

    _CATALOG = items
    _LETTER_COUNTS = counts
    _TOTAL = len(items)


# carrega ao subir
_load_catalog()


def _filter_catalog(q: str, letter: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    q = (q or "").strip().lower()
    letter = (letter or "").strip().upper()

    data = _CATALOG

    if letter and letter != "ALL":
        if letter == "#":
            data = [x for x in data if x["letter"] == "#"]
        else:
            data = [x for x in data if x["letter"] == letter]

    if q:
        data = [x for x in data if q in x["titulo"].lower()]

    total = len(data)

    # paginação
    if offset < 0:
        offset = 0
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    return data[offset : offset + limit], total


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse("OK - WebApp online. Use /catalogo")


@app.get("/api/letters")
def api_letters():
    # sempre incluir A-Z e #
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
    # HTML + CSS + JS inline (sem arquivos externos)
    html = f"""
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Catálogo — Source Baltigo</title>

  <style>
    :root {{
      --bg0: #070b12;
      --bg1: #0a1220;
      --card: rgba(255,255,255,0.04);
      --stroke: rgba(255,255,255,0.10);
      --stroke2: rgba(255,255,255,0.14);
      --txt: rgba(255,255,255,0.92);
      --muted: rgba(255,255,255,0.58);
      --brand: #5aa8ff;
      --brand2: rgba(90,168,255,0.20);
      --shadow: 0 14px 30px rgba(0,0,0,0.55);
      --r: 22px;
    }}

    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{
      margin: 0;
      font-family: -apple-system, system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      color: var(--txt);
      background: radial-gradient(1200px 600px at 50% -10%, rgba(90,168,255,0.18), transparent 55%),
                  linear-gradient(180deg, var(--bg0), var(--bg1));
      overflow-x: hidden;
    }}

    /* fundo "pattern" */
    .bg-pattern {{
      position: fixed;
      inset: 0;
      background-image: url("{BACKGROUND_PATTERN_URL}");
      background-size: 520px;
      background-repeat: repeat;
      opacity: 0.10;
      filter: grayscale(1) contrast(1.1);
      pointer-events: none;
      z-index: 0;
    }}

    .wrap {{
      position: relative;
      z-index: 1;
      max-width: 980px;
      margin: 0 auto;
      padding: 18px 14px 40px;
    }}

    .top-banner {{
      width: 100%;
      border-radius: 24px;
      overflow: hidden;
      border: 1px solid var(--stroke);
      box-shadow: var(--shadow);
      position: relative;
      background: #000;
    }}
    .top-banner img {{
      width: 100%;
      height: 160px;
      object-fit: cover;
      display: block;
    }}
    .top-banner::after {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, rgba(0,0,0,0.10), rgba(0,0,0,0.65));
      pointer-events: none;
    }}

    .head {{
      padding: 16px 10px 8px;
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
    }}

    .title {{
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 22px;
      line-height: 1.15;
    }}
    .subtitle {{
      margin-top: 6px;
      color: var(--muted);
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 12px;
    }}

    .search {{
      flex: 1;
      max-width: 380px;
      display: flex;
      align-items: center;
      gap: 10px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--stroke);
      border-radius: 18px;
      padding: 12px 14px;
      box-shadow: 0 10px 18px rgba(0,0,0,0.35);
    }}
    .search input {{
      width: 100%;
      border: 0;
      outline: none;
      background: transparent;
      color: var(--txt);
      font-size: 14px;
    }}
    .search input::placeholder {{ color: rgba(255,255,255,0.35); font-weight: 600; letter-spacing: 0.06em; }}

    .letters {{
      margin-top: 14px;
      background: rgba(255,255,255,0.035);
      border: 1px solid var(--stroke);
      border-radius: 26px;
      padding: 14px;
      box-shadow: 0 16px 26px rgba(0,0,0,0.36);
    }}

    .letters-grid {{
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 10px;
    }}

    @media (min-width: 720px) {{
      .letters-grid {{ grid-template-columns: repeat(10, 1fr); }}
      .top-banner img {{ height: 190px; }}
    }}

    .letter {{
      user-select: none;
      cursor: pointer;
      border-radius: 16px;
      padding: 12px 10px;
      text-align: center;
      border: 1px solid var(--stroke);
      background: rgba(255,255,255,0.03);
      transition: transform .08s ease, border-color .12s ease, background .12s ease;
    }}
    .letter:hover {{
      transform: translateY(-1px);
      border-color: var(--stroke2);
    }}
    .letter .k {{
      font-weight: 900;
      letter-spacing: 0.10em;
      font-size: 13px;
    }}
    .letter .n {{
      margin-top: 6px;
      font-size: 12px;
      color: rgba(255,255,255,0.55);
      font-weight: 800;
      letter-spacing: 0.08em;
    }}
    .letter.active {{
      background: rgba(90,168,255,0.18);
      border-color: rgba(90,168,255,0.42);
    }}

    .cards {{
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }}
    @media (min-width: 720px) {{
      .cards {{ grid-template-columns: repeat(3, 1fr); }}
    }}

    .card {{
      cursor: pointer;
      border-radius: 26px;
      overflow: hidden;
      border: 1px solid var(--stroke);
      background: rgba(255,255,255,0.03);
      box-shadow: 0 18px 30px rgba(0,0,0,0.44);
      transition: transform .10s ease, border-color .12s ease;
      position: relative;
    }}
    .card:hover {{ transform: translateY(-2px); border-color: var(--stroke2); }}

    .cover {{
      width: 100%;
      height: 210px;
      background: linear-gradient(135deg, rgba(90,168,255,0.18), rgba(255,255,255,0.03));
      position: relative;
    }}
    .cover img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}

    .badge {{
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
    }}

    .meta {{
      padding: 12px 14px 14px;
    }}
    .meta .name {{
      font-weight: 900;
      letter-spacing: 0.04em;
      font-size: 14px;
      text-transform: uppercase;
      line-height: 1.2;
      margin: 0;
    }}
    .meta .sub {{
      margin-top: 8px;
      color: rgba(255,255,255,0.50);
      font-weight: 800;
      letter-spacing: 0.12em;
      font-size: 11px;
      text-transform: uppercase;
    }}

    .footer {{
      margin-top: 14px;
      color: rgba(255,255,255,0.40);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-align: center;
    }}

    .loadmore {{
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
    }}
    .loadmore:disabled {{
      opacity: 0.5;
      cursor: not-allowed;
    }}
  </style>
</head>

<body>
  <div class="bg-pattern"></div>

  <div class="wrap">
    <div class="top-banner">
      <img src="{CATALOG_BANNER_URL}" alt="Banner"/>
    </div>

    <div class="head">
      <div>
        <div class="title">CATÁLOGO GERAL</div>
        <div class="subtitle"><span id="totalTxt">TOTAL NA SEÇÃO: ...</span></div>
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

    let state = {{
      letter: "ALL",
      q: "",
      limit: 60,
      offset: 0,
      total: 0,
      loading: false,
    }};

    function esc(s) {{
      return (s || "").replace(/[&<>"']/g, (m) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}}[m]));
    }}

    function openLink(link) {{
      // Em WebApp do Telegram, o ideal é abrir via API do Telegram se existir
      try {{
        if (window.Telegram && Telegram.WebApp && Telegram.WebApp.openTelegramLink) {{
          Telegram.WebApp.openTelegramLink(link);
          return;
        }}
      }} catch (e) {{}}
      window.open(link, "_blank");
    }}

    function makeLetterButton(key, count) {{
      const el = document.createElement("div");
      el.className = "letter" + (state.letter === key ? " active" : "");
      el.innerHTML = `
        <div class="k">${{esc(key === "ALL" ? "TODOS" : key)}}</div>
        <div class="n">${{key === "ALL" ? (count > 999 ? "999+" : count) : count}}</div>
      `;
      el.onclick = () => {{
        state.letter = key;
        state.offset = 0;
        document.getElementById("cards").innerHTML = "";
        renderLetters(); // re-render active
        loadCatalog(true);
      }};
      return el;
    }}

    async function renderLetters() {{
      const grid = document.getElementById("lettersGrid");
      grid.innerHTML = "";

      const res = await fetch(apiLetters);
      const data = await res.json();

      document.getElementById("totalTxt").textContent = "TOTAL NA SEÇÃO: " + data.total;

      // Ordem igual print: TODOS, #, A..Z
      grid.appendChild(makeLetterButton("ALL", data.all_count || data.total || 0));
      grid.appendChild(makeLetterButton("#", (data.counts && data.counts["#"]) ? data.counts["#"] : 0));

      for (let c = 65; c <= 90; c++) {{
        const k = String.fromCharCode(c);
        const n = (data.counts && data.counts[k]) ? data.counts[k] : 0;
        grid.appendChild(makeLetterButton(k, n));
      }}
    }}

    function makeCard(item) {{
      const card = document.createElement("div");
      card.className = "card";

      const hasCover = item.cover_url && item.cover_url.length > 5;
      const coverHtml = hasCover
        ? `<img src="${{esc(item.cover_url)}}" alt="${{esc(item.titulo)}}"/>`
        : ``;

      card.innerHTML = `
        <div class="cover">
          ${coverHtml}
          <div class="badge">TV</div>
        </div>
        <div class="meta">
          <p class="name">${{esc(item.titulo)}}</p>
          <div class="sub">ANIME</div>
        </div>
      `;

      card.onclick = () => openLink(item.link_post);

      return card;
    }}

    async function loadCatalog(reset=false) {{
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

      const res = await fetch(apiCatalogo + "?" + params.toString());
      const data = await res.json();

      state.total = data.total || 0;

      const cards = document.getElementById("cards");
      for (const it of (data.items || [])) {{
        cards.appendChild(makeCard(it));
      }}

      state.offset += (data.items || []).length;

      // se acabou, desabilita
      if (state.offset >= state.total) {{
        btn.disabled = true;
        btn.textContent = "FIM DA LISTA";
      }} else {{
        btn.disabled = false;
        btn.textContent = "CARREGAR MAIS";
      }}

      state.loading = false;
    }}

    function debounce(fn, ms) {{
      let t = null;
      return (...args) => {{
        if (t) clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
      }};
    }}

    const onSearch = debounce(() => {{
      state.q = (document.getElementById("q").value || "").trim();
      state.offset = 0;
      document.getElementById("cards").innerHTML = "";
      loadCatalog(true);
    }}, 250);

    document.getElementById("q").addEventListener("input", onSearch);

    document.getElementById("btnMore").addEventListener("click", () => {{
      loadCatalog(false);
    }});

    (async () => {{
      await renderLetters();
      await loadCatalog(true);
    }})();
  </script>
</body>
</html>
    """.strip()

    return HTMLResponse(html)
