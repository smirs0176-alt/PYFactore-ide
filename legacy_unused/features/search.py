"""Поиск и замена: Ctrl+F / Ctrl+H в файле, Ctrl+Shift+F по всему проекту."""
import os
import tkinter as tk
from tkinter import ttk
from pyfactor.config import ACC, BG2, BG3, DIM, FG, TEXT_EXT
from pyfactor.ui.widgets import mkbtn

SKIP_DIRS = {"__pycache__", "node_modules", "venv", ".venv", ".git", "site-packages"}
MAX_HITS = 500


class SearchMixin:
    # ---------- панель поиска в редакторе
    def build_findbar(self, parent):
        self.find_var, self.repl_var = tk.StringVar(), tk.StringVar()
        self.find_case = tk.BooleanVar(value=False)
        self.find_visible = False
        self.findbar = tk.Frame(parent, bg=BG2)
        top = tk.Frame(self.findbar, bg=BG2)
        top.pack(fill="x", padx=8, pady=(6, 2))
        self.find_entry = tk.Entry(top, textvariable=self.find_var, bg=BG3, fg=FG, insertbackground="#ffffff",
                                   relief="flat", width=28, font=("Segoe UI", 10))
        self.find_entry.pack(side="left", ipady=3)
        mkbtn(top, "▲", lambda: self.find_next(-1), padx=7, pady=1).pack(side="left", padx=(6, 2))
        mkbtn(top, "▼", lambda: self.find_next(1), padx=7, pady=1).pack(side="left", padx=2)
        tk.Checkbutton(top, text="Aa", variable=self.find_case, command=self.find_refresh, bg=BG2, fg=FG,
                       selectcolor=BG3, activebackground=BG2, activeforeground=FG, bd=0,
                       highlightthickness=0).pack(side="left", padx=6)
        self.find_count = tk.Label(top, text="", bg=BG2, fg=DIM, font=("Segoe UI", 9))
        self.find_count.pack(side="left", padx=6)
        mkbtn(top, "✕", self.hide_find, padx=7, pady=1).pack(side="right")
        self.repl_row = tk.Frame(self.findbar, bg=BG2)
        self.repl_entry = tk.Entry(self.repl_row, textvariable=self.repl_var, bg=BG3, fg=FG,
                                   insertbackground="#ffffff", relief="flat", width=28, font=("Segoe UI", 10))
        self.repl_entry.pack(side="left", ipady=3)
        mkbtn(self.repl_row, "Заменить", self.replace_one, padx=8, pady=1).pack(side="left", padx=(6, 2))
        mkbtn(self.repl_row, "Все", self.replace_all_matches, padx=8, pady=1).pack(side="left", padx=2)

        t = self.editor.text
        t.tag_configure("find", background="#3b3f5c")
        t.tag_configure("findcur", background=ACC, foreground="#ffffff")
        self.find_entry.bind("<KeyRelease>", lambda e: self.find_refresh(jump=e.keysym not in ("Return", "Escape")))
        self.find_entry.bind("<Return>", lambda e: self.find_next(1))
        self.find_entry.bind("<Shift-Return>", lambda e: self.find_next(-1))
        self.repl_entry.bind("<Return>", lambda e: self.replace_one())
        for w in (self.find_entry, self.repl_entry):
            w.bind("<Escape>", lambda e: self.hide_find())
        t.bind("<Escape>", lambda e: self.hide_find() if self.find_visible else None)
        for key in ("<Control-f>", "<Control-F>", "<Command-f>"):
            t.bind(key, lambda e: self.show_find(False))
            self.find_entry.bind(key, lambda e: self.show_find(False))
        for key in ("<Control-h>", "<Control-H>", "<Command-h>"):
            t.bind(key, lambda e: self.show_find(True))
            self.find_entry.bind(key, lambda e: self.show_find(True))
        t.bind("<F3>", lambda e: self.find_next(1))
        t.bind("<Shift-F3>", lambda e: self.find_next(-1))
        self.bind_all("<Control-Shift-F>", lambda e: self.project_search())

    def show_find(self, replace=False):
        self.nb.select(self.tab_code)
        t = self.editor.text
        if not self.find_visible:
            self.findbar.pack(fill="x", before=self.editor)
            self.find_visible = True
        if replace:
            self.repl_row.pack(fill="x", padx=8, pady=(0, 6))
        else:
            self.repl_row.pack_forget()
        try:
            sel = t.get("sel.first", "sel.last")
            if sel and "\n" not in sel:
                self.find_var.set(sel)
        except tk.TclError:
            pass
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")
        self.find_refresh()
        return "break"

    def hide_find(self):
        if not self.find_visible:
            return
        self.findbar.pack_forget()
        self.find_visible = False
        for tag in ("find", "findcur"):
            self.editor.text.tag_remove(tag, "1.0", "end")
        self.editor.text.focus_set()

    # ---------- поиск
    def _find_all(self):
        q = self.find_var.get()
        t = self.editor.text
        res, pos = [], "1.0"
        if not q:
            return res
        nocase = not self.find_case.get()
        while len(res) < 5000:
            i = t.search(q, pos, stopindex="end", nocase=nocase)
            if not i:
                break
            j = "%s+%dc" % (i, len(q))
            res.append((i, j))
            pos = j
        return res

    def find_refresh(self, jump=False):
        if not getattr(self, "find_visible", False):
            return
        t = self.editor.text
        for tag in ("find", "findcur"):
            t.tag_remove(tag, "1.0", "end")
        hits = self._find_all()
        for a, b in hits:
            t.tag_add("find", a, b)
        if not self.find_var.get():
            self.find_count.config(text="")
        elif not hits:
            self.find_count.config(text="нет совпадений", fg="#ff5370")
        else:
            self.find_count.config(text="найдено: %d" % len(hits), fg=DIM)
            if jump:
                self.find_next(1, from_start=True)

    def find_next(self, step=1, from_start=False):
        t = self.editor.text
        hits = self._find_all()
        if not hits:
            return "break"
        cur = t.index("insert")
        if from_start:
            try:
                cur = t.index("sel.first")
            except tk.TclError:
                pass
        pick = None
        if step > 0:
            for a, b in hits:
                if t.compare(a, ">=" if from_start else ">", cur):
                    pick = (a, b)
                    break
            pick = pick or hits[0]
        else:
            for a, b in reversed(hits):
                if t.compare(a, "<", cur):
                    pick = (a, b)
                    break
            pick = pick or hits[-1]
        a, b = pick
        t.tag_remove("findcur", "1.0", "end")
        t.tag_add("findcur", a, b)
        t.tag_remove("sel", "1.0", "end")
        t.tag_add("sel", a, b)
        t.mark_set("insert", a)
        t.see(a)
        n = hits.index(pick) + 1
        self.find_count.config(text="%d из %d" % (n, len(hits)), fg=DIM)
        self.update_pos()
        return "break"

    # ---------- замена
    def replace_one(self):
        t = self.editor.text
        try:
            a, b = t.index("sel.first"), t.index("sel.last")
        except tk.TclError:
            self.find_next(1)
            return
        q = self.find_var.get()
        chosen = t.get(a, b)
        if q and (chosen == q if self.find_case.get() else chosen.lower() == q.lower()):
            t.edit_separator()
            t.delete(a, b)
            t.insert(a, self.repl_var.get())
            t.edit_separator()
            t.mark_set("insert", "%s+%dc" % (a, len(self.repl_var.get())))
            self.editor.schedule(0)
        self.find_refresh()
        self.find_next(1)

    def replace_all_matches(self):
        t = self.editor.text
        hits = self._find_all()
        if not hits:
            return
        new = self.repl_var.get()
        t.edit_separator()
        for a, b in reversed(hits):          # с конца, чтобы индексы не сдвигались
            t.delete(a, b)
            t.insert(a, new)
        t.edit_separator()
        self.editor.schedule(0)
        self.find_refresh()
        self.toast("Заменено: %d" % len(hits))

    # ---------- поиск по проекту
    def project_search(self):
        if not self.project:
            return
        if getattr(self, "psearch", None) and self.psearch.winfo_exists():
            self.psearch.lift()
            self.ps_entry.focus_set()
            return
        w = self.psearch = tk.Toplevel(self)
        w.title("Поиск по проекту")
        w.geometry("720x460")
        w.configure(bg=BG2)
        w.transient(self)
        top = tk.Frame(w, bg=BG2)
        top.pack(fill="x", padx=10, pady=10)
        self.ps_var, self.ps_case = tk.StringVar(), tk.BooleanVar(value=False)
        e = self.ps_entry = tk.Entry(top, textvariable=self.ps_var, bg=BG3, fg=FG, insertbackground="#ffffff",
                                     relief="flat", font=("Segoe UI", 11))
        e.pack(side="left", fill="x", expand=True, ipady=4)
        tk.Checkbutton(top, text="Aa", variable=self.ps_case, bg=BG2, fg=FG, selectcolor=BG3,
                       activebackground=BG2, activeforeground=FG, bd=0, highlightthickness=0).pack(side="left", padx=8)
        mkbtn(top, "🔍 Найти", self.run_project_search, bg=ACC, fg="#ffffff").pack(side="left")
        self.ps_info = tk.Label(w, text="Введи текст и нажми Enter", bg=BG2, fg=DIM, anchor="w", font=("Segoe UI", 9))
        self.ps_info.pack(fill="x", padx=12)
        self.ps_tree = ttk.Treeview(w, columns=("where", "text"), show="headings", selectmode="browse")
        self.ps_tree.heading("where", text="Файл : строка")
        self.ps_tree.heading("text", text="Строка")
        self.ps_tree.column("where", width=220, stretch=False)
        self.ps_tree.column("text", width=460)
        self.ps_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.ps_hits = {}
        e.bind("<Return>", lambda ev: self.run_project_search())
        e.bind("<Escape>", lambda ev: w.destroy())
        self.ps_tree.bind("<Double-1>", self.project_search_open)
        self.ps_tree.bind("<Return>", self.project_search_open)
        e.focus_set()

    def run_project_search(self):
        q = self.ps_var.get()
        tree = self.ps_tree
        tree.delete(*tree.get_children())
        self.ps_hits = {}
        if not q:
            return
        self._stash()
        open_buf = {t["path"]: t["code"] for t in self.tabs if t["path"]}   # учитываем несохранённые правки
        needle = q if self.ps_case.get() else q.lower()
        files = 0
        for root, dirs, names in os.walk(self.project):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for n in sorted(names):
                ext = os.path.splitext(n)[1].lower()
                if ext not in TEXT_EXT:
                    continue
                p = os.path.join(root, n)
                text = open_buf.get(p)
                if text is None:
                    try:
                        if os.path.getsize(p) > 1_000_000:
                            continue
                        with open(p, "r", encoding="utf-8", errors="replace") as f:
                            text = f.read()
                    except OSError:
                        continue
                files += 1
                for ln, line in enumerate(text.split("\n"), 1):
                    hay = line if self.ps_case.get() else line.lower()
                    if needle in hay:
                        rel = os.path.relpath(p, self.project)
                        iid = tree.insert("", "end", values=("%s : %d" % (rel, ln), line.strip()[:200]))
                        self.ps_hits[iid] = (p, ln)
                        if len(self.ps_hits) >= MAX_HITS:
                            self.ps_info.config(text="Показаны первые %d совпадений" % MAX_HITS)
                            return
        n = len(self.ps_hits)
        self.ps_info.config(text=("Найдено: %d  (файлов проверено: %d)" % (n, files)) if n else "Ничего не найдено")

    def project_search_open(self, e=None):
        sel = self.ps_tree.selection()
        if not sel or sel[0] not in self.ps_hits:
            return
        path, ln = self.ps_hits[sel[0]]
        self.open_file(path)
        self.find_var.set(self.ps_var.get())
        self.find_case.set(self.ps_case.get())
        self.show_find(False)
        self.editor.goto(ln)
