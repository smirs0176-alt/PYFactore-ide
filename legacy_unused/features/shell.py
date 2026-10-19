"""Оболочка окна как в современных IDE: полоса значков слева, панель инструментов,
проводник, терминал внизу и строка состояния."""
import sys
import tkinter as tk

from pyfactor import config
from pyfactor.config import ACC, ACT, BAR, BG3, DIM, FG
from pyfactor.core.langs import LANG_NAMES
from pyfactor.ui.widgets import Tooltip, flatbtn

UI = "Segoe UI"
# (ключ, значок, подсказка)
SECTIONS = [("files", "📄", "Проводник (Ctrl+B)"), ("search", "🔍", "Поиск по проекту (Ctrl+Shift+F)"),
            ("git", "⎇", "GitHub и аккаунт"), ("bug", "🐞", "Проверка кода"), ("lib", "📚", "Библиотеки"),
            ("prev", "👁", "Просмотр HTML / CSS"), ("games", "🎮", "Игры"), ("langs", "🌍", "Языки")]


class ShellMixin:
    # ================================================= верхняя часть
    def build_brand(self):
        bar = tk.Frame(self, bg=ACT)
        bar.pack(fill="x")
        try:
            image_path = config.asset_path("icon.png")
            self._brand_img = tk.PhotoImage(file=image_path).subsample(16)
            tk.Label(bar, image=self._brand_img, bg=ACT).pack(side="left", padx=(12, 6), pady=4)
        except Exception:
            pass
        tk.Label(bar, text="PyFactor", bg=ACT, fg="#ffffff", font=(UI, 11, "bold")).pack(side="left", pady=4)
        self.proj_lbl = tk.Label(bar, text="", bg=ACT, fg=DIM, font=(UI, 9))
        self.proj_lbl.pack(side="left", padx=12)

    def build_toolbar(self):
        bar = tk.Frame(self, bg=BAR)
        bar.pack(fill="x")

        def sep():
            tk.Frame(bar, bg="#3a424a", width=1).pack(side="left", fill="y", pady=8, padx=6)

        self.menu_btn = flatbtn(bar, "☰", self.main_menu, "Меню", font=(UI, 13), padx=12)
        self.menu_btn.pack(side="left", padx=(4, 0))
        flatbtn(bar, "📂 Open", self.ask_open_dir, "Открыть папку проекта").pack(side="left")
        flatbtn(bar, "💾 Save", self.save_file, "Сохранить (Ctrl+S)").pack(side="left")
        flatbtn(bar, "🗋＋", self.new_file_menu, "Новый файл").pack(side="left")
        sep()
        flatbtn(bar, "Run", self.run_file, "Запустить файл (F5)", font=(UI, 10, "bold")).pack(side="left")
        flatbtn(bar, "▷", self.web_run, "Просмотр HTML / CSS", font=(UI, 12)).pack(side="left")
        flatbtn(bar, "🐞", lambda: self.show_section("bug"), "Проверка кода", font=(UI, 12)).pack(side="left")
        flatbtn(bar, "◆", self.toggle_right, "Панель: библиотеки в коде, мои коды, ИИ", font=(UI, 12)).pack(side="left")
        flatbtn(bar, "⎇", self.publish_github, "Выложить проект на GitHub", font=(UI, 12)).pack(side="left")
        flatbtn(bar, "🔍", self.project_search, "Поиск по проекту (Ctrl+Shift+F)", font=(UI, 12)).pack(side="left")

    def main_menu(self):
        m = tk.Menu(self, tearoff=0, bg=BG3, fg=FG, activebackground=ACC, activeforeground="#ffffff", bd=0)
        m.add_cascade(label="Новый файл", menu=self.new_file_submenu(m))
        m.add_command(label="Открыть папку…", command=self.ask_open_dir)
        m.add_command(label="Сохранить      Ctrl+S", command=self.save_file)
        m.add_command(label="Сохранить всё", command=self.tabs_save_all)
        m.add_separator()
        m.add_command(label="Поиск по проекту      Ctrl+Shift+F", command=self.project_search)
        m.add_command(label="Проводник      Ctrl+B", command=self.toggle_sidebar)
        m.add_command(label="Терминал      Ctrl+`", command=self.toggle_terminal)
        m.add_separator()
        m.add_command(label="Горячие клавиши      F1", command=self.show_help)
        m.add_command(label="Выход", command=self.on_close)
        m.tk_popup(self.menu_btn.winfo_rootx(), self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height())

    def settings_menu(self, btn):
        from pyfactor.features.extras import THEMES
        m = tk.Menu(self, tearoff=0, bg=BG3, fg=FG, activebackground=ACC, activeforeground="#ffffff", bd=0)
        tm = tk.Menu(m, tearoff=0, bg=BG3, fg=FG, activebackground=ACC, activeforeground="#ffffff")
        cur = self.settings.get("theme", 0)
        for i, t in enumerate(THEMES):
            tm.add_command(label=("● " if i == cur else "   ") + t[0], command=lambda i=i: self.apply_theme(i))
        m.add_cascade(label="Тема редактора", menu=tm)
        m.add_command(label="Шрифт крупнее    Ctrl +", command=lambda: self.editor.zoom(1))
        m.add_command(label="Шрифт мельче    Ctrl −", command=lambda: self.editor.zoom(-1))
        m.add_separator()
        m.add_command(label="Журнал    Ctrl+J", command=lambda: self.open_file(self.journal_path, force=True))
        m.add_command(label="Горячие клавиши    F1", command=self.show_help)
        m.tk_popup(btn.winfo_rootx() + btn.winfo_width(), btn.winfo_rooty())

    # ================================================= полоса значков слева
    def build_activity(self, parent):
        bar = tk.Frame(parent, bg=ACT, width=48)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)
        self._act = {}
        for key, glyph, tip in SECTIONS:
            self._act[key] = self._act_item(bar, key, glyph, tip, side="top")
        for key, glyph, tip in (("account", "👤", "Аккаунт"), ("settings", "⚙", "Настройки")):
            self._act[key] = self._act_item(bar, key, glyph, tip, side="bottom")
        self.section = "files"

    def _act_item(self, bar, key, glyph, tip, side):
        cell = tk.Frame(bar, bg=ACT, height=46)
        cell.pack(side=side, fill="x")
        cell.pack_propagate(False)
        mark = tk.Frame(cell, bg=ACT, width=2)
        mark.pack(side="left", fill="y")
        lbl = tk.Label(cell, text=glyph, bg=ACT, fg=DIM, font=("Segoe UI Symbol", 15), cursor="hand2")
        lbl.pack(side="left", fill="both", expand=True)
        for w in (cell, lbl):
            w.bind("<Button-1>", lambda e, k=key, l=lbl: self.act_click(k, l))
            w.bind("<Enter>", lambda e, k=key, l=lbl: l.config(fg="#ffffff"))
            w.bind("<Leave>", lambda e, k=key, l=lbl: self._act_paint(k))
        Tooltip(lbl, tip, "right")
        return {"cell": cell, "mark": mark, "lbl": lbl}

    def _act_paint(self, current=None):
        for k, it in self._act.items():
            on = (k == self.section)
            it["lbl"].config(fg="#ffffff" if on else DIM)
            it["mark"].config(bg=ACC if on else ACT)
            it["cell"].config(bg="#222930" if on else ACT)
            it["lbl"].config(bg="#222930" if on else ACT)

    def act_click(self, key, lbl):
        if key == "files":
            if self.section == "files" and self._nb_key() == "files":
                self.toggle_sidebar()
            else:
                self.toggle_sidebar(True)
                self.show_section("files")
        elif key == "search":
            self.project_search()
        elif key == "git":
            self.show_right("acc")
        elif key == "account":
            self.show_right("acc")
        elif key == "settings":
            self.settings_menu(lbl)
        else:
            self.show_section(key)

    def _nb_tabs(self):
        return {"files": getattr(self, "tab_code", None), "prev": getattr(self, "tab_prev", None),
                "lib": getattr(self, "tab_lib", None), "bug": getattr(self, "tab_bug", None),
                "games": getattr(self, "tab_games", None), "langs": getattr(self, "tab_langs", None)}

    def _nb_key(self):
        try:
            cur = self.nb.select()
        except tk.TclError:
            return "files"
        for k, w in self._nb_tabs().items():
            if w is not None and str(w) == cur:
                return k
        return "files"

    def show_section(self, key):
        w = self._nb_tabs().get(key)
        if w is not None:
            self.nb.select(w)
        self.section = key
        self._act_paint()

    def shell_ready(self):
        self.nb.bind("<<NotebookTabChanged>>", self._sync_section, "+")
        self.bind_all("<Control-grave>", lambda e: self.toggle_terminal() or "break")
        self.bind_all("<Control-b>", lambda e: self.toggle_sidebar() or "break")
        self.editor.text.bind("<Control-b>", lambda e: self.toggle_sidebar() or "break")
        self._act_paint()

    def _sync_section(self, e=None):
        self.section = self._nb_key()
        self._act_paint()

    # ================================================= панели
    def toggle_sidebar(self, force=None):
        want = (not self.sidebar_on) if force is None else force
        if want == self.sidebar_on:
            return
        if want:
            self.pw.add(self.left_pane, before=self.center_pane, minsize=180, width=250)
        else:
            self.pw.forget(self.left_pane)
        self.sidebar_on = want

    def toggle_right(self, force=None):
        want = (not self.right_on) if force is None else force
        if want == self.right_on:
            return
        if want:
            self.pw.add(self.right_pane, minsize=260, width=340)
        else:
            self.pw.forget(self.right_pane)
        self.right_on = want
        self.settings["right_open"] = want

    def show_right(self, key):
        self.toggle_right(True)
        self.show_panel(key)

    def toggle_terminal(self, force=None):
        want = (not self.term_on) if force is None else force
        if want == self.term_on:
            return
        if want:
            self.cpw.add(self.term_frame, minsize=90, height=190)
        else:
            self.cpw.forget(self.term_frame)
        self.term_on = want

    def show_terminal(self):
        self.toggle_terminal(True)

    # ================================================= строка состояния
    def set_ready(self, text):
        self.ready_lbl.config(text=text)

    def lang_text(self, lang):
        if lang == "python":
            return "Python %d.%d.%d" % sys.version_info[:3]
        return LANG_NAMES.get(lang, lang.upper())
