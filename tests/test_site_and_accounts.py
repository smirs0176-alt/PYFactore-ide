import hashlib
import importlib.util
import os
import sqlite3
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "site"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


store = _load("pf_site_store", "site/store.py")
site_server = _load("pf_site_server", "site/server.py")
from pyfactor.core.account import local  # noqa: E402

# ---------- хранилище сайта

def test_new_user_uses_current_iterations_and_logs_in(tmp_path):
    st = store.Store(str(tmp_path / "d" / "site.db"))
    uid = st.create_user("a@b.co", "A", "correct horse")
    row = st.user_by_email("a@b.co")
    assert row["id"] == uid and row["iter"] == store.ITER == 600_000
    assert st.verify_login("a@b.co", "correct horse")
    assert st.verify_login("a@b.co", "wrong") is None
    assert st.verify_login("nobody@b.co", "x") is None


def _legacy_db(path, password):
    """База в старом формате: без колонки iter, хеш на 240 000 кругов."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    salt = b"s" * 16
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000).hex()
    db = sqlite3.connect(path)
    db.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
        salt TEXT NOT NULL, hash TEXT NOT NULL, created INTEGER NOT NULL);""")
    db.execute("INSERT INTO users(email,name,salt,hash,created) VALUES(?,?,?,?,?)", ("old@b.co", "Old", salt.hex(), h, 1))
    db.commit()
    db.close()


def test_legacy_account_keeps_working_and_is_upgraded(tmp_path):
    path = str(tmp_path / "d" / "site.db")
    _legacy_db(path, "old password 1")
    st = store.Store(path)                                          # миграция колонки
    assert st.user_by_email("old@b.co")["iter"] == 240_000
    assert st.verify_login("old@b.co", "wrong") is None
    assert st.user_by_email("old@b.co")["iter"] == 240_000          # неверный пароль хеш не трогает
    assert st.verify_login("old@b.co", "old password 1")["email"] == "old@b.co"
    row = st.user_by_email("old@b.co")
    assert row["iter"] == 600_000                                   # хеш обновлён
    assert st.verify_login("old@b.co", "old password 1")            # и снова входит


def test_session_and_device_token_flow(tmp_path):
    st = store.Store(str(tmp_path / "d" / "site.db"))
    uid = st.create_user("a@b.co", "A", "correct horse")
    sid = st.new_session(uid)
    assert st.user_by_session(sid)["id"] == uid
    st.end_session(sid)
    assert st.user_by_session(sid) is None
    code = st.new_claim(uid)
    token, _ = st.redeem_claim(code, "pc")
    assert st.user_by_token(token)["id"] == uid
    with pytest.raises(store.SiteError):                            # код одноразовый
        st.redeem_claim(code, "pc2")
    st.revoke_token(token)
    assert st.user_by_token(token) is None


def test_device_revoke_only_own_devices(tmp_path):
    st = store.Store(str(tmp_path / "d" / "site.db"))
    u1, u2 = st.create_user("a@b.co", "A", "password1"), st.create_user("c@d.co", "C", "password2")
    t1, _ = st.redeem_claim(st.new_claim(u1), "pc")
    dev = st.devices(u1)[0]["id"]
    st.revoke_device(u2, dev)                                       # чужой пользователь
    assert st.user_by_token(t1) is not None
    st.revoke_device(u1, dev)
    assert st.user_by_token(t1) is None


def test_limiter_blocks_and_resets():
    lim = store.Limiter()
    assert all(lim.hit("k", 3, 60) for _ in range(3))
    assert lim.hit("k", 3, 60) is False
    lim.reset("k")
    assert lim.hit("k", 3, 60) is True


# ---------- адрес клиента и PENDING

def test_client_ip_ignores_xff_without_trusted_proxy():
    assert site_server.client_ip("6.6.6.6", "10.0.0.1", False) == "10.0.0.1"


def test_client_ip_takes_last_entry_behind_proxy():
    assert site_server.client_ip("6.6.6.6, 9.9.9.9", "10.0.0.1", True) == "9.9.9.9"
    assert site_server.client_ip("", "10.0.0.1", True) == "10.0.0.1"
    assert site_server.client_ip("not-an-ip", "10.0.0.1", True) == "10.0.0.1"


def test_pending_cleanup_drops_expired_and_caps_size():
    site_server.PENDING.clear()
    now = time.time()
    site_server.PENDING["old@x.co"] = {"exp": now - 1, "sent": now - 700}
    site_server.PENDING["new@x.co"] = {"exp": now + 500, "sent": now}
    site_server.pending_cleanup(now)
    assert list(site_server.PENDING) == ["new@x.co"]
    for i in range(site_server.PENDING_MAX + 10):
        site_server.PENDING["u%d" % i] = {"exp": now + 500, "sent": now + i}
    site_server.pending_cleanup(now)
    assert len(site_server.PENDING) == site_server.PENDING_MAX
    site_server.PENDING.clear()


def test_github_auth_url_is_built_for_web_oauth():
    auth = site_server.github_auth_url("https://example.com/oauth/github/callback")
    assert "https://github.com/login/oauth/authorize" in auth
    assert "client_id=" in auth
    assert "redirect_uri=https%3A%2F%2Fexample.com%2Foauth%2Fgithub%2Fcallback" in auth


# ---------- локальные аккаунты IDE

def test_local_register_login_and_min_password(tmp_path):
    f = str(tmp_path / "users.json")
    with pytest.raises(local.AuthError):
        local.register(f, "a@b.co", "short", "A")
    local.register(f, "A@B.co", "long enough pw", "A")
    assert local.login(f, "a@b.co", "long enough pw")["email"] == "a@b.co"
    with pytest.raises(local.AuthError):
        local.login(f, "a@b.co", "bad password!")


def test_local_legacy_hash_upgraded_on_login(tmp_path):
    f = str(tmp_path / "users.json")
    salt = b"t" * 16
    h = hashlib.pbkdf2_hmac("sha256", b"oldpass", salt, 240_000).hex()
    local._save(f, {"x@y.co": {"name": "X", "email": "x@y.co", "salt": salt.hex(), "hash": h, "fails": 0, "locked_until": 0}})
    assert local.login(f, "x@y.co", "oldpass")["name"] == "X"
    u = local._load(f)["x@y.co"]
    assert u["iter"] == local.ITER and u["hash"] != h
    assert local.login(f, "x@y.co", "oldpass")


def test_local_lockout_after_five_failures(tmp_path):
    f = str(tmp_path / "users.json")
    local.register(f, "a@b.co", "long enough pw", "A")
    for _ in range(5):
        with pytest.raises(local.AuthError):
            local.login(f, "a@b.co", "wrong password")
    with pytest.raises(local.AuthError, match="Слишком много"):
        local.login(f, "a@b.co", "long enough pw")                  # даже верный пароль заблокирован


# ---------- OAuth сайта: state и подтверждённая почта

def test_state_ok():
    assert site_server.state_ok("abc", "abc")
    assert not site_server.state_ok("abc", "abd")
    assert not site_server.state_ok("", "")
    assert not site_server.state_ok("abc", None)


def test_google_email_requires_verified():
    assert site_server.google_email({"email": "A@b.co", "email_verified": True}) == "a@b.co"
    assert site_server.google_email({"email": "a@b.co", "email_verified": False}) == ""
    assert site_server.google_email({"email": "a@b.co"}) == ""


def test_github_email_ignores_unverified_and_prefers_primary():
    emails = [{"email": "victim@x.co", "verified": False, "primary": False},        # чужая почта, добавленная без подтверждения
              {"email": "mine2@x.co", "verified": True, "primary": False},
              {"email": "Mine@x.co", "verified": True, "primary": True}]
    assert site_server.github_email({}, emails) == "mine@x.co"
    assert site_server.github_email({}, emails[:1]) == ""
    assert site_server.github_email({"email": "victim@x.co"}, []) == ""            # публичное поле профиля без проверки не берём


def test_oauth_login_sets_state_cookie_and_callback_rejects_bad_state(tmp_path, monkeypatch):
    import http.client
    import threading
    monkeypatch.setattr(site_server, "ST", store.Store(str(tmp_path / "d" / "site.db")))
    monkeypatch.setattr(site_server, "GITHUB_CLIENT_ID", "cid")
    monkeypatch.setattr(site_server, "GITHUB_CLIENT_SECRET", "sec")
    monkeypatch.setattr(site_server, "google_json_request", lambda *a, **k: pytest.fail("наружу ходить нельзя до проверки state"))
    srv = site_server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), site_server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
        c.request("GET", "/auth/github")
        r = c.getresponse()
        r.read()
        cookie = r.getheader("Set-Cookie")
        assert r.status == 302 and cookie.startswith("oauth_github=") and "HttpOnly" in cookie
        state = cookie.split("=", 1)[1].split(";")[0]
        assert "state=" + state in r.getheader("Location")
        for hdrs, qs in (({}, "code=x&state=" + state),                           # нет куки
                         ({"Cookie": "oauth_github=" + state}, "code=x&state=other"),   # state не совпал
                         ({"Cookie": "oauth_github=" + state}, "code=x")):          # state не прислан
            c2 = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
            c2.request("GET", "/oauth/github/callback?" + qs, headers=hdrs)
            r2 = c2.getresponse()
            assert r2.status == 400, (hdrs, qs, r2.status, r2.read())
    finally:
        srv.shutdown()


def test_norm_url_schemes_and_local_hosts():
    pytest.importorskip("tkinter")                      # норма адреса живёт в модуле с интерфейсом
    from pyfactor.features.account.server import norm_url
    assert norm_url("localhost:8080/") == "http://localhost:8080"
    assert norm_url("172.20.1.5:80") == "http://172.20.1.5:80"
    assert norm_url("example.com") == "https://example.com"
    assert norm_url("172.200.1.5") == "https://172.200.1.5"          # не локальная сеть
    assert norm_url("file:///etc/passwd") == ""
    assert norm_url("ftp://x") == ""
    assert norm_url("HTTPS://X.co/") == "HTTPS://X.co"


def test_corrupt_users_file_is_not_overwritten(tmp_path):
    f = tmp_path / "users.json"
    f.write_text('{"a@b.co": {"name": "A", "hash": ', encoding="utf-8")        # оборванная запись
    with pytest.raises(local.AuthError):
        local.register(str(f), "new@b.co", "long enough pw", "N")
    with pytest.raises(local.AuthError):
        local.login(str(f), "a@b.co", "whatever")
    assert f.read_text(encoding="utf-8").startswith('{"a@b.co"')               # исходный файл цел
    assert (tmp_path / "users.json.corrupt").exists()                          # и есть копия для восстановления


def test_users_file_is_private_and_roundtrips(tmp_path):
    f = tmp_path / "sub" / "users.json"
    local.register(str(f), "a@b.co", "long enough pw", "A")
    assert local.login(str(f), "a@b.co", "long enough pw")["name"] == "A"
    if os.name == "posix":
        assert (f.stat().st_mode & 0o077) == 0
    assert not [p for p in f.parent.iterdir() if p.name.endswith(".tmp")]      # временные файлы не остаются
