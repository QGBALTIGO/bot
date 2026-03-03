import os
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Importa o que a miniapp vai usar do seu database.py
from database import init_db, list_collection_cards

app = FastAPI()

# serve arquivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/app", response_class=HTMLResponse)
def miniapp_home():
    # HTML base da miniapp
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/collection", response_class=JSONResponse)
def api_collection(user_id: int = Query(...)):
    """
    Retorna coleção do user_id em JSON.
    """
    items = list_collection_cards(user_id)
    return {"ok": True, "items": items}
