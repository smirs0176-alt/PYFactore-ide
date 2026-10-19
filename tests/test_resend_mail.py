import os
import sys
import types

import pytest

from pyfactor import resend_mail


def test_no_embedded_key_and_importable_without_resend_package(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    src = open(resend_mail.__file__, encoding="utf-8").read()
    assert "AQ.Ab8" not in src and "gmail.com" not in src
    with pytest.raises(ValueError):
        resend_mail.get_api_key()


def test_send_uses_env_key_and_fake_client(monkeypatch):
    sent = []
    fake = types.SimpleNamespace(api_key=None, Emails=types.SimpleNamespace(send=lambda payload: sent.append(payload) or {"id": "1"}))
    monkeypatch.setitem(sys.modules, "resend", fake)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    assert resend_mail.send_email("a@x.io", "S", "<p>b</p>") == {"id": "1"}
    assert fake.api_key == "re_test" and sent[0]["to"] == ["a@x.io"]
    assert os.environ["RESEND_API_KEY"] == "re_test"
