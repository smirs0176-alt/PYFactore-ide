"""Центр игр."""
import os
import re
import shutil
import tempfile
import time
import tkinter as tk
import urllib.error
import urllib.request
import zipfile
from tkinter import filedialog, messagebox, simpledialog, ttk

from pyfactor.config import ACC, BG, DIM, GAMES, GREEN
from pyfactor.core.utils import load_json, save_json
from pyfactor.ui.widgets import mkbtn


class GamesMixin:
    # ---------- Центр игр
    def build_games(self):
        f = self.tab_games
        tk.Label(f, text="Центр игр", bg=BG, fg="#ffffff", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
        tk.Label(f, text="Выкладывай свои игры на Python и запускай чужие. Делись файлом .pyfgame или ссылкой на .py.",
                 bg=BG, fg=DIM).pack(anchor="w", padx=14)
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=14, pady=8)
        mkbtn(row, "⬆ Выложить текущий проект", self.game_publish, bg=ACC, fg="#ffffff").pack(side="left", padx=2)
        mkbtn(row, "🎮 Играть", self.game_play, bg=GREEN, fg="#102018").pack(side="left", padx=2)
        mkbtn(row, "📤 Экспорт", self.game_export).pack(side="left", padx=2)
        mkbtn(row, "📥 Импорт", self.game_import).pack(side="left", padx=2)
        mkbtn(row, "🗑", self.game_delete).pack(side="left", padx=2)
        self.games_tv = ttk.Treeview(f, columns=("author", "date", "desc"), show="tree headings")
        self.games_tv.heading("#0", text="Игра")
        self.games_tv.heading("author", text="Автор")
        self.games_tv.heading("date", text="Дата")
        self.games_tv.heading("desc", text="Описание")
        self.games_tv.column("#0", width=200)
        self.games_tv.column("author", width=120)
        self.games_tv.column("date", width=100)
        self.games_tv.column("desc", width=360)
        self.games_tv.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.games_tv.bind("<Double-1>", lambda e: self.game_play())
        self.refresh_games()

    def refresh_games(self):
        self.games_tv.delete(*self.games_tv.get_children())
        for gid in sorted(os.listdir(GAMES)):
            meta = load_json(os.path.join(GAMES, gid, "meta.json"), None)
            if meta:
                self.games_tv.insert("", "end", iid=gid, text="🎮 " + meta.get("title", gid),
                                     values=(meta.get("author", "?"), meta.get("date", ""), meta.get("desc", "")))

    def _selected_game(self):
        sel = self.games_tv.selection()
        if not sel:
            messagebox.showinfo("Игры", "Выбери игру в списке.", parent=self)
            return None
        return sel[0]

    def game_publish(self):
        if not self.project or not self.cur_file:
            messagebox.showinfo("Игры", "Открой главный файл игры (.py) и нажми снова.", parent=self)
            return
        self.save_file()
        title = simpledialog.askstring("Выложить игру", "Название игры:", initialvalue=os.path.basename(self.project), parent=self)
        if not title:
            return
        desc = simpledialog.askstring("Выложить игру", "Короткое описание:", parent=self) or ""
        gid = re.sub(r"[^\w-]", "_", title) + "_" + str(int(time.time()))
        dest = os.path.join(GAMES, gid)
        shutil.copytree(self.project, os.path.join(dest, "files"),
                        ignore=shutil.ignore_patterns(".*", "__pycache__"))
        save_json(os.path.join(dest, "meta.json"), {
            "title": title, "desc": desc, "author": self.account.get("name", "Гость"),
            "date": time.strftime("%d.%m.%Y"), "main": os.path.relpath(self.cur_file, self.project)})
        self.refresh_games()
        self.toast("Игра выложена в Центр игр")

    def game_play(self):
        gid = self._selected_game()
        if not gid:
            return
        meta = load_json(os.path.join(GAMES, gid, "meta.json"), {})
        base = os.path.join(GAMES, gid, "files")
        script = os.path.join(base, meta.get("main", "main.py"))
        if os.path.isfile(script):
            self.spawn(script, base)
        else:
            messagebox.showerror("Игры", "Не найден файл запуска.", parent=self)

    def game_export(self):
        gid = self._selected_game()
        if not gid:
            return
        out = filedialog.asksaveasfilename(defaultextension=".pyfgame", initialfile=gid + ".pyfgame",
                                           filetypes=[("PyFactor game", "*.pyfgame")], parent=self)
        if not out:
            return
        base = os.path.join(GAMES, gid)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(base):
                for fn in files:
                    full = os.path.join(root, fn)
                    z.write(full, os.path.relpath(full, base))
        self.toast("Экспортировано: " + os.path.basename(out))

    def game_import(self):
        src = simpledialog.askstring("Импорт", "Ссылка на .py / .pyfgame\n(оставь пустым, чтобы выбрать файл):", parent=self)
        try:
            if src:
                if not src.strip().lower().startswith(("http://", "https://")):
                    raise ValueError("Нужна ссылка http:// или https://")
                data = urllib.request.urlopen(src.strip(), timeout=30).read(5_000_000)  # noqa: S310 — схема проверена выше
                name = os.path.basename(src.split("?")[0]) or "game.py"
                if name.endswith(".py"):
                    gid = re.sub(r"\W", "_", name[:-3]) + "_" + str(int(time.time()))
                    d = os.path.join(GAMES, gid, "files")
                    os.makedirs(d)
                    with open(os.path.join(d, name), "wb") as f:
                        f.write(data)
                    save_json(os.path.join(GAMES, gid, "meta.json"), {
                        "title": name[:-3], "desc": "Импорт по ссылке", "author": "?", "date": time.strftime("%d.%m.%Y"), "main": name})
                else:
                    tmp = os.path.join(tempfile.gettempdir(), "imp.pyfgame")
                    with open(tmp, "wb") as f:
                        f.write(data)
                    self._import_zip(tmp)
            else:
                p = filedialog.askopenfilename(filetypes=[("PyFactor game", "*.pyfgame"), ("Python", "*.py")], parent=self)
                if not p:
                    return
                if p.endswith(".py"):
                    gid = re.sub(r"\W", "_", os.path.basename(p)[:-3]) + "_" + str(int(time.time()))
                    d = os.path.join(GAMES, gid, "files")
                    os.makedirs(d)
                    shutil.copy(p, d)
                    save_json(os.path.join(GAMES, gid, "meta.json"), {
                        "title": os.path.basename(p)[:-3], "desc": "Импорт файла", "author": "?",
                        "date": time.strftime("%d.%m.%Y"), "main": os.path.basename(p)})
                else:
                    self._import_zip(p)
        except Exception as e:
            messagebox.showerror("Импорт", "Не получилось: %s" % e, parent=self)
            return
        self.refresh_games()
        self.toast("Игра импортирована")

    def _import_zip(self, path):
        gid = "imp_" + str(int(time.time()))
        dest = os.path.join(GAMES, gid)
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in n.split("/"):
                    raise ValueError("небезопасный архив")
            z.extractall(dest)

    def game_delete(self):
        gid = self._selected_game()
        if gid and messagebox.askyesno("Удалить", "Удалить игру из Центра?", parent=self):
            shutil.rmtree(os.path.join(GAMES, gid), ignore_errors=True)
            self.refresh_games()
