"""Проект и файлы: дерево, открытие, сохранение, сортировка."""
import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import simpledialog
from pyfactor.config import ACC, BG3, DATA_EXT, FG, FOLDER_ICONS, IMG_EXT, PROJ_ROOT, SETTINGS_F, TEXT_EXT, WEB_EXT
from pyfactor.core.langs import LANG_ICONS, TEMPLATES, lang_of
from pyfactor.core.utils import load_json, save_json


class ProjectMixin:
    # ---------- проект и файлы
    def default_project(self):
        d = os.path.join(PROJ_ROOT, "Проект1")
        os.makedirs(d, exist_ok=True)
        return d

    def open_project(self, path):
        self.tabs_save_all()
        self.tabs_reset()
        self.project = path
        self.settings["last_project"] = path
        save_json(SETTINGS_F, self.settings)
        self.proj_lbl.config(text="📁 " + os.path.basename(path))
        if not [n for n in os.listdir(path) if not n.startswith(".")]:
            with open(os.path.join(path, "main.py"), "w", encoding="utf-8") as f:
                f.write('"""Мой первый проект в PyFactor"""\n\n\ndef main():\n    name = input("Как тебя зовут? ")\n'
                        '    print(f"Привет, {name}! Добро пожаловать в PyFactor ⚡")\n\n\n'
                        'if __name__ == "__main__":\n    main()\n')
        self.refresh_tree()
        mains = [os.path.join(r, "main.py") for r, _, fs in os.walk(path) if "main.py" in fs]
        first = mains[0] if mains else None
        if first:
            self.open_file(first, force=True)

    def ask_open_dir(self):
        d = filedialog.askdirectory(initialdir=PROJ_ROOT, parent=self)
        if d:
            self.open_project(d)

    def refresh_tree(self):
        t = self.tree
        t.delete(*t.get_children())
        if not self.project:
            return

        def icon_file(n):
            e = os.path.splitext(n)[1].lower()
            lg = lang_of(n)
            return LANG_ICONS.get(lg) or ("🖼" if e in IMG_EXT else "🧾" if e == ".json" else "📄")

        def add(parent, path):
            try:
                names = sorted(os.listdir(path), key=lambda n: (not os.path.isdir(os.path.join(path, n)), n.lower()))
            except OSError:
                return
            for n in names:
                if n.startswith(".") or n == "__pycache__":
                    continue
                p = os.path.join(path, n)
                if os.path.isdir(p):
                    iid = t.insert(parent, "end", iid=p, text="%s %s" % (FOLDER_ICONS.get(n, "📁"), n), open=True)
                    add(iid, p)
                else:
                    t.insert(parent, "end", iid=p, text="%s %s" % (icon_file(n), n))
        root = t.insert("", "end", iid=self.project, text="📁 " + os.path.basename(self.project), open=True)
        add(root, self.project)

    def _target_dir(self):
        sel = self.tree.selection()
        if sel:
            p = sel[0]
            return p if os.path.isdir(p) else os.path.dirname(p)
        return self.project

    def new_file(self, default="new.py"):
        name = simpledialog.askstring("Новый файл", "Имя файла:", initialvalue=default, parent=self)
        if not name:
            return
        p = os.path.join(self._target_dir(), name)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write(TEMPLATES.get(os.path.splitext(name)[1].lower(), ""))
        self.refresh_tree()
        self.open_file(p)

    NEW_KINDS = (("🐍 Python  (.py)", "new.py"), ("🌐 HTML  (.html)", "index.html"),
                 ("🎨 CSS  (.css)", "style.css"), ("📜 JavaScript  (.js)", "script.js"), ("📄 Текст  (.txt)", "notes.txt"),
                 ("🧠 Brainfuck  (.bf)", "new.bf"), ("🦧 Ook!  (.ook)", "new.ook"), ("😹 LOLCODE  (.lol)", "new.lol"),
                 ("🇷🇺 Русский Питон  (.rus)", "new.rus"))

    def new_file_submenu(self, parent):
        sub = tk.Menu(parent, tearoff=0, bg=BG3, fg=FG, activebackground=ACC)
        for label, name in self.NEW_KINDS:
            sub.add_command(label=label, command=lambda n=name: self.new_file(n))
        return sub

    def new_file_menu(self):
        m = self.new_file_submenu(self)
        m.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def new_folder(self):
        name = simpledialog.askstring("Новая папка", "Имя папки:", parent=self)
        if name:
            os.makedirs(os.path.join(self._target_dir(), name), exist_ok=True)
            self.refresh_tree()

    def tree_menu(self, e):
        iid = self.tree.identify_row(e.y)
        if iid:
            self.tree.selection_set(iid)
        m = tk.Menu(self, tearoff=0, bg=BG3, fg=FG, activebackground=ACC)
        m.add_cascade(label="Новый файл", menu=self.new_file_submenu(m))
        m.add_command(label="Новая папка", command=self.new_folder)
        if iid and iid != self.project:
            m.add_separator()
            m.add_command(label="Переименовать", command=lambda: self.rename(iid))
            m.add_command(label="Удалить", command=lambda: self.delete(iid))
        m.tk_popup(e.x_root, e.y_root)

    def rename(self, p):
        new = simpledialog.askstring("Переименовать", "Новое имя:", initialvalue=os.path.basename(p), parent=self)
        if new:
            np_ = os.path.join(os.path.dirname(p), new)
            os.rename(p, np_)
            self.tab_rename(p, np_)
            self.refresh_tree()

    def delete(self, p):
        if messagebox.askyesno("Удалить", "Удалить «%s»?" % os.path.basename(p), parent=self):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
            self.tab_drop(p)
            self.refresh_tree()

    def on_tree_open(self, e):
        iid = self.tree.focus()
        if iid and os.path.isfile(iid):
            self.open_file(iid)

    def open_file(self, path, force=False):
        if self.tab_activate_existing(path):
            self.nb.select(self.tab_code)
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in IMG_EXT or (ext not in TEXT_EXT and ext != ""):
            messagebox.showinfo("Файл", "Это не текстовый файл — открыть в редакторе нельзя.", parent=self)
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
        except OSError as ex:
            messagebox.showerror("Ошибка", str(ex), parent=self)
            return
        self.tab_open(path, data)
        self.nb.select(self.tab_code)

    def save_file(self):
        if not self.cur_file:
            p = filedialog.asksaveasfilename(initialdir=self.project, defaultextension=".py", parent=self)
            if not p:
                return
            self.cur_file = p
        try:
            code = self.editor.get_code()
            with open(self.cur_file, "w", encoding="utf-8") as f:
                f.write(code)
            self.editor.saved_code = code
        except OSError as ex:
            messagebox.showerror("Ошибка", str(ex), parent=self)
            return
        self.colors_save()
        self.refresh_tree()
        self.update_title()
        self.toast("Сохранено: " + os.path.basename(self.cur_file))

    def update_title(self):
        name = os.path.basename(self.cur_file) if self.cur_file else "без имени"
        dirty = "● " if self.editor.is_dirty() else ""
        self.title("PyFactor IDE — %s%s" % (dirty, name))
        self.editor.set_lang(lang_of(self.cur_file))
        self.render_tabs()

    def sort_project(self):
        if not self.project:
            return
        self.tabs_save_all()
        moves = []
        for n in sorted(os.listdir(self.project)):
            p = os.path.join(self.project, n)
            if os.path.isdir(p) or n.startswith("."):
                continue
            ext = os.path.splitext(n)[1].lower()
            if ext == ".py":
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        src = f.read()
                except OSError:
                    continue
                dest = "python" if (n == "main.py" or re.search(r"^if\s+__name__\s*==", src, re.M)) else "libraries"
            elif ext in WEB_EXT:
                dest = "web"
            elif ext in IMG_EXT:
                dest = "assets"
            elif ext in DATA_EXT:
                dest = "data"
            else:
                dest = "other"
            dd = os.path.join(self.project, dest)
            os.makedirs(dd, exist_ok=True)
            target = os.path.join(dd, n)
            if os.path.exists(target):
                continue
            shutil.move(p, target)
            moves.append([p, target])
            self.tab_rename(p, target)
        save_json(os.path.join(self.project, ".pyfactor_sort.json"), moves)
        self.refresh_tree()
        self.update_title()
        self.toast("Отсортировано файлов: %d (↶ вернёт назад)" % len(moves))

    def undo_sort(self):
        f = os.path.join(self.project, ".pyfactor_sort.json")
        moves = load_json(f, [])
        if not moves:
            self.toast("Нечего возвращать")
            return
        for src, dst in reversed(moves):
            if os.path.exists(dst) and not os.path.exists(src):
                shutil.move(dst, src)
                self.tab_rename(dst, src)
        save_json(f, [])
        for d in ("python", "web", "libraries", "assets", "data", "other"):
            dd = os.path.join(self.project, d)
            if os.path.isdir(dd) and not os.listdir(dd):
                os.rmdir(dd)
        self.refresh_tree()
        self.update_title()
        self.toast("Сортировка отменена")

    # ---------- запуск
    def import_paths(self):
        if not self.project:
            return []
        paths = [self.project]
        try:
            for n in os.listdir(self.project):
                p = os.path.join(self.project, n)
                if os.path.isdir(p) and not n.startswith(".") and n != "__pycache__":
                    paths.append(p)
        except OSError:
            pass
        return paths
