"""Архив релиза: нужные файлы есть, лишнего и секретов нет, сканер реально ловит секреты."""
import importlib.util
import os
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mod():
    spec = importlib.util.spec_from_file_location("make_release", os.path.join(ROOT, "scripts", "make_release.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    m = _mod()
    target, digest, n = m.build(ROOT, tmp_path_factory.mktemp("rel"))
    with zipfile.ZipFile(target) as z:
        return m, target, digest, z.namelist()


def test_archive_has_required_files(archive):
    m, target, digest, names = archive
    top = "PyFactor-%s/" % m.read_version()
    for need in ("README.md", "pyfactor/__main__.py", "pyfactor/assets/icon.ico", "scripts/build_exe.py", "requirements-dev.txt", ".env.example", "server/main.go"):
        assert top + need in names, need
    assert len(digest) == 64 and target.name == "PyFactor-%s-source.zip" % m.read_version()


def test_archive_excludes_junk_local_state_and_legacy(archive):
    names = archive[3]
    bad = [n for n in names if "__pycache__" in n or "/legacy_unused/" in n or "/server/dist/" in n or "/.git/" in n
           or n.endswith((".pyc", ".db", "/.env", "/admin_token.txt", "/connect.json", "/secrets.json", "folder site.txt"))]
    assert bad == []


def test_scanner_finds_synthetic_secrets_without_leaking_values(tmp_path):
    m = _mod()
    (tmp_path / "pyfactor").mkdir()
    (tmp_path / "pyfactor" / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    fake = "AIza" + "x" * 35                                   # собираем на лету, чтобы в исходниках теста не было ключеподобной строки
    (tmp_path / "leak.txt").write_text("key = %s\n" % fake, encoding="utf-8")
    hits = m.scan_secrets(m.collect_files(tmp_path), tmp_path)
    assert hits == [("leak.txt", 1, "Google API key")]
    with pytest.raises(SystemExit) as e:
        m.build(tmp_path, tmp_path / "out")
    assert fake not in str(e.value)
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").glob("*.zip"))


def test_release_tree_has_no_secrets():
    m = _mod()
    assert m.scan_secrets(m.collect_files(ROOT), ROOT) == []
