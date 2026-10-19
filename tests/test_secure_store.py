import json

import pytest

from pyfactor.core import secure_store as ss


class FakeKeyring:
    def __init__(self):
        self.d = {}

    def get_password(self, svc, key):
        return self.d.get((svc, key))

    def set_password(self, svc, key, val):
        self.d[(svc, key)] = val

    def delete_password(self, svc, key):
        del self.d[(svc, key)]


class BrokenKeyring:
    def get_password(self, *a):
        raise RuntimeError("no backend")

    set_password = delete_password = get_password


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "LEGACY_SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(ss, "DEFAULT_PATH", str(tmp_path / "secrets.json"))
    return tmp_path


def test_file_fallback_roundtrip_and_delete(paths, monkeypatch):
    monkeypatch.setattr(ss, "keyring", None)
    assert ss.get_secret("k", "def") == "def"
    assert ss.set_secret("k", "v")
    assert ss.get_secret("k") == "v"
    assert ss.delete_secret("k") is True
    assert ss.get_secret("k", "def") == "def"


def test_keyring_used_and_plaintext_copies_purged(paths, monkeypatch):
    fk = FakeKeyring()
    monkeypatch.setattr(ss, "keyring", fk)
    (paths / "secrets.json").write_text(json.dumps({"k": "old-plain", "other": "keep"}))
    (paths / "settings.json").write_text(json.dumps({"k": "old-plain", "theme": "dark"}))
    assert ss.set_secret("k", "new")
    assert fk.d[(ss.SERVICE_NAME, "k")] == "new"
    assert ss.get_secret("k") == "new"
    assert json.loads((paths / "secrets.json").read_text()) == {"other": "keep"}
    assert json.loads((paths / "settings.json").read_text()) == {"theme": "dark"}   # чужие настройки целы


def test_broken_keyring_falls_back_to_file(paths, monkeypatch):
    monkeypatch.setattr(ss, "keyring", BrokenKeyring())
    assert ss.set_secret("k", "v")
    assert ss.get_secret("k") == "v"


def test_legacy_settings_value_is_still_readable(paths, monkeypatch):
    monkeypatch.setattr(ss, "keyring", None)
    (paths / "settings.json").write_text(json.dumps({"gemini_key": "legacy"}))
    assert ss.get_secret("gemini_key") == "legacy"


def test_empty_name_rejected(paths):
    with pytest.raises(ValueError):
        ss.get_secret("  ")


def test_file_fallback_produces_visible_warning_once(paths, monkeypatch):
    monkeypatch.setattr(ss, "keyring", None)
    monkeypatch.setattr(ss, "_warned_file", False)
    ss.take_warning()
    assert ss.backend() == "file"
    assert ss.set_secret("k", "v")
    first = ss.take_warning()
    assert "открытым текстом" in first and "secrets.json" in first
    assert "v" not in first.replace("secrets.json", "").split("файле")[0]      # значение секрета в сообщение не попадает
    assert ss.set_secret("k2", "v2")
    assert ss.take_warning() == ""                                              # повторно не надоедаем


def test_strict_mode_refuses_plaintext_file(paths, monkeypatch):
    monkeypatch.setattr(ss, "keyring", None)
    monkeypatch.setenv(ss.STRICT_ENV, "1")
    ss.take_warning()
    assert ss.set_secret("k", "v") is False
    assert not (paths / "secrets.json").exists()
    assert ss.STRICT_ENV in ss.take_warning()


def test_keyring_backend_reports_no_warning(paths, monkeypatch):
    monkeypatch.setattr(ss, "keyring", FakeKeyring())
    ss.take_warning()
    assert ss.backend() == "keyring"
    assert ss.set_secret("k", "v")
    assert ss.take_warning() == ""
