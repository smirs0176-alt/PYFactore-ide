"""Отправка писем через Resend (https://resend.com). Только стандартная библиотека, пакет `resend` ставить не нужно.
API-ключ в коде не хранится: он берётся из настроек IDE (⚙ → «Почта Resend…») или переменной PYFACTOR_RESEND_KEY."""
import json
import urllib.error
import urllib.request

API = "https://api.resend.com/emails"
DEFAULT_FROM = "onboarding@resend.dev"      # тестовый адрес Resend: шлёт только на почту владельца аккаунта Resend


class MailError(Exception):
    pass


def send(key, to, subject, html, sender=DEFAULT_FROM, timeout=20):
    """Отправляет письмо. Возвращает id письма."""
    if not key:
        raise MailError("Нет ключа Resend. Вставь его: ⚙ → «Почта Resend…».")
    body = json.dumps({"from": sender or DEFAULT_FROM, "to": [to], "subject": subject, "html": html}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "PyFactor-IDE"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8") or "{}").get("id", "")
    except urllib.error.HTTPError as ex:
        raw = ex.read().decode("utf-8", "ignore")
        try:
            raw = json.loads(raw).get("message", raw)
        except ValueError:
            pass
        hint = {401: "ключ Resend не подошёл", 403: "ключ Resend не подошёл или адрес отправителя не разрешён",
                422: "неверный адрес", 429: "слишком много писем, подожди"}.get(ex.code, "")
        raise MailError("Resend %s%s: %s" % (ex.code, " (%s)" % hint if hint else "", raw[:220]))
    except Exception as ex:
        raise MailError("Нет связи с Resend: %s" % ex)


def send_code(key, to, code, sender=DEFAULT_FROM):
    html = ("<div style='font-family:Segoe UI,Arial,sans-serif;max-width:420px'>"
            "<h2 style='margin:0 0 8px'>PyFactor</h2><p>Твой код подтверждения:</p>"
            "<p style='font-size:32px;font-weight:700;letter-spacing:6px;background:#f2f3f7;padding:12px 18px;"
            "border-radius:8px;display:inline-block;margin:4px 0'>%s</p>"
            "<p style='color:#666'>Код действует 10 минут. Если это был не ты, просто проигнорируй письмо.</p></div>" % code)
    return send(key, to, "Код подтверждения PyFactor: " + code, html, sender)
