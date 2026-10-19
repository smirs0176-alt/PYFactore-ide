"""Собирает архив приложения для скачивания. В архив кладётся connect.json с одноразовым кодом подключения к аккаунту."""
import io
import json
import os
import time
import zipfile
from pathlib import Path

TOP = "PyFactor"
INCLUDE = ("pyfactor", "scripts")          # папки приложения; site/ и server/ в архив не попадают
SKIP_DIRS = {"__pycache__", ".git"}


def _write_bundle(buf, root, code, server_url, include_exe=False):
    now = time.localtime()[:6]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def add(path, arc):
            zi = zipfile.ZipInfo(TOP + "/" + arc.replace(os.sep, "/"), now)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o755 if arc.endswith((".sh", "run.py")) else 0o644) << 16
            with open(path, "rb") as f:
                z.writestr(zi, f.read())
        if include_exe:
            exe_candidates = [
                Path(root) / "dist" / "PyFactor.exe",
                Path(root) / "build" / "PyFactor" / "PyFactor.exe",
                Path(root) / "PyFactor.exe",
            ]
            exe_path = next((p for p in exe_candidates if p.exists()), None)
            if exe_path is not None:
                z.writestr(TOP + "/PyFactor.exe", exe_path.read_bytes())
        for top in INCLUDE:
            for dirpath, dirs, files in os.walk(os.path.join(root, top)):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for fn in sorted(files):
                    if not fn.endswith(".pyc"):
                        full = os.path.join(dirpath, fn)
                        add(full, os.path.relpath(full, root))
        for extra in ("README.md",):
            if os.path.isfile(os.path.join(root, extra)):
                add(os.path.join(root, extra), extra)
        z.writestr(TOP + "/connect.json", json.dumps({"v": 1, "server": server_url, "code": code}, indent=1))


def build_zip(root, code, server_url):
    buf = io.BytesIO()
    _write_bundle(buf, root, code, server_url, include_exe=False)
    return buf.getvalue()


def build_windows_bundle(root, code, server_url):
    """Try to produce a Windows exe bundle if a built binary exists; otherwise fall back to zip."""
    root_path = Path(root)
    exe_candidates = [
        root_path / "dist" / "PyFactor.exe",
        root_path / "build" / "PyFactor" / "PyFactor.exe",
        root_path / "PyFactor.exe",
    ]
    buf = io.BytesIO()
    _write_bundle(buf, root, code, server_url, include_exe=any(p.exists() for p in exe_candidates))
    return buf.getvalue()
