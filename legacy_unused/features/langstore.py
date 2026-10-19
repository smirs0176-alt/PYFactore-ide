"""Вкладка «Языки»: выбираешь язык → анимация скачивания → установка → сразу открывается Mystery.<расширение>."""
import os
import shutil
import sys
import time
import tkinter as tk

from pyfactor.config import ACC, BG, BG2, BG3, BLUE, DIM, FG, GREEN, SETTINGS_F
from pyfactor.core import packs
from pyfactor.core.packs import PACKS
from pyfactor.core.utils import save_json
from pyfactor.ui.widgets import ScrollFrame, mkbtn

BAR = 170


class LangStoreMixin:
    def build_langstore(self):
        for pid in self.settings.get("packs", []):
            if pid in PACKS:
                packs.install(pid)
        f = self.tab_langs = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="🌍  Языки")
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=14, pady=12)
        tk.Label(top, text="Магазин языков", bg=BG, fg="#ffffff", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(top, text="Нажми «Скачать» — язык установится, и сразу откроется файл Mystery с примером.",
                 bg=BG, fg=DIM).pack(anchor="w")
        self.pack_sf = ScrollFrame(f, bg=BG)
        self.pack_sf.pack(fill="both", expand=True, padx=10)
        self._pw, self._dl = {}, set()
        self.render_packs()

    def render_packs(self):
        sf = self.pack_sf
        sf.clear()
        self._pw = {}
        for pid, p in PACKS.items():
            card = tk.Frame(sf.inner, bg=BG2)
            card.pack(fill="x", pady=3, padx=4)
            tk.Label(card, text=p["icon"], bg=BG2, font=("Segoe UI Emoji", 22)).pack(side="left", padx=12, pady=8)
            info = tk.Frame(card, bg=BG2)
            info.pack(side="left", fill="x", expand=True, pady=6)
            line = tk.Frame(info, bg=BG2)
            line.pack(anchor="w")
            inst = pid in packs.INSTALLED
            tk.Label(line, text=p["name"], bg=BG2, fg=BLUE, font=("Segoe UI", 11, "bold")).pack(side="left")
            tk.Label(line, text="  ✓ установлен" if inst else "  " + p["ext"], bg=BG2, fg=GREEN if inst else DIM,
                     font=("Segoe UI", 8)).pack(side="left")
            tk.Label(info, text=p["desc"], bg=BG2, fg=DIM, font=("Segoe UI", 9), wraplength=260, justify="left").pack(anchor="w")
            right = tk.Frame(card, bg=BG2)
            right.pack(side="right", padx=10)
            if pid in self._dl:
                c = tk.Canvas(right, width=BAR, height=14, bg=BG3, highlightthickness=0)
                c.pack()
                lb = tk.Label(right, bg=BG2, fg=FG, font=("Segoe UI", 8))
                lb.pack()
                self._pw[pid] = (c, lb)
            elif inst:
                mkbtn(right, "📂 Mystery" + p["ext"], lambda i=pid: self.open_mystery(i), bg=ACC, fg="#ffffff").pack(pady=2)
                mkbtn(right, "Удалить", lambda i=pid: self.remove_pack(i), padx=6).pack()
            else:
                mkbtn(right, "⬇ Скачать", lambda i=pid: self.download_pack(i), bg=ACC, fg="#ffffff").pack(pady=10)

    def download_pack(self, pid):
        if pid in self._dl:
            return
        self._dl.add(pid)
        self.render_packs()
        t0, dur = time.time(), 3.2

        def tick():
            k = min(1.0, (time.time() - t0) / dur)
            pct = int(100 * (1 - (1 - k) ** 1.6))
            w = self._pw.get(pid)
            if w:
                c, lb = w
                fill = BAR * pct / 100
                c.delete("all")
                c.create_rectangle(0, 0, fill, 14, fill=ACC, width=0)
                off = int((time.time() - t0) * 120) % 40
                for x in range(off - 40, int(fill), 40):
                    if min(x + 12, fill) > max(x, 0):
                        c.create_rectangle(max(x, 0), 0, min(x + 12, fill), 14, fill="#9d86ff", width=0)
                lb.config(text="Подключение…" if k < .08 else "Скачивание… %d%%" % pct if k < .75 else
                          "Распаковка…" if k < .92 else "Установка…")
            if k < 1:
                self.after(40, tick)
            else:
                self._pack_done(pid)
        tick()

    def _pack_done(self, pid):
        packs.install(pid)
        lst = self.settings.setdefault("packs", [])
        if pid not in lst:
            lst.append(pid)
        save_json(SETTINGS_F, self.settings)
        self._dl.discard(pid)
        self.render_packs()
        self.toast("Язык %s установлен!" % PACKS[pid]["name"])
        if hasattr(self, "log"):
            self.log("установлен язык " + PACKS[pid]["name"])
        self.open_mystery(pid)

    def open_mystery(self, pid):
        p = PACKS[pid]
        path = os.path.join(self._target_dir(), "Mystery" + p["ext"])
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(p["tpl"])
        self.refresh_tree()
        self.open_file(path)
        self.nb.select(self.tab_code)

    def remove_pack(self, pid):
        packs.uninstall(pid)
        self.settings["packs"] = [x for x in self.settings.get("packs", []) if x != pid]
        save_json(SETTINGS_F, self.settings)
        self.render_packs()
        self.toast("Язык %s удалён" % PACKS[pid]["name"])

    def run_pack(self, pid):
        p = PACKS[pid]
        for cmd in p["run"]:
            if shutil.which(cmd[0]):
                self.spawn(self.cur_file, self.project, cmd=[x.replace("{f}", self.cur_file) for x in cmd])
                return
        if p["run"]:
            self.toast("Не найден %s — установи его на компьютер. Подсветка работает." % p["run"][0][0])
        else:
            self.toast("%s нужно компилировать самому. Подсветка и шаблон работают." % p["name"])
