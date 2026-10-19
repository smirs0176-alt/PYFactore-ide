"""Helpers for sending transactional emails via Resend."""

from __future__ import annotations

import os
from typing import Iterable

DEFAULT_FROM_EMAIL = "onboarding@resend.dev"


def get_api_key() -> str:
    """API-ключ только из окружения (RESEND_API_KEY). Ключа по умолчанию в коде нет."""
    api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not api_key or api_key == "re_xxxxxxxxx":
        raise ValueError("RESEND_API_KEY не задан. Укажи ключ в переменной окружения.")
    return api_key


def _client():
    """Пакет resend необязателен: импортируем при первой отправке, а не при импорте модуля."""
    try:
        import resend
    except ImportError as exc:
        raise RuntimeError("Не установлен пакет resend: pip install resend") from exc
    resend.api_key = get_api_key()
    return resend


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    from_email: str = DEFAULT_FROM_EMAIL,
):
    """Send a single email."""
    return _client().Emails.send(
        {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
    )


def send_bulk_emails(
    emails: Iterable[str],
    subject: str,
    html_body: str,
    from_email: str = DEFAULT_FROM_EMAIL,
):
    """Send the same email to multiple recipients."""
    results = []
    for email in emails:
        result = send_email(email, subject, html_body, from_email=from_email)
        results.append({"email": email, "result": result})
    return results


if __name__ == "__main__":
    recipients = ["user1@example.com", "user2@example.com"]
    result = send_bulk_emails(
        recipients,
        "Hello World",
        "<p>Congrats on sending your <strong>first email</strong>!</p>",
    )
    print(result)
