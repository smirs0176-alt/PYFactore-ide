"""Правая кнопка мыши в редакторе: меню и выбор цвета для выделенного кода."""
import os
import tkinter as tk
from tkinter import colorchooser
from pyfactor.config import ACC, BG3, FG
from pyfactor.core.utils import load_json, save_json

PALETTE = [("Красный", "#ff5370"), ("Оранжевый", "#f78c6c"), ("Жёлтый", "#ffcb6b"), ("Зелёный", "#c3e88d"),
           ("Бирюзовый", "#89ddff"), ("Синий", "#82aaff"), ("Фиолетовый", "#c792ea"), ("Розовый", "#ff79c6"),
           ("Белый", "#ffffff"), ("Серый", "#8a90a6")]
COLORS_FILE = ".pyfactor_colors.json"


class ColorsMixin:
    def init_colors(self):
        self._swatches = {}

    def _swatch(self, color):
        if color not in self._swatches:
            img = tk.PhotoImage(width=16, height=16)
            img.put(color, to=(0, 0, 16, 16))
            self._swatches[color] = img
        return self._swatches[color]

    # ---------- меню по правой кнопке
    def editor_menu(self, e):
        t = self.editor.text
        t.focus_set()
        idx = t.index("@%d,%d" % (e.x, e.y))
        inside = False
        if t.tag_ranges("sel"):
            inside = t.compare("sel.first", "<=", idx) and t.compare(idx, "<", "sel.last")
        if not inside:                                   # нет выделения — берём слово под курсором
            a, b = t.index(idx + " wordstart"), t.index(idx + " wordend")
            t.mark_set("insert", idx)
            t.tag_remove("sel", "1.0", "end")
            if t.get(a, b).strip():
                t.tag_add("sel", a, b)

        m = tk.Menu(self, tearoff=0, bg=BG3, fg=FG, activebackground=ACC, activeforeground="#ffffff")
        m.add_command(label="Вырезать", command=lambda: t.event_generate("<<Cut>>"))
        m.add_command(label="Копировать", command=lambda: t.event_generate("<<Copy>>"))
        m.add_command(label="Вставить", command=lambda: t.event_generate("<<Paste>>"))
        m.add_command(label="Выделить всё", command=lambda: t.tag_add("sel", "1.0", "end-1c"))
        m.add_separator()
        cm = tk.Menu(m, tearoff=0, bg=BG3, fg=FG, activebackground=ACC, activeforeground="#ffffff")
        for name, col in PALETTE:
            cm.add_command(label="  " + name, image=self._swatch(col), compound="left",
                           command=lambda c=col: self.apply_color(c))
        cm.add_separator()
        cm.add_command(label="🌈 Свой цвет…", command=self.pick_color)
        cm.add_command(label="✕ Убрать цвет", command=self.clear_color)
        m.add_cascade(label="🎨 Цвет текста", menu=cm)
        m.add_separator()
        m.add_command(label="Закомментировать / раскомментировать   Ctrl+/", command=self.editor.toggle_comment)
        m.add_command(label="Найти…   Ctrl+F", command=lambda: self.show_find(False))
        m.add_command(label="Заменить…   Ctrl+H", command=lambda: self.show_find(True))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
        return "break"

    # ---------- цвета
    def _selection(self):
        t = self.editor.text
        try:
            return t.index("sel.first"), t.index("sel.last")
        except tk.TclError:
            self.toast("Сначала выдели код (или кликни правой кнопкой по слову)")
            return None

    def _clear_range(self, a, b):
        t = self.editor.text
        for name in t.tag_names():
            if name.startswith("c_"):
                t.tag_remove(name, a, b)

    def apply_color(self, color):
        sel = self._selection()
        if not sel:
            return
        a, b = sel
        t = self.editor.text
        tag = "c_" + color.lstrip("#").lower()
        t.tag_configure(tag, foreground=color)
        self._clear_range(a, b)
        t.tag_add(tag, a, b)
        self.colors_save()
        self.toast("Цвет применён" + ("" if self.cur_file else " (сохрани файл — цвета запомнятся)"))

    def pick_color(self):
        if not self._selection():
            return
        _, hexcol = colorchooser.askcolor(parent=self, title="Выбери цвет для кода")
        if hexcol:
            self.apply_color(hexcol)

    def clear_color(self):
        sel = self._selection()
        if sel:
            self._clear_range(*sel)
            self.colors_save()
            self.toast("Цвет убран")

    # ---------- запоминание цветов (вкладки и файл проекта)
    def colors_collect(self):
        t, out = self.editor.text, []
        for name in t.tag_names():
            if name.startswith("c_"):
                r = t.tag_ranges(name)
                out += [["#" + name[2:], str(r[k]), str(r[k + 1])] for k in range(0, len(r) - 1, 2)]
        return out

    def colors_apply(self, items):
        t = self.editor.text
        for col, a, b in items or []:
            try:
                tag = "c_" + col.lstrip("#").lower()
                t.tag_configure(tag, foreground=col)
                t.tag_add(tag, a, b)
            except tk.TclError:
                pass

    def _colors_path(self):
        return os.path.join(self.project, COLORS_FILE) if self.project else None

    def colors_load(self, path):
        f = self._colors_path()
        if not f or not path:
            return []
        try:
            return load_json(f, {}).get(os.path.relpath(path, self.project), [])
        except ValueError:
            return []

    def colors_save(self):
        f = self._colors_path()
        if not f or not self.cur_file:
            return
        try:
            data = load_json(f, {})
            rel = os.path.relpath(self.cur_file, self.project)
            items = self.colors_collect()
            if items:
                data[rel] = items
            else:
                data.pop(rel, None)
            if data or os.path.exists(f):
                save_json(f, data)
        except (OSError, ValueError):
            pass
