"""Вкладка Library: каталог библиотек."""
import re
import tkinter as tk
from tkinter import simpledialog

from pyfactor import config
from pyfactor.config import ACC, BG, BG2, BG3, BLUE, DIM, FG, GREEN, LIBS, SETTINGS_F, YEL
from pyfactor.core.python.analysis import add_import
from pyfactor.core.utils import save_json
from pyfactor.ui.widgets import ScrollFrame, mkbtn


class LibraryMixin:
    # ---------- вкладка Library
    def build_library(self):
        f = self.tab_lib
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=14, pady=12)
        tk.Label(top, text="Каталог библиотек", bg=BG, fg="#ffffff", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(top, text="Нажми ＋ — в код добавится import (Python) или ссылка в <head> (Web). Ничего устанавливать не нужно.", bg=BG, fg=DIM).pack(anchor="w")
        row = tk.Frame(top, bg=BG)
        row.pack(fill="x", pady=8)
        e = tk.Entry(row, textvariable=self.lib_search, bg=BG3, fg=FG, insertbackground="#ffffff", relief="flat",
                     font=("Segoe UI", 11))
        e.pack(side="left", fill="x", expand=True, ipady=5)
        self.lib_search.trace_add("write", lambda *a: self.render_libs())
        for txt, val in (("Все", "all"), ("Встроенные", "std"), ("Внешние", "ext"), ("Web", "web")):
            tk.Radiobutton(row, text=txt, variable=self.lib_filter, value=val, indicatoron=0, bg=BG3, fg=FG,
                           selectcolor=ACC, relief="flat", padx=10, pady=4, bd=0, command=self.render_libs).pack(side="left", padx=3)
        mkbtn(row, "＋ Своя", self.add_custom_lib, bg=ACC, fg="#ffffff").pack(side="left", padx=(10, 0))
        self.lib_sf = ScrollFrame(f, bg=BG)
        self.lib_sf.pack(fill="both", expand=True, padx=10)
        self.render_libs()

    def render_libs(self):
        sf = self.lib_sf
        sf.clear()
        q, flt = self.lib_search.get().strip().lower(), self.lib_filter.get()
        for name, imp, desc, kind in self.all_libs():
            if flt != "all" and kind != flt:
                continue
            if q and q not in name.lower() and q not in desc.lower():
                continue
            card = tk.Frame(sf.inner, bg=BG2)
            card.pack(fill="x", pady=3, padx=4)
            info = tk.Frame(card, bg=BG2)
            info.pack(side="left", fill="x", expand=True, padx=10, pady=6)
            line1 = tk.Frame(info, bg=BG2)
            line1.pack(anchor="w")
            tk.Label(line1, text=name, bg=BG2, fg=BLUE, font=("Segoe UI", 11, "bold")).pack(side="left")
            badge = {"std": ("  встроенная", GREEN), "ext": ("  внешняя", YEL), "web": ("  для сайта", BLUE)}[kind]
            tk.Label(line1, text=badge[0], bg=BG2, fg=badge[1], font=("Segoe UI", 8)).pack(side="left")
            tk.Label(info, text=desc, bg=BG2, fg=DIM, font=("Segoe UI", 9)).pack(anchor="w")
            tk.Label(info, text=imp if len(imp) < 72 else imp[:70] + "…", bg=BG2, fg="#c3e88d",
                     font=(config.MONO, 10)).pack(anchor="w")
            mkbtn(card, "＋", lambda n=name, l=imp, k=kind: self.add_lib(n, l, k), bg=ACC, fg="#ffffff", width=3,
                  font=("Segoe UI", 14, "bold")).pack(side="right", padx=10, pady=8)
            if [name, imp, desc, kind] in self.settings.get("custom_libs", []):
                mkbtn(card, "✕", lambda n=name: self.remove_custom_lib(n), padx=6).pack(side="right")

    def add_import_line(self, line):
        code = self.editor.get_code()
        if re.search(r"^\s*" + re.escape(line) + r"\s*$", code, re.M):
            self.toast("Уже есть: " + line)
            return
        self.editor.replace_all(add_import(code, line))
        self.toast("Добавлено: " + line)

    # ---------- свои библиотеки и Web-ссылки
    def all_libs(self):
        return list(LIBS) + [tuple(x) for x in self.settings.get("custom_libs", [])]

    def add_lib(self, name, line, kind):
        if kind == "web":
            self.add_web_snippet(line)
        else:
            self.add_import_line(line)

    def add_web_snippet(self, snippet):
        lang, code = self.editor.lang, self.editor.get_code()
        if snippet in code:
            self.toast("Уже подключено")
            return
        if lang == "html":
            m = re.search(r"</head\s*>", code, re.I)
            if m:
                before = code[:m.start()]
                new = before + ("" if before.endswith("\n") or not before else "\n") + "    " + snippet + "\n" + code[m.start():]
            else:
                new = snippet + "\n" + code
            self.editor.replace_all(new)
            self.toast("Подключено в <head>")
        elif lang == "css":
            href = re.search(r'href="([^"]+)"', snippet)
            if not href:
                self.toast("Скрипты подключаются в HTML-файле, не в CSS")
                return
            line = '@import url("%s");\n' % href.group(1)
            lines = code.split("\n", 1)
            if lines[0].startswith("@charset"):
                new = lines[0] + "\n" + line + (lines[1] if len(lines) > 1 else "")
            else:
                new = line + code
            self.editor.replace_all(new)
            self.toast("Добавлен @import")
        else:
            self.toast("Открой файл .html — туда подключаются Web-библиотеки")

    def add_custom_lib(self):
        name = simpledialog.askstring("Своя библиотека", "Название:", parent=self)
        if not name:
            return
        line = simpledialog.askstring("Своя библиотека",
                                      "Что вставлять в код?\nНапример: import mylib   или   <script src=\"...\"></script>",
                                      parent=self)
        if not line:
            return
        desc = simpledialog.askstring("Своя библиотека", "Короткое описание (можно пустое):", parent=self) or "Моя библиотека"
        kind = "web" if line.lstrip().startswith(("<", "@import")) else "ext"
        self.settings.setdefault("custom_libs", []).append([name.strip(), line.strip(), desc.strip(), kind])
        save_json(SETTINGS_F, self.settings, private=True)
        self.lib_filter.set("all")
        self.render_libs()
        self.toast("Библиотека добавлена: " + name.strip())

    def remove_custom_lib(self, name):
        self.settings["custom_libs"] = [x for x in self.settings.get("custom_libs", []) if x[0] != name]
        save_json(SETTINGS_F, self.settings, private=True)
        self.render_libs()

