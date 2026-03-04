import os
import json
import random
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import database as db

app = FastAPI()

# ===============================
# Helpers
# ===============================

def get_user(user_id):
    user = db.get_user_row(user_id)
    if not user:
        db.ensure_user_row(user_id, "Player")
        user = db.get_user_row(user_id)
    return user


# ===============================
# DADO
# ===============================

@app.get("/dado", response_class=HTMLResponse)
async def dado_page():

    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Dado</title>

<style>

body{
background:linear-gradient(135deg,#141e30,#243b55);
font-family:Arial;
color:white;
text-align:center;
padding:40px;
}

button{
background:#ff4757;
border:none;
padding:15px 30px;
border-radius:10px;
font-size:18px;
color:white;
cursor:pointer;
}

.card{
background:#1e272e;
padding:20px;
border-radius:12px;
margin:10px;
display:inline-block;
width:200px;
}

</style>

</head>
<body>

<h1>🎲 Dado da Sorte</h1>

<button onclick="roll()">Rolar Dado</button>

<div id="result"></div>

<script>

async function roll(){

let r = await fetch("/api/dado/start?user_id=1");
let data = await r.json();

if(!data.options){
alert("Erro no dado");
return;
}

let html = "";

for(let o of data.options){

html += `<div class="card">
<h3>${o.anime}</h3>
<button onclick="pick(${data.roll_id},${o.id})">Escolher</button>
</div>`;

}

document.getElementById("result").innerHTML = html;

}

async function pick(roll,option){

let r = await fetch("/api/dado/pick",{
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({
roll_id:roll,
option_id:option,
user_id:1
})
});

let data = await r.json();

alert(JSON.stringify(data));

}

</script>

</body>
</html>
"""


# ===============================
# API DADO START
# ===============================

@app.get("/api/dado/start")
def dado_start(user_id: int):

    user = get_user(user_id)

    balance = user["dado_balance"]

    if balance <= 0:
        raise HTTPException(400,"Sem dados")

    db.inc_dado_balance(user_id,-1)

    dice = random.randint(1,6)

    animes = db.pool_random_animes(dice)

    roll_id = db.create_dice_roll(
        user_id,
        dice,
        json.dumps(animes),
        "pending",
        int(time.time())
    )

    options = []

    for i,a in enumerate(animes):
        options.append({
            "id":i+1,
            "anime":a["anime"]
        })

    return {
        "roll_id":roll_id,
        "dice":dice,
        "options":options
    }


# ===============================
# API PICK
# ===============================

@app.post("/api/dado/pick")
def dado_pick(data: dict):

    roll_id = data["roll_id"]
    option_id = data["option_id"]
    user_id = data["user_id"]

    roll = db.get_dice_roll(roll_id)

    if not roll:
        raise HTTPException(400,"roll inválido")

    options = json.loads(roll["options_json"])

    chosen = options[option_id-1]

    char = db.pool_random_character(chosen["anime"])

    if not char:
        return {"status":"no_character"}

    db.add_character_to_collection(
        user_id,
        char["character_id"],
        char["name"],
        char["image"],
        char["anime"]
    )

    db.set_dice_roll_status(roll_id,"done")

    return {
        "status":"ok",
        "character":char["name"]
    }


# ===============================
# LOJA
# ===============================

@app.get("/shop", response_class=HTMLResponse)
async def shop():

    return """
<html>
<body style="background:#111;color:white;text-align:center">

<h1>🛒 Loja</h1>

<button onclick="buy()">Comprar dado (10 moedas)</button>

<script>

async function buy(){

let r = await fetch("/api/shop/buy?user_id=1");
let d = await r.json();

alert(JSON.stringify(d));

}

</script>

</body>
</html>
"""


@app.get("/api/shop/buy")
def buy(user_id:int):

    ok = db.spend_coins_and_add_giro(user_id,10,1)

    if not ok:
        return {"status":"no_coins"}

    return {"status":"ok"}


# ===============================
# COLEÇÃO
# ===============================

@app.get("/colecao", response_class=HTMLResponse)
async def colecao():

    return """
<html>
<body style="background:#111;color:white">

<h1>🎴 Coleção</h1>

<div id="cards"></div>

<script>

async function load(){

let r = await fetch("/api/colecao?user_id=1");
let d = await r.json();

let html="";

for(let c of d){

html+=`<div>
<img src="${c.image}" width="120"><br>
${c.name}
</div>`;

}

document.getElementById("cards").innerHTML=html;

}

load();

</script>

</body>
</html>
"""


@app.get("/api/colecao")
def api_colecao(user_id:int):

    return db.list_collection_cards(user_id,200)
