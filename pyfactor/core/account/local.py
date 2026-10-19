"""Локальные аккаунты: регистрация и вход по email и паролю, без Google и ключей.
Пароль нигде не хранится: только соль и хеш PBKDF2-SHA256 (600 000 кругов; у старых записей 240 000, при входе обновляются). Файл users.json лежит рядом с настройками."""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import time

from pyfactor.core.utils import save_json

ITER = 600_000
LEGACY_ITER = 240_000     # у аккаунтов без поля iter было столько кругов
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
MIN_PASS = 8


class AuthError(Exception):
    pass


def _load(path):
    """Читает users.json. Нет файла — пусто. Файл есть, но повреждён — кладём копию рядом (.corrupt) и бросаем AuthError:
    раньше возвращалось {}, и следующая регистрация или вход затирали бы всех пользователей."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        raise ValueError("ожидался объект")
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        try:
            shutil.copy2(path, path + ".corrupt")
        except OSError:
            pass
        raise AuthError("Файл аккаунтов повреждён. Копия: %s.corrupt — восстанови её или удали файл" % os.path.basename(path))


def _save(path, data):
    # атомарно (уникальный временный файл + fsync), права 0600
    if not save_json(path, data, private=True):
        raise AuthError("Не удалось сохранить файл аккаунтов")


def _hash(password, salt, iters=ITER):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters).hex()


def validate(path, email, password, name=""):
    """Проверяет данные регистрации, ничего не создаёт. Возвращает (email, имя)."""
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("Введи настоящий email, например name@gmail.com")
    if len(password) < MIN_PASS:
        raise AuthError("Пароль слишком короткий: минимум %d символов" % MIN_PASS)
    name = name.strip() or email.split("@")[0]
    if len(name) > 40:
        raise AuthError("Имя слишком длинное (до 40 символов)")
    if email in _load(path):
        raise AuthError("Аккаунт с таким email уже есть: нажми «Войти»")
    return email, name


def register(path, email, password, name=""):
    """Регистрация: email — логин. Имя необязательно (по умолчанию часть email до @)."""
    email, name = validate(path, email, password, name)
    users = _load(path)
    salt = secrets.token_bytes(16)
    users[email] = {"name": name, "email": email, "salt": salt.hex(), "hash": _hash(password, salt), "iter": ITER,
                    "created": int(time.time()), "fails": 0, "locked_until": 0}
    _save(path, users)
    return {"provider": "PyFactor", "name": name, "email": email}


# --- коды подтверждения email (живут только в памяти программы, 10 минут, 5 попыток)
_PENDING = {}
CODE_TTL, CODE_TRIES, RESEND_WAIT = 600, 5, 30


def make_code(email):
    email = email.strip().lower()
    old = _PENDING.get(email)
    if old and time.time() - old["sent"] < RESEND_WAIT:
        raise AuthError("Подожди %d сек. перед повторной отправкой" % (RESEND_WAIT - (time.time() - old["sent"]) + 1))
    code = "%06d" % secrets.randbelow(10 ** 6)
    _PENDING[email] = {"code": code, "exp": time.time() + CODE_TTL, "tries": 0, "sent": time.time()}
    return code


def drop_code(email):
    _PENDING.pop(email.strip().lower(), None)


def check_code(email, code):
    email = email.strip().lower()
    p = _PENDING.get(email)
    if not p or p["exp"] < time.time():
        _PENDING.pop(email, None)
        raise AuthError("Код устарел. Отправь новый")
    p["tries"] += 1
    if not hmac.compare_digest(p["code"], code.strip()):
        if p["tries"] >= CODE_TRIES:
            _PENDING.pop(email, None)
            raise AuthError("Слишком много неверных попыток. Отправь код заново")
        raise AuthError("Неверный код. Осталось попыток: %d" % (CODE_TRIES - p["tries"]))
    _PENDING.pop(email, None)
    return True


def login(path, email, password):
    users = _load(path)
    key = email.strip().lower()
    u = users.get(key) or next((v for v in users.values() if v.get("name", "").lower() == key), None)
    if u and u.get("locked_until", 0) > time.time():
        raise AuthError("Слишком много неверных попыток. Подожди %d сек." % (u["locked_until"] - time.time() + 1))
    # хеш считаем всегда, чтобы нельзя было узнать по времени, существует ли логин
    salt = bytes.fromhex(u["salt"]) if u else b"\0" * 16
    iters = u.get("iter", LEGACY_ITER) if u else ITER
    ok = hmac.compare_digest(_hash(password, salt, iters), u["hash"] if u else "0" * 64)
    if not (u and ok):
        if u:
            u["fails"] = u.get("fails", 0) + 1
            if u["fails"] >= 5:
                u["fails"], u["locked_until"] = 0, time.time() + 30
            _save(path, users)
        raise AuthError("Неверный email или пароль")
    u["fails"], u["locked_until"] = 0, 0
    if iters < ITER:                                  # старый хеш: пересчитываем с новым числом кругов
        new_salt = secrets.token_bytes(16)
        u["salt"], u["hash"], u["iter"] = new_salt.hex(), _hash(password, new_salt), ITER
    _save(path, users)
    return {"provider": "PyFactor", "name": u["name"], "email": u.get("email", "")}
