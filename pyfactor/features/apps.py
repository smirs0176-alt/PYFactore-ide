"""Центр приложений PyFactor."""

import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from pyfactor.config import ACC, BG, DIM, GREEN
from pyfactor.core.utils import save_json
from pyfactor.ui.widgets import mkbtn


class AppsMixin:
    def build_apps(self):
        f = self.tab_apps
        tk.Label(f, text="Центр приложений", bg=BG, fg="#ffffff", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
        tk.Label(f, text="Хранилище, запуск и импорт готовых приложений для PyFactor.", bg=BG, fg=DIM).pack(anchor="w", padx=14)
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=14, pady=8)
        mkbtn(row, "➕ Опубликовать", self.app_publish, bg=ACC, fg="#ffffff").pack(side="left", padx=2)
        mkbtn(row, "▶ Запустить", self.app_run, bg=GREEN, fg="#102018").pack(side="left", padx=2)
        mkbtn(row, "📥 Импорт", self.app_import).pack(side="left", padx=2)
        mkbtn(row, "🗑 Удалить", self.app_delete).pack(side="left", padx=2)

        self._app_icons = {}
        self.apps_tv = ttk.Treeview(f, columns=("author", "version", "desc"), show="tree headings")
        self.apps_tv.heading("#0", text="Приложение")
        self.apps_tv.heading("author", text="Автор")
        self.apps_tv.heading("version", text="Версия")
        self.apps_tv.heading("desc", text="Описание")
        self.apps_tv.column("#0", width=220)
        self.apps_tv.column("author", width=120)
        self.apps_tv.column("version", width=90)
        self.apps_tv.column("desc", width=420)
        self.apps_tv.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.apps_tv.bind("<Double-1>", lambda e: self.app_run())
        self.refresh_apps()

    def _icon_for_app(self, app):
        app_id = app["app_id"]
        if app_id in self._app_icons:
            return self._app_icons[app_id]
        icon_rel = app.get("icon") or ""
        if not icon_rel:
            self._app_icons[app_id] = None
            return None
        path = os.path.join(app["path"], icon_rel.replace("/", os.sep))
        try:
            img = tk.PhotoImage(file=path)
            max_dim = max(img.width(), img.height())
            if max_dim > 32:
                scale = 32 / max_dim
                img = img.subsample(max(1, int(round(1 / scale))))
            self._app_icons[app_id] = img
            return img
        except Exception:
            self._app_icons[app_id] = None
            return None

    def refresh_apps(self):
        self.apps_tv.delete(*self.apps_tv.get_children())
        self._app_icons.clear()
        for app in self.app_engine.list_apps():
            icon = self._icon_for_app(app)
            text = app["title"]
            if not icon:
                text = "📱 " + text
            self.apps_tv.insert(
                "",
                "end",
                iid=app["app_id"],
                text=text,
                image=icon,
                values=(app.get("author", "?"), app.get("version", "1.0.0"), app.get("description", "")),
            )

    def _selected_app(self):
        sel = self.apps_tv.selection()
        if not sel:
            messagebox.showinfo("Приложения", "Выбери приложение в списке.", parent=self)
            return None
        return sel[0]

    def app_publish(self):
        source_dir = self.project or (os.path.dirname(self.cur_file) if self.cur_file else None)
        if not source_dir or not os.path.isdir(source_dir):
            messagebox.showinfo("Приложения", "Сначала открой проект или выбери папку приложения.", parent=self)
            return

        title = simpledialog.askstring("Публикация приложения", "Название приложения:",
                                      initialvalue=os.path.basename(source_dir), parent=self)
        if not title:
            return
        desc = simpledialog.askstring("Публикация приложения", "Короткое описание:", parent=self) or ""
        version = simpledialog.askstring("Публикация приложения", "Версия:", initialvalue="1.0.0", parent=self) or "1.0.0"
        slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", title).strip("_") or "app"
        dest = os.path.join(self.app_engine.root_dir, slug)
        i = 1
        while os.path.exists(dest):
            dest = os.path.join(self.app_engine.root_dir, f"{slug}_{i}")
            i += 1

        shutil.copytree(source_dir, dest, ignore=shutil.ignore_patterns(".*", "__pycache__", ".git"))
        app_json = os.path.join(dest, "app.json")
        entry = "main.py"
        if self.cur_file and os.path.isfile(self.cur_file):
            rel = os.path.relpath(self.cur_file, source_dir)
            if rel and rel.endswith(".py"):
                entry = rel
        if not os.path.exists(os.path.join(dest, entry)):
            for cand in ("main.py", "app.py", "index.py"):
                if os.path.exists(os.path.join(dest, cand)):
                    entry = cand
                    break
        save_json(app_json, {
            "title": title,
            "description": desc,
            "author": self.account.get("name", "Guest"),
            "version": version,
            "entry": entry,
        })
        self.app_engine.register_app(dest)
        self.refresh_apps()
        self.toast("Приложение опубликовано: " + title)

    def app_run(self):
        app_id = self._selected_app()
        if not app_id:
            return
        try:
            proc = self.app_engine.launch_app(app_id)
            self.toast(f"Запускается: {self.app_engine.get_app(app_id)['title']} (PID {proc.pid})")
        except Exception as exc:
            messagebox.showerror("Приложения", f"Не удалось запустить: {exc}", parent=self)

    def app_import(self):
        path = filedialog.askopenfilename(
            title="Импорт приложения",
            filetypes=[("PyFactor App", "*.zip *.pyapp"), ("Папка приложения", "*.*")],
            parent=self,
        )
        if not path:
            return
        try:
            bundle = self.app_engine.import_app(path)
            self.refresh_apps()
            self.toast("Импортировано: " + bundle.title)
        except Exception as exc:
            messagebox.showerror("Приложения", f"Не удалось импортировать: {exc}", parent=self)

    def app_delete(self):
        app_id = self._selected_app()
        if not app_id:
            return
        if not messagebox.askyesno("Удалить приложение", "Удалить это приложение из движка?", parent=self):
            return
        app = self.app_engine.get_app(app_id)
        if app and self.app_engine.delete_app(app_id):
            self.refresh_apps()
            self.toast("Удалено: " + app["title"])
