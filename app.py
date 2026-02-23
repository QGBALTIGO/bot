from flask import Flask, request
import requests
import os
from database import init_db, save_user_token

app = Flask(__name__)
init_db()

CLIENT_ID = "36358"
CLIENT_SECRET = "9ttdEOMhVL6aYP5vuJixCYFeqlmhIGBXsf898eie"
REDIRECT_URI = "https://bot-production-1980.up.railway.app/callback"

@app.route("/")
def home():
    return "Servidor rodando."

@app.route("/callback")
def callback():
    code = request.args.get("code")
    telegram_id = request.args.get("state")

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
        return "Erro ao obter token do AniList."

    save_user_token(telegram_id, token)

    return "Login realizado com sucesso! Pode voltar para o Telegram."
