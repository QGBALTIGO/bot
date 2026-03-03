# webapp.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
      <head><title>Baltigo MiniApp</title></head>
      <body style="font-family:Arial;padding:20px">
        <h2>✅ Web rodando!</h2>
        <p>Agora falta ligar isso no Telegram Mini App.</p>
      </body>
    </html>
    """
