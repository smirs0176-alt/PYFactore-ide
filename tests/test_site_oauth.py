"""Сайт: вход через Google/GitHub не должен оставлять доступ тому, кто заранее зарегистрировал чужую почту; в коде нет секретов."""
import importlib.util
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "site"))
spec = importlib.util.spec_from_file_location("site_store_oauth", os.path.join(ROOT, "site", "store.py"))
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


def _st(tmp_path):
    return store.Store(str(tmp_path / "d" / "site.db"))


def test_oauth_takes_over_unverified_preregistered_account(tmp_path):
    st = _st(tmp_path)
    attacker_uid = st.create_user("victim@x.io", "Mallory", "attacker-password")          # без подтверждения почты
    attacker_sid = st.new_session(attacker_uid)
    uid = st.oauth_user("Victim@X.io", "Victim")                                          # настоящий владелец вошёл через Google
    assert uid == attacker_uid
    assert st.user_by_session(attacker_sid) is None                                       # старая сессия закрыта
    assert st.verify_login("victim@x.io", "attacker-password") is None                    # пароль злоумышленника больше не подходит
    assert st.user_by_email("victim@x.io")["verified"] == 1


def test_verified_account_keeps_its_password_after_oauth(tmp_path):
    st = _st(tmp_path)
    uid = st.create_user("a@x.io", "A", "my-real-password", verified=True)               # почта подтверждена кодом из письма
    sid = st.new_session(uid)
    assert st.oauth_user("a@x.io", "A") == uid
    assert st.user_by_session(sid) is not None
    assert st.verify_login("a@x.io", "my-real-password")


def test_oauth_creates_new_verified_user_and_is_idempotent(tmp_path):
    st = _st(tmp_path)
    uid = st.oauth_user("new@x.io", "New")
    assert st.user_by_email("new@x.io")["verified"] == 1
    assert st.oauth_user("new@x.io", "New") == uid


def test_old_database_gets_verified_column(tmp_path):
    p = tmp_path / "d" / "site.db"
    p.parent.mkdir()
    db = sqlite3.connect(str(p))
    db.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, salt TEXT NOT NULL, "
               "hash TEXT NOT NULL, created INTEGER NOT NULL, iter INTEGER NOT NULL DEFAULT 240000)")
    db.execute("INSERT INTO users VALUES(1,'old@x.io','Old','00','00',1,240000)")
    db.commit()
    db.close()
    st = store.Store(str(p))
    assert st.user_by_email("old@x.io")["verified"] == 0         # про старые аккаунты неизвестно — считаем неподтверждёнными


def test_no_secrets_or_dead_domain_defaults_in_site_code():
    src = open(os.path.join(ROOT, "site", "server.py"), encoding="utf-8").read()
    assert not re.search(r"GOCSPX-[A-Za-z0-9_-]{6,}", src)
    assert "xip.io" not in src
