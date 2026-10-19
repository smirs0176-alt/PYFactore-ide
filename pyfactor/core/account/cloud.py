"""Связь приложения с сайтом PyFactor: обмен кода подключения на токен устройства и проверка аккаунта.
Только стандартная библиотека. Токен лежит в ~/.pyfactor/settings.json, а не в папке приложения."""
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request


class CloudError(Exception):
    def __init__(self, msg, kind="other"):
        super().__init__(msg)
        self.kind = kind                 # "network" — сайт недоступен, "auth" — код/токен не подошёл, "other"


def _safe_url(url):
    """Разрешаем только https. Обычный http допустим лишь для localhost и домашней сети (иначе токен уйдёт открытым текстом)."""
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise CloudError("Неверный адрес сайта в connect.json")
    if u.scheme == "http":
        host, local = u.hostname, u.hostname == "localhost"
        try:
            ip = ipaddress.ip_address(host)
            local = ip.is_loopback or ip.is_private
        except ValueError:
            pass
        if not local:
            raise CloudError("Сайт без HTTPS: подключаться небезопасно")
    return url.rstrip("/")


def _call(url, path, method="GET", token=None, body=None, timeout=8):
    url = _safe_url(url)
    headers = {"User-Agent": "PyFactor-IDE"}
    data = None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode("utf-8"), "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url + path, data=data, headers=headers, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as ex:
        try:
            msg = json.loads(ex.read().decode("utf-8")).get("error", "")
        except Exception:
            msg = ""
        raise CloudError(msg or "Сайт ответил ошибкой %s" % ex.code, "auth" if ex.code in (401, 403) else "other")
    except Exception as ex:
        raise CloudError("Сайт недоступен: %s" % ex, "network")


def claim(url, code, label):
    """Меняет одноразовый код из скачанного архива на токен устройства. Возвращает {token, name, email}."""
    return _call(url, "/api/device/claim", "POST", body={"code": code, "label": label})


def me(url, token):
    """Проверяет, что устройство всё ещё подключено. CloudError(kind='auth') — отключено на сайте."""
    return _call(url, "/api/device/me", token=token)


def revoke_quiet(url, token):
    try:
        _call(url, "/api/device/logout", "POST", token=token, body={}, timeout=5)
    except CloudError:
        pass
