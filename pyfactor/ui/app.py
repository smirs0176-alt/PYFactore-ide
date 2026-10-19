"""Главное окно PyFactor: собирает все возможности (миксины) в одно приложение."""
import os
import queue
import sys
import tkinter as tk
from tkinter import ttk

from pyfactor import config
from pyfactor.config import ACC, ACCOUNT_F, BG, BG2, BG3, BLUE, DIM, FG, GREEN, RED, SETTINGS_F, YEL
from pyfactor.core.account.vault import load_account, migrate_settings_secrets
from pyfactor.core.utils import load_json, save_json
from pyfactor.features.account.account import AccountMixin
from pyfactor.features.account.auth import AuthMixin
from pyfactor.features.account.server import ServerMixin
from pyfactor.features.ai.ai import AiMixin
from pyfactor.features.ai.panels import PanelsMixin
from pyfactor.features.project.games import GamesMixin
from pyfactor.features.project.langstore import LangStoreMixin
from pyfactor.features.project.library import LibraryMixin
from pyfactor.features.project.project import ProjectMixin
from pyfactor.features.tools.bug import BugMixin
from pyfactor.features.tools.voice import VoiceMixin
from pyfactor.features.tools.web import WebMixin
from pyfactor.features.workspace.colors import ColorsMixin
from pyfactor.features.workspace.extras import ExtrasMixin
from pyfactor.features.workspace.palette import PaletteMixin
from pyfactor.features.workspace.runner import RunnerMixin
from pyfactor.features.workspace.search import SearchMixin
from pyfactor.features.workspace.status import StatusMixin
from pyfactor.features.workspace.tabs import TabsMixin
from pyfactor.ui.editor import Editor
from pyfactor.ui.widgets import mkbtn


class App(
    LibraryMixin,
    BugMixin,
    PanelsMixin,
    AccountMixin,
    GamesMixin,
    ProjectMixin,
    RunnerMixin,
    StatusMixin,
    TabsMixin,
    SearchMixin,
    WebMixin,
    ColorsMixin,
    ExtrasMixin,
    VoiceMixin,
    LangStoreMixin,
    AuthMixin,
    ServerMixin,
    AiMixin,
    PaletteMixin,
    tk.Tk,
):
    def __init__(self):
        super().__init__()
        config.detect_mono()
        self.title("PyFactor IDE")
        self.geometry("1400x880")
        self.minsize(1050, 650)
        self.configure(bg=BG)
        self.q = queue.Queue()
        self.project, self.cur_file, self.proc = None, None, None
        self.init_tabs()
        self.init_web()
        self.init_colors()
        self.account = load_account(ACCOUNT_F)
        self.settings = load_json(SETTINGS_F, {})
        if migrate_settings_secrets(self.settings):          # ключи из старого settings.json — в хранилище
            save_json(SETTINGS_F, self.settings, private=True)
        self.bug_mode = tk.StringVar(value="quick")
        self.lib_filter = tk.StringVar(value="all")
        self.lib_search = tk.StringVar()
        self.init_ai()
        self.setup_style()
        self.build_topbar()
        self.build_statusbar()
        self.build_body()
        last = self.settings.get("last_project")
        self.open_project(last if last and os.path.isdir(last) else self.default_project())
        self.init_extras()
        self.init_voice()
        self.build_langstore()
        self.auth_gate()
        self.init_server()
        self.bind_all("<Control-s>", lambda e: self.save_file())
        self.bind_all("<F5>", lambda e: self.run_file())
        self.bind_all("<F1>", self.show_help)
        self.init_palette()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(80, self.poll)

    # ---------- оформление
    def setup_style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("Treeview", background=BG2, fieldbackground=BG2, foreground=FG, borderwidth=0, rowheight=26)
        s.map("Treeview", background=[("selected", "#2a3a55")], foreground=[("selected", "#ffffff")])
        s.configure("Treeview.Heading", background=BG3, foreground=DIM, borderwidth=0)
        s.configure("TNotebook", background=BG3, borderwidth=0, tabmargins=(8, 6, 0, 0))
        s.configure("TNotebook.Tab", background=BG3, foreground=DIM, padding=(20, 9), borderwidth=0,
                    font=("Segoe UI", 10, "bold"))
        s.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", "#ffffff")])
        s.layout("Hidden.TNotebook.Tab", [])
        s.configure("Hidden.TNotebook", background=BG, borderwidth=0, tabmargins=0, bordercolor=BG, lightcolor=BG, darkcolor=BG)
        s.configure("Treeview", bordercolor=BG2, lightcolor=BG2, darkcolor=BG2)
        s.configure("TFrame", background=BG)
        s.configure("TScrollbar", bordercolor=BG, lightcolor=BG3, darkcolor=BG3)
        s.configure("Vertical.TScrollbar", background=BG3, troughcolor=BG2, borderwidth=0, arrowcolor=DIM)
        s.configure("Horizontal.TScrollbar", background=BG3, troughcolor=BG2, borderwidth=0, arrowcolor=DIM)

    def build_topbar(self):
        top = tk.Frame(self, bg=BG3)
        top.pack(fill="x")
        title = tk.Frame(top, bg=BG3)
        title.pack(fill="x")
        tk.Label(title, text="PYFactor", bg=BG3, fg="#ffffff", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(14, 10), pady=(6, 0))
        self.proj_lbl = tk.Label(title, text="", bg=BG3, fg=DIM, font=("Segoe UI", 9))
        self.proj_lbl.pack(side="left", pady=(6, 0))
        bar = tk.Frame(top, bg=BG3)
        bar.pack(fill="x", padx=6, pady=(2, 6))

        def tb(text, cmd, font=("Segoe UI", 10), **kw):
            b = mkbtn(bar, text, cmd, bg=BG3, font=font, padx=9, pady=3, **kw)
            b.pack(side="left", padx=1)
            return b
        self.menu_btn = tb("☰", self.main_menu, font=("Segoe UI", 14))
        tb("📂 Открыть", self.ask_open_dir)
        tb("💾 Сохранить", self.save_file)
        tb("▶ Запуск", self.run_file, fg=GREEN)
        tb("■", self.stop_file, fg=RED)
        tk.Frame(bar, bg=DIM, width=1, height=18).pack(side="left", padx=8)
        tb("🐞", lambda: self.show_page("bug"), font=("Segoe UI Emoji", 11))
        tb("🔀", self.publish_github, font=("Segoe UI Emoji", 11))
        tb("🔍", self.project_search, font=("Segoe UI Emoji", 11))
        tk.Frame(top, bg="#12151a", height=1).pack(fill="x")

    def main_menu(self):
        m = tk.Menu(self, tearoff=0, bg=BG3, fg=FG, activebackground=ACC, activeforeground="#ffffff", bd=0)
        for txt, cmd in (("Открыть папку…", self.ask_open_dir), ("Новый файл…", self.new_file_menu),
                         ("Сохранить  Ctrl+S", self.save_file), ("Поиск по проекту", self.project_search), None,
                         ("Панель справа (ИИ, библиотеки)", lambda: self.toggle_right("ai")),
                         ("Сменить тему  Ctrl+T", lambda: self.apply_theme(self.settings.get("theme", 0) + 1)),
                         ("Палитра команд  Ctrl+Shift+P", self.open_palette),
                         ("Горячие клавиши  F1", self.show_help), None, ("Выход", self.on_close)):
            m.add_separator() if cmd is None else m.add_command(label=txt, command=cmd)
        b = self.menu_btn
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def build_statusbar(self):
        bar = tk.Frame(self, bg=BG3, height=24)
        bar.pack(side="bottom", fill="x")
        tk.Frame(bar, bg="#12151a", height=1).pack(side="top", fill="x")
        self.pos_lbl = tk.Label(bar, text="", bg=BG3, fg=DIM, font=("Segoe UI", 9))
        self.pos_lbl.pack(side="left", padx=(12, 10))
        self.toast_lbl = tk.Label(bar, text="", bg=BG3, fg=YEL, font=("Segoe UI", 9))
        self.toast_lbl.pack(side="left", padx=6)
        self.status_lbl = tk.Label(bar, text="", bg=BG3, fg=FG, font=("Segoe UI", 9))
        self.status_lbl.pack(side="right", padx=(6, 12))
        self.led = tk.Canvas(bar, width=14, height=14, bg=BG3, highlightthickness=0)
        self.led.pack(side="right")
        self.led_id = self.led.create_oval(2, 2, 12, 12, fill=DIM, outline="")
        tk.Label(bar, text="Python %d.%d.%d  │  PyFactor" % sys.version_info[:3], bg=BG3, fg=DIM, font=("Segoe UI", 9)).pack(side="right", padx=12)
        self.lang_lbl = tk.Label(bar, text="Python", bg=BG3, fg="#c792ea", font=("Segoe UI", 9, "bold"))
        self.lang_lbl.pack(side="right", padx=6)

    def build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        self.build_activity(body)
        pw = self.body_pw = tk.PanedWindow(body, orient="horizontal", bg=BG, sashwidth=3, bd=0, sashrelief="flat")
        pw.pack(side="left", fill="both", expand=True)
        left = tk.Frame(pw, bg=BG2, width=250)
        center = tk.Frame(pw, bg=BG)
        right = self.right_f = tk.Frame(pw, bg=BG2, width=340)
        pw.add(left, minsize=190)
        pw.add(center, minsize=480, stretch="always")
        pw.add(right, minsize=260)
        self.build_left(left)
        self.build_center(center)
        self.build_right(right)
        pw.forget(right)
        self.nb.bind("<<NotebookTabChanged>>", self._sync_act)
        self.act_set("files")

    # ---------- полоса значков слева (как в VS Code)
    def build_activity(self, parent):
        bar = tk.Frame(parent, bg=BG2, width=48)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)
        self.act = {}

        def add(key, icon, cmd, side="top", page=True):
            row = tk.Frame(bar, bg=BG2, height=46)
            row.pack(side=side, fill="x")
            row.pack_propagate(False)
            ind = tk.Frame(row, bg=BG2, width=2)
            ind.pack(side="left", fill="y")
            lb = tk.Label(row, text=icon, bg=BG2, fg=DIM, font=("Segoe UI Emoji", 15), cursor="hand2")
            lb.pack(expand=True)
            for w in (row, lb):
                w.bind("<Button-1>", lambda e, c=cmd: c())
            lb.bind("<Enter>", lambda e: lb.config(fg="#ffffff"))
            lb.bind("<Leave>", lambda e, k=key: lb.config(fg="#ffffff" if self._act_cur == k else DIM))
            self.act[key] = (ind, lb)
        self._act_cur = None
        for key, icon in (("files", "📁"), ("prev", "👁"), ("lib", "📚"), ("bug", "🐞"), ("games", "🎮"), ("langs", "🌍")):
            add(key, icon, lambda k=key: self.show_page(k))
        add("settings", "⚙", self.settings_menu, side="bottom")
        add("account", "👤", lambda: self.toggle_right("acc"), side="bottom")
        add("ai", "🤖", lambda: self.toggle_right("ai"), side="bottom")

    def act_set(self, key):
        self._act_cur = key
        for k, (ind, lb) in self.act.items():
            ind.config(bg=ACC if k == key else BG2)
            lb.config(fg="#ffffff" if k == key else DIM)

    def show_page(self, key):
        tab = {"files": self.tab_code, "prev": self.tab_prev, "lib": self.tab_lib, "bug": self.tab_bug,
               "games": self.tab_games, "langs": getattr(self, "tab_langs", None)}.get(key)
        if tab is not None:
            self.nb.select(tab)

    def _sync_act(self, e=None):
        try:
            cur = str(self.nb.select())
        except tk.TclError:
            return
        for key, name in (("files", "tab_code"), ("prev", "tab_prev"), ("lib", "tab_lib"), ("bug", "tab_bug"),
                          ("games", "tab_games"), ("langs", "tab_langs")):
            if str(getattr(self, name, "")) == cur:
                self.act_set(key)
                return

    def toggle_right(self, key="ai"):
        pw = self.body_pw
        if str(self.right_f) in pw.panes():
            pw.forget(self.right_f)
        else:
            pw.add(self.right_f, minsize=260, width=340)
            self.show_panel(key)

    def settings_menu(self):
        m = tk.Menu(self, tearoff=0, bg=BG3, fg=FG, activebackground=ACC, activeforeground="#ffffff", bd=0)
        m.add_command(label="Сменить тему  Ctrl+T", command=lambda: self.apply_theme(self.settings.get("theme", 0) + 1))
        m.add_command(label="Ключи входа (Google / GitHub)", command=lambda: self.auth_keys(self))
        m.add_command(label="Сервер (адрес)…", command=self.server_dialog)
        m.add_command(label="Авто-папки для новых файлов (вкл/выкл)", command=self.toggle_auto_folders)
        m.add_command(label="Почта Resend (коды на email)…", command=self.resend_dialog)
        m.add_command(label="Ключ Gemini…", command=lambda: self.gemini_key(True))
        m.add_command(label="Модель Gemini…", command=self.gemini_model_dialog)
        m.add_command(label="Горячие клавиши  F1", command=self.show_help)
        ind, lb = self.act["settings"]
        m.tk_popup(lb.winfo_rootx() + 40, lb.winfo_rooty())

    # ---------- левая панель: файлы
    def build_left(self, f):
        head = tk.Frame(f, bg=BG2)
        head.pack(fill="x", padx=8, pady=8)
        tk.Label(head, text="ФАЙЛЫ", bg=BG2, fg=DIM, font=("Segoe UI", 9, "bold")).pack(side="left")
        mkbtn(head, "📂", self.ask_open_dir, padx=6).pack(side="right")
        mkbtn(head, "📁＋", self.new_folder, padx=6).pack(side="right", padx=3)
        mkbtn(head, "📄＋", self.new_file_menu, padx=6).pack(side="right")
        row = tk.Frame(f, bg=BG2)
        row.pack(fill="x", padx=8, pady=(0, 8))
        mkbtn(row, "⇅  Сортировать", self.sort_project, bg=ACC, fg="#ffffff").pack(side="left", fill="x", expand=True)
        mkbtn(row, "↶", self.undo_sort, padx=8).pack(side="left", padx=(4, 0))
        self.tree = ttk.Treeview(f, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        self.tree.bind("<Double-1>", self.on_tree_open)
        for ev in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
            self.tree.bind(ev, self.tree_menu)

    # ---------- центр: вкладки + консоль
    def build_center(self, f):
        pw = tk.PanedWindow(f, orient="vertical", bg=BG, sashwidth=4, bd=0)
        pw.pack(fill="both", expand=True)
        self.nb = ttk.Notebook(pw, style="Hidden.TNotebook")
        pw.add(self.nb, minsize=300, stretch="always")
        self.tab_code, self.tab_lib = tk.Frame(self.nb, bg=BG), tk.Frame(self.nb, bg=BG)
        self.tab_bug, self.tab_games = tk.Frame(self.nb, bg=BG), tk.Frame(self.nb, bg=BG)
        self.tab_prev = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_code, text="✎  Код")
        self.nb.add(self.tab_prev, text="👁  Просмотр")
        self.nb.add(self.tab_lib, text="📚  Library")
        self.nb.add(self.tab_bug, text="🐞  Bug")
        self.nb.add(self.tab_games, text="🎮  Игры")
        self.build_tabbar(self.tab_code)
        self.editor = Editor(self.tab_code, self)
        self.editor.pack(fill="both", expand=True)
        self.build_findbar(self.tab_code)
        self.build_library()
        self.build_bug()
        self.build_games()
        self.build_preview()
        con = tk.Frame(pw, bg=BG2)
        pw.add(con, minsize=90, height=190)
        h = tk.Frame(con, bg=BG2)
        h.pack(fill="x")
        tk.Label(h, text="  ТЕРМИНАЛ", bg=BG2, fg=DIM, font=("Segoe UI", 9, "bold")).pack(side="left", pady=4)
        mkbtn(h, "✕", self.console_clear, padx=6, pady=0).pack(side="right", padx=6)
        self.console = tk.Text(con, height=8, bg="#14151b", fg=FG, font=(config.MONO, 11), relief="flat", bd=0,
                               state="disabled", padx=8, pady=4, highlightthickness=0)
        self.console.tag_configure("err", foreground=RED)
        self.console.tag_configure("info", foreground=BLUE)
        self.console.pack(fill="both", expand=True)
        self.stdin_entry = tk.Entry(con, bg=BG3, fg=FG, insertbackground="#ffffff", relief="flat", font=(config.MONO, 11))
        self.stdin_entry.pack(fill="x", ipady=4)
        self.stdin_entry.bind("<Return>", self.send_stdin)
