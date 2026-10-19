"""Палитра команд (Ctrl+Shift+P): быстрый поиск и запуск любого действия IDE."""
import tkinter as tk

from pyfactor import config


def fuzzy_score(query, text):
    """Чем меньше число, тем лучше совпадение; None — не подходит. Подстрока лучше, чем буквы вразбивку."""
    q, t = query.strip().lower(), text.lower()
    if not q:
        return 0
    if q in t:
        return t.index(q)                       # 0 — совпало с начала названия
    pos, gaps = -1, 0
    for ch in q.replace(" ", ""):
        nxt = t.find(ch, pos + 1)
        if nxt < 0:
            return None
        gaps += nxt - pos - 1 if pos >= 0 else 0
        pos = nxt
    return 1000 + gaps


def filter_commands(query, commands):
    """commands — список (название, подсказка, функция). Возвращает подходящие, лучшие первыми."""
    scored = []
    for i, c in enumerate(commands):
        s = fuzzy_score(query, c[0])
        if s is not None:
            scored.append((s, i, c))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [c for _, _, c in scored]


class PaletteMixin:
    def init_palette(self):
        self._palette = None
        for seq in ("<Control-Shift-P>", "<Control-Shift-p>"):
            self.bind_all(seq, self.open_palette)

    def palette_commands(self):
        """Только реально существующие действия приложения. Открытые вкладки добавляются как «Перейти к …»."""
        spec = [
            ("Открыть папку…", "", "ask_open_dir"), ("Сохранить", "Ctrl+S", "save_file"), ("Сохранить все вкладки", "", "tabs_save_all"),
            ("Запустить", "F5", "run_file"), ("Остановить программу", "", "stop_file"), ("Очистить терминал", "", "console_clear"),
            ("Найти в файле", "Ctrl+F", lambda s: s.show_find(False)), ("Заменить в файле", "Ctrl+H", lambda s: s.show_find(True)),
            ("Поиск по проекту", "Ctrl+Shift+F", "project_search"),
            ("Закрыть вкладку", "Ctrl+W", lambda s: s.tab_close(s.active_tab)),
            ("Следующая вкладка", "Ctrl+Tab", lambda s: s.tab_cycle(1)), ("Предыдущая вкладка", "", lambda s: s.tab_cycle(-1)),
            ("Закомментировать / раскомментировать", "Ctrl+/", lambda s: s.editor.toggle_comment()),
            ("Панель справа (ИИ, библиотеки)", "", lambda s: s.toggle_right("ai")),
            ("ИИ: отменить запрос", "Esc", "ai_cancel"), ("ИИ: очистить чат", "", "ai_clear"),
            ("ИИ: ключ Gemini…", "", lambda s: s.gemini_key(True)), ("ИИ: модель Gemini…", "", "gemini_model_dialog"),
            ("Отладка / ошибки", "", lambda s: s.show_page("bug")), ("Опубликовать на GitHub", "", "publish_github"),
            ("Сменить тему", "Ctrl+T", lambda s: s.apply_theme(s.settings.get("theme", 0) + 1)),
            ("Сервер (адрес)…", "", "server_dialog"), ("Горячие клавиши", "F1", "show_help"), ("Выход", "", "on_close"),
        ]
        out = []
        for title, hint, act in spec:
            fn = (lambda a=act: getattr(self, a)()) if isinstance(act, str) else (lambda a=act: a(self))
            if isinstance(act, str) and not callable(getattr(self, act, None)):
                continue
            out.append((title, hint, fn))
        try:
            for i in range(len(self.tabs)):
                out.append(("Перейти к: " + self._tab_name(i), "", lambda i=i: self.tab_switch(i)))
        except Exception:
            pass
        return out

    def open_palette(self, e=None):
        if getattr(self, "_palette", None) is not None:
            try:
                self._palette.destroy()
            except tk.TclError:
                pass
            self._palette = None
            return "break"
        cmds = self.palette_commands()
        win = tk.Toplevel(self)
        self._palette = win
        win.transient(self)
        win.configure(bg=config.BG3)
        w, h = 560, 360
        win.geometry("%dx%d+%d+%d" % (w, h, self.winfo_rootx() + (self.winfo_width() - w) // 2, self.winfo_rooty() + 90))
        win.overrideredirect(True)
        entry = tk.Entry(win, bg=config.BG, fg=config.FG, insertbackground="#ffffff", relief="flat", font=("Segoe UI", 12),
                         highlightthickness=1, highlightbackground=config.ACC, highlightcolor=config.ACC)
        entry.pack(fill="x", padx=10, pady=(10, 6), ipady=6)
        lb = tk.Listbox(win, bg=config.BG2, fg=config.FG, selectbackground=config.ACC, selectforeground="#ffffff", relief="flat",
                        font=("Segoe UI", 11), activestyle="none", highlightthickness=0, bd=0)
        lb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        shown = []

        def refresh(*_):
            shown[:] = filter_commands(entry.get(), cmds)
            lb.delete(0, "end")
            for title, hint, _fn in shown:
                lb.insert("end", title + (("      " + hint) if hint else ""))
            if shown:
                lb.selection_set(0)
                lb.activate(0)
            if not shown:
                lb.insert("end", "Ничего не найдено")

        def close(_e=None):
            self._palette = None
            try:
                win.destroy()
            except tk.TclError:
                pass
            try:
                self.focus_force()                 # вернуть фокус в окно, иначе горячие клавиши перестанут работать
                self.editor.text.focus_set()
            except (tk.TclError, AttributeError):
                pass
            return "break"

        def run(_e=None):
            sel = lb.curselection()
            if not shown or not sel:
                return "break"
            fn = shown[sel[0]][2]
            close()
            self.after(30, fn)                     # после закрытия окна, чтобы фокус вернулся в редактор
            return "break"

        def move(step):
            sel = lb.curselection()
            if not shown:
                return "break"
            i = max(0, min(len(shown) - 1, (sel[0] if sel else 0) + step))
            lb.selection_clear(0, "end")
            lb.selection_set(i)
            lb.activate(i)
            lb.see(i)
            return "break"

        entry.bind("<KeyRelease>", lambda ev: refresh() if ev.keysym not in ("Up", "Down", "Return", "Escape") else None)
        entry.bind("<Down>", lambda ev: move(1))
        entry.bind("<Up>", lambda ev: move(-1))
        entry.bind("<Return>", run)
        entry.bind("<Escape>", close)
        lb.bind("<Double-Button-1>", run)
        win.bind("<FocusOut>", lambda ev: win.after(120, lambda: close() if self._palette is win and win.focus_displayof() is None else None))
        refresh()
        win.update_idletasks()
        win.lift()
        entry.focus_force()
        return "break"
