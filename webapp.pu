# ==========================================
# webapp.py
# Source Baltigo — WebApp Server
# ==========================================

import os
import json
import time
import hmac
import hashlib

from urllib.parse import parse_qsl
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# ==========================================
# CONFIG
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN não encontrado.")

MINIAPP_SIGNING_SECRET = os.getenv("MINIAPP_SIGNING_SECRET", "").strip()

# ==========================================
# APP
# ==========================================

app = FastAPI()

# Servir arquivos estáticos
app.mount("/css", StaticFiles(directory="webapp/css"), name="css")
app.mount("/js", StaticFiles(directory="webapp/js"), name="js")

# ==========================================
# VERIFY TELEGRAM WEBAPP
# ==========================================

def verify_telegram_init_data(init_data: str):

    if not init_data:
        raise HTTPException(status_code=401, detail="initData ausente")

    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)

    if not received_hash:
        raise HTTPException(status_code=401, detail="hash ausente")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256
    ).digest()

    calculated_hash = hmac.new(
        secret_key,
        check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="initData inválido")

    user_json = data.get("user")

    user = json.loads(user_json) if user_json else None

    if not user:
        raise HTTPException(status_code=401, detail="user inválido")

    return user


# ==========================================
# ROOT
# ==========================================

@app.get("/")
def root():

    return {
        "status": "ok",
        "app": "Source Baltigo WebApp"
    }


# ==========================================
# UI — COLEÇÃO
# ==========================================

@app.get("/app")
def open_collection():

    return FileResponse("webapp/index.html")


# ==========================================
# UI — DADO
# ==========================================

@app.get("/dado")
def open_dado():

    return FileResponse("webapp/dado.html")


# ==========================================
# UI — LOJA
# ==========================================

@app.get("/shop")
def open_shop():

    return FileResponse("webapp/shop.html")


# ==========================================
# API — COLLECTION
# ==========================================

@app.get("/api/me/collection")
def api_me_collection(x_telegram_init_data: str = Header(default="")):

    user = verify_telegram_init_data(x_telegram_init_data)

    import database as db

    user_id = int(user["id"])
    first_name = user.get("first_name", "User")

    db.ensure_user_row(user_id, first_name)

    coins = db.get_user_coins(user_id)
    giros = db.get_extra_dado(user_id)

    cards = db.list_collection_cards(user_id, limit=500)

    return JSONResponse({
        "ok": True,
        "owner_id": user_id,
        "owner_name": first_name,
        "coins": coins,
        "giros": giros,
        "cards": cards
    })


# ==========================================
# API — SHOP STATE
# ==========================================

@app.get("/api/shop/state")
def api_shop_state(x_telegram_init_data: str = Header(default="")):

    user = verify_telegram_init_data(x_telegram_init_data)

    import database as db

    user_id = int(user["id"])

    coins = db.get_user_coins(user_id)
    giros = db.get_extra_dado(user_id)

    return JSONResponse({

        "ok": True,
        "coins": coins,
        "giros": giros

    })


# ==========================================
# API — SELL CHARACTER
# ==========================================

@app.post("/api/shop/sell")
def api_sell(payload: dict, x_telegram_init_data: str = Header(default="")):

    user = verify_telegram_init_data(x_telegram_init_data)

    import database as db

    user_id = int(user["id"])
    char_id = int(payload.get("character_id", 0))

    if not char_id:
        raise HTTPException(400)

    ok = db.remove_one_from_collection(user_id, char_id)

    if not ok:

        return JSONResponse({
            "ok": False,
            "error": "not_found"
        })

    db.add_coin(user_id, 1)

    coins = db.get_user_coins(user_id)

    return JSONResponse({

        "ok": True,
        "coins": coins

    })


# ==========================================
# API — BUY GIRO
# ==========================================

@app.post("/api/shop/buy/giro")
def api_buy_giro(x_telegram_init_data: str = Header(default="")):

    user = verify_telegram_init_data(x_telegram_init_data)

    import database as db

    user_id = int(user["id"])

    ok = db.spend_coins_and_add_giro(user_id, 2)

    if not ok:

        return JSONResponse({
            "ok": False
        })

    coins = db.get_user_coins(user_id)
    giros = db.get_extra_dado(user_id)

    return JSONResponse({

        "ok": True,
        "coins": coins,
        "giros": giros

    })


# ==========================================
# API — DADO START
# ==========================================

@app.post("/api/dado/start")
def api_dado_start(x_telegram_init_data: str = Header(default="")):

    user = verify_telegram_init_data(x_telegram_init_data)

    import database as db

    user_id = int(user["id"])

    roll = db.create_dice_roll(user_id)

    return JSONResponse({

        "ok": True,
        "roll": roll

    })


# ==========================================
# API — DADO PICK
# ==========================================

@app.post("/api/dado/pick")
def api_dado_pick(payload: dict, x_telegram_init_data: str = Header(default="")):

    user = verify_telegram_init_data(x_telegram_init_data)

    import database as db

    user_id = int(user["id"])

    anime_id = int(payload.get("anime_id"))
    roll_id = int(payload.get("roll_id"))

    char = db.resolve_dice_roll(user_id, roll_id, anime_id)

    if not char:

        return JSONResponse({
            "ok": False
        })

    return JSONResponse({

        "ok": True,
        "character": char

    })
