"""Хранение аккаунта: профиль лежит в account.json, а GitHub-токен (право repo) — в системном хранилище ключей.

Раньше токен лежал в account.json открытым текстом. Теперь он уходит в secure_store (Windows Credential Manager,
если установлен keyring; иначе файл secrets.json с правами 0600). Старые файлы переносятся при первом чтении.
Если токен не удалось сохранить в хранилище, он остаётся в account.json: лучше так, чем потерять."""
from pyfactor.core import secure_store
from pyfactor.core.utils import load_json, save_json

TOKEN_KEY = "github_token"  # noqa: S105  (имя ключа в хранилище, не пароль)


def load_account(path):
    acc = load_json(path, {})
    if not isinstance(acc, dict):
        return {}
    legacy = acc.get("token")
    if legacy:                                    # перенос со старого формата
        save_account(path, acc)
        return acc
    tok = secure_store.get_secret(TOKEN_KEY, "")
    if tok and acc:                               # токен без профиля (после выхода) не подставляем
        acc["token"] = tok
    return acc


def save_account(path, acc):
    """Сохраняет профиль; токен — в хранилище. Возвращает True, если файл записан."""
    data = dict(acc or {})
    tok = data.pop("token", "")
    if tok:
        if not secure_store.set_secret(TOKEN_KEY, tok):
            data["token"] = tok                   # хранилище недоступно — не теряем токен
    else:
        secure_store.delete_secret(TOKEN_KEY)
    return save_json(path, data, private=True)


# --- токен устройства (связь с сайтом) и секреты из старого settings.json ---------------------------------
CLOUD_KEY = "cloud_token"
SETTINGS_SECRETS = ("gemini_key", "resend_key", "google_client_secret", "eleven_key")


def cloud_save(settings, url, token):
    """В settings остаётся только адрес; токен — в хранилище (если оно недоступно, токен остаётся в settings, а не теряется)."""
    if secure_store.set_secret(CLOUD_KEY, token):
        settings["cloud"] = {"url": url}
    else:
        settings["cloud"] = {"url": url, "token": token}


def cloud_get(settings):
    """{'url', 'token'} или None, если устройство не подключено."""
    c = settings.get("cloud")
    if not isinstance(c, dict) or not c.get("url"):
        return None
    tok = c.get("token") or secure_store.get_secret(CLOUD_KEY, "")
    return {"url": c["url"], "token": tok} if tok else None


def cloud_clear(settings):
    settings.pop("cloud", None)
    secure_store.delete_secret(CLOUD_KEY)


def migrate_settings_secrets(settings):
    """Переносит ключи, оставшиеся в settings.json открытым текстом, в хранилище. True — settings изменён, его нужно сохранить."""
    changed = False
    for k in SETTINGS_SECRETS:
        v = settings.get(k)
        if not v:
            continue
        cur = secure_store.get_secret(k, "")
        if (cur and cur != v) or secure_store.set_secret(k, v):      # в хранилище уже более новое значение, либо перенесли
            settings.pop(k, None)
            changed = True
    c = settings.get("cloud")
    if isinstance(c, dict) and c.get("token") and secure_store.set_secret(CLOUD_KEY, c["token"]):
        c.pop("token", None)
        changed = True
    return changed
