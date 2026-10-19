"""Ключ ElevenLabs не должен лежать открытым текстом в settings.json: он идёт в защищённое хранилище."""
import json

import pytest

pytest.importorskip("tkinter")

from pyfactor.core import secure_store as ss  # noqa: E402
from pyfactor.core.account import vault  # noqa: E402
from pyfactor.features.tools import voice  # noqa: E402


class _Stub:
    voice_key = voice.VoiceMixin.voice_key

    def __init__(self):
        self.settings = {}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "keyring", None)
    monkeypatch.setattr(ss, "DEFAULT_PATH", str(tmp_path / "secrets.json"))
    monkeypatch.setattr(ss, "LEGACY_SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(voice, "SETTINGS_F", str(tmp_path / "settings.json"))
    monkeypatch.setattr(voice.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.delenv(ss.STRICT_ENV, raising=False)
    return tmp_path


def test_entered_key_goes_to_secure_store_not_settings(store, monkeypatch):
    monkeypatch.setattr(voice.simpledialog, "askstring", lambda *a, **k: "  el-test-key  ")
    app = _Stub()
    assert app.voice_key(True) == "el-test-key"
    assert "eleven_key" not in app.settings
    assert "el-test-key" not in (store / "settings.json").read_text(encoding="utf-8")
    assert ss.get_secret("eleven_key") == "el-test-key"
    assert app.voice_key() == "el-test-key"                       # второй раз спрашивать не надо


def test_cancelled_dialog_keeps_existing_key(store, monkeypatch):
    ss.set_secret("eleven_key", "kept")
    monkeypatch.setattr(voice.simpledialog, "askstring", lambda *a, **k: None)
    assert _Stub().voice_key(True) == "kept"


def test_plaintext_key_from_old_settings_is_migrated(store):
    settings = {"eleven_key": "old-plain", "theme": "dark"}
    assert vault.migrate_settings_secrets(settings) is True
    assert "eleven_key" not in settings and settings["theme"] == "dark"
    assert ss.get_secret("eleven_key") == "old-plain"
    assert json.loads((store / "secrets.json").read_text(encoding="utf-8"))["eleven_key"] == "old-plain"
