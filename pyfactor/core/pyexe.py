"""Какой Python запускать для программ пользователя.

Из исходников это sys.executable. В собранном EXE (PyInstaller) sys.executable — сам PyFactor.exe: запуск «python файл.py»
открывал бы ещё одно окно IDE вместо программы. Поэтому в EXE ищем установленный на компьютере Python 3:
путь из настроек (python_path) или PYFACTOR_PYTHON, затем «py -3», «python», «python3». Каждый кандидат проверяется пробным запуском
(так отсеивается заглушка Microsoft Store)."""
import os
import shutil
import subprocess
import sys

_NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PROBE = ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"]
_cache = {}


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def _works(cmd):
    try:
        r = subprocess.run(cmd + _PROBE, capture_output=True, timeout=15, stdin=subprocess.DEVNULL,  # noqa: S603
                           creationflags=_NO_WIN, check=False)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def candidates(override=None):
    out = []
    for p in (override, os.environ.get("PYFACTOR_PYTHON")):
        if p and str(p).strip():
            out.append([str(p).strip()])
    if sys.platform == "win32":
        out.append(["py", "-3"])
    out += [["python"], ["python3"]]
    return out


def python_cmd(override=None):
    """Список для начала команды запуска, например ['py', '-3'], или None, если Python не найден."""
    if not is_frozen() and not override:
        return [sys.executable]
    key = (override or "", os.environ.get("PYFACTOR_PYTHON", ""))
    if key in _cache and _cache[key]:
        return list(_cache[key])
    for cmd in candidates(override):
        exe = cmd[0] if os.path.isabs(cmd[0]) else shutil.which(cmd[0])
        if exe and _works([exe] + cmd[1:]):
            _cache[key] = [exe] + cmd[1:]
            return list(_cache[key])
    if not is_frozen():
        return [sys.executable]                   # override не подошёл — запасной вариант из исходников
    return None


def reset_cache():
    _cache.clear()
