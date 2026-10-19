"""GitHub-токен не должен лежать в account.json открытым текстом."""
import json

import pytest

from pyfactor.core import secure_store as ss
from pyfactor.core.account import vault


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "keyring", None)
    monkeypatch.setattr(ss, "DEFAULT_PATH", str(tmp_path / "secrets.json"))
    monkeypatch.setattr(ss, "LEGACY_SETTINGS_PATH", str(tmp_path / "settings.json"))
    return tmp_path


def test_token_goes_to_store_not_to_account_file(env):
    f = str(env / "account.json")
    assert vault.save_account(f, {"name": "A", "token": "ghp_SECRET"})
    assert "ghp_SECRET" not in open(f, encoding="utf-8").read()
    assert vault.load_account(f) == {"name": "A", "token": "ghp_SECRET"}


def test_legacy_plaintext_token_is_migrated_on_load(env):
    f = env / "account.json"
    f.write_text(json.dumps({"name": "A", "token": "ghp_OLD"}), encoding="utf-8")
    acc = vault.load_account(str(f))
    assert acc["token"] == "ghp_OLD"                                    # работает как раньше
    assert "ghp_OLD" not in f.read_text(encoding="utf-8")               # но на диске открытого текста нет


def test_logout_removes_token(env):
    f = str(env / "account.json")
    vault.save_account(f, {"name": "A", "token": "t"})
    vault.save_account(f, {})
    assert ss.get_secret(vault.TOKEN_KEY, "") == ""
    assert vault.load_account(f) == {}


def test_token_kept_in_file_if_store_unavailable(env, monkeypatch):
    monkeypatch.setattr(ss, "set_secret", lambda *a, **k: False)
    f = str(env / "account.json")
    vault.save_account(f, {"name": "A", "token": "t"})
    assert vault.load_account(f)["token"] == "t"                        # токен не потерян


def test_missing_or_broken_file_gives_empty_account(env):
    assert vault.load_account(str(env / "none.json")) == {}
    (env / "bad.json").write_text("[1,2]", encoding="utf-8")
    assert vault.load_account(str(env / "bad.json")) == {}


def test_cloud_token_not_in_settings(env):
    st = {}
    vault.cloud_save(st, "https://site.example", "DEVICE-TOKEN")
    assert st == {"cloud": {"url": "https://site.example"}}                 # токена в settings нет
    assert vault.cloud_get(st) == {"url": "https://site.example", "token": "DEVICE-TOKEN"}
    vault.cloud_clear(st)
    assert vault.cloud_get(st) is None and "cloud" not in st
    assert ss.get_secret(vault.CLOUD_KEY, "") == ""


def test_cloud_token_kept_in_settings_if_store_unavailable(env, monkeypatch):
    monkeypatch.setattr(ss, "set_secret", lambda *a, **k: False)
    st = {}
    vault.cloud_save(st, "https://s", "T")
    assert vault.cloud_get(st)["token"] == "T"


def test_legacy_settings_secrets_are_migrated(env):
    st = {"font_size": 12, "gemini_key": "G", "resend_key": "R", "google_client_secret": "S",
          "cloud": {"url": "https://s", "token": "CT"}}
    (env / "settings.json").write_text(json.dumps(st), encoding="utf-8")     # так выглядел старый файл на диске
    assert vault.migrate_settings_secrets(st) is True
    assert st == {"font_size": 12, "cloud": {"url": "https://s"}}
    assert (ss.get_secret("gemini_key"), ss.get_secret("resend_key"), ss.get_secret("google_client_secret")) == ("G", "R", "S")
    assert vault.cloud_get(st)["token"] == "CT"
    assert "G" not in (env / "settings.json").read_text(encoding="utf-8")    # и с диска открытый текст ушёл
    assert vault.migrate_settings_secrets(st) is False                        # повторно ничего не делает


def test_migration_does_not_overwrite_newer_stored_value(env):
    ss.set_secret("gemini_key", "NEW")
    st = {"gemini_key": "OLD"}
    assert vault.migrate_settings_secrets(st) is True
    assert ss.get_secret("gemini_key") == "NEW" and "gemini_key" not in st


def test_corrupt_secrets_file_is_backed_up_not_silently_wiped(env):
    f = env / "secrets.json"
    f.write_text('{"a": "1", "b": ', encoding="utf-8")
    assert ss.set_secret("c", "3")
    assert (env / "secrets.json.corrupt").read_text(encoding="utf-8").startswith('{"a": "1"')
