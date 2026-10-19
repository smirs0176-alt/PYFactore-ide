"""Редактор кода с подсветкой, нумерацией строк и индикатором."""
import difflib
import re
import tkinter as tk
import tkinter.font as tkfont
from bisect import bisect_right
from tkinter import ttk

from pyfactor import config
from pyfactor.config import BG, BG2, BUILTINS, DIM, FG, GREEN, KW, RED, SETTINGS_F, YEL
from pyfactor.core.check import check_code
from pyfactor.core.languages.packs import PACKS
from pyfactor.core.utils import save_json
from pyfactor.core.web.pyg import spans_for_path
from pyfactor.core.web.syntax import spans

TOKEN = re.compile(
    r'(?P<comment>#[^\n]*)'
    r'|(?P<string>[rRbBfFuU]{0,2}(?:"""[\s\S]*?(?:"""|\Z)|' + r"'''[\s\S]*?(?:'''|\Z)" +
    r'|"(?:\\.|[^"\\\n])*"?|' + r"'(?:\\.|[^'\\\n])*'?))" +
    r'|(?P<number>\b\d[\d_]*(?:\.\d+)?\b)'
    r'|(?P<word>[A-Za-z_]\w*)'
    r'|(?P<deco>@[A-Za-z_][\w.]*)')


class Editor(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app, self.job, self.status, self.saved_code = app, None, {}, ""
        self.lang = "python"
        size = getattr(app, "settings", {}).get("font_size", 12)
        self.font = tkfont.Font(family=config.MONO, size=size)
        self.gutter = tk.Canvas(self, width=64, bg=BG2, highlightthickness=0)
        self.text = tk.Text(self, wrap="none", undo=True, maxundo=-1, bg=BG, fg=FG, insertbackground="#ffffff",
                            selectbackground="#3b3f5c", font=self.font, relief="flat", bd=0, padx=8, pady=4,
                            highlightthickness=0)
        self.vs = ttk.Scrollbar(self, orient="vertical", command=self._yview)
        self.hs = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=self._yset, xscrollcommand=self.hs.set)
        self.gutter.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        self.vs.grid(row=0, column=2, sticky="ns")
        self.hs.grid(row=1, column=1, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        t = self.text
        t.tag_configure("kw", foreground="#c792ea")
        t.tag_configure("bi", foreground="#82aaff")
        t.tag_configure("func", foreground="#ffcb6b")
        t.tag_configure("cls", foreground="#f78c6c")
        t.tag_configure("deco", foreground="#89ddff")
        t.tag_configure("self", foreground="#ff5370")
        t.tag_configure("number", foreground="#f78c6c")
        t.tag_configure("string", foreground="#c3e88d")
        t.tag_configure("comment", foreground="#5c6370")
        t.tag_configure("err", background="#4a1f2b", underline=True)
        t.tag_configure("warn", underline=True, underlinefg=YEL) if False else t.tag_configure("warn", underline=True)
        t.bind("<<Modified>>", self._modified)
        t.bind("<Return>", self._return)
        t.bind("<Tab>", self._tab)
        t.bind("<Control-slash>", self.toggle_comment)
        for ev in ("<Control-equal>", "<Control-plus>", "<Control-KP_Add>"):
            t.bind(ev, lambda e: self.zoom(1))
        for ev in ("<Control-minus>", "<Control-KP_Subtract>"):
            t.bind(ev, lambda e: self.zoom(-1))
        t.bind("<Control-0>", lambda e: self.zoom(0))
        t.bind("<Control-MouseWheel>", lambda e: self.zoom(1 if e.delta > 0 else -1))
        t.bind("<Control-Button-4>", lambda e: self.zoom(1))
        t.bind("<Control-Button-5>", lambda e: self.zoom(-1))
        menu_keys = ["<Button-3>", "<Control-Button-1>"]
        if app.tk.call("tk", "windowingsystem") == "aqua":
            menu_keys.append("<Button-2>")
        for ev in menu_keys:
            t.bind(ev, app.editor_menu)
        t.bind("<KeyRelease>", lambda e: app.update_pos())
        t.bind("<ButtonRelease-1>", lambda e: app.update_pos())
        self.gutter.bind("<Configure>", lambda e: self.draw_gutter())
        t.bind("<Configure>", lambda e: self.draw_gutter())

    # --- базовые операции
    def get_code(self):
        return self.text.get("1.0", "end-1c")

    def set_code(self, code):
        t = self.text
        t.delete("1.0", "end")
        t.insert("1.0", code)
        t.edit_reset()
        t.edit_modified(False)
        t.mark_set("insert", "1.0")
        t.yview_moveto(0)
        self.saved_code = code
        self.refresh()

    def replace_all(self, new):
        """Заменяет весь текст, но меняет только отличающиеся строки:
        прокрутка, курсор и ручные цвета остаются на месте."""
        t = self.text
        old = self.get_code().split("\n")
        new_l = new.split("\n")
        n_old = len(old)
        t.edit_separator()
        sm = difflib.SequenceMatcher(None, old, new_l, autojunk=False)
        for op, i1, i2, j1, j2 in reversed(sm.get_opcodes()):
            if op == "equal":
                continue
            text = "\n".join(new_l[j1:j2])
            if op == "insert":
                if i1 < n_old:
                    t.insert("%d.0" % (i1 + 1), text + "\n")
                else:
                    t.insert("%d.end" % n_old, "\n" + text)
            elif op == "delete":
                if i2 < n_old:
                    t.delete("%d.0" % (i1 + 1), "%d.0" % (i2 + 1))
                elif i1 > 0:
                    t.delete("%d.end" % i1, "%d.end" % i2)
                else:
                    t.delete("1.0", "end-1c")
            else:
                t.delete("%d.0" % (i1 + 1), "%d.end" % i2)
                t.insert("%d.0" % (i1 + 1), text)
        t.edit_separator()
        self.schedule(0)

    def set_lang(self, lang):
        if lang != self.lang:
            self.lang = lang
            self.schedule(0)

    def zoom(self, d):
        size = 12 if d == 0 else max(8, min(32, int(self.font.cget("size")) + d))
        self.font.configure(size=size)
        self.app.settings["font_size"] = size
        save_json(SETTINGS_F, self.app.settings, private=True)
        self.draw_gutter()
        return "break"

    def goto(self, line):
        self.text.mark_set("insert", "%d.0" % line)
        self.text.see("%d.0" % line)
        self.text.focus_set()
        self.app.update_pos()

    def is_dirty(self):
        return self.get_code() != self.saved_code

    # --- события
    def _yview(self, *a):
        self.text.yview(*a)
        self.draw_gutter()

    def _yset(self, a, b):
        self.vs.set(a, b)
        self.draw_gutter()

    def _modified(self, e=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.schedule(220)

    def schedule(self, ms=220):
        if self.job:
            self.after_cancel(self.job)
        self.job = self.after(ms, self.refresh)

    def _return(self, e):
        t = self.text
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        line = t.get("insert linestart", "insert")
        indent = re.match(r"[ \t]*", line).group()
        end = line.rstrip()
        if (self.lang in ("python", "text", "rus") and end.endswith(":")) or \
                ((self.lang in ("js", "css") or self.lang in PACKS) and end.endswith(("{", "(", "["))):
            indent += "    "
        t.insert("insert", "\n" + indent)
        t.see("insert")
        return "break"

    def _tab(self, e):
        t = self.text
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        t.insert("insert", "    ")
        return "break"

    def toggle_comment(self, e=None):
        t = self.text
        pre, post = {"js": ("// ", ""), "css": ("/* ", " */"), "html": ("<!-- ", " -->")}.get(self.lang, (PACKS[self.lang]["cm"] + " ", "") if self.lang in PACKS else ("# ", ""))  # noqa: E501
        rx = re.compile(r"^(\s*)" + re.escape(pre.strip()) + r" ?(.*?)" +
                        ((" ?" + re.escape(post.strip())) if post else "") + r"\s*$")
        try:
            a = int(t.index("sel.first").split(".")[0])
            b = int(t.index("sel.last").split(".")[0])
        except tk.TclError:
            a = b = int(t.index("insert").split(".")[0])
        rng = list(range(a, b + 1))
        lines = [t.get("%d.0" % i, "%d.end" % i) for i in rng]
        allc = all(rx.match(l) for l in lines if l.strip())
        t.edit_separator()
        for i, l in zip(rng, lines):
            if not l.strip():
                continue
            if allc:
                new = rx.sub(lambda m: m.group(1) + m.group(2), l)
            else:
                indent = re.match(r"\s*", l).group()
                new = indent + pre + l.strip() + post
            t.delete("%d.0" % i, "%d.end" % i)
            t.insert("%d.0" % i, new)
        t.edit_separator()
        return "break"

    # --- анализ и подсветка
    def refresh(self):
        self.job = None
        code = self.get_code()
        res = check_code(code, self.lang)
        self.highlight(code)
        self.mark(code, res)
        self.draw_gutter()
        self.app.after_refresh(res, code)

    def highlight(self, code):
        t = self.text
        for tag in ("kw", "bi", "func", "cls", "deco", "self", "number", "string", "comment"):
            t.tag_remove(tag, "1.0", "end")
        starts = [0]
        for m in re.finditer("\n", code):
            starts.append(m.end())

        def idx(p):
            l = bisect_right(starts, p) - 1
            return "%d.%d" % (l + 1, p - starts[l])

        if self.lang == "text":                       # JSON, YAML, Markdown… — через Pygments, если он установлен
            for s, e, tag in spans_for_path(code, getattr(self.app, "cur_file", None)):
                t.tag_add(tag, idx(s), idx(e))
            return
        if self.lang != "python":
            for s, e, tag in spans(code, self.lang):
                t.tag_add(tag, idx(s), idx(e))
            return
        prev = ""
        for m in TOKEN.finditer(code):
            k, tag = m.lastgroup, None
            if k == "word":
                w = m.group()
                if w in KW:
                    tag = "kw"
                elif prev == "def":
                    tag = "func"
                elif prev == "class":
                    tag = "cls"
                elif w == "self":
                    tag = "self"
                elif w in BUILTINS:
                    tag = "bi"
                prev = w
            else:
                prev = ""
                tag = k
            if tag:
                t.tag_add(tag, idx(m.start()), idx(m.end()))

    def mark(self, code, res):
        t = self.text
        t.tag_remove("err", "1.0", "end")
        t.tag_remove("warn", "1.0", "end")
        lines = code.split("\n")
        st = {}
        if res["errors"]:
            E = min(res["errors"][0][0], len(lines))
            for i, l in enumerate(lines, 1):
                if i < E and l.strip():
                    st[i] = "ok"
            st[E] = "err"
            t.tag_add("err", "%d.0" % E, "%d.end" % E)
        else:
            for i, l in enumerate(lines, 1):
                if l.strip():
                    st[i] = "ok"
            for ln, col, _msg, kind, name in res["warnings"]:
                st[ln] = "warn"
                if kind == "undef":
                    t.tag_add("warn", "%d.%d" % (ln, col), "%d.%d" % (ln, col + len(name)))
        self.status = st

    def draw_gutter(self):
        c, t = self.gutter, self.text
        c.delete("all")
        colors = {"ok": GREEN, "err": RED, "warn": YEL}
        i, guard = t.index("@0,0"), 0
        while guard < 600:
            guard += 1
            d = t.dlineinfo(i)
            if d is None:
                break
            y, h = d[1], d[3]
            ln = int(i.split(".")[0])
            col = colors.get(self.status.get(ln))
            if col:
                c.create_oval(8, y + h / 2 - 4, 16, y + h / 2 + 4, fill=col, outline="")
            c.create_text(58, y + h / 2, anchor="e", text=str(ln), fill=DIM, font=self.font)
            nxt = t.index("%s+1line" % i)
            if nxt == i:
                break
            i = nxt
