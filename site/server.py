#!/usr/bin/env python3
"""Сайт PyFactor: регистрация и вход, скачивание приложения, автоподключение приложения к аккаунту.

Запуск:  python site/server.py        (открой http://127.0.0.1:8081)
Только стандартная библиотека Python. Настройки через переменные окружения — см. site/README.md."""
import base64
import hashlib
import hmac
import http.cookies
import http.server
import importlib.util
import ipaddress
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import packager  # noqa: E402
from store import Limiter, SiteError, Store  # noqa: E402

HOST = os.environ.get("SITE_HOST", "127.0.0.1")
PORT = int(os.environ.get("SITE_PORT", "8081"))
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
SECURE = os.environ.get("SITE_SECURE", "") == "1"                # сайт за HTTPS: ставит Secure на cookie
TRUST_PROXY = os.environ.get("SITE_TRUST_PROXY", "") == "1"      # сайт за nginx/Caddy: верим X-Forwarded-*
DATA = os.environ.get("SITE_DATA", os.path.join(HERE, "data"))
RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "160255116606-inmm024d28l3tn89mq2mm6up184no70t.apps.googleusercontent.com")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")      # секрет только из окружения, в коде его быть не должно
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")
GOOGLE_SCOPE = os.environ.get("GOOGLE_SCOPE", "openid email profile")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.environ.get("GITHUB_REDIRECT_URI", "")
GITHUB_SCOPE = os.environ.get("GITHUB_SCOPE", "read:user user:email")

_spec = importlib.util.spec_from_file_location("pf_mailer", os.path.join(ROOT, "pyfactor", "core", "account", "mailer.py"))
mailer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mailer)

ST, LIM = None, Limiter()
PENDING = {}                         # email -> код подтверждения почты (только в памяти)
PAGE = os.path.join(HERE, "index.html")                   # вся страница в одном файле: HTML + CSS + JS
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
if SECURE:
    HEADERS["Strict-Transport-Security"] = "max-age=31536000"


def page():
    """Отдаёт index.html. Скрипт и стили встроены в него, поэтому CSP разрешает не всё подряд, а только их точные хеши."""
    with open(PAGE, encoding="utf-8") as f:
        html = f.read()

    def sha(text):
        return "'sha256-%s'" % base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode()
    scripts = " ".join(sha(t) for t in re.findall(r"<script>(.*?)</script>", html, re.S))
    styles = " ".join(sha(t) for t in re.findall(r"<style>(.*?)</style>", html, re.S))
    csp = ("default-src 'self'; script-src %s; style-src %s; img-src 'self' data:; base-uri 'none'; "
           "form-action 'self'; frame-ancestors 'none'" % (scripts, styles))
    return html.encode("utf-8"), csp


def client_ip(xff, peer, trust_proxy):
    """Адрес клиента. За прокси берём ПОСЛЕДНЕЕ значение X-Forwarded-For: его дописал наш прокси, а всё левее подделывает клиент."""
    if trust_proxy and xff:
        last = xff.split(",")[-1].strip()
        try:
            ipaddress.ip_address(last)
            return last
        except ValueError:
            pass
    return peer


PENDING_MAX = 5000


def pending_cleanup(now=None):
    """Убирает просроченные коды подтверждения и не даёт словарю расти без предела."""
    now = now or time.time()
    for k in [k for k, v in PENDING.items() if v["exp"] < now]:
        del PENDING[k]
    while len(PENDING) > PENDING_MAX:
        PENDING.pop(min(PENDING, key=lambda k: PENDING[k]["sent"]))


def get_cookie(headers, name):
    raw = headers.get("Cookie", "")
    try:
        c = http.cookies.SimpleCookie(raw)
    except http.cookies.CookieError:
        return ""
    return c[name].value if name in c else ""


def oauth_cookie(provider, value, max_age=600):
    return "oauth_%s=%s; HttpOnly; SameSite=Lax; Path=/; Max-Age=%d%s" % (provider, value, max_age, "; Secure" if SECURE else "")


def state_ok(expected, got):
    """state из куки и из адреса возврата должны совпасть (защита входа от подделки запроса)."""
    return bool(expected) and bool(got) and hmac.compare_digest(expected, got)


def google_email(user):
    """Почта из Google годится для входа только если Google её подтвердил."""
    if user.get("email_verified") not in (True, "true"):
        return ""
    return (user.get("email") or "").strip().lower()


def github_email(user, emails):
    """Подтверждённая почта GitHub: сначала основная, потом любая подтверждённая. Неподтверждённые не берём:
    иначе чужую почту можно приписать себе и войти в чужой аккаунт."""
    good = [x for x in (emails or []) if isinstance(x, dict) and x.get("verified") is True and x.get("email")]
    good.sort(key=lambda x: not x.get("primary"))
    if good:
        return good[0]["email"].strip().lower()
    return ""


def google_auth_url(redirect_uri, state=None):
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "select_account",
    }
    if state:
        params["state"] = state
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def github_auth_url(redirect_uri, state=None):
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GITHUB_SCOPE,
        "state": state or secrets.token_urlsafe(16),
    }
    return "https://github.com/login/oauth/authorize?" + urllib.parse.urlencode(params)


def google_json_request(url, data=None, headers=None):
    payload = None if data is None else urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST" if data is not None else "GET")  # noqa: S310
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8") or "{}")


def public(u):
    return {"name": u["name"], "email": u["email"]}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "PyFactorSite"
    sys_version = ""

    # ---------- вспомогательное
    def log_message(self, fmt, *a):
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % a))

    def ip(self):
        return client_ip(self.headers.get("X-Forwarded-For", ""), self.client_address[0], TRUST_PROXY)

    def base_url(self):
        if SITE_URL:
            return SITE_URL
        host = self.headers.get("Host", "")
        if not re.match(r"^[A-Za-z0-9.\-]+(:\d+)?$|^\[[0-9a-fA-F:]+\](:\d+)?$", host):
            host = "%s:%d" % (HOST, PORT)
        proto = self.headers.get("X-Forwarded-Proto", "") if TRUST_PROXY else ""
        return "%s://%s" % ("https" if (SECURE or proto == "https") else "http", host)

    def send_raw(self, status, body, ctype, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in HEADERS.items():
            if k not in (extra or {}):
                self.send_header(k, v)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, status=200, extra=None):
        self.send_raw(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", extra)

    def body(self):
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise SiteError("Нужен JSON", 415)
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise SiteError("Неверный запрос", 400)
        if n > 16384:
            raise SiteError("Слишком большой запрос", 413)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise SiteError("Неверный JSON", 400)
        if not isinstance(data, dict):
            raise SiteError("Неверный JSON", 400)
        return data

    def cookie_sid(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "sid":
                return v
        return ""

    def session_user(self):
        return ST.user_by_session(self.cookie_sid())

    def need_user(self):
        u = self.session_user()
        if not u:
            raise SiteError("Нужно войти в аккаунт", 401)
        return u

    def same_origin(self):
        """Защита от CSRF: запрос из браузера должен идти с нашего же сайта."""
        origin = self.headers.get("Origin")
        if origin and origin.rstrip("/") != self.base_url():
            raise SiteError("Запрос с чужого сайта отклонён", 403)

    def bearer(self):
        a = self.headers.get("Authorization", "")
        return a[7:].strip() if a.startswith("Bearer ") else ""

    # ---------- маршруты
    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_HEAD(self):
        self.route("HEAD")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, HEAD, OPTIONS")
        self.end_headers()

    def route(self, method):
        path = self.path.split("?", 1)[0]
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        try:
            if method in ("GET", "HEAD") and path == "/":
                body, csp = page()
                if method == "HEAD":
                    self.send_raw(200, b"", "text/html; charset=utf-8", {"Content-Security-Policy": csp, "Content-Length": str(len(body))})
                    return
                return self.send_raw(200, body, "text/html; charset=utf-8", {"Content-Security-Policy": csp})
            fn = {("GET", "/api/session"): self.api_session, ("POST", "/api/register"): self.api_register,
                  ("POST", "/api/login"): self.api_login, ("POST", "/api/logout"): self.api_logout,
                  ("POST", "/api/download"): self.api_download, ("GET", "/api/devices"): self.api_devices,
                  ("POST", "/api/devices/revoke"): self.api_revoke, ("POST", "/api/device/claim"): self.api_claim,
                  ("GET", "/api/device/me"): self.api_device_me, ("POST", "/api/device/logout"): self.api_device_logout,
                  ("GET", "/auth/google"): self.google_login, ("GET", "/oauth/google/callback"): self.google_callback,
                  ("GET", "/auth/github"): self.github_login, ("GET", "/oauth/github/callback"): self.github_callback,
                  ("GET", "/healthz"): lambda: self.send_json({"ok": True}),
                  ("HEAD", "/api/session"): self.api_session, ("HEAD", "/api/devices"): self.api_devices,
                  ("HEAD", "/healthz"): lambda: self.send_json({"ok": True})}.get((method, path))
            if not fn:
                raise SiteError("Не найдено", 404)
            fn()
        except SiteError as ex:
            self.send_json({"error": str(ex)}, ex.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as ex:                                  # не показываем внутренности пользователю
            sys.stderr.write("ОШИБКА %s %s: %r\n" % (method, path, ex))
            self.send_json({"error": "Ошибка сервера. Попробуй ещё раз"}, 500)

    def set_cookie(self, sid, max_age):
        return {"Set-Cookie": "sid=%s; HttpOnly; SameSite=Lax; Path=/; Max-Age=%d%s" % (sid, max_age, "; Secure" if SECURE else "")}

    # ---------- сайт
    def google_login(self):
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise SiteError("Google OAuth не настроен: задайте GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET", 500)
        redirect_uri = GOOGLE_REDIRECT_URI or (self.base_url() + "/oauth/google/callback")
        state = secrets.token_urlsafe(24)
        self.send_response(302)
        self.send_header("Set-Cookie", oauth_cookie("google", state))
        self.send_header("Location", google_auth_url(redirect_uri, state))
        self.end_headers()

    def google_callback(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = (q.get("code") or [None])[0]
        if not code:
            raise SiteError("Google не вернул code", 400)
        if not state_ok(get_cookie(self.headers, "oauth_google"), (q.get("state") or [None])[0]):
            raise SiteError("Вход через Google не подтверждён (state). Начни вход заново", 400)
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise SiteError("Google OAuth не настроен: задайте GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET", 500)
        redirect_uri = GOOGLE_REDIRECT_URI or (self.base_url() + "/oauth/google/callback")
        token = google_json_request("https://oauth2.googleapis.com/token", {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        if "access_token" not in token:
            raise SiteError(token.get("error_description") or token.get("error") or "Google не дал access_token", 400)
        user = google_json_request("https://openidconnect.googleapis.com/v1/userinfo", headers={
            "Authorization": "Bearer " + token["access_token"],
            "Accept": "application/json",
        })
        email = google_email(user)
        if not email:
            raise SiteError("Google не вернул подтверждённый email", 400)
        name = (user.get("name") or email.split("@")[0] or "Google user").strip()[:40]
        sid = ST.new_session(ST.oauth_user(email, name))
        self.send_response(302)
        self.send_header("Set-Cookie", oauth_cookie("google" if "google" in self.path else "github", "", 0))
        self.send_header("Location", self.base_url())
        self.send_header("Set-Cookie", "sid=%s; HttpOnly; SameSite=Lax; Path=/; Max-Age=%d%s" % (sid, 30 * 86400, "; Secure" if SECURE else ""))
        self.end_headers()

    def github_login(self):
        if not GITHUB_CLIENT_ID:
            raise SiteError("GitHub OAuth не настроен: задайте GITHUB_CLIENT_ID и GITHUB_CLIENT_SECRET", 500)
        redirect_uri = GITHUB_REDIRECT_URI or (self.base_url() + "/oauth/github/callback")
        state = secrets.token_urlsafe(24)
        self.send_response(302)
        self.send_header("Set-Cookie", oauth_cookie("github", state))
        self.send_header("Location", github_auth_url(redirect_uri, state))
        self.end_headers()

    def github_callback(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = (q.get("code") or [None])[0]
        state = (q.get("state") or [None])[0]
        if not code:
            raise SiteError("GitHub не вернул code", 400)
        if not state_ok(get_cookie(self.headers, "oauth_github"), state):
            raise SiteError("Вход через GitHub не подтверждён (state). Начни вход заново", 400)
        if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
            raise SiteError("GitHub OAuth не настроен: задайте GITHUB_CLIENT_ID и GITHUB_CLIENT_SECRET", 500)
        redirect_uri = GITHUB_REDIRECT_URI or (self.base_url() + "/oauth/github/callback")
        token = google_json_request("https://github.com/login/oauth/access_token", {
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
        }, {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        access_token = token.get("access_token")
        if not access_token:
            raise SiteError(token.get("error_description") or token.get("error") or "GitHub не дал access_token", 400)
        user = google_json_request("https://api.github.com/user", headers={
            "Authorization": "Bearer " + access_token,
            "Accept": "application/json",
            "User-Agent": "PyFactorSite",
        })
        listing = google_json_request("https://api.github.com/user/emails", headers={
            "Authorization": "Bearer " + access_token,
            "Accept": "application/json",
            "User-Agent": "PyFactorSite",
        })
        email = github_email(user, listing if isinstance(listing, list) else [])
        if not email:
            raise SiteError("GitHub не вернул подтверждённый email", 400)
        name = (user.get("name") or user.get("login") or email.split("@")[0] or "GitHub user").strip()[:40]
        sid = ST.new_session(ST.oauth_user(email, name))
        self.send_response(302)
        self.send_header("Set-Cookie", oauth_cookie("google" if "google" in self.path else "github", "", 0))
        self.send_header("Location", self.base_url())
        self.send_header("Set-Cookie", "sid=%s; HttpOnly; SameSite=Lax; Path=/; Max-Age=%d%s" % (sid, 30 * 86400, "; Secure" if SECURE else ""))
        self.end_headers()

    def api_session(self):
        u = self.session_user()
        self.send_json({"user": public(u) if u else None, "verify_email": bool(RESEND_KEY)})

    def api_register(self):
        self.same_origin()
        b = self.body()
        if not LIM.hit("reg:" + self.ip(), 15, 3600):
            raise SiteError("Слишком много попыток с этого адреса. Попробуй позже", 429)
        password = str(b.get("password", ""))
        email, name = ST.validate_signup(str(b.get("email", "")), password, str(b.get("name", "")))
        if RESEND_KEY:                                           # подтверждаем почту кодом из письма
            pending_cleanup()
            code = str(b.get("code", "")).strip()
            p = PENDING.get(email)
            if not code:
                if p and time.time() - p["sent"] < 30:
                    raise SiteError("Подожди %d сек. перед повторной отправкой" % (30 - (time.time() - p["sent"]) + 1), 429)
                c = "%06d" % secrets.randbelow(10 ** 6)
                PENDING[email] = {"code": c, "exp": time.time() + 600, "tries": 0, "sent": time.time()}
                try:
                    mailer.send_code(RESEND_KEY, email, c, RESEND_FROM or mailer.DEFAULT_FROM)
                except mailer.MailError as ex:
                    PENDING.pop(email, None)
                    sys.stderr.write("Resend: %s\n" % ex)
                    raise SiteError("Не удалось отправить письмо с кодом. Проверь email или попробуй позже", 502)
                return self.send_json({"need_code": True})
            if not p or p["exp"] < time.time():
                PENDING.pop(email, None)
                raise SiteError("Код устарел. Запроси новый")
            p["tries"] += 1
            if not hmac.compare_digest(p["code"], code):
                if p["tries"] >= 5:
                    PENDING.pop(email, None)
                    raise SiteError("Слишком много неверных попыток. Запроси код заново")
                raise SiteError("Неверный код. Осталось попыток: %d" % (5 - p["tries"]))
            PENDING.pop(email, None)
        uid = ST.create_user(email, name, password, verified=bool(RESEND_KEY))      # почта подтверждена кодом, только если письма включены
        sid = ST.new_session(uid)
        self.send_json({"user": {"name": name, "email": email}}, 200, self.set_cookie(sid, 30 * 86400))

    def api_login(self):
        self.same_origin()
        b = self.body()
        email, ip = str(b.get("email", "")).strip().lower(), self.ip()
        if LIM.blocked("lf:" + ip, 30, 300) or LIM.blocked("lf:" + email, 5, 300):
            raise SiteError("Слишком много неверных попыток. Подожди несколько минут", 429)
        u = ST.verify_login(email, str(b.get("password", "")))
        if not u:
            LIM.add("lf:" + ip, 300)
            LIM.add("lf:" + email, 300)
            raise SiteError("Неверный email или пароль", 401)
        LIM.reset("lf:" + email)
        sid = ST.new_session(u["id"])
        self.send_json({"user": public(u)}, 200, self.set_cookie(sid, 30 * 86400))

    def api_logout(self):
        self.same_origin()
        self.body()
        ST.end_session(self.cookie_sid())
        self.send_json({"ok": True}, 200, self.set_cookie("", 0))

    def api_download(self):
        self.same_origin()
        self.body()
        u = self.need_user()
        if not LIM.hit("dl:%d" % u["id"], 10, 3600):
            raise SiteError("Слишком много скачиваний за час. Попробуй позже", 429)
        data = packager.build_windows_bundle(ROOT, ST.new_claim(u["id"]), self.base_url())
        self.send_raw(200, data, "application/octet-stream", {"Content-Disposition": 'attachment; filename="PyFactor.exe"'})

    def api_devices(self):
        self.send_json({"devices": ST.devices(self.need_user()["id"])})

    def api_revoke(self):
        self.same_origin()
        b = self.body()
        u = self.need_user()
        try:
            ST.revoke_device(u["id"], int(b.get("id")))
        except (TypeError, ValueError):
            raise SiteError("Неверный запрос")
        self.send_json({"devices": ST.devices(u["id"])})

    # ---------- приложение (IDE)
    def api_claim(self):
        b = self.body()
        if not LIM.hit("cl:" + self.ip(), 20, 300):
            raise SiteError("Слишком много попыток. Подожди несколько минут", 429)
        token, u = ST.redeem_claim(str(b.get("code", "")), str(b.get("label", "")))
        self.send_json({"token": token, **public(u)})

    def api_device_me(self):
        u = ST.user_by_token(self.bearer())
        if not u:
            raise SiteError("Устройство отключено. Войди заново", 401)
        self.send_json(public(u))

    def api_device_logout(self):
        self.body()
        ST.revoke_token(self.bearer())
        self.send_json({"ok": True})


def main():
    global ST
    ST = Store(os.path.join(DATA, "site.db"))
    try:
        srv = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as ex:
        raise SystemExit("Не удалось занять %s:%d (%s).\nПорт уже занят — например, Go-сервером-выключателем или вторым запуском сайта.\n"
                         "Выбери другой порт:  set SITE_PORT=8082  (Windows)  /  SITE_PORT=8082 python site/server.py" % (HOST, PORT, ex))
    print("PyFactor сайт: http://%s:%d" % (HOST, PORT))
    if not RESEND_KEY:
        print("! RESEND_API_KEY не задан: регистрация БЕЗ подтверждения почты кодом.")
    elif not RESEND_FROM:
        print("! RESEND_FROM не задан: тестовый адрес Resend шлёт письма только владельцу аккаунта Resend.")
    if not SITE_URL and HOST not in ("127.0.0.1", "localhost"):
        print("! Задай SITE_URL (https://твой-домен), иначе адрес в скачанном архиве берётся из заголовка Host.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено")


if __name__ == "__main__":
    main()
