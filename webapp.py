import os
import time
import hmac
import hashlib
import base64

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from database import init_db, save_anilist_token

app = FastAPI()

ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID", "").strip()
ANILIST_CLIENT_SECRET = os.getenv("ANILIST_CLIENT_SECRET", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()
OAUTH_STATE_SECRET = os.getenv("OAUTH_STATE_SECRET", "").strip()

def parse_and_verify_state(state: str):
    try:
        pad = "=" * (-len(state) % 4)
        raw = base64.urlsafe_b64decode(state + pad)
        payload, sig = raw.rsplit(b".", 1)
        expected = hmac.new(OAUTH_STATE_SECRET.encode(), payload, hashlib.sha256).digest()

        if not hmac.compare_digest(sig, expected):
            return None

        user_id_s, ts_s = payload.decode().split(".", 1)
        return int(user_id_s)
    except Exception:
        return None

@app.on_event("startup")
def _startup():
    init_db()

@app.get("/callback")
async def callback(code: str = Query(default=""), state: str = Query(default="")):
    user_id = parse_and_verify_state(state)
    if not user_id:
        return HTMLResponse("<h3>Erro: state inválido.</h3>", status_code=400)

    if not code:
        return HTMLResponse("<h3>Erro: code ausente.</h3>", status_code=400)

    redirect_uri = f"{PUBLIC_BASE_URL}/callback"

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://anilist.co/api/v2/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": ANILIST_CLIENT_ID,
                "client_secret": ANILIST_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )

    if resp.status_code != 200:
        return HTMLResponse(
            "<h3>Erro ao autorizar.</h3>"
            f"<pre>{resp.text[:800]}</pre>",
            status_code=400,
        )

    data = resp.json()
    token = data.get("access_token")
    if not token:
        return HTMLResponse("<h3>Erro: token não retornou.</h3>", status_code=400)

    save_anilist_token(user_id, token, int(time.time()))

    return HTMLResponse(
        "<h2>✅ Conta AniList conectada!</h2>"
        "<p>Você já pode voltar ao Telegram.</p>"
    )
