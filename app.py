from flask import Flask, request
import requests
import os

app = Flask(__name__)

CLIENT_ID = "36358"
CLIENT_SECRET = "9ttdEOMhVL6aYP5vuJixCYFeqlmhIGBXsf898eie"
REDIRECT_URI = "https://bot-production-1980.up.railway.app/callback"

@app.route("/")
def home():
    return "Servidor rodando."

@app.route("/callback")
def callback():
    code = request.args.get("code")

    token_url = "https://anilist.co/api/v2/oauth/token"

    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code
    }

    response = requests.post(token_url, json=data)
    return response.json()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))