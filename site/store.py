"""Хранилище сайта PyFactor: SQLite. Пароли — PBKDF2-SHA256 с солью, сессии и коды хранятся только в виде хешей."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time

ITER = 600_000                      # круги PBKDF2 для новых и обновлённых паролей
LEGACY_ITER = 240_000               # столько кругов было у старых аккаунтов (колонка iter заполняется по умолчанию)
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
MIN_PASS, MAX_PASS = 8, 200
SESSION_TTL, CLAIM_TTL = 30 * 86400, 7 * 86400
MAX_DEVICES, MAX_OPEN_CLAIMS = 10, 20

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  salt TEXT NOT NULL, hash TEXT NOT NULL, created INTEGER NOT NULL, iter INTEGER NOT NULL DEFAULT 240000);
CREATE TABLE IF NOT EXISTS sessions(sid_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS claims(code_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS devices(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT UNIQUE NOT NULL, label TEXT NOT NULL, created INTEGER NOT NULL, last_seen INTEGER NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0);
"""


class SiteError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def _h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _pw(password, salt, iters=None):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters or ITER).hex()


def hash_password(password):
    salt = secrets.token_bytes(16)
    return salt.hex(), _pw(password, salt)


class Limiter:
    """Простой ограничитель попыток в памяти (по ключу: IP, email, пользователь)."""
    def __init__(self):
        self.lock, self.hits = threading.Lock(), {}

    def _prune(self, key, window, now):
        lst = [t for t in self.hits.get(key, []) if now - t < window]
        self.hits[key] = lst
        return lst

    def blocked(self, key, limit, window):
        with self.lock:
            return len(self._prune(key, window, time.time())) >= limit

    def add(self, key, window=3600):
        with self.lock:
            now = time.time()
            self._prune(key, window, now).append(now)
            if len(self.hits) > 20000:
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < window}

    def hit(self, key, limit, window):
        """Записывает попытку; False, если лимит уже исчерпан."""
        if self.blocked(key, limit, window):
            return False
        self.add(key, window)
        return True

    def reset(self, key):
        with self.lock:
            self.hits.pop(key, None)


class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript(SCHEMA)
        cols = [r[1] for r in self.db.execute("PRAGMA table_info(users)")]
        if "iter" not in cols:                                   # база создана старой версией: добавляем колонку
            self.db.execute("ALTER TABLE users ADD COLUMN iter INTEGER NOT NULL DEFAULT %d" % LEGACY_ITER)
        if "verified" not in cols:                               # 1 — владение почтой подтверждено (кодом из письма или входом через Google/GitHub)
            self.db.execute("ALTER TABLE users ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    # ---------- аккаунты
    def validate_signup(self, email, password, name=""):
        email = email.strip().lower()
        if not EMAIL_RE.match(email) or len(email) > 120:
            raise SiteError("Введи настоящий email, например name@gmail.com")
        if len(password) < MIN_PASS:
            raise SiteError("Пароль слишком короткий: минимум %d символов" % MIN_PASS)
        if len(password) > MAX_PASS:
            raise SiteError("Пароль слишком длинный")
        name = name.strip() or email.split("@")[0]
        if len(name) > 40:
            raise SiteError("Имя слишком длинное (до 40 символов)")
        if self.user_by_email(email):
            raise SiteError("Аккаунт с таким email уже есть. Нажми «Войти»", 409)
        return email, name

    def user_by_email(self, email):
        with self.lock:
            return self.db.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()

    def create_user(self, email, name, password, verified=False):
        salt, h = hash_password(password)
        try:
            with self.lock:
                cur = self.db.execute("INSERT INTO users(email,name,salt,hash,created,iter,verified) VALUES(?,?,?,?,?,?,?)",
                                      (email, name, salt, h, int(time.time()), ITER, 1 if verified else 0))
                return cur.lastrowid
        except sqlite3.IntegrityError:
            raise SiteError("Аккаунт с таким email уже есть. Нажми «Войти»", 409)

    def oauth_user(self, email, name):
        """Вход через Google/GitHub по подтверждённой ими почте -> id пользователя.
        Нет аккаунта — создаём. Есть аккаунт, но почту при регистрации никто не подтверждал: мог зарегистрироваться посторонний
        на чужой адрес и знать пароль. Раз владелец только что доказал почту через провайдера, меняем пароль на случайный
        и закрываем все старые сессии и коды (войти можно через провайдера)."""
        email = email.strip().lower()
        with self.lock:
            u = self.user_by_email(email)
            if not u:
                return self.create_user(email, name, secrets.token_urlsafe(24), verified=True)
            if not u["verified"]:
                salt, h = hash_password(secrets.token_urlsafe(24))
                self.db.execute("UPDATE users SET salt=?, hash=?, iter=?, verified=1 WHERE id=?", (salt, h, ITER, u["id"]))
                self.db.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
                self.db.execute("DELETE FROM claims WHERE user_id=?", (u["id"],))
            return u["id"]

    def verify_login(self, email, password):
        """Проверяет пароль. Старый хеш (меньше кругов) после успешного входа тихо пересчитывается."""
        u = self.user_by_email(email)
        iters = (u["iter"] if u else ITER)
        # хеш считаем всегда: по времени ответа нельзя узнать, есть ли такой email
        salt = bytes.fromhex(u["salt"]) if u else b"\0" * 16
        ok = hmac.compare_digest(_pw(password[:MAX_PASS], salt, iters), u["hash"] if u else "0" * 64)
        if not (u and ok):
            return None
        if iters < ITER:
            new_salt, new_hash = hash_password(password[:MAX_PASS])
            with self.lock:
                self.db.execute("UPDATE users SET salt=?, hash=?, iter=? WHERE id=?", (new_salt, new_hash, ITER, u["id"]))
            u = self.user_by_email(email)
        return u

    # ---------- сессии сайта
    def new_session(self, uid):
        sid = secrets.token_urlsafe(32)
        with self.lock:
            self.db.execute("INSERT INTO sessions VALUES(?,?,?)", (_h(sid), uid, int(time.time()) + SESSION_TTL))
        return sid

    def user_by_session(self, sid):
        if not sid:
            return None
        with self.lock:
            return self.db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                                   "WHERE s.sid_hash=? AND s.expires>?", (_h(sid), int(time.time()))).fetchone()

    def end_session(self, sid):
        with self.lock:
            self.db.execute("DELETE FROM sessions WHERE sid_hash=?", (_h(sid or ""),))

    # ---------- коды подключения приложения (кладутся в скачанный архив)
    def new_claim(self, uid):
        now = int(time.time())
        with self.lock:
            self.db.execute("DELETE FROM claims WHERE expires<? OR used=1", (now,))
            self.db.execute("DELETE FROM sessions WHERE expires<?", (now,))
            n = self.db.execute("SELECT COUNT(*) FROM claims WHERE user_id=?", (uid,)).fetchone()[0]
            if n >= MAX_OPEN_CLAIMS:
                raise SiteError("Слишком много неиспользованных скачиваний. Запусти уже скачанное приложение", 429)
            code = "pfc_" + secrets.token_urlsafe(24)
            self.db.execute("INSERT INTO claims VALUES(?,?,?,0)", (_h(code), uid, now + CLAIM_TTL))
        return code

    def redeem_claim(self, code, label):
        """Меняет одноразовый код на долгий токен устройства. Код после этого больше не работает."""
        now = int(time.time())
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT user_id FROM claims WHERE code_hash=? AND used=0 AND expires>?",
                                      (_h(code), now)).fetchone()
                if not row:
                    self.db.execute("ROLLBACK")
                    raise SiteError("Код подключения недействителен или устарел. Скачай приложение на сайте заново", 401)
                uid = row[0]
                active = self.db.execute("SELECT COUNT(*) FROM devices WHERE user_id=? AND revoked=0", (uid,)).fetchone()[0]
                if active >= MAX_DEVICES:
                    self.db.execute("ROLLBACK")
                    raise SiteError("Слишком много подключённых устройств. Отключи лишние на сайте", 409)
                self.db.execute("UPDATE claims SET used=1 WHERE code_hash=?", (_h(code),))
                token = "pfd_" + secrets.token_urlsafe(32)
                self.db.execute("INSERT INTO devices(user_id,token_hash,label,created,last_seen) VALUES(?,?,?,?,?)",
                                (uid, _h(token), label[:60] or "Устройство", now, now))
                self.db.execute("COMMIT")
            except SiteError:
                raise
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            user = self.db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return token, user

    # ---------- устройства (приложения)
    def user_by_token(self, token):
        if not token or not token.startswith("pfd_"):
            return None
        with self.lock:
            row = self.db.execute("SELECT u.*, d.id AS dev_id FROM devices d JOIN users u ON u.id=d.user_id "
                                  "WHERE d.token_hash=? AND d.revoked=0", (_h(token),)).fetchone()
            if row:
                self.db.execute("UPDATE devices SET last_seen=? WHERE id=?", (int(time.time()), row["dev_id"]))
            return row

    def devices(self, uid):
        with self.lock:
            rows = self.db.execute("SELECT id,label,created,last_seen FROM devices WHERE user_id=? AND revoked=0 "
                                   "ORDER BY id DESC", (uid,)).fetchall()
        return [dict(r) for r in rows]

    def revoke_device(self, uid, dev_id):
        with self.lock:
            self.db.execute("UPDATE devices SET revoked=1 WHERE id=? AND user_id=?", (dev_id, uid))

    def revoke_token(self, token):
        with self.lock:
            self.db.execute("UPDATE devices SET revoked=1 WHERE token_hash=?", (_h(token or ""),))
