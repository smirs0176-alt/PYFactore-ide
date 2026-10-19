"""Вход через Google (OAuth для приложений: локальный адрес 127.0.0.1 + PKCE) и GitHub (Device Flow).
Чистый Python. Нужны свои client_id (создаются бесплатно у Google и GitHub)."""
import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

GH_SCOPE = "read:user user:email repo"
UA = {"User-Agent": "PyFactor-IDE", "Accept": "application/json"}


def _read(req):
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"error": "http_%s" % e.code}
    except urllib.error.URLError as e:
        raise RuntimeError("Нет связи с сервером: %s" % e.reason)


def _post(url, data):
    return _read(urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers=UA))


def _get(url, token):
    return _read(urllib.request.Request(url, headers=dict(UA, Authorization="Bearer " + token)))


def github_start(client_id):
    d = _post("https://github.com/login/device/code", {"client_id": client_id, "scope": GH_SCOPE})
    if "device_code" not in d:
        raise RuntimeError(d.get("error_description") or d.get("error") or "GitHub не выдал код")
    return d


def github_wait(client_id, d, stop):
    interval, end, tok = d.get("interval", 5), time.time() + d.get("expires_in", 900), None
    while time.time() < end and not stop.is_set():
        if stop.wait(interval):
            break
        r = _post("https://github.com/login/oauth/access_token", {
            "client_id": client_id, "device_code": d["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        e = r.get("error")
        if r.get("access_token"):
            tok = r["access_token"]
            break
        if e == "authorization_pending":
            continue
        if e == "slow_down":
            interval = r.get("interval", interval + 5)
            continue
        raise RuntimeError({"expired_token": "Код устарел — попробуй ещё раз", "access_denied": "Доступ отклонён"}.get(
            e, r.get("error_description") or e or "Ошибка GitHub"))
    if stop.is_set():
        raise RuntimeError("Отменено")
    if not tok:
        raise RuntimeError("Время вышло — попробуй ещё раз")
    u = _get("https://api.github.com/user", tok)
    return {"provider": "GitHub", "name": u.get("name") or u.get("login"), "login": u.get("login"),
            "email": u.get("email") or "", "picture": u.get("avatar_url", ""), "token": tok}


def google_login(client_id, client_secret, stop, open_url=webbrowser.open, timeout=240):
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state, got = secrets.token_urlsafe(16), {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q or "error" in q:
                got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<html><body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
                             "<h2>Готово! Закрой вкладку и вернись в PyFactor.</h2></body></html>".encode("utf-8"))

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    srv.timeout = 1
    redirect = "http://127.0.0.1:%d" % srv.server_port
    open_url("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": "openid email profile",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state, "prompt": "select_account"}))
    end = time.time() + timeout
    try:
        while not got and time.time() < end and not stop.is_set():
            srv.handle_request()
    finally:
        srv.server_close()
    if stop.is_set():
        raise RuntimeError("Отменено")
    if got.get("error"):
        raise RuntimeError("Google: " + got["error"])
    if not got:
        raise RuntimeError("Время вышло — попробуй ещё раз")
    if got.get("state") != state:
        raise RuntimeError("Ответ Google не прошёл проверку")
    r = _post("https://oauth2.googleapis.com/token", {
        "code": got["code"], "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect,
        "grant_type": "authorization_code", "code_verifier": verifier})
    if "access_token" not in r:
        raise RuntimeError(r.get("error_description") or r.get("error") or "Google не выдал токен")
    u = _get("https://openidconnect.googleapis.com/v1/userinfo", r["access_token"])
    return {"provider": "Google", "name": u.get("name") or u.get("email"), "email": u.get("email", ""),
            "picture": u.get("picture", "")}
