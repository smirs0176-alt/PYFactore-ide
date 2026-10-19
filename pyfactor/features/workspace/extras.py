"""Дополнения редактора: автодополнение, парные скобки, сниппеты, автосохранение,
восстановление вкладок, структура файла, темы, форматирование, подсветка строки."""
import os
import re
import threading
import time
import tkinter as tk

from pyfactor import config
from pyfactor.config import ACC, BG3, BUILTINS, FG, HOME, KW, MYCODES, SETTINGS_F
from pyfactor.core.ai.brain import Brain
from pyfactor.core.utils import save_json

PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
SNIPS = {
    "def": "def $0():\n    pass",
    "class": "class $0:\n    def __init__(self):\n        pass",
    "for": "for $0 in range():\n    pass",
    "while": "while $0:\n    pass",
    "if": "if $0:\n    pass",
    "try": "try:\n    $0\nexcept Exception as e:\n    print(e)",
    "with": "with open($0) as f:\n    pass",
    "main": "def main():\n    $0\n\n\nif __name__ == \"__main__\":\n    main()",
}
THEMES = [("Тёмная", "#1d2128", "#d4d7de", "#262c36"), ("Океан", "#0f1b2a", "#cdd6e4", "#1a2c44"),
          ("Тёплая", "#2b2118", "#e6dccf", "#3a2d20"), ("Чёрная", "#000000", "#e0e0e0", "#1a1a1a")]
OUTLINE = re.compile(r"^(\s*)(?:async\s+)?(def|class|function)\s+(\w+)")


class ExtrasMixin:
    def _init_icon(self):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PyFactor.IDE")
        except Exception:
            pass
        try:
            self._icon = tk.PhotoImage(file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "icon.png"))
            self.iconphoto(True, self._icon)
        except Exception:
            pass

    def init_extras(self):
        self._init_icon()
        t = self.editor.text
        self._pop, self._n = None, 0
        t.tag_configure("curline")
        t.tag_lower("curline")
        self.apply_theme(self.settings.get("theme", 0), toast=False)
        t.bind("<Tab>", self._x_tab)
        t.bind("<Return>", self._x_return)
        t.bind("<BackSpace>", self._x_back)
        t.bind("<KeyPress>", self._x_press, "+")
        t.bind("<KeyRelease>", self._x_release, "+")
        t.bind("<ButtonRelease-1>", self._curline, "+")
        t.bind("<ButtonPress-1>", lambda e: self._pop_close(), "+")
        t.bind("<FocusOut>", lambda e: self._pop_close(), "+")
        for k in ("Up", "Down"):
            t.bind("<%s>" % k, lambda e, d=(-1 if k == "Up" else 1): self._pop_move(d), "+")
        t.bind("<Escape>", lambda e: self._pop_close() or None, "+")
        t.bind("<Control-space>", self.autocomplete)
        t.bind("<Control-r>", self.show_outline)
        t.bind("<Control-t>", lambda e: self.apply_theme(self.settings.get("theme", 0) + 1) or "break")
        for k in ("<Control-Alt-l>", "<Control-Shift-L>"):
            t.bind(k, self.format_code)
        self._restore_session()
        self._init_journal()
        self._init_brain()
        self.after(5000, self._tick)

    # ---------- своя нейросеть
    def _init_brain(self):
        self.brain, self._brain_msg, self._training = Brain(), None, False
        self.brain_path = os.path.join(HOME, "brain.json")
        t = self.editor.text
        t.bind("<Control-Shift-N>", lambda e: self.brain_train() or "break")
        if not self.brain.load(self.brain_path):
            self.after(3000, self.brain_train)

    def brain_train(self):
        if self._training:
            return self.toast("Нейросеть уже учится…")
        self._training = True
        self.toast("Нейросеть учится на твоём коде…")
        roots = [self.project, MYCODES]

        def work():
            texts = []
            for root in roots:
                for r, ds, fs in os.walk(root or "."):
                    ds[:] = [d for d in ds if not d.startswith((".", "__"))]
                    for fn in fs:
                        if fn.endswith((".py", ".js", ".html", ".css")):
                            try:
                                if os.path.getsize(os.path.join(r, fn)) < 300000:
                                    with open(os.path.join(r, fn), encoding="utf-8", errors="ignore") as f:
                                        texts.append(f.read())
                            except OSError:
                                pass
            nb = Brain()
            try:
                if nb.train(texts):
                    nb.save(self.brain_path)
                    self.brain = nb
                    self._brain_msg = "Нейросеть обучена: " + nb.info
                else:
                    self._brain_msg = "Мало кода для обучения — напиши ещё"
            except Exception as ex:
                self._brain_msg = "Нейросеть: ошибка " + str(ex)
            self._training = False
        threading.Thread(target=work, daemon=True).start()

    # ---------- журнал: всё, что делали в IDE, пишется в отдельный файл
    def _init_journal(self):
        self.journal_path = os.path.join(HOME, "journal.md")
        if not os.path.exists(self.journal_path):
            with open(self.journal_path, "w", encoding="utf-8") as f:
                f.write("# Журнал PyFactor\n\n")
        self._auto = False
        base = lambda: os.path.basename(self.cur_file) if self.cur_file else "без имени"
        for name, fmt in (("open_project", lambda a: "проект " + os.path.basename(a[0])),
                          ("open_file", lambda a: "открыт " + os.path.basename(a[0])),
                          ("save_file", lambda a: "сохранён " + base()),
                          ("run_file", lambda a: "запуск " + base()),
                          ("format_code", lambda a: "форматирование " + base())):
            orig = getattr(self, name)

            def wrap(*a, _o=orig, _f=fmt, _n=name, **k):
                r = _o(*a, **k)
                if not (_n == "save_file" and self._auto):
                    try:
                        self.log(_f(a))
                    except Exception:
                        pass
                return r
            setattr(self, name, wrap)
        self.bind_all("<Control-j>", lambda e: self.open_file(self.journal_path, force=True) or "break")
        self.log("— IDE запущена —")

    def log(self, text):
        proj = os.path.basename(self.project) if self.project else "-"
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write("- %s · [%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M"), proj, text))

    # ---------- автосохранение и сессия
    def _tick(self):
        self._n += 1
        if self._brain_msg:
            self.toast(self._brain_msg)
            self.log(self._brain_msg)
            self._brain_msg = None
        try:
            if self._n % 3 == 0 and self.settings.get("autosave", True) and self.cur_file and self.editor.is_dirty():
                self._auto = True
                try:
                    self.save_file()
                finally:
                    self._auto = False
            files = [x["path"] for x in self.tabs if x.get("path")]
            if self.cur_file and self.cur_file not in files:
                files.append(self.cur_file)
            ses = {"project": self.project, "files": files, "active": self.cur_file}
            if self.settings.get("session") != ses:
                self.settings["session"] = ses
                save_json(SETTINGS_F, self.settings, private=True)
        except Exception:
            pass
        self.after(5000, self._tick)

    def _restore_session(self):
        s = self.settings.get("session") or {}
        if s.get("project") != self.project:
            return
        for p in s.get("files", []):
            if os.path.isfile(p):
                self.open_file(p, force=True)
        if s.get("active") and os.path.isfile(s["active"]):
            self.open_file(s["active"], force=True)

    # ---------- подсветка строки, темы
    def _curline(self, e=None):
        t = self.editor.text
        t.tag_remove("curline", "1.0", "end")
        t.tag_add("curline", "insert linestart", "insert lineend+1c")

    def apply_theme(self, i, toast=True):
        i %= len(THEMES)
        name, bg, fg, cl = THEMES[i]
        t = self.editor.text
        t.config(bg=bg, fg=fg, insertbackground=fg)
        t.tag_configure("curline", background=cl)
        self.settings["theme"] = i
        if toast:
            self.log("тема " + name)
        save_json(SETTINGS_F, self.settings, private=True)
        self._curline()
        if toast:
            self.toast("Тема: " + name)
        return "break"

    # ---------- форматирование
    def format_code(self, e=None):
        code = self.editor.get_code()
        new = "\n".join(l.rstrip().replace("\t", "    ") for l in code.split("\n"))
        new = re.sub(r"\n{4,}", "\n\n\n", new).rstrip("\n") + "\n"
        if new != code:
            self.editor.replace_all(new)
            self.toast("Код отформатирован")
        return "break"

    # ---------- всплывающий список
    def _pop_close(self):
        if self._pop:
            self._pop[0].destroy()
            self._pop = None

    def _pop_show(self, items, pick, modal=False):
        self._pop_close()
        t = self.editor.text
        bb = t.bbox("insert")
        if not bb or not items:
            return
        top = tk.Toplevel(self)
        top.overrideredirect(True)
        top.geometry("+%d+%d" % (t.winfo_rootx() + bb[0], t.winfo_rooty() + bb[1] + bb[3]))
        lb = tk.Listbox(top, bg=BG3, fg=FG, selectbackground=ACC, selectforeground="#ffffff", relief="flat",
                        highlightthickness=1, highlightbackground=ACC, activestyle="none", exportselection=False,
                        font=(config.MONO, 11), height=min(len(items), 10), width=max(16, max(map(len, items)) + 2))
        lb.pack()
        lb.insert("end", *items)
        lb.selection_set(0)
        self._pop = (top, lb, pick)
        lb.bind("<Double-Button-1>", lambda e: self._pop_accept())
        if modal:
            lb.focus_force()
            lb.bind("<Return>", lambda e: self._pop_accept())
            lb.bind("<Escape>", lambda e: self._pop_close())
            lb.bind("<FocusOut>", lambda e: self.after(100, self._pop_close))

    def _pop_move(self, d):
        if not self._pop:
            return
        lb = self._pop[1]
        i = max(0, min(lb.size() - 1, (lb.curselection() or (0,))[0] + d))
        lb.selection_clear(0, "end")
        lb.selection_set(i)
        lb.see(i)
        return "break"

    def _pop_accept(self):
        if not self._pop:
            return
        _, lb, pick = self._pop
        sel = lb.curselection()
        self._pop_close()
        if sel:
            pick(sel[0])
            self.editor.text.focus_set()
        return "break"

    # ---------- автодополнение
    def _prefix(self):
        m = re.search(r"[A-Za-z_]\w*$", self.editor.text.get("insert linestart", "insert"))
        return m.group() if m else ""

    def autocomplete(self, e=None, auto=False):
        t = self.editor.text
        pre = self._prefix()
        nn = []
        if self.brain.ready and (pre or not auto):
            nn = [w for w, _ in self.brain.predict(t.get("insert-300c", "insert-%dc" % len(pre)), pre)]
        if (not pre and not nn) or (auto and len(pre) < 3):
            self._pop_close()
            return "break"
        rest = []
        if pre:
            words = set(re.findall(r"[A-Za-z_]\w{2,}", self.editor.get_code())) | set(KW) | set(BUILTINS)
            rest = sorted((w for w in words if w.lower().startswith(pre.lower()) and w != pre and w not in nn),
                          key=lambda w: (len(w), w))
        items = (nn + rest)[:30]
        if not items:
            self._pop_close()
            return "break"

        def pick(i):
            t.delete("insert-%dc" % len(pre), "insert")
            t.insert("insert", items[i])
        self._pop_show([("★ " if w in nn else "") + w for w in items], pick)
        return "break"

    # ---------- структура файла
    def show_outline(self, e=None):
        rows = []
        for n, line in enumerate(self.editor.get_code().split("\n"), 1):
            m = OUTLINE.match(line)
            if m:
                rows.append((n, "  " * (len(m.group(1)) // 4) + ("◆ " if m.group(2) == "class" else "ƒ ") + m.group(3) + "  :" + str(n)))
        if not rows:
            self.toast("В файле нет функций и классов")
            return "break"
        self._pop_show([r[1] for r in rows], lambda i: self.editor.goto(rows[i][0]), modal=True)
        return "break"

    # ---------- клавиши
    def _x_tab(self, e):
        if self._pop:
            return self._pop_accept()
        t = self.editor.text
        if self.editor.lang == "python" and not t.tag_ranges("sel"):
            before = t.get("insert linestart", "insert")
            m = re.search(r"(?:^|\s)(\w+)$", before)
            if m and m.group(1) in SNIPS:
                word = m.group(1)
                indent = re.match(r"[ \t]*", before).group()
                lines = SNIPS[word].split("\n")
                text = lines[0] + "".join("\n" + indent + l for l in lines[1:])
                pos = text.index("$0")
                t.delete("insert-%dc" % len(word), "insert")
                start = t.index("insert")
                t.insert("insert", text.replace("$0", "", 1))
                t.mark_set("insert", "%s+%dc" % (start, pos))
                return "break"
        return self.editor._tab(e)

    def _x_return(self, e):
        if self._pop:
            return self._pop_accept()
        return self.editor._return(e)

    def _x_back(self, e):
        t = self.editor.text
        if t.tag_ranges("sel"):
            return None
        a, b = t.get("insert-1c", "insert"), t.get("insert", "insert+1c")
        if a in PAIRS and PAIRS[a] == b:
            t.delete("insert-1c", "insert+1c")
            return "break"

    def _x_press(self, e):
        c, t = e.char, self.editor.text
        if not c or e.state & 0x4 or c not in "([{)]}\"'":
            return None
        if t.tag_ranges("sel") and c in PAIRS:
            s = t.get("sel.first", "sel.last")
            t.delete("sel.first", "sel.last")
            t.insert("insert", c + s + PAIRS[c])
            return "break"
        nxt, prev = t.get("insert", "insert+1c"), t.get("insert-1c", "insert")
        if c in ")]}\"'" and nxt == c:
            t.mark_set("insert", "insert+1c")
            return "break"
        if c in PAIRS:
            if c in "\"'" and (prev.isalnum() or prev == "_" or prev == c):
                return None
            if nxt and not nxt.isspace() and nxt not in ")]}\"',;:":
                return None
            t.insert("insert", c + PAIRS[c])
            t.mark_set("insert", "insert-1c")
            return "break"

    def _x_release(self, e):
        self._curline()
        if e.keysym in ("Up", "Down", "Return", "Tab", "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        if e.keysym == "space" and e.state & 0x4:
            return
        if len(e.char) == 1 and (e.char.isalnum() or e.char == "_") and self.editor.lang in ("python", "js"):
            self.autocomplete(auto=True)
        else:
            self._pop_close()
