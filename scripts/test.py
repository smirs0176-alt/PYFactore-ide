#!/usr/bin/env python3
"""Единая команда тестов:  python scripts/test.py [аргументы pytest]

Проверяет зависимости, в Linux без дисплея сам запускает xvfb-run, чтобы GUI-тесты не пропускались."""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def missing():
    return [m for m in ("pytest", "flask") if importlib.util.find_spec(m) is None]


def main(argv):
    miss = missing()
    if miss:
        sys.exit("Не хватает: %s. Установи: pip install -r requirements-dev.txt" % ", ".join(miss))
    cmd = [sys.executable, "-m", "pytest", "-q", "-rs"] + argv
    env = dict(os.environ)
    if sys.platform.startswith("linux") and not env.get("DISPLAY"):
        if shutil.which("xvfb-run"):
            cmd = ["xvfb-run", "-a"] + cmd
        else:
            print("! Нет DISPLAY и xvfb-run: GUI-тесты будут пропущены (sudo apt install xvfb python3-tk)")
    return subprocess.call(cmd, cwd=str(ROOT), env=env)  # noqa: S603


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
