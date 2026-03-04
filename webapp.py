
# webapp_ultra.py
# Ultra UI: Coleção + Loja + Dado estilo gacha premium

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<style>

body{
margin:0;
font-family:system-ui;
background:radial-gradient(circle at top,#1a1a35,#050510);
color:white;
overflow-x:hidden;
}

canvas{
position:fixed;
top:0;
left:0;
z-index:-1;
}

.container{
max-width:520px;
margin:auto;
padding:18px;
}

.header{
display:flex;
justify-content:space-between;
align-items:center;
margin-bottom:20px;
}

.balance{
display:flex;
gap:10px;
background:rgba(255,255,255,0.05);
padding:8px 14px;
border-radius:16px;
backdrop-filter:blur(10px);
}

.tabs{
display:flex;
gap:10px;
margin-bottom:16px;
}

.tab{
flex:1;
padding:10px;
border-radius:20px;
background:#111;
text-align:center;
font-weight:700;
cursor:pointer;
transition:.2s;
}

.tab.active{
background:linear-gradient(90deg,#ff2b4a,#b06cff);
}

.grid{
display:grid;
grid-template-columns:1fr 1fr;
gap:14px;
}

.card{
position:relative;
border-radius:20px;
overflow:hidden;
background:rgba(255,255,255,0.06);
backdrop-filter:blur(16px);
border:1px solid rgba(255,255,255,0.1);
transition:transform .25s;
}

.card:hover{
transform:scale(1.05);
}

.card img{
width:100%;
height:230px;
object-fit:cover;
}

.card-info{
position:absolute;
bottom:0;
width:100%;
padding:12px;
background:linear-gradient(transparent,black);
}

.rarity-common{color:#aaa}
.rarity-rare{color:#4fc3f7;text-shadow:0 0 10px #4fc3f7}
.rarity-epic{color:#ba68c8;text-shadow:0 0 14px #ba68c8}
.rarity-mythic{color:gold;text-shadow:0 0 22px gold}

.shop-card{
background:rgba(255,255,255,0.06);
border:1px solid rgba(255,255,255,0.1);
border-radius:20px;
padding:18px;
text-align:center;
backdrop-filter:blur(12px);
transition:.2s;
}

.shop-card:hover{
transform:scale(1.05);
}

button{
margin-top:12px;
padding:10px 16px;
border:none;
border-radius:12px;
background:linear-gradient(90deg,#ff2b4a,#b06cff);
color:white;
font-weight:700;
cursor:pointer;
transition:.2s;
}

button:hover{
transform:scale(1.05);
}

.dice3d{
font-size:90px;
text-align:center;
margin-top:40px;
transition:transform 1s;
}

.open-card{
width:260px;
height:360px;
margin:auto;
margin-top:40px;
border-radius:20px;
overflow:hidden;
background:rgba(255,255,255,0.05);
display:flex;
align-items:center;
justify-content:center;
font-size:60px;
backdrop-filter:blur(10px);
}

.glow{
animation:glow 1s infinite alternate;
}

@keyframes glow{
from{text-shadow:0 0 10px gold}
to{text-shadow:0 0 30px gold}
}

</style>
</head>

<body>

<canvas id="bg"></canvas>

<div class="container">

<div class="header">
<div>Hello | Player</div>
<div class="balance">💎 5 ❤️ 24</div>
</div>

<div class="tabs">
<div class="tab active" onclick="showPage('collection')">Coleção</div>
<div class="tab" onclick="showPage('shop')">Loja</div>
<div class="tab" onclick="showPage('dice')">Dado</div>
</div>

<!-- COLEÇÃO -->

<div id="collection">

<div class="grid">

<div class="card">
<img src="https://i.imgur.com/9yG6F8R.jpeg">
<div class="card-info">
Nicole
<div class="rarity-epic">Epic</div>
</div>
</div>

<div class="card">
<img src="https://i.imgur.com/1Q9Z1Zm.jpeg">
<div class="card-info">
Isa
<div class="rarity-rare">Rare</div>
</div>
</div>

<div class="card">
<img src="https://i.imgur.com/mK3J9sL.jpeg">
<div class="card-info">
Luna
<div class="rarity-common">Common</div>
</div>
</div>

<div class="card">
<img src="https://i.imgur.com/rm5K6Xk.jpeg">
<div class="card-info">
Elysia
<div class="rarity-mythic glow">Mythic</div>
</div>
</div>

</div>

</div>

<!-- LOJA -->

<div id="shop" style="display:none">

<div class="grid">

<div class="shop-card">
<h3>🎲 Dado</h3>
<p>Sortear personagem</p>
<button onclick="buy('dado')">Comprar</button>
</div>

<div class="shop-card">
<h3>🎴 Abrir Carta</h3>
<p>Gacha premium</p>
<button onclick="openCard()">Abrir</button>
</div>

</div>

<div class="open-card" id="gacha">🎴</div>

</div>

<!-- DADO -->

<div id="dice" style="display:none">

<div class="dice3d" id="dice3d">🎲</div>

<div style="text-align:center">
<button onclick="rollDice()">Rolar Dado</button>
</div>

</div>

</div>

<script>

function showPage(p){

document.getElementById("collection").style.display="none"
document.getElementById("shop").style.display="none"
document.getElementById("dice").style.display="none"

document.getElementById(p).style.display="block"

}

function buy(item){
alert("Comprado: "+item)
}

function openCard(){

const card=document.getElementById("gacha")

card.innerText="✨"

setTimeout(()=>{

card.innerHTML='<img src="https://i.imgur.com/rm5K6Xk.jpeg" style="width:100%;height:100%;object-fit:cover">'

},1200)

}

function rollDice(){

const d=document.getElementById("dice3d")

d.style.transform="rotateX(720deg) rotateY(720deg)"

setTimeout(()=>{

d.innerText=Math.floor(Math.random()*6)+1

},1000)

}

const canvas=document.getElementById("bg")
const ctx=canvas.getContext("2d")

canvas.width=window.innerWidth
canvas.height=window.innerHeight

let particles=[]

for(let i=0;i<80;i++){
particles.push({
x:Math.random()*canvas.width,
y:Math.random()*canvas.height,
r:Math.random()*2
})
}

function draw(){

ctx.clearRect(0,0,canvas.width,canvas.height)

particles.forEach(p=>{

ctx.beginPath()
ctx.arc(p.x,p.y,p.r,0,Math.PI*2)
ctx.fillStyle="white"
ctx.fill()

p.y+=0.3

if(p.y>canvas.height)p.y=0

})

requestAnimationFrame(draw)

}

draw()

</script>

</body>
</html>
"""

@app.get("/")
def root():
    return HTMLResponse(HTML)

@app.get("/colecao")
def colecao():
    return HTMLResponse(HTML)

@app.get("/loja")
def loja():
    return HTMLResponse(HTML)

@app.get("/dado")
def dado():
    return HTMLResponse(HTML)
