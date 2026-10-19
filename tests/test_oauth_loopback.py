"""Google-вход: локальный приёмник принимает только ответ с правильным state (без браузера и без сети)."""
import threading
import urllib.error
import urllib.parse
import urllib.request

from pyfactor.core.account import oauth


def _run_login(monkeypatch, browser, userinfo=None):
    """Запускает google_login; browser(auth_url) играет роль браузера. Сетевые вызовы подменены."""
    posts = []
    monkeypatch.setattr(oauth, "_post", lambda url, data: posts.append(data) or {"access_token": "AT"})
    monkeypatch.setattr(oauth, "_get", lambda url, tok: userinfo or {"name": "N", "email": "n@x.io", "email_verified": True})
    box = {}

    def opener(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        t = threading.Thread(target=browser, args=(q,), daemon=True)
        box["t"] = t
        t.start()

    try:
        box["res"] = oauth.google_login("cid", "sec", threading.Event(), open_url=opener, timeout=8)
    except RuntimeError as e:
        box["err"] = str(e)
    box["t"].join(3)
    box["posts"] = posts
    return box


def _hit(q, extra):
    base = q["redirect_uri"][0]
    try:
        with urllib.request.urlopen(base + "/?" + urllib.parse.urlencode(extra), timeout=3) as r:  # noqa: S310
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_forged_requests_are_rejected_and_real_one_still_works(monkeypatch):
    codes = []

    def browser(q):
        codes.append(_hit(q, {"error": "access_denied", "state": "wrong"}))      # чужой запрос не срывает вход
        codes.append(_hit(q, {"code": "EVIL", "state": "wrong"}))                # и не подсовывает code
        codes.append(_hit(q, {"code": "GOOD", "state": q["state"][0]}))

    box = _run_login(monkeypatch, browser)
    assert codes == [400, 400, 200]
    assert box["res"]["email"] == "n@x.io"
    assert box["posts"][0]["code"] == "GOOD"
    assert box["posts"][0]["code_verifier"]


def test_unverified_google_email_is_dropped(monkeypatch):
    box = _run_login(monkeypatch, lambda q: _hit(q, {"code": "C", "state": q["state"][0]}),
                     userinfo={"name": "N", "email": "evil@x.io", "email_verified": False})
    assert box["res"]["email"] == ""


def test_user_denied_is_reported(monkeypatch):
    box = _run_login(monkeypatch, lambda q: _hit(q, {"error": "access_denied", "state": q["state"][0]}))
    assert "access_denied" in box["err"]
