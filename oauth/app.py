from flask import Flask, request
import requests
import os
from database import save_user_token

app = Flask(__name__)

# AQUI são os NOMES das variáveis do Railway
CLIENT_ID = os.environ.get("36358")
CLIENT_SECRET = os.environ.get("9ttdEOMhVL6aYP5vuJixCYFeqlmhIGBXsf898eie")
REDIRECT_URI = os.environ.get("https://bot-production-1980.up.railway.app/callback")

@app.route("/")
def home():
    return "Servidor rodando."

@app.route("/callback")
def callback():
    code = request.args.get("code")
    telegram_id = request.args.get("state")

    if not code:
        return "Code não recebido", 400

    token_url = "https://anilist.co/api/v2/oauth/token"

    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code
    }

    response = requests.post(token_url, json=data)
    token = response.json().get("access_token")

    if not token:
        return response.json(), 400

    # depois a gente salva no banco
    return "Login feito com sucesso ✅ Pode voltar pro Telegram."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("Iniciando servidor Flask...")
    app.run(host="0.0.0.0", port=port)