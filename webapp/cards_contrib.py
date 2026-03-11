from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/cards/contrib")
async def cards_contrib():

    html = """
<!DOCTYPE html>
<html>
<head>

<meta name="viewport" content="width=device-width, initial-scale=1">

<style>

body{
background:#0f0f0f;
color:white;
font-family:Arial;
text-align:center;
}

.btn{
display:block;
width:80%;
margin:20px auto;
padding:20px;
border-radius:12px;
background:#1f1f1f;
font-size:18px;
}

</style>

</head>

<body>

<h2>Central de Contribuições</h2>

<div class="btn" onclick="window.location='/cards/contrib/image'">
🖼 Alterar foto de personagem
</div>

<div class="btn" onclick="window.location='/cards/contrib/work'">
🎬 Pedir nova obra para cards
</div>

<div class="btn" onclick="window.location='/cards/contrib/rules'">
📜 Regras
</div>

</body>
</html>
"""

    return HTMLResponse(html)
