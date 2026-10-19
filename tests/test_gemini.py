import http.client
import json
import socket
import threading
import time

import pytest

from pyfactor.core.ai import gemini


def _ok(text="привет"):
    return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()


@pytest.mark.parametrize("bad", ["a/b", "../x", "m:generate", "m?key=1", "m#x", "a b", "-x", "x" * 65, "модель"])
def test_bad_model_rejected_before_any_request(bad, monkeypatch):
    monkeypatch.setattr(gemini, "_post", lambda *a, **k: pytest.fail("запрос не должен уйти"))
    with pytest.raises(gemini.GeminiError, match="имя модели"):
        gemini.ask("k", "hi", model=bad)


def test_default_and_normal_models_ok(monkeypatch):
    seen = []
    monkeypatch.setattr(gemini, "_post", lambda url, *a, **k: seen.append(url) or _ok())
    assert gemini.ask("k", "hi") == "привет"
    assert gemini.ask("k", "hi", model="gemini-2.5-pro") == "привет"
    assert seen[0].endswith("/models/gemini-2.5-flash:generateContent")
    assert seen[1].endswith("/models/gemini-2.5-pro:generateContent")


def test_key_goes_in_header_not_url(monkeypatch):
    got = {}
    monkeypatch.setattr(gemini, "_post", lambda url, headers, *a, **k: got.update(url=url, h=headers) or _ok())
    gemini.ask("SECRET-KEY", "hi")
    assert "SECRET-KEY" not in got["url"]
    assert got["h"]["x-goog-api-key"] == "SECRET-KEY"


def test_no_key():
    with pytest.raises(gemini.GeminiError, match="Нет ключа"):
        gemini.ask("", "hi")


def test_oversized_response_rejected(monkeypatch):
    monkeypatch.setattr(gemini, "MAX_RESPONSE", 100)
    monkeypatch.setattr(gemini, "_post", lambda *a, **k: (200, b"x" * 500))
    with pytest.raises(gemini.GeminiError, match="слишком большой"):
        gemini.ask("k", "hi")


def test_http_429_and_network_errors_are_readable(monkeypatch):
    monkeypatch.setattr(gemini, "_post", lambda *a, **k: (429, json.dumps({"error": {"message": "quota"}}).encode()))
    with pytest.raises(gemini.GeminiError, match="429.*подожди.*quota"):
        gemini.ask("k", "hi")

    def down(*a, **k):
        raise OSError("нет сети")
    monkeypatch.setattr(gemini, "_post", down)
    with pytest.raises(gemini.GeminiError, match="Нет связи"):
        gemini.ask("k", "hi")


def test_blocked_prompt_and_garbage(monkeypatch):
    monkeypatch.setattr(gemini, "_post", lambda *a, **k: (200, b'{"promptFeedback":{"blockReason":"SAFETY"}}'))
    with pytest.raises(gemini.GeminiError, match="SAFETY"):
        gemini.ask("k", "hi")
    monkeypatch.setattr(gemini, "_post", lambda *a, **k: (200, b"<html>"))
    with pytest.raises(gemini.GeminiError, match="непонятный"):
        gemini.ask("k", "hi")


def test_code_blocks():
    assert gemini.code_blocks("a\n```python\nprint(1)\n```\nb") == ["print(1)"]


# ---------- настоящая отмена: сервер принимает соединение и молчит

@pytest.fixture
def silent_server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    conns = []

    def accept():
        try:
            conns.append(srv.accept()[0])
        except OSError:                      # сокет закрыли в конце теста
            pass
    threading.Thread(target=accept, daemon=True).start()
    yield "http://127.0.0.1:%d/v1/x" % srv.getsockname()[1]
    for c in conns:
        c.close()
    srv.close()


def test_cancel_interrupts_hanging_request(silent_server, monkeypatch):
    monkeypatch.setattr(gemini.http.client, "HTTPSConnection", http.client.HTTPConnection)   # без TLS, только для теста
    monkeypatch.setattr(gemini, "URL", silent_server.replace("/x", "/models/%s:g"))
    cancel = gemini.Cancel()
    threading.Timer(0.3, cancel.cancel).start()
    t0 = time.time()
    with pytest.raises(gemini.GeminiCancelled):
        gemini.ask("k", "hi", timeout=30, cancel=cancel)
    assert time.time() - t0 < 5          # не 30 секунд тайм-аута


def test_cancel_before_request_aborts_immediately(silent_server, monkeypatch):
    monkeypatch.setattr(gemini.http.client, "HTTPSConnection", http.client.HTTPConnection)
    monkeypatch.setattr(gemini, "URL", silent_server.replace("/x", "/models/%s:g"))
    cancel = gemini.Cancel()
    cancel.cancel()
    with pytest.raises(gemini.GeminiCancelled):
        gemini.ask("k", "hi", timeout=30, cancel=cancel)
