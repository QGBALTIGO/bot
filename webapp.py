import os
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from database import create_or_get_user, accept_terms, set_language

TERMS_VERSION = (os.getenv("TERMS_VERSION", "v1").strip() or "v1")

app = FastAPI()

# =========================
# Textos por idioma
# =========================
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
        "no": "❌ Você não aceitou. Sem aceite, o bot não libera acesso.",
        "error": "Erro. Tente novamente.",
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
        "no": "❌ You did not accept. Without acceptance, access is not granted.",
        "error": "Error. Please try again.",
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
        "no": "❌ No aceptaste. Sin aceptación, no se concede acceso.",
        "error": "Error. Inténtalo de nuevo.",
    },
}

# =========================
# Termos (texto longo) por idioma
# (Você pode editar depois com calma)
# =========================
TERMS_LONG = {
    "pt": """
<div class="section">
  <div class="sectionTitle">SUA PRIVACIDADE</div>
  <div class="sectionText">
    Coletamos apenas o seu ID numérico do Telegram e dados necessários para o funcionamento do bot
    (ex.: idioma, registro de aceite, e informações relacionadas ao uso dentro do bot).
    Não temos acesso às suas conversas privadas fora do bot.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">USO JUSTO E SEGURANÇA</div>
  <div class="sectionText">
    Não é permitido spam, automação, exploração de falhas, tentativa de duplicação de recompensas,
    abuso de botões/callbacks ou qualquer prática que prejudique a experiência de outros usuários.
    Podemos aplicar limites, bloqueios e reversões para manter o bot estável e justo.
  </div>
</div>

<div class="section">
  <div class="sectionTitle">SUA RESPONSABILIDADE</div>
  <div class="sectionText">
    Ao aceitar, você confirma que leu e concorda com estas regras.
    O uso do bot é por sua conta e risco, e as funcionalidades podem mudar para garantir equilíbrio e segurança.
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
  <div class="sectionTitle">FAIR USE & SECURITY</div>
  <div class="sectionText">
    Spam, automation, exploit attempts, reward duplication, abusive button/callback usage, or any behavior
    that harms other users is not allowed. We may apply limits, blocks, and reversions to keep the bot stable and fair.
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
  <div class="sectionTitle">USO JUSTO Y SEGURIDAD</div>
  <div class="sectionText">
    No se permite spam, automatización, explotación de fallos, duplicación de recompensas ni abuso de botones/callbacks.
    Podemos aplicar límites, bloqueos y reversiones para mantener el bot estable y justo.
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

def pick_lang(lang: str | None) -> str:
    lang = (lang or "").lower().strip()
    if lang.startswith("pt"):
        return "pt"
    if lang.startswith("es"):
        return "es"
    if lang.startswith("en"):
        return "en"
    return "en"

# =========================
# Página do WebApp
# =========================
@app.get("/terms", response_class=HTMLResponse)
def terms_page(
    uid: int = Query(..., description="Telegram user id"),
    lang: str = Query("en", description="pt|en|es"),
):
    L = pick_lang(lang)
    t = TEXTS[L]
    body = TERMS_LONG[L]

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
<title>{t["title"]}</title>
<style>
  :root {{
    --bg: #0b0f1a;
    --card: rgba(255,255,255,0.06);
    --stroke: rgba(255,255,255,0.10);
    --stroke2: rgba(255,255,255,0.14);
    --text: #e7eaf3;
    --muted: rgba(231,234,243,0.75);
    --okbg: #4ade80;
    --oktxt: #052e16;
  }}

  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
  }}

  .wrap {{
    max-width: 760px;
    margin: 0 auto;
    padding: 18px;
  }}

  .card {{
    background: var(--card);
    border: 1px solid var(--stroke);
    border-radius: 18px;
    padding: 16px;
    box-shadow: 0 12px 30px rgba(0,0,0,0.25);
  }}

  .top {{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap: 12px;
    margin-bottom: 14px;
  }}

  .brand {{
    display:flex;
    align-items:center;
    gap: 10px;
  }}

  .badge {{
    width: 38px;
    height: 38px;
    border-radius: 12px;
    background: rgba(59,130,246,0.18);
    border: 1px solid rgba(59,130,246,0.30);
    display:flex;
    align-items:center;
    justify-content:center;
    font-weight: 900;
  }}

  .brandText {{
    display:flex;
    flex-direction:column;
  }}

  .brandTitle {{
    font-weight: 900;
    letter-spacing: .6px;
    font-size: 15px;
    line-height: 1.1;
  }}

  .brandSub {{
    opacity: .75;
    font-size: 12px;
    margin-top: 2px;
    letter-spacing: .3px;
  }}

  /* ===== PILL DO IDIOMA (igual print) ===== */
  .langPill {{
    display:flex;
    align-items:center;
    gap: 10px;
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--stroke);
    padding: 10px 14px;
    border-radius: 14px;
    cursor: pointer;
    user-select:none;
  }}

  .langIcon {{
    font-size: 13px;
    opacity: .9;
  }}

  .langCode {{
    font-size: 13px;
    font-weight: 900;
    letter-spacing: .4px;
    opacity: .95;
  }}

  .langMenu {{
    display:none;
    justify-content:flex-end;
    gap: 10px;
    margin: 10px 0 14px 0;
  }}

  .langBtn {{
    width: 56px;
    text-align:center;
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--stroke);
    padding: 10px 0;
    border-radius: 14px;
    font-size: 13px;
    font-weight: 900;
    cursor: pointer;
  }}

  h1 {{
    font-size: 20px;
    margin: 6px 0 2px 0;
  }}

  .sub {{
    color: var(--muted);
    font-size: 13px;
    margin-bottom: 14px;
  }}

  .section {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 14px;
    margin: 12px 0;
  }}

  .sectionTitle {{
    font-weight: 900;
    letter-spacing: .5px;
    font-size: 14px;
    margin-bottom: 8px;
  }}

  .sectionText {{
    color: rgba(231,234,243,0.85);
    line-height: 1.45;
    font-size: 13.5px;
  }}

  .divider {{
    height: 1px;
    background: rgba(255,255,255,0.10);
    margin: 14px 0;
  }}

  label {{
    display:flex;
    gap: 12px;
    align-items:flex-start;
    font-size: 14px;
    margin: 12px 0;
    color: rgba(231,234,243,0.92);
  }}

  input[type="checkbox"] {{
    margin-top: 3px;
    transform: scale(1.15);
  }}

  .actions {{
    display:flex;
    flex-direction:column;
    gap: 10px;
    margin-top: 14px;
  }}

  button {{
    border: 0;
    border-radius: 16px;
    padding: 14px 12px;
    font-weight: 900;
    cursor: pointer;
    letter-spacing: .6px;
  }}

  .accept {{
    background: var(--okbg);
    color: var(--oktxt);
    opacity: 0.45;
    cursor: not-allowed;
  }}

  .decline {{
    background: rgba(255,255,255,0.06);
    color: var(--text);
    border: 1px solid var(--stroke2);
  }}

  .footer {{
    margin-top: 14px;
    text-align:center;
    font-size: 12px;
    color: rgba(231,234,243,0.50);
    letter-spacing: 2px;
  }}

  .msg {{
    margin-top: 10px;
    font-size: 14px;
    color: rgba(231,234,243,0.90);
    min-height: 18px;
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="top">
      <div class="brand">
        <div class="badge">🛡️</div>
        <div class="brandText">
          <div class="brandTitle">SOURCE BALTIGO</div>
          <div class="brandSub">LEGAL & PRIVACY</div>
        </div>
      </div>

      <div class="langPill" id="langPill" title="Change language">
        <span class="langIcon">文A</span>
        <span class="langCode">{L.upper()}</span>
      </div>
    </div>

    <div class="langMenu" id="langMenu">
      <div class="langBtn" data-lang="pt">PT</div>
      <div class="langBtn" data-lang="en">EN</div>
      <div class="langBtn" data-lang="es">ES</div>
    </div>

    <h1>{t["title"]}</h1>
    <div class="sub">{t["subtitle"]} • {t["intro"]}</div>

    {body}

    <div class="divider"></div>

    <label>
      <input id="c1" type="checkbox" />
      <span>{t["check1"]}</span>
    </label>

    <label>
      <input id="c2" type="checkbox" />
      <span>{t["check2"]}</span>
    </label>

    <div class="actions">
      <button class="accept" id="acceptBtn">{t["accept"]}</button>
      <button class="decline" id="declineBtn">{t["decline"]}</button>
    </div>

    <div class="msg" id="msg"></div>
    <div class="footer">REVISÃO • {TERMS_VERSION.upper()}</div>
  </div>
</div>

<script>
  const uid = {uid};
  let lang = "{L}";

  const langPill = document.getElementById("langPill");
  const langMenu = document.getElementById("langMenu");

  // abre/fecha menu de idioma (igual print)
  langPill.addEventListener("click", (e) => {{
    e.stopPropagation();
    langMenu.style.display = (langMenu.style.display === "flex") ? "none" : "flex";
    if (langMenu.style.display === "flex") {{
      langMenu.style.justifyContent = "flex-end";
    }}
  }});

  document.addEventListener("click", () => {{
    langMenu.style.display = "none";
  }});

  document.querySelectorAll(".langBtn").forEach(btn => {{
    btn.addEventListener("click", () => {{
      const newLang = btn.getAttribute("data-lang");
      const url = new URL(window.location.href);
      url.searchParams.set("lang", newLang);
      window.location.href = url.toString();
    }});
  }});

  const c1 = document.getElementById("c1");
  const c2 = document.getElementById("c2");
  const acceptBtn = document.getElementById("acceptBtn");
  const declineBtn = document.getElementById("declineBtn");
  const msg = document.getElementById("msg");

  function updateAcceptButton() {{
    const ok = c1.checked && c2.checked;
    acceptBtn.style.opacity = ok ? "1" : "0.45";
    acceptBtn.style.cursor = ok ? "pointer" : "not-allowed";
  }}
  c1.addEventListener("change", updateAcceptButton);
  c2.addEventListener("change", updateAcceptButton);
  updateAcceptButton();

  acceptBtn.addEventListener("click", async () => {{
    if (!(c1.checked && c2.checked)) return;
    try {{
      const res = await fetch("/api/terms/accept", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ uid, lang }})
      }});
      const data = await res.json();
      msg.textContent = (data && data.message) ? data.message : "{t["done"]}";
    }} catch (e) {{
      msg.textContent = "{t["error"]}";
    }}
  }});

  declineBtn.addEventListener("click", async () => {{
    try {{
      const res = await fetch("/api/terms/decline", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ uid, lang }})
      }});
      const data = await res.json();
      msg.textContent = (data && data.message) ? data.message : "{t["no"]}";
    }} catch (e) {{
      msg.textContent = "{t["error"]}";
    }}
  }});
</script>

</body>
</html>
"""
    return HTMLResponse(html)


# =========================
# APIs
# =========================
@app.post("/api/terms/accept")
def api_accept(payload: dict):
    uid = int(payload.get("uid") or 0)
    lang = pick_lang(payload.get("lang"))

    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)

    create_or_get_user(uid)
    set_language(uid, lang)
    accept_terms(uid, TERMS_VERSION)

    return {"ok": True, "message": TEXTS[lang]["done"]}


@app.post("/api/terms/decline")
def api_decline(payload: dict):
    uid = int(payload.get("uid") or 0)
    lang = pick_lang(payload.get("lang"))

    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)

    create_or_get_user(uid)
    set_language(uid, lang)

    return {"ok": True, "message": TEXTS[lang]["no"]}
