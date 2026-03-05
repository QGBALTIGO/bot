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
