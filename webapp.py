from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

STYLE = """
<style>
body{
margin:0;
font-family:system-ui;
background:radial-gradient(circle at top,#1a1a35,#050510);
color:white;
overflow-x:hidden;
}

.container{
max-width:520px;
margin:auto;
padding:20px;
}

.title{
font-size:26px;
font-weight:800;
margin-bottom:18px;
}

.grid{
display:grid;
grid-template-columns:1fr 1fr;
gap:14px;
}

.card{
background:rgba(255,255,255,0.06);
backdrop-filter:blur(14px);
border-radius:20px;
border:1px solid rgba(255,255,255,0.1);
overflow:hidden;
}

.card img{
width:100%;
height:220px;
object-fit:cover;
}

.card-info{
padding:10px;
}

.rarity-common{color:#aaa}
.rarity-rare{color:#4fc3f7}
.rarity-epic{color:#ba68c8}
.rarity-mythic{color:gold}

.shop-card{
background:rgba(255,255,255,0.05);
border-radius:20px;
padding:18px;
text-align:center;
border:1px solid rgba(255,255,255,0.1);
}

button{
margin-top:10px;
padding:10px 16px;
border:none;
border-radius:12px;
background:linear-gradient(90deg,#ff2b4a,#b06cff);
color:white;
font-weight:700;
cursor:pointer;
}

.dice{
width:90px;
height:90px;
background:#111;
border-radius:18px;
display:flex;
align-items:center;
justify-content:center;
font-size:40px;
margin:auto;
transition:transform 1s;
}

.result{
text-align:center;
margin-top:20px;
font-size:22px;
}
</style>
"""

COLLECTION_HTML = """
<html>
<head>""" + STYLE + """</head>
<body>

<div class="container">
<div class="title">🖼 Coleção</div>

<div class="grid">

<div class="card">
<img src="https://picsum.photos/400/600?1">
<div class="card-info">
Luna
<div class="rarity-common">Common</div>
</div>
</div>

<div class="card">
<img src="https://picsum.photos/400/600?2">
<div class="card-info">
Mika
<div class="rarity-rare">Rare</div>
</div>
</div>

<div class="card">
<img src="https://picsum.photos/400/600?3">
<div class="card-info">
Aurora
<div class="rarity-epic">Epic</div>
</div>
</div>

<div class="card">
<img src="https://picsum.photos/400/600?4">
<div class="card-info">
Elysia
<div class="rarity-mythic">Mythic</div>
</div>
</div>

</div>
</div>

</body>
</html>
"""

SHOP_HTML = """
<html>
<head>""" + STYLE + """</head>
<body>

<div class="container">
<div class="title">🏪 Loja</div>

<div class="grid">

<div class="shop-card">
<h3>🎲 Dado</h3>
<p>Preço: <b>2 coins</b></p>
<button onclick="buyDice()">Comprar</button>
</div>

<div class="shop-card">
<h3>🎴 Carta</h3>
<p>Preço: <b>1 coin</b></p>
<button onclick="openCard()">Abrir</button>
</div>

</div>
</div>

<script>
function buyDice(){
alert("Você comprou 1 dado por 2 coins")
}

function openCard(){
alert("Carta aberta!")
}
</script>

</body>
</html>
"""

DICE_HTML = """
<html>
<head>""" + STYLE + """</head>
<body>

<div class="container">

<div class="title">🎲 Dado da Sorte</div>

<div class="dice" id="dice">🎲</div>

<div style="text-align:center;margin-top:20px">
<button onclick="rollDice()">Rolar</button>
</div>

<div class="result" id="result"></div>

</div>

<script>

function rollDice(){

let dice=document.getElementById("dice")

dice.style.transform="rotateX(720deg) rotateY(720deg)"

setTimeout(()=>{

let value=Math.floor(Math.random()*6)+1

dice.innerText=value

document.getElementById("result").innerText="Resultado: "+value

},1000)

}

</script>

</body>
</html>
"""

@app.get("/colecao")
def colecao():
    return HTMLResponse(COLLECTION_HTML)

@app.get("/shop")
def shop():
    return HTMLResponse(SHOP_HTML)

@app.get("/dado")
def dado():
    return HTMLResponse(DICE_HTML)
