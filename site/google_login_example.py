import os
from urllib.parse import urlencode

import requests
from flask import Flask, jsonify, redirect, render_template, request

app = Flask(__name__, template_folder="templates")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:5000/oauth/google/callback",
)
GOOGLE_SCOPE = "openid email profile"


def build_google_auth_url() -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


@app.route("/")
def index():
    if not GOOGLE_CLIENT_ID:
        return render_template(
            "google_login.html",
            google_client_id="",
            login_url="#",
            message="Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in environment before running.",
        )
    return render_template(
        "google_login.html",
        google_client_id=GOOGLE_CLIENT_ID,
        login_url=build_google_auth_url(),
        message="",
    )


@app.route("/auth/google")
def auth_google():
    if not GOOGLE_CLIENT_ID:
        return "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in environment.", 500
    return redirect(build_google_auth_url())


@app.route("/oauth/google/callback")
def google_callback():
    code = request.args.get("code")
    if not code:
        return "No code in callback.", 400
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET before starting the app.", 500

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    token_data = token_response.json()
    if "access_token" not in token_data:
        return jsonify({"error": token_data}), 400

    user_response = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": "Bearer " + token_data["access_token"]},
        timeout=30,
    )
    user = user_response.json()
    return render_template(
        "google_login.html",
        google_client_id=GOOGLE_CLIENT_ID,
        login_url=build_google_auth_url(),
        message="Success! You are logged in.",
        user=user,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)   # debug=True на 0.0.0.0 даёт удалённое выполнение кода
