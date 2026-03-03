# webapp.py — Mini App Coleção (REAL) + validação initData (Telegram WebApp)

import os
import json
import hmac
import hashlib
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from database import (
    init_db,
    ensure_user_row,
    list_collection_cards,
    get_collection_name,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado nas variáveis de ambiente.")


def verify_telegram_init_data(init_data: str) -> dict:
    """
    Valida initData do Telegram WebApp.
    Sem isso, qualquer um poderia fingir ser outro usuário.
    """
    if not init_data:
        raise HTTPException(status_code=401, detail="initData ausente")

    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="hash ausente")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="initData inválido")

    user_json = data.get("user")
    user = json.loads(user_json) if user_json else None
    if not user or "id" not in user:
        raise HTTPException(status_code=401, detail="user inválido")

    return {"user": user, "raw": data}


app = FastAPI()


@app.on_event("startup")
def _startup():
    # garante tabelas/migrações (para o serviço WEB também)
    init_db()


@app.get("/", response_class=HTMLResponse)
def root():
    return "✅ Web rodando! Abra /app para ver a miniapp."


@app.get("/api/me/collection")
def api_me_collection(x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    # garante linha do usuário
    ensure_user_row(user_id, first_name)

    cards = list_collection_cards(user_id, limit=200)
    return JSONResponse(
        {
            "ok": True,
            "user_id": user_id,
            "collection_name": get_collection_name(user_id),
            "cards": cards,
        }
    )


@app.get("/app", response_class=HTMLResponse)
def miniapp():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Coleção</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 12px; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 10px; }
    img { width: 100%; border-radius: 10px; }
    .name { font-weight: 700; margin-top: 6px; }
    .meta { opacity: .8; font-size: 13px; margin-top: 2px; }
  </style>
</head>
<body>
  <h2>📦 Minha coleção</h2>
  <div id="status">Carregando...</div>
  <div class="grid" id="grid"></div>

  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) tg.ready();

    async function load() {
      const initData = tg?.initData || "";
      const res = await fetch("/api/me/collection", {
        headers: { "X-Telegram-Init-Data": initData }
      });

      if (!res.ok) {
        document.getElementById("status").innerText = "❌ Falha ao carregar coleção.";
        return;
      }

      const data = await res.json();
      document.getElementById("status").innerText = data.collection_name || "Minha Coleção";

      const grid = document.getElementById("grid");
      grid.innerHTML = "";
      const cards = data.cards || [];

      if (!cards.length) {
        grid.innerHTML = "<div>Você ainda não tem cards.</div>";
        return;
      }

      for (const c of cards) {
        const img = c.custom_image || c.image || "";
        const anime = c.anime_title || "";
        const qty = c.quantity || 1;

        const el = document.createElement("div");
        el.className = "card";
        el.innerHTML = `
          ${img ? `<img src="${img}" alt="">` : ""}
          <div class="name">${c.character_name || "Personagem"}</div>
          <div class="meta">${anime}</div>
          <div class="meta">x${qty} • ID ${c.character_id}</div>
        `;
        grid.appendChild(el);
      }
    }

    load().catch(() => {
      document.getElementById("status").innerText = "❌ Erro inesperado.";
    });
  </script>
</body>
</html>
    """
