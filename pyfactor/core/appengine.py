"""Движок приложений PyFactor: регистрация, запуск и управление пакетами приложений."""

import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field

from pyfactor.core.utils import load_json, save_json


def _slugify(value):
    text = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (value or "app").strip())
    text = text.strip("_")
    return (text or "app").lower()


def _resolve_icon_path(app_dir, manifest):
    if not os.path.isdir(app_dir):
        return ""
    candidates = []
    icon_value = manifest.get("icon") if isinstance(manifest, dict) else ""
    if icon_value:
        candidates.append(str(icon_value))
    candidates.extend([
        "icon.png", "icon.ico", "icon.jpg", "icon.jpeg", "icon.gif", "icon.svg",
        "app.png", "app.ico", "app.jpg", "app.jpeg", "logo.png", "logo.ico"
    ])
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        raw = candidate.strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        full = raw if os.path.isabs(raw) else os.path.join(app_dir, raw)
        if os.path.isfile(full):
            try:
                rel = os.path.relpath(full, app_dir)
            except ValueError:
                rel = raw
            return rel.replace("\\", "/")
    return ""


@dataclass
class AppBundle:
    app_id: str
    title: str
    description: str
    author: str
    version: str
    entry: str
    path: str
    icon: str = ""
    tags: list[str] = field(default_factory=list)
    runtime: dict = field(default_factory=dict)

    @property
    def abs_entry(self):
        return os.path.join(self.path, self.entry)

    def to_dict(self):
        data = {
            "app_id": self.app_id,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "entry": self.entry,
            "path": self.path,
            "icon": self.icon,
            "tags": list(self.tags),
            "runtime": dict(self.runtime),
        }
        return data


class AppEngine:
    """Управляет каталогом приложений и их запуском."""

    def __init__(self, root_dir=None):
        from pyfactor import config

        self.root_dir = os.path.abspath(root_dir or config.APPS)
        os.makedirs(self.root_dir, exist_ok=True)
        self._apps = {}
        self._processes = {}
        self._scan_root()

    def _scan_root(self):
        if not os.path.isdir(self.root_dir):
            return
        for name in sorted(os.listdir(self.root_dir)):
            path = os.path.join(self.root_dir, name)
            if os.path.isdir(path):
                try:
                    self.register_app(path)
                except ValueError:
                    continue

    def register_app(self, app_dir):
        app_dir = os.path.abspath(app_dir)
        if not os.path.isdir(app_dir):
            raise ValueError(f"Папка приложения не найдена: {app_dir}")
        manifest = load_json(os.path.join(app_dir, "app.json"), {})
        title = manifest.get("title") or os.path.basename(app_dir)
        app_id = manifest.get("app_id") or manifest.get("id") or _slugify(title)
        entry = manifest.get("entry") or "main.py"
        entry = entry.lstrip("./")
        full_entry = os.path.join(app_dir, entry)
        if not os.path.isfile(full_entry):
            if os.path.isfile(os.path.join(app_dir, "main.py")):
                entry = "main.py"
                full_entry = os.path.join(app_dir, entry)
            else:
                raise ValueError(f"Точка входа не найдена в приложении: {app_dir}")
        base_id = app_id
        i = 1
        while app_id in self._apps:
            app_id = f"{base_id}_{i}"
            i += 1

        bundle = AppBundle(
            app_id=app_id,
            title=title,
            description=str(manifest.get("description") or ""),
            author=str(manifest.get("author") or "Guest"),
            version=str(manifest.get("version") or "1.0.0"),
            entry=entry,
            path=app_dir,
            icon=_resolve_icon_path(app_dir, manifest),
            tags=list(manifest.get("tags") or []),
        )
        bundle.runtime = {
            "app_id": bundle.app_id,
            "title": bundle.title,
            "entry": bundle.entry,
            "path": bundle.path,
            "python": sys.executable,
        }
        self._apps[bundle.app_id] = bundle
        return bundle

    def list_apps(self):
        return [self._apps[key].to_dict() for key in sorted(self._apps, key=lambda k: self._apps[k].title.lower())]

    def get_app(self, app_id):
        bundle = self._apps.get(app_id)
        return None if bundle is None else bundle.to_dict()

    def has_app(self, app_id):
        return app_id in self._apps

    def launch_app(self, app_id, extra_env=None):
        bundle = self._apps.get(app_id)
        if bundle is None:
            raise KeyError(f"Приложение не найдено: {app_id}")
        if self._processes.get(app_id) and self._processes[app_id].poll() is None:
            return self._processes[app_id]

        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        env["PYFACTOR_APP_ID"] = app_id
        env["PYFACTOR_APP_DIR"] = bundle.path

        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, "-u", bundle.abs_entry],
            cwd=bundle.path,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._processes[app_id] = proc
        return proc

    def stop_app(self, app_id):
        proc = self._processes.get(app_id)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._processes.pop(app_id, None)
        return True

    def delete_app(self, app_id):
        bundle = self._apps.get(app_id)
        if bundle is None:
            return False
        self.stop_app(app_id)
        shutil.rmtree(bundle.path, ignore_errors=True)
        self._apps.pop(app_id, None)
        return True

    def import_app(self, source_path, new_name=None):
        source_path = os.path.abspath(source_path)
        if os.path.isdir(source_path):
            dest = os.path.join(self.root_dir, new_name or os.path.basename(source_path))
            if os.path.exists(dest):
                base = os.path.basename(dest)
                i = 1
                while os.path.exists(dest):
                    dest = os.path.join(self.root_dir, f"{base}_{i}")
                    i += 1
            shutil.copytree(source_path, dest)
            return self.register_app(dest)
        if os.path.isfile(source_path) and source_path.lower().endswith((".zip", ".pyapp")):
            dest = os.path.join(self.root_dir, new_name or os.path.splitext(os.path.basename(source_path))[0])
            if os.path.exists(dest):
                base = os.path.basename(dest)
                i = 1
                while os.path.exists(dest):
                    dest = os.path.join(self.root_dir, f"{base}_{i}")
                    i += 1
            with zipfile.ZipFile(source_path, "r") as zf:
                zf.extractall(dest)
            manifest = os.path.join(dest, "app.json")
            if not os.path.exists(manifest):
                main = next((n for n in ("main.py", "app.py") if os.path.exists(os.path.join(dest, n))), None)
                if main:
                    save_json(manifest, {
                        "title": os.path.basename(dest),
                        "description": "Импортировано в движок приложений",
                        "author": "Guest",
                        "version": "1.0.0",
                        "entry": main,
                    })
            return self.register_app(dest)
        raise ValueError("Поддерживаются только папки и архивы .zip / .pyapp")
