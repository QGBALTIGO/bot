import os
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from database import create_or_get_user, accept_terms, set_language

TERMS_VERSION = os.getenv("TERMS_VERSION", "v1").strip() or "v1"

app = FastAPI()

TEXTS = {
    "pt": {
        "title": "Termos de Uso e Privacidade",
        "subtitle": f"Versão {TERMS_VERSION}",
        "intro": "Antes de usar o bot, você precisa ler e aceitar os termos abaixo.",
        "check1": "Li e aceito os Termos de Uso",
        "check2": "Li e aceito a Política de Privacidade",
        "accept": "Aceitar e continuar",
        "decline": "Não aceito",
        "done": "✅ Aceito com sucesso. Volte ao Telegram.",
        "no": "❌ Você não aceitou. Sem aceite, o bot não libera acesso.",
        "lang": "Idioma",
    },
    "en": {
        "title": "Terms of Use & Privacy",
        "subtitle": f"Version {TERMS_VERSION}",
        "intro": "Before using the bot, you must read and accept the terms below.",
        "check1": "I read and accept the Terms of Use",
        "check2": "I read and accept the Privacy Policy",
        "accept": "Accept and continue",
        "decline": "I do not accept",
        "done": "✅ Accepted successfully. Go back to Telegram.",
        "no": "❌ You did not accept. Without acceptance, access is not granted.",
        "lang": "Language",
    },
    "es": {
        "title": "Términos de Uso y Privacidad",
        "subtitle": f"Versión {TERMS_VERSION}",
        "intro": "Antes de usar el bot, debes leer y aceptar los términos a continuación.",
        "check1": "He leído y acepto los Términos de Uso",
        "check2": "He leído y acepto la Política de Privacidad",
        "accept": "Aceptar y continuar",
        "decline": "No acepto",
        "done": "✅ Aceptado con éxito. Vuelve a Telegram.",
        "no": "❌ No aceptaste. Sin aceptación, no se concede acceso.",
        "lang": "Idioma",
    },
}

TERMS_LONG = {
    "pt": """
<h3>1) O que este bot é</h3>
<p>Este bot oferece recursos interativos no Telegram. Podemos atualizar funcionalidades, regras e interface para manter estabilidade e segurança.</p>

<h3>2) Conta e acesso</h3>
<p>O uso é vinculado ao seu ID do Telegram. Você é responsável pelas ações feitas na sua conta.</p>

<h3>3) Regras de uso e proteção</h3>
<p>Não é permitido spam, automação, exploração de falhas, tentativa de duplicação de recompensas ou abuso de botões/callbacks. Podemos aplicar limites, bloqueios e reversões.</p>

<h3>4) Privacidade</h3>
<p>Armazenamos apenas dados necessários para o funcionamento (ex.: ID do Telegram, idioma, aceite destes termos e dados de uso dentro do bot). Não temos acesso às suas conversas privadas fora do bot.</p>

<h3>5) Alterações</h3>
<p>Podemos atualizar estes termos. Caso necessário, solicitaremos novo aceite.</p>
""",
    "en": """
<h3>1) What this bot is</h3>
<p>This bot provides interactive features inside Telegram. We may update features, rules, and UI to keep the service stable and safe.</p>

<h3>2) Account and access</h3>
<p>Usage is tied to your Telegram ID. You are responsible for actions performed on your account.</p>

<h3>3) Fair use & protections</h3>
<p>Spam, automation, exploit attempts, reward duplication, and abusive button/callback usage are not allowed. We may apply limits, blocks, and reversions.</p>

<h3>4) Privacy</h3>
<p>We store only what is required to operate (e.g., Telegram ID, language, acceptance record, and bot usage data). We do not access your private chats outside the bot.</p>

<h3>5) Changes</h3>
<p>We may update these terms. If needed, we will require acceptance again.</p>
""",
    "es": """
<h3>1) Qué es este bot</h3>
<p>Este bot ofrece funciones interactivas dentro de Telegram. Podemos actualizar funciones, reglas e interfaz para mantener estabilidad y seguridad.</p>

<h3>2) Cuenta y acceso</h3>
<p>El uso está vinculado a tu ID de Telegram. Eres responsable de las acciones realizadas en tu cuenta.</p>

<h3>3) Uso justo y protecciones</h3>
<p>No se permite spam, automatización, explotación de fallos, duplicación de recompensas ni abuso de botones/callbacks. Podemos aplicar límites, bloqueos y reversiones.</p>

<h3>4) Privacidad</h3>
<p>Guardamos solo lo necesario para operar (p. ej., ID de Telegram, idioma, registro de aceptación y datos de uso dentro del bot). No accedemos a tus chats privados fuera del bot.</p>

<h3>5) Cambios</h3>
<p>Podemos actualizar estos términos. Si es necesario, pediremos aceptar nuevamente.</p>
""",
}

def _pick_lang(lang: str | None) -> str:
    lang = (lang or "").lower()
    if lang.startswith("pt"):
        return "pt"
    if lang.startswith("es"):
        return "es"
    if lang.startswith("en"):
        return "en"
    return "en"

@app.get("/terms", response_class=HTMLResponse)
def terms_page(
    uid: int = Query(..., description="Telegram user id"),
    lang: str = Query("en", description="pt|en|es")
):
    L = _pick_lang(lang)
    t = TEXTS[L]
    body = TERMS_LONG[L]

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
<title>{t["title"]}</title>
<style>
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    background: #0b0f1a;
    color: #e7eaf3;
  }}
  .wrap {{
    max-width: 720px;
    margin: 0 auto;
    padding: 18px;
  }}
  .card {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 18px;
    padding: 16px;
    box-shadow: 0 12px 30px rgba(0,0,0,0.25);
  }}
  .top {{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap: 12px;
    margin-bottom: 12px;
  }}
  .brand {{
    font-weight: 800;
    letter-spacing: 0.3px;
  }}
  .pill {{
    display:flex;
    gap: 8px;
    align-items:center;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    padding: 8px 10px;
    border-radius: 999px;
    font-size: 13px;
    cursor: pointer;
    user-select:none;
  }}
  .langmenu {{
    display:none;
    margin-top: 10px;
    gap: 8px;
  }}
  .langbtn {{
    flex:1;
    text-align:center;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    padding: 10px 8px;
    border-radius: 12px;
    font-size: 13px;
    cursor: pointer;
  }}
  h1 {{
    font-size: 20px;
    margin: 4px 0 2px 0;
  }}
  .sub {{
    opacity: 0.85;
    font-size: 13px;
    margin-bottom: 12px;
  }}
  .terms {{
    line-height: 1.45;
    font-size: 14px;
    opacity: 0.96;
  }}
  .divider {{
    height: 1px;
    background: rgba(255,255,255,0.10);
    margin: 14px 0;
  }}
  label {{
    display:flex;
    gap:10px;
    align-items:flex-start;
    font-size: 14px;
    margin: 10px 0;
  }}
  input[type="checkbox"] {{
    margin-top: 3px;
    transform: scale(1.15);
  }}
  .actions {{
    display:flex;
    gap: 10px;
    margin-top: 12px;
  }}
  button {{
    flex: 1;
    border: 0;
    border-radius: 14px;
    padding: 12px 12px;
    font-weight: 800;
    cursor: pointer;
  }}
  .accept {{
    background: #4ade80;
    color: #052e16;
    opacity: 0.45;
    cursor:not-allowed;
  }}
  .decline {{
    background: rgba(255,255,255,0.10);
    color: #e7eaf3;
    border: 1px solid rgba(255,255,255,0.14);
  }}
  .msg {{
    margin-top: 10px;
    font-size: 14px;
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="top">
      <div class="brand">Source Baltigo 🎴✨</div>
      <div class="pill" id="langpill">🌐 {t["lang"]}: {L.upper()}</div>
    </div>

    <div class="langmenu" id="langmenu">
      <div class="langbtn" data-lang="pt">🇧🇷 PT</div>
      <div class="langbtn" data-lang="en">🇺🇸 EN</div>
      <div class="langbtn" data-lang="es">🇪🇸 ES</div>
    </div>

    <h1>{t["title"]}</h1>
    <div class="sub">{t["subtitle"]} • {t["intro"]}</div>

    <div class="terms">{body}</div>

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
      <button class="decline" id="declineBtn">{t["decline"]}</button>
      <button class="accept" id="acceptBtn">{t["accept"]}</button>
    </div>

    <div class="msg" id="msg"></div>
  </div>
</div>

<script>
  const uid = {uid};
  let lang = "{L}";

  const pill = document.getElementById("langpill");
  const menu = document.getElementById("langmenu");
  pill.addEventListener("click", () => {{
    menu.style.display = (menu.style.display === "flex") ? "none" : "flex";
    if (menu.style.display === "flex") menu.style.gap = "8px";
    if (menu.style.display === "flex") menu.style.display = "flex";
  }});

  document.querySelectorAll(".langbtn").forEach(btn => {{
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

  function updateButton() {{
    const ok = c1.checked && c2.checked;
    acceptBtn.style.opacity = ok ? "1" : "0.45";
    acceptBtn.style.cursor = ok ? "pointer" : "not-allowed";
  }}
  c1.addEventListener("change", updateButton);
  c2.addEventListener("change", updateButton);
  updateButton();

  acceptBtn.addEventListener("click", async () => {{
    if (!(c1.checked && c2.checked)) return;

    try {{
      const res = await fetch("/api/terms/accept", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ uid, lang }})
      }});
      const data = await res.json();
      msg.textContent = data.message || "{t["done"]}";
    }} catch (e) {{
      msg.textContent = "Erro ao aceitar. Tente novamente.";
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
      msg.textContent = data.message || "{t["no"]}";
    }} catch (e) {{
      msg.textContent = "Erro. Tente novamente.";
    }}
  }});
</script>

</body>
</html>
"""
    return HTMLResponse(html)

@app.post("/api/terms/accept")
def api_accept(payload: dict):
    uid = int(payload.get("uid") or 0)
    lang = _pick_lang(payload.get("lang"))

    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)

    create_or_get_user(uid)
    set_language(uid, lang)
    accept_terms(uid, TERMS_VERSION)
    return {"ok": True, "message": TEXTS[lang]["done"]}

@app.post("/api/terms/decline")
def api_decline(payload: dict):
    uid = int(payload.get("uid") or 0)
    lang = _pick_lang(payload.get("lang"))
    if uid <= 0:
        return JSONResponse({"ok": False, "message": "UID inválido."}, status_code=400)
    create_or_get_user(uid)
    set_language(uid, lang)
    return {"ok": True, "message": TEXTS[lang]["no"]}
