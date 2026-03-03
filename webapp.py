# webapp.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def home():
    return "<h1>✅ Web rodando!</h1><p>Abra /app para ver a miniapp.</p>"

@app.get("/app", response_class=HTMLResponse)
def miniapp():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Coleção</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body { font-family: Arial; margin: 0; padding: 16px; background: #0b0b10; color: #fff; }
    .card { background:#141420; border-radius:16px; padding:12px; margin-bottom:12px; }
    .muted { opacity:.75; font-size: 12px; }
  </style>
</head>
<body>
  <h2>📦 Minha Coleção</h2>
  <div class="muted" id="info"></div>
  <div id="list"></div>

  <script>
    const tg = window.Telegram.WebApp;
    tg.ready();

    const user = tg.initDataUnsafe?.user;
    document.getElementById("info").textContent =
      user ? ("Logado como: @" + (user.username || "") + " | ID: " + user.id) : "Abra dentro do Telegram";

    const list = document.getElementById("list");
    const demo = [
      { id: 1, nome: "Nicole", anime: "Exemplo" },
      { id: 2, nome: "Morgana", anime: "Exemplo" },
    ];
    demo.forEach(it => {
      const div = document.createElement("div");
      div.className = "card";
      div.innerHTML = `<b>${it.nome}</b><div class="muted">${it.anime} • ID ${it.id}</div>`;
      list.appendChild(div);
    });
  </script>
</body>
</html>
"""
