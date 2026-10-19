#!/usr/bin/env python3
"""Сборка PyFactor в один EXE для Windows (запускать на Windows):

    pip install pyinstaller keyring pygments
    python scripts/build_exe.py

Результат: dist\\PyFactor.exe. Проверено только статически (состав команды в tests/test_build_config.py);
сама сборка требует Windows и PyInstaller."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "pyfactor" / "assets"
ICON = ASSET_DIR / "icon.ico"
ENTRY = ROOT / "pyfactor" / "__main__.py"
PG2_DIR = ROOT / "pyfactor" / "pg2"
FUNRUN = ROOT / "pyfactor" / "core" / "languages" / "funrun.py"


def read_version():
    """Версия из pyfactor/__init__.py без импорта пакета."""
    import re
    m = re.search(r'^__version__\s*=\s*"([0-9]+(?:\.[0-9]+){1,3})"', (ROOT / "pyfactor" / "__init__.py").read_text(encoding="utf-8"), re.M)
    if not m:
        raise RuntimeError("Не найден __version__ в pyfactor/__init__.py")
    return m.group(1)


def version_info_text(version):
    """Текст файла версии для PyInstaller (--version-file): свойства PyFactor.exe в Windows. Компания и copyright не выдумываются."""
    parts = (version.split(".") + ["0", "0", "0"])[:4]
    tup = ", ".join(parts)
    return """VSVersionInfo(
  ffi=FixedFileInfo(filevers=(%s), prodvers=(%s), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', 'PyFactor IDE'),
      StringStruct('FileVersion', '%s'),
      StringStruct('InternalName', 'PyFactor'),
      StringStruct('OriginalFilename', 'PyFactor.exe'),
      StringStruct('ProductName', 'PyFactor IDE'),
      StringStruct('ProductVersion', '%s')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""" % (tup, tup, version, version)


def _have(mod):
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def build_command(python=None, have=_have, version_file=None):
    """Команда PyInstaller. keyring и pygments подгружают части себя динамически, поэтому собираем их явно, но только если они
    установлены (--copy-metadata без пакета роняет сборку). Без keyring EXE хранит ключи в файле secrets.json.
    pg2 и funrun.py запускаются с диска (import pg2 в играх; python funrun.py), поэтому кладём их как файлы."""
    cmd = [
        python or sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "PyFactor",
        "--specpath", str(ROOT / "build"),          # иначе PyInstaller перезапишет рукописный PyFactor.spec в корне
        "--icon", str(ICON),
        "--paths", str(ROOT),
        "--add-data", "%s%s%s" % (ASSET_DIR, os.pathsep, "pyfactor/assets"),
        "--add-data", "%s%s%s" % (PG2_DIR, os.pathsep, "pyfactor/pg2"),
        "--add-data", "%s%s%s" % (FUNRUN, os.pathsep, "pyfactor/core/languages"),
    ]
    if version_file:
        cmd += ["--version-file", str(version_file)]
    if have("keyring"):
        cmd += ["--collect-submodules", "keyring.backends", "--copy-metadata", "keyring"]
    if have("pygments"):
        cmd += ["--collect-submodules", "pygments.lexers", "--collect-submodules", "pygments.styles"]
    return cmd + [str(ENTRY)]


def main():
    for p in (ICON, ENTRY, PG2_DIR, FUNRUN):
        if not p.exists():
            raise FileNotFoundError("Не найден файл: %s" % p)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("Нет PyInstaller. Установи: pip install pyinstaller keyring pygments")
    vfile = None
    if sys.platform == "win32":                      # ресурс версии имеет смысл только для .exe
        (ROOT / "build").mkdir(exist_ok=True)
        vfile = ROOT / "build" / "version_info.txt"
        vfile.write_text(version_info_text(read_version()), encoding="utf-8")
    cmd = build_command(version_file=vfile)
    if not _have("keyring"):
        print("[PyFactor Build] keyring не установлен: ключи в EXE будут храниться в файле, а не в Credential Manager")
    print("[PyFactor Build]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)  # noqa: S603
    print("[PyFactor Build] Готово: dist%sPyFactor%s" % (os.sep, ".exe" if sys.platform == "win32" else ""))


if __name__ == "__main__":
    main()
