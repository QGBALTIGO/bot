# webapp.py — Mini App Coleção (REAL) + validação initData (Telegram WebApp)
# - NÃO quebra se faltar função no database.py
# - Importa database dentro das rotas (evita crash no boot)
# - UI estilo cards (parecido com seu exemplo)

import os
import json
import hmac
import hashlib
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse


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


@app.get("/", response_class=HTMLResponse)
def root():
    return "✅ Web rodando! Abra /app para ver a miniapp."


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _get_user_coins_and_giros(user_id: int) -> tuple[int, int]:
    """
    Pega coins e giros sem depender de funções específicas.
    - coins: tenta vir de get_user_row()
    - giros: tenta vir de get_extra_state() (extra_dado)
    """
    coins = 0
    giros = 0

    # Importa database aqui dentro pra não quebrar o boot do uvicorn
    import database

    # COINS (tenta por user row)
    try:
        row = database.get_user_row(user_id)
        # tenta campos comuns
        coins = _safe_int(
            row.get("coins") if isinstance(row, dict) else None,
            default=0
        )
    except Exception:
        coins = 0

    # GIROS (extra_dado)
    try:
        # seu bot usa get_extra_state(user_id) -> {"x":..., "s":...}
        st = database.get_extra_state(user_id)
        if isinstance(st, dict):
            giros = _safe_int(st.get("x"), default=0)
    except Exception:
        giros = 0

    return coins, giros


def _get_collection_name_safe(user_id: int) -> str:
    import database
    try:
        name = database.get_collection_name(user_id)
        if isinstance(name, str) and name.strip():
            return name.strip()
    except Exception:
        pass
    return "Minha coleção"


def _list_collection_cards_safe(user_id: int, limit: int = 200) -> list[dict]:
    """
    Busca cards da coleção.
    Tenta usar list_collection_cards() se existir.
    Se não existir, retorna lista vazia (webapp sobe igual).
    """
    import database

    try:
        fn = getattr(database, "list_collection_cards", None)
        if callable(fn):
            cards = fn(user_id, limit=limit)
            if isinstance(cards, list):
                # garante dicts
                return [c for c in cards if isinstance(c, dict)]
    except Exception:
        pass

    return []


@app.get("/api/me/collection")
def api_me_collection(x_telegram_init_data: str = Header(default="")):
    payload = verify_telegram_init_data(x_telegram_init_data)
    user = payload["user"]
    user_id = int(user["id"])
    first_name = user.get("first_name") or "User"

    import database

    # garante linha do usuário (se a função existir)
    try:
        database.ensure_user_row(user_id, first_name)
    except Exception:
        # se ensure_user_row não existir ou falhar, não derruba a miniapp
        pass

    coins, giros = _get_user_coins_and_giros(user_id)
    collection_name = _get_collection_name_safe(user_id)
    cards = _list_collection_cards_safe(user_id, limit=200)

    return JSONResponse(
        {
            "ok": True,
            "user_id": user_id,
            "collection_name": collection_name,
            "coins": coins,
            "giros": giros,
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
  <meta name="viewport" content="width=device-width,initial-scale=1, viewport-fit=cover">
  <title>Coleção</title>
  <style>
    :root{
      --bg:#0b0b0f;
      --card:#151522;
      --muted: rgba(255,255,255,.65);
      --muted2: rgba(255,255,255,.45);
      --stroke: rgba(255,255,255,.12);
      --accent:#ff4fd8;
      --accent2:#7c4dff;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
      background:var(--bg);
      color:#fff;
      padding:12px 12px 88px;
    }
    .top{
      display:flex; align-items:center; justify-content:space-between; gap:10px;
      margin-top:4px;
    }
    .title{display:flex; flex-direction:column; gap:2px;}
    .title h1{margin:0; font-size:18px; font-weight:900;}
    .title .sub{font-size:12px; color:var(--muted2);}

    .stats{
      display:flex; align-items:center; gap:8px;
      padding:10px 12px;
      border:1px solid var(--stroke);
      background:rgba(255,255,255,.04);
      border-radius:999px;
      white-space:nowrap;
    }
    .stat{display:flex; align-items:center; gap:6px; font-weight:900; font-size:13px;}
    .dot{width:1px; height:16px; background:var(--stroke);}

    .tabs{
      display:flex; gap:10px;
      margin:14px 0 10px;
      padding:8px;
      border:1px solid var(--stroke);
      border-radius:999px;
      background:rgba(255,255,255,.04);
    }
    .tab{
      flex:1; text-align:center;
      padding:10px 12px; border-radius:999px;
      font-weight:900; font-size:14px;
      color:var(--muted);
      background:transparent; border:0;
    }
    .tab.active{
      color:#fff;
      background:linear-gradient(90deg, rgba(255,79,216,.9), rgba(124,77,255,.9));
      box-shadow:0 10px 30px rgba(255,79,216,.15);
    }

    .search{display:flex; gap:10px; align-items:center; margin:8px 0 14px;}
    .search input{
      width:100%;
      padding:12px 12px;
      border-radius:14px;
      border:1px solid var(--stroke);
      background:rgba(255,255,255,.04);
      color:#fff;
      outline:none;
      font-size:14px;
    }
    .search input::placeholder{color:rgba(255,255,255,.35)}

    .status{
      margin:10px 0;
      padding:10px 12px;
      border-radius:14px;
      border:1px solid var(--stroke);
      background:rgba(255,255,255,.03);
      color:var(--muted);
      font-size:13px;
    }
    .status.ok{ border-color: rgba(0,255,140,.18); }
    .status.err{ border-color: rgba(255,60,60,.18); color: rgba(255,120,120,.9); }

    .grid{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px;}
    .card{
      position:relative;
      border-radius:20px;
      overflow:hidden;
      border:1px solid var(--stroke);
      background:var(--card);
      min-height:220px;
    }
    .card img{width:100%; height:220px; object-fit:cover; display:block;}
    .overlay{
      position:absolute; left:0; right:0; bottom:0;
      padding:10px;
      background:linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.75));
    }
    .name{font-weight:900; font-size:16px; margin:0;}
    .meta{margin-top:3px; font-size:12px; color:rgba(255,255,255,.75);}
    .pill{
      position:absolute; top:10px; left:10px;
      padding:6px 10px;
      background:rgba(0,0,0,.45);
      border:1px solid rgba(255,255,255,.14);
      border-radius:999px;
      font-weight:900; font-size:12px;
    }

    .bottom{
      position:fixed; left:12px; right:12px; bottom:14px;
      padding:12px 14px;
      border-radius:18px;
      border:1px solid var(--stroke);
      background:rgba(20,20,30,.72);
      backdrop-filter:blur(14px);
      display:flex; justify-content:space-between; gap:10px;
    }
    .nav{
      flex:1; text-align:center;
      color:rgba(255,255,255,.75);
      font-weight:900; font-size:12px;
      border-radius:14px;
      padding:10px 8px;
      background:transparent; border:0;
    }
    .nav.active{ color:#fff; background:rgba(255,255,255,.06
