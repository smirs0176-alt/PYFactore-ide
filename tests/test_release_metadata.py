"""Версия, ленивый импорт Flask и ресурс версии для EXE."""
import importlib.util
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build():
    spec = importlib.util.spec_from_file_location("build_exe", os.path.join(ROOT, "scripts", "build_exe.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_version_is_semver_and_read_by_build_script():
    import pyfactor
    assert re.fullmatch(r"\d+\.\d+\.\d+", pyfactor.__version__)
    assert _build().read_version() == pyfactor.__version__


def test_import_pyfactor_does_not_import_flask():
    code = "import sys, pyfactor; sys.exit(1 if 'flask' in sys.modules else 0)"
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)  # noqa: S603
    assert r.returncode == 0, "import pyfactor тянет Flask: " + r.stderr[-300:]


def test_register_pairing_still_works_with_flask():
    flask = pytest.importorskip("flask")
    import pyfactor
    app = flask.Flask(__name__)
    pyfactor.register_pairing(app)
    assert len(app.blueprints) == 1


def _stub_namespace():
    """Заглушки классов версии: проверяют синтаксис и состав полей на любой ОС (настоящий разбор PyInstaller есть только на Windows)."""
    class Node:
        def __init__(self, *a, **kw):
            self.a, self.kw = a, kw
    names = ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable", "StringStruct", "VarFileInfo", "VarStruct")
    return {n: type(n, (Node,), {}) for n in names}


def test_version_info_text_structure():
    text = _build().version_info_text("1.0.0")
    assert "filevers=(1, 0, 0, 0)" in text and "OriginalFilename', 'PyFactor.exe'" in text
    assert "CompanyName" not in text and "Copyright" not in text           # не выдумываем юридические данные
    root = eval(text, _stub_namespace())  # noqa: S307  (текст сгенерирован этим же репозиторием)
    assert type(root).__name__ == "VSVersionInfo"


@pytest.mark.skipif(sys.platform != "win32", reason="PyInstaller.utils.win32.versioninfo импортируется только в Windows (нужен pywin32)")
def test_version_info_text_parses_with_real_pyinstaller(tmp_path):
    from PyInstaller.utils.win32 import versioninfo
    f = tmp_path / "v.txt"
    f.write_text(_build().version_info_text("1.0.0"), encoding="utf-8")
    assert versioninfo.load_version_info_from_text_file(str(f)) is not None


def test_build_command_adds_version_file_only_when_given():
    m = _build()
    assert "--version-file" not in m.build_command("python", have=lambda mod: False)
    assert "--version-file" in m.build_command("python", have=lambda mod: False, version_file="v.txt")
