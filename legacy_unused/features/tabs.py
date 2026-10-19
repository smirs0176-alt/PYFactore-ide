"""Вкладки файлов: несколько открытых файлов, переключение, закрытие, звёздочка у несохранённых."""
import os
import tkinter as tk
from tkinter import messagebox
from pyfactor.config import ACC, BG, BG2, BG3, DIM, FG, YEL
from pyfactor.core.langs import LANG_ICONS, lang_of


class TabsMixin:
    # Состояние вкладки: {"path", "code", "saved", "cursor", "yview"}.
    # Активная вкладка живёт в редакторе, остальные — в словарях self.tabs.
    # self.cur_file всегда равен пути активной вкладки.

    def init_tabs(self):
        self.tabs = []
        self.active_tab = None
        self._tabs_sig = None

    def build_tabbar(self, parent):
        self.tabbar = tk.Frame(parent, bg=BG2)
        self.tabbar.pack(fill="x")
        self.tabs_menu_btn = tk.Button(self.tabbar, text="▾", bg=BG2, fg=DIM, relief="flat", bd=0, padx=8,
                                       activebackground=ACC, activeforeground="#ffffff", cursor="hand2",
                                       command=self.tabs_popup)
        self.tabs_menu_btn.pack(side="right")
        self.tabs_holder = tk.Frame(self.tabbar, bg=BG2)
        self.tabs_holder.pack(side="left", fill="x", expand=True)
        self.bind_all("<Control-w>", lambda e: self.tab_close(self.active_tab))
        self.bind_all("<Control-Tab>", lambda e: self.tab_cycle(1))
        self.bind_all("<Control-Shift-Tab>", lambda e: self.tab_cycle(-1))
        self.bind_all("<Control-ISO_Left_Tab>", lambda e: self.tab_cycle(-1))

    # ---------- состояние
    def _tab_dirty(self, i):
        t = self.tabs[i]
        if i == self.active_tab:
            return self.editor.is_dirty()
        return t["code"] != t["saved"]

    def _stash(self):
        """Запомнить состояние редактора в активную вкладку."""
        if self.active_tab is None or self.active_tab >= len(self.tabs):
            return
        t, tx = self.tabs[self.active_tab], self.editor.text
        t.update(path=self.cur_file, code=self.editor.get_code(), saved=self.editor.saved_code,
                 cursor=tx.index("insert"), yview=tx.yview()[0], colors=self.colors_collect())

    def _load(self, i):
        """Показать вкладку i в редакторе."""
        t, tx = self.tabs[i], self.editor.text
        self.active_tab = i
        self.cur_file = t["path"]
        self.editor.lang = lang_of(t["path"])
        self.editor.set_code(t["code"])
        self.editor.saved_code = t["saved"]
        self.colors_apply(t.get("colors"))
        try:
            tx.mark_set("insert", t["cursor"])
            tx.yview_moveto(t["yview"])
        except tk.TclError:
            pass
        self.update_title()
        self.update_pos()
        self.render_tabs()
        self.find_refresh()

    def _tab_index(self, path):
        self._stash()
        for i, t in enumerate(self.tabs):
            if path and t["path"] == path:
                return i
        return None

    # ---------- открыть / переключить
    def tab_activate_existing(self, path):
        i = self._tab_index(path)
        if i is None:
            return False
        if i != self.active_tab:
            self.tab_switch(i)
        return True

    def tab_open(self, path, data, title=None):
        """Открыть новую вкладку с текстом data (для path=None — вкладка без файла)."""
        self._stash()
        self.tabs.append({"path": path, "code": data, "saved": data if path else "", "cursor": "1.0",
                          "yview": 0.0, "title": title, "colors": self.colors_load(path)})
        self._load(len(self.tabs) - 1)

    def tab_switch(self, i):
        if i is None or i == self.active_tab or not (0 <= i < len(self.tabs)):
            return
        self._stash()
        self._load(i)
        self.nb.select(self.tab_code)

    def tab_cycle(self, step):
        if len(self.tabs) > 1 and self.active_tab is not None:
            self.tab_switch((self.active_tab + step) % len(self.tabs))
        return "break"

    # ---------- закрыть
    def tab_close(self, i, ask=True):
        if i is None or not (0 <= i < len(self.tabs)):
            return "break"
        self._stash()
        if ask and self._tab_dirty(i):
            name = self._tab_name(i)
            ans = messagebox.askyesnocancel("PyFactor", "Сохранить изменения в «%s»?" % name, parent=self)
            if ans is None:
                return "break"
            if ans:
                if i != self.active_tab:
                    self._load(i)
                self.save_file()
                if self._tab_dirty(i):      # сохранение отменили
                    return "break"
        was_active = i == self.active_tab
        del self.tabs[i]
        if not self.tabs:
            self.active_tab = None
            self.cur_file = None
            self.editor.set_code("")
            self.update_title()
            self.render_tabs()
            self.find_refresh()
            return "break"
        if was_active:
            self._load(min(i, len(self.tabs) - 1))
        else:
            if i < self.active_tab:
                self.active_tab -= 1
            self.render_tabs()
        return "break"

    def tabs_reset(self):
        """Закрыть все вкладки без вопросов (после сохранения)."""
        self.tabs, self.active_tab = [], None
        self.cur_file = None
        self.editor.set_code("")
        self.update_title()
        self.render_tabs()

    # ---------- изменения на диске
    def tab_rename(self, old, new):
        """Файл или папка переименованы/перемещены: обновить пути вкладок."""
        self._stash()
        for t in self.tabs:
            p = t["path"]
            if p == old:
                t["path"] = new
            elif p and p.startswith(old + os.sep):
                t["path"] = new + p[len(old):]
        if self.active_tab is not None:
            self.cur_file = self.tabs[self.active_tab]["path"]
        self.render_tabs()

    def tab_drop(self, path):
        """Файл или папка удалены: закрыть их вкладки без вопросов."""
        self._stash()
        for i in range(len(self.tabs) - 1, -1, -1):
            p = self.tabs[i]["path"]
            if p and (p == path or p.startswith(path + os.sep)):
                self.tab_close(i, ask=False)

    # ---------- сохранение
    def tabs_dirty(self):
        self._stash()
        return [i for i in range(len(self.tabs)) if self._tab_dirty(i)]

    def tabs_save_all(self):
        """Сохраняет все изменённые вкладки, у которых уже есть файл."""
        self._stash()
        keep = self.active_tab
        for i in self.tabs_dirty():
            if self.tabs[i]["path"]:
                if i != self.active_tab:
                    self._load(i)
                self.save_file()
        if keep is not None and keep < len(self.tabs) and keep != self.active_tab:
            self._load(keep)

    # ---------- рисование
    def _tab_name(self, i):
        t = self.tabs[i]
        path = self.cur_file if i == self.active_tab else t["path"]
        return os.path.basename(path) if path else (t.get("title") or "без имени")

    def render_tabs(self):
        sig = tuple((self._tab_name(i), self._tab_dirty(i), i == self.active_tab) for i in range(len(self.tabs)))
        if sig == self._tabs_sig:
            return
        self._tabs_sig = sig
        for w in self.tabs_holder.winfo_children():
            w.destroy()
        for i, (name, dirty, active) in enumerate(sig):
            bg = BG if active else BG2
            fg = "#ffffff" if active else DIM
            path = self.cur_file if active else self.tabs[i]["path"]
            icon = LANG_ICONS.get(lang_of(path), "📄")
            cell = tk.Frame(self.tabs_holder, bg=bg)
            cell.pack(side="left", padx=(0, 1))
            tk.Frame(cell, bg=ACC if active else bg, height=2).pack(side="top", fill="x")
            row = tk.Frame(cell, bg=bg)
            row.pack(side="top")
            ic = tk.Label(row, text=icon, bg=bg, fg=fg, font=("Segoe UI Emoji", 9), padx=(10), pady=6, cursor="hand2")
            ic.pack(side="left", padx=(0, 0))
            lbl = tk.Label(row, text=name, bg=bg, fg=YEL if dirty else fg, font=("Segoe UI", 10), pady=6, cursor="hand2")
            lbl.pack(side="left")
            x = tk.Label(row, text="●" if dirty else "✕", bg=bg, fg=YEL if dirty else DIM, font=("Segoe UI", 9),
                         padx=8, cursor="hand2")
            x.pack(side="left", padx=(2, 2))
            for w in (cell, row, ic, lbl):
                w.bind("<Button-1>", lambda e, i=i: self.tab_switch(i))
                w.bind("<Button-2>", lambda e, i=i: self.tab_close(i))
            x.bind("<Button-1>", lambda e, i=i: self.tab_close(i))
            x.bind("<Enter>", lambda e, w=x: w.config(fg="#ff5370", text="✕"))
            x.bind("<Leave>", lambda e, w=x, d=dirty: w.config(fg=YEL if d else DIM, text="●" if d else "✕"))

    def tabs_popup(self):
        m = tk.Menu(self, tearoff=0, bg=BG3, fg=FG, activebackground=ACC)
        if not self.tabs:
            m.add_command(label="Нет открытых файлов", state="disabled")
        for i in range(len(self.tabs)):
            mark = "● " if self._tab_dirty(i) else ""
            m.add_command(label=mark + self._tab_name(i), command=lambda i=i: self.tab_switch(i))
        if self.tabs:
            m.add_separator()
            m.add_command(label="Закрыть текущую  (Ctrl+W)", command=lambda: self.tab_close(self.active_tab))
        b = self.tabs_menu_btn
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
