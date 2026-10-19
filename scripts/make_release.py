#!/usr/bin/env python3
"""Сборка архива исходников релиза:  python scripts/make_release.py [--out ПАПКА]

В архив не попадают кэши, локальное состояние, .env, старые копии модулей (legacy_unused) и непроверенные готовые бинарники
(server/dist). Перед записью каждый файл сканируется на секреты; при находке архив НЕ создаётся, а значение секрета не печатается.
Результат: release/PyFactor-<версия>-source.zip и его SHA-256.
Это архив исходников, а не установщик и не PyFactor.exe (EXE собирает scripts/build_exe.py на Windows)."""
import argparse
import hashlib
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".venv", "venv", "build", "dist", "release", "node_modules",
                "legacy_unused", ".github_cache"}
EXCLUDE_REL_DIRS = {"server/dist", "site/data"}                 # готовые бинарники сервера не проверены; данные сайта — локальные
EXCLUDE_NAMES = {".env", "connect.json", "state.json", "admin_token.txt", "secrets.json", "settings.json", "folder site.txt"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".log", ".corrupt")

SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Google OAuth client secret": re.compile(r"GOCSPX-[A-Za-z0-9_\-]{20,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "Resend key": re.compile(r"\bre_[A-Za-z0-9]{20,}\b"),
    "Old Resend default key": re.compile(r"AQ\.Ab8[A-Za-z0-9_\-]{20,}"),
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}


def read_version(root=ROOT):
    m = re.search(r'^__version__\s*=\s*"([0-9]+(?:\.[0-9]+){2})"', (Path(root) / "pyfactor" / "__init__.py").read_text(encoding="utf-8"), re.M)
    if not m:
        raise RuntimeError("В pyfactor/__init__.py нет __version__ вида X.Y.Z")
    return m.group(1)


def collect_files(root=ROOT):
    root = Path(root)
    out = []
    for base, dirs, files in os.walk(root):
        rel_base = Path(base).relative_to(root).as_posix()
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS and ((rel_base + "/" + d) if rel_base != "." else d) not in EXCLUDE_REL_DIRS)
        for f in sorted(files):
            if f in EXCLUDE_NAMES or f.endswith(EXCLUDE_SUFFIXES):
                continue
            out.append(Path(base) / f)
    return out


def scan_secrets(paths, root=ROOT):
    """[(путь, строка, тип)] — само значение не возвращается и нигде не печатается."""
    hits = []
    for p in paths:
        try:
            text = Path(p).read_bytes().decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue                                              # бинарные файлы (png, ico) текстом не сканируем
        for n, line in enumerate(text.splitlines(), 1):
            for kind, rx in SECRET_PATTERNS.items():
                if rx.search(line):
                    hits.append((Path(p).relative_to(root).as_posix(), n, kind))
    return hits


def build(root=ROOT, out_dir=None):
    root = Path(root)
    version = read_version(root)
    files = collect_files(root)
    hits = scan_secrets(files, root)
    if hits:
        for rel, n, kind in hits:
            print("СЕКРЕТ? %s:%d — %s" % (rel, n, kind), file=sys.stderr)
        raise SystemExit("Архив не создан: найдены секреты (значения не показаны). Удали их и ротируй ключи.")
    out_dir = Path(out_dir) if out_dir else root / "release"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / ("PyFactor-%s-source.zip" % version)
    top = "PyFactor-%s" % version
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, "%s/%s" % (top, p.relative_to(root).as_posix()))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return target, digest, len(files)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="папка для архива (по умолчанию release/)")
    args = ap.parse_args(argv)
    target, digest, n = build(ROOT, args.out)
    print("Готово: %s (%d файлов)\nSHA-256: %s" % (target, n, digest))


if __name__ == "__main__":
    main()
