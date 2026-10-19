"""Запуск программ пользователя и пути в собранном EXE (PyInstaller подменяет sys.executable и __file__)."""
import os
import sys

from pyfactor import config
from pyfactor.core import pyexe


def test_source_run_uses_current_interpreter(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    pyexe.reset_cache()
    assert pyexe.python_cmd() == [sys.executable]


def test_frozen_never_returns_the_exe_itself(monkeypatch, tmp_path):
    fake_exe = str(tmp_path / "PyFactor.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", fake_exe)
    monkeypatch.delenv("PYFACTOR_PYTHON", raising=False)
    monkeypatch.setattr(pyexe, "_works", lambda cmd: False)          # на «компьютере» Python нет
    pyexe.reset_cache()
    assert pyexe.python_cmd() is None                                  # а не [PyFactor.exe]


def test_frozen_finds_python_and_probes_candidates(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "PyFactor.exe"))
    monkeypatch.delenv("PYFACTOR_PYTHON", raising=False)
    tried = []

    def works(cmd):
        tried.append(cmd)
        return cmd[0].endswith("good-python")
    monkeypatch.setattr(pyexe, "_works", works)
    monkeypatch.setattr(pyexe.shutil, "which", lambda n: "/x/bad-%s" % n if n != "python3" else "/x/good-python")
    pyexe.reset_cache()
    assert pyexe.python_cmd() == ["/x/good-python"]
    assert len(tried) >= 2 and not any(c[0] == sys.executable for c in tried)
    n = len(tried)
    assert pyexe.python_cmd() == ["/x/good-python"] and len(tried) == n   # результат запоминается


def test_explicit_python_path_wins(monkeypatch, tmp_path):
    py = tmp_path / "mypython"
    py.write_text("")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(pyexe, "_works", lambda cmd: True)
    pyexe.reset_cache()
    assert pyexe.python_cmd(str(py)) == [str(py)]


def test_app_root_is_next_to_exe_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "PyFactor.exe"))
    assert config._app_root() == str(tmp_path)
    monkeypatch.delattr(sys, "frozen")
    assert os.path.isfile(os.path.join(config._app_root(), "pyfactor", "config.py"))


def test_run_py_uses_resolver(monkeypatch, tmp_path):
    from pyfactor.core.python import analysis
    script = tmp_path / "a.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    monkeypatch.setattr(analysis, "python_cmd", lambda *a: None)
    rc, out, err, to = analysis.run_py(str(script), str(tmp_path), dict(os.environ))
    assert rc == 1 and "Python" in err
    monkeypatch.undo()
    rc, out, err, to = analysis.run_py(str(script), str(tmp_path), dict(os.environ))
    assert (rc, out.strip(), to) == (0, "hi", False)
