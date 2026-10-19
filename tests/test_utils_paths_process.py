import os
import stat
import sys

import pytest

from pyfactor.core.paths import UnsafePath, is_within, safe_join, safe_name
from pyfactor.core.process import kill_tree, popen_extra, scrubbed_env
from pyfactor.core.secure_store import delete_secret, get_secret, set_secret
from pyfactor.core.utils import load_json, save_json

# ---------- save_json


def test_save_json_roundtrip_and_no_tmp_left(tmp_path):
    f = tmp_path / "s.json"
    assert save_json(str(f), {"a": "ё"}) is True
    assert load_json(str(f), None) == {"a": "ё"}
    assert [p.name for p in tmp_path.iterdir()] == ["s.json"]


def test_save_json_failure_keeps_old_file(tmp_path):
    f = tmp_path / "s.json"
    save_json(str(f), {"ok": 1})
    assert save_json(str(f), {"bad": object()}) is False          # не сериализуется
    assert load_json(str(f), None) == {"ok": 1}                   # старый файл цел
    assert [p.name for p in tmp_path.iterdir()] == ["s.json"]     # мусора нет


def test_secure_store_round_trip(tmp_path):
    f = tmp_path / "secrets.json"
    assert set_secret("demo_key", "demo-value", path=str(f)) is True
    assert get_secret("demo_key", path=str(f)) == "demo-value"
    assert delete_secret("demo_key", path=str(f)) is True
    assert get_secret("demo_key", path=str(f), default="") == ""


@pytest.mark.skipif(sys.platform == "win32", reason="права POSIX")
def test_save_json_private_mode(tmp_path):
    f = tmp_path / "s.json"
    save_json(str(f), {"k": "v"}, private=True)
    assert stat.S_IMODE(os.stat(f).st_mode) == 0o600


# ---------- пути

@pytest.mark.parametrize("bad", ["", " ", ".", "..", "a/b", "a\\b", "../x", "/etc/passwd", "C:x", "C:\\x", "a\0b"])
def test_safe_name_rejects(bad):
    with pytest.raises(UnsafePath):
        safe_name(bad)


def test_safe_name_accepts_plain():
    assert safe_name(" main.py ") == "main.py"


@pytest.mark.parametrize("bad", ["../x", "a/../../x", "/tmp/x", "C:\\Windows", "", "."])
def test_safe_join_rejects_escape(tmp_path, bad):
    with pytest.raises(UnsafePath):
        safe_join(str(tmp_path), bad)


def test_safe_join_allows_subfolder(tmp_path):
    assert safe_join(str(tmp_path), "a/b") == os.path.normpath(str(tmp_path / "a" / "b"))


@pytest.mark.skipif(sys.platform == "win32", reason="симлинки")
def test_safe_join_blocks_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    os.symlink(outside, proj / "link")
    assert not is_within(str(proj), str(proj / "link" / "f"))
    with pytest.raises(UnsafePath):
        safe_join(str(proj), "link/f")


# ---------- окружение и процессы

def _alive(pid):
    """Процесс жив, если он есть и не зомби (осиротевший зомби без init в контейнере уже мёртв)."""
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def test_scrubbed_env_removes_pyfactor_secrets_only():
    env = scrubbed_env({"PYFACTOR_GEMINI_KEY": "x", "PYFACTOR_RESEND_KEY": "x", "PYFACTOR_ADMIN_TOKEN": "x",
                        "PYFACTOR_GOOGLE_CLIENT_SECRET": "x", "PYFACTOR_NO_LOGIN": "1", "PATH": "/bin", "HOME": "/h"})
    assert env == {"PYFACTOR_NO_LOGIN": "1", "PATH": "/bin", "HOME": "/h"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-группы процессов")
def test_kill_tree_kills_children(tmp_path):
    import subprocess
    import time
    pidfile = tmp_path / "child.pid"
    code = ("import subprocess,sys,time;"
            "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
            "open(sys.argv[1],'w').write(str(c.pid));time.sleep(60)")
    p = subprocess.Popen([sys.executable, "-c", code, str(pidfile)], **popen_extra())
    for _ in range(50):
        if pidfile.exists() and pidfile.read_text():
            break
        time.sleep(0.1)
    child = int(pidfile.read_text())
    kill_tree(p)
    p.wait(5)
    time.sleep(0.3)
    assert not _alive(child)
