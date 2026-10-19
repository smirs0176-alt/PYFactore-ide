"""Правая панель: библиотеки в коде, мои коды, ИИ-подсказки."""
import ast
import os
import tkinter as tk
from tkinter import messagebox
from tkinter import simpledialog
from tkinter import ttk
from pyfactor.config import ACC, BG, BG2, BG3, DIM, FG, MYCODES, STD, YEL
from pyfactor.core.analysis import ai_suggest
from pyfactor.ui.widgets import ScrollFrame, mkbtn


class PanelsMixin:
    # ---------- правая панель
    def build_right(self, f):
        row = tk.Frame(f, bg=BG2)
        row.pack(fill="x", padx=6, pady=8)
        self.panels, self.panel_btns = {}, {}
        for key, txt in (("libs", "📦 Библиотеки"), ("codes", "🗂 Мои коды"), ("ai", "🤖 ИИ"), ("acc", "👤 Аккаунт")):
            b = mkbtn(row, txt, lambda k=key: self.show_panel(k), padx=6, font=("Segoe UI", 9, "bold"))
            b.pack(side="left", padx=2, fill="x", expand=True)
            self.panel_btns[key] = b
        self.panel_host = tk.Frame(f, bg=BG2)
        self.panel_host.pack(fill="both", expand=True)
        for key in ("libs", "codes", "ai", "acc"):
            self.panels[key] = tk.Frame(self.panel_host, bg=BG2)
        self.build_used_panel()
        self.build_codes_panel()
        self.build_ai_panel()
        self.refresh_account()
        self.show_panel("libs")

    def show_panel(self, key):
        for k, p in self.panels.items():
            p.pack_forget()
            self.panel_btns[k].config(bg=ACC if k == key else BG3)
        self.panels[key].pack(fill="both", expand=True)
        if key == "ai":
            self.refresh_ai()
        if key == "codes":
            self.refresh_codes()

    # --- библиотеки в этом коде
    def build_used_panel(self):
        p = self.panels["libs"]
        tk.Label(p, text="Библиотеки в этом коде", bg=BG2, fg="#ffffff", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(p, text="Двойной клик — перейти к import", bg=BG2, fg=DIM, font=("Segoe UI", 9)).pack(anchor="w", padx=12)
        self.used = ttk.Treeview(p, columns=("kind", "line"), show="tree headings", height=14)
        self.used.heading("#0", text="Модуль")
        self.used.heading("kind", text="Тип")
        self.used.heading("line", text="Строка")
        self.used.column("#0", width=130)
        self.used.column("kind", width=90, anchor="center")
        self.used.column("line", width=50, anchor="center")
        self.used.pack(fill="both", expand=True, padx=8, pady=8)
        self.used.bind("<Double-1>", lambda e: self._used_open())

    def _used_open(self):
        sel = self.used.selection()
        if sel:
            self.editor.goto(int(self.used.item(sel[0], "values")[1]))

    def refresh_used(self, res):
        self.used.delete(*self.used.get_children())
        tree = res.get("tree")
        if not tree:
            return
        local = set()
        for d in self.import_paths():
            try:
                for n in os.listdir(d):
                    if n.endswith(".py"):
                        local.add(n[:-3])
            except OSError:
                pass
        seen = set()
        for n in ast.walk(tree):
            names = []
            if isinstance(n, ast.Import):
                names = [a.name.split(".")[0] for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                names = [n.module.split(".")[0]]
            for nm in names:
                if nm in seen:
                    continue
                seen.add(nm)
                kind = "встроенная" if nm in STD else ("своя" if nm in local else "внешняя")
                self.used.insert("", "end", text=nm, values=(kind, n.lineno))

    # --- мои коды
    def build_codes_panel(self):
        p = self.panels["codes"]
        tk.Label(p, text="Библиотека твоих кодов", bg=BG2, fg="#ffffff", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(p, text="Сюда собираются все твои сохранённые коды", bg=BG2, fg=DIM, font=("Segoe UI", 9)).pack(anchor="w", padx=12)
        self.codes_lb = tk.Listbox(p, bg=BG, fg=FG, selectbackground=ACC, relief="flat", bd=0, highlightthickness=0,
                                   font=("Segoe UI", 10), activestyle="none")
        self.codes_lb.pack(fill="both", expand=True, padx=8, pady=8)
        row = tk.Frame(p, bg=BG2)
        row.pack(fill="x", padx=8, pady=(0, 4))
        mkbtn(row, "💾 Сохранить текущий", self.codes_save, bg=ACC, fg="#ffffff").pack(side="left", fill="x", expand=True)
        row2 = tk.Frame(p, bg=BG2)
        row2.pack(fill="x", padx=8, pady=(0, 10))
        mkbtn(row2, "Открыть", lambda: self.codes_use("open")).pack(side="left", padx=2)
        mkbtn(row2, "Вставить", lambda: self.codes_use("insert")).pack(side="left", padx=2)
        mkbtn(row2, "Удалить", lambda: self.codes_use("del")).pack(side="left", padx=2)

    def refresh_codes(self):
        self.codes_lb.delete(0, "end")
        for n in sorted(os.listdir(MYCODES)):
            if n.endswith(".py"):
                self.codes_lb.insert("end", n)

    def codes_save(self):
        default = os.path.basename(self.cur_file) if self.cur_file else "code.py"
        name = simpledialog.askstring("Сохранить в библиотеку", "Название кода:", initialvalue=default, parent=self)
        if not name:
            return
        if not name.endswith(".py"):
            name += ".py"
        with open(os.path.join(MYCODES, os.path.basename(name)), "w", encoding="utf-8") as f:
            f.write(self.editor.get_code())
        self.refresh_codes()
        self.toast("Сохранено в библиотеку: " + name)

    def codes_use(self, action):
        sel = self.codes_lb.curselection()
        if not sel:
            return
        name = self.codes_lb.get(sel[0])
        path = os.path.join(MYCODES, name)
        if action == "del":
            if messagebox.askyesno("Удалить", "Удалить %s из библиотеки?" % name, parent=self):
                os.remove(path)
                self.refresh_codes()
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
        if action == "open":
            self.tab_open(None, data, title=name + " (из библиотеки)")
            self.nb.select(self.tab_code)
            self.title("PyFactor IDE — %s (из библиотеки)" % name)
        else:
            self.editor.text.insert("insert", data)

    # --- ИИ
    def build_ai_panel(self):
        p = self.panels["ai"]
        tk.Label(p, text="PyFactor AI", bg=BG2, fg="#ffffff", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(p, text="Подсказывает, что добавить в код", bg=BG2, fg=DIM, font=("Segoe UI", 9)).pack(anchor="w", padx=12)
        mkbtn(p, "🔍 Подсказать", self.refresh_ai, bg=ACC, fg="#ffffff").pack(fill="x", padx=10, pady=8)
        self.ai_sf = ScrollFrame(p, bg=BG2)
        self.ai_sf.pack(fill="both", expand=True, padx=6, pady=(0, 8))

    def refresh_ai(self):
        sf = self.ai_sf
        sf.clear()
        for title, text, action in ai_suggest(self.editor.get_code()):
            card = tk.Frame(sf.inner, bg=BG3)
            card.pack(fill="x", pady=4, padx=4)
            tk.Label(card, text=title, bg=BG3, fg=YEL, font=("Segoe UI", 10, "bold"), anchor="w", wraplength=270,
                     justify="left").pack(fill="x", padx=10, pady=(8, 0))
            tk.Label(card, text=text, bg=BG3, fg=FG, font=("Segoe UI", 9), anchor="w", wraplength=270,
                     justify="left").pack(fill="x", padx=10, pady=(2, 6))
            if action:
                mkbtn(card, "＋ Добавить", lambda a=action: self.apply_ai(a), bg=ACC, fg="#ffffff").pack(anchor="e", padx=10, pady=(0, 8))

    def apply_ai(self, action):
        self.editor.replace_all(action(self.editor.get_code()))
        self.after(350, self.refresh_ai)
