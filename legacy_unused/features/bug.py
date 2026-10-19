"""Вкладка Bug: быстрый, авто, ручной и максимальный тест."""
import ast
import os
import shutil
import tempfile
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk
from pyfactor import config
from pyfactor.config import ACC, BG, BG3, BLUE, DIM, FG, GREEN, IMPORT_BY_NAME, RED, YEL
from pyfactor.core.analysis import add_import, analyze, fix_syntax, last_err_line, required_args, run_py
from pyfactor.core.check import check_code
from pyfactor.ui.widgets import mkbtn


class BugMixin:
    # ---------- вкладка Bug
    def build_bug(self):
        f = self.tab_bug
        tk.Label(f, text="Проверка кода", bg=BG, fg="#ffffff", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        self.bug_shim = self.add_shimmer(f, 6)
        self.bug_shim.pack(fill="x", padx=14)
        self.mode_desc = {
            "quick": "Быстрый тест: проверка синтаксиса, поиск неопределённых имён и пробный запуск на 4 секунды.",
            "auto": "Авто: ИИ сам ищет ошибки и правит их (скобки, двоеточия, отступы, недостающие import) "
                    "и затем запускает код. Ctrl+Z отменит правки.",
            "manual": "Ручной: ты сам управляешь. Список проблем обновляется на лету — двойной клик переходит к строке.",
            "max": "Максимальный: КАЖДАЯ функция и класс запускаются отдельно в своём процессе, параллельно.",
        }
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=14, pady=6)
        for txt, val in (("⚡ Быстрый", "quick"), ("🤖 Авто", "auto"), ("🎛 Ручной", "manual"), ("🔬 Максимальный", "max")):
            tk.Radiobutton(row, text=txt, variable=self.bug_mode, value=val, indicatoron=0, bg=BG3, fg=FG,
                           selectcolor=ACC, relief="flat", padx=12, pady=7, bd=0, font=("Segoe UI", 10, "bold"),
                           command=self.on_bug_mode).pack(side="left", padx=3)
        self.bug_desc_lbl = tk.Label(f, text="", bg=BG, fg=DIM, wraplength=760, justify="left")
        self.bug_desc_lbl.pack(anchor="w", padx=14)
        self.bug_warn = tk.Label(f, text="", bg=BG, fg=YEL, font=("Segoe UI", 9, "bold"))
        self.bug_warn.pack(anchor="w", padx=14)
        mkbtn(f, "▶  Проверить", self.run_bug, bg=GREEN, fg="#102018", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=8)
        cols = ("kind", "line", "msg")
        self.issues = ttk.Treeview(f, columns=cols, show="headings", height=6)
        for c, w, t in (("kind", 60, ""), ("line", 70, "Строка"), ("msg", 600, "Проблема")):
            self.issues.heading(c, text=t)
            self.issues.column(c, width=w, stretch=(c == "msg"))
        self.issues.pack(fill="x", padx=14)
        self.issues.bind("<Double-1>", self.on_issue_open)
        self.blog = tk.Text(f, bg="#171b1e", fg=FG, font=(config.MONO, 11), relief="flat", bd=0, padx=10, pady=6, state="disabled",
                            highlightthickness=0)
        for tag, col in (("ok", GREEN), ("bad", RED), ("warn", YEL), ("info", BLUE)):
            self.blog.tag_configure(tag, foreground=col)
        self.blog.pack(fill="both", expand=True, padx=14, pady=10)
        self.on_bug_mode()

    def on_bug_mode(self):
        m, lang = self.bug_mode.get(), self.editor.lang
        if lang == "python":
            self.bug_desc_lbl.config(text=self.mode_desc[m])
        else:
            self.bug_desc_lbl.config(text=self.WEB_DESC.get(lang, "Для текстовых файлов проверка не нужна."))
        self.bug_warn.config(text="⚠ Рекомендуется ПК с 16 ГБ оперативной памяти (много процессов сразу)"
                             if m == "max" and lang == "python" else "")
        if m == "manual":
            self.fill_issues(check_code(self.editor.get_code(), lang))

    def blog_print(self, text, tag=None):
        b = self.blog
        b.config(state="normal")
        b.insert("end", text + "\n", tag)
        b.see("end")
        b.config(state="disabled")

    def fill_issues(self, res):
        self.issues.delete(*self.issues.get_children())
        for ln, col, msg in res["errors"]:
            self.issues.insert("", "end", values=("🔴", ln, msg))
        for ln, col, msg, kind, name in res["warnings"]:
            self.issues.insert("", "end", values=("🟡", ln, msg))

    def on_issue_open(self, e=None):
        sel = self.issues.selection()
        if sel:
            self.nb.select(self.tab_code)
            self.editor.goto(int(self.issues.item(sel[0], "values")[1]))

    def run_bug(self):
        mode = self.bug_mode.get()
        code = self.editor.get_code()
        self.blog.config(state="normal")
        self.blog.delete("1.0", "end")
        self.blog.config(state="disabled")
        lang = self.editor.lang
        if lang == "text":
            self.blog_print("Для текстовых файлов проверка не нужна.", "info")
            return
        if lang != "python":
            self.run_bug_web(mode, code, lang)
            return
        res = analyze(code)
        self.fill_issues(res)
        if mode == "manual":
            self.blog_print("Ручной режим: найдено ошибок — %d, предупреждений — %d." % (len(res["errors"]), len(res["warnings"])), "info")
            return
        if self.cur_file and self.editor.is_dirty():
            self.save_file()
        threading.Thread(target=self._bug_worker, args=(mode, code), daemon=True).start()

    def _log(self, text, tag=None):
        self.ui(lambda: self.blog_print(text, tag))

    def _bug_worker(self, mode, code):
        env = self.make_env(self.project)
        tmpd = tempfile.mkdtemp(prefix="pyfactor_")
        try:
            if mode == "auto":
                code = self._auto_fix(code)
            res = analyze(code)
            if res["errors"]:
                ln, _, msg = res["errors"][0]
                self._log("✗ Синтаксическая ошибка, строка %d: %s" % (ln, msg), "bad")
                return
            self._log("✓ Синтаксис в порядке", "ok")
            for ln, col, msg, kind, name in res["warnings"]:
                self._log("• строка %d: %s" % (ln, msg), "warn")
            if mode == "max":
                self._max_test(code, res["tree"], env, tmpd)
                return
            path = os.path.join(tmpd, "_check.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            self._log("… пробный запуск (до 4 сек)", "info")
            rc, out, err, to = run_py(path, self.project, env, 4)
            if to:
                self._log("✓ Программа работает и не упала за 4 сек (цикл/окно)", "ok")
            elif rc == 0:
                self._log("✓ Запуск прошёл без ошибок", "ok")
            else:
                self._log("✗ Ошибка при запуске: " + last_err_line(err), "bad")
                if mode == "auto" and "ModuleNotFoundError" in err:
                    self._log("ℹ Библиотека не найдена на этом ПК. Установи её или убери import.", "warn")
        finally:
            shutil.rmtree(tmpd, ignore_errors=True)

    def _auto_fix(self, code):
        self._log("🤖 ИИ ищет ошибки…", "info")
        fixed = 0
        for _ in range(25):
            r = analyze(code)
            if r["errors"]:
                ln, _, msg = r["errors"][0]
                new = fix_syntax(code, ln, msg)
                if not new or new == code:
                    self._log("✗ Строка %d: «%s» — автоматически не починить, поправь вручную." % (ln, msg), "bad")
                    break
                self._log("🔧 строка %d: %s → исправлено" % (ln, msg), "ok")
                code, fixed = new, fixed + 1
                continue
            done = True
            for ln, col, msg, kind, name in r["warnings"]:
                if kind == "undef" and name in IMPORT_BY_NAME:
                    imp = IMPORT_BY_NAME[name]
                    code = add_import(code, imp)
                    self._log("🔧 добавлен %s (использовался '%s')" % (imp, name), "ok")
                    fixed, done = fixed + 1, False
                    break
            if done:
                break
        if fixed:
            final = code
            self.ui(lambda: self.editor.replace_all(final))
            self._log("✓ Исправлений: %d (Ctrl+Z в редакторе отменит)" % fixed, "ok")
        else:
            self._log("Автоисправлять нечего.", "info")
        return code

    def _max_test(self, code, tree, env, tmpd):
        lines = code.split("\n")

        def seg(n):
            start = min([d.lineno for d in n.decorator_list] + [n.lineno]) if hasattr(n, "decorator_list") else n.lineno
            return "\n".join(lines[start - 1:n.end_lineno])

        ctx, targets = [], []
        for n in tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign)):
                ctx.append(seg(n))
            if isinstance(n, ast.FunctionDef):
                targets.append((n.name, "def", required_args(n) == 0))
            elif isinstance(n, ast.ClassDef):
                init = next((b for b in n.body if isinstance(b, ast.FunctionDef) and b.name == "__init__"), None)
                targets.append((n.name, "class", init is None or required_args(init) <= 1))
        if not targets:
            self._log("В файле нет функций и классов для отдельной проверки.", "warn")
            return
        workers = max(1, min(4, (os.cpu_count() or 2)))
        self._log("🔬 Проверяю %d блок(ов) по отдельности, параллельно: %d" % (len(targets), workers), "info")
        base = "\n".join(ctx)

        def one(t):
            name, kind, callable_ = t
            body = base + "\n\n" + ("%s()\n" % name if callable_ else "pass\n")
            path = os.path.join(tmpd, "t_%s.py" % name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            rc, out, err, to = run_py(path, self.project, env, 6)
            tag = "функция" if kind == "def" else "класс"
            if to:
                self._log("✓ %s %s — работает 6+ сек (цикл/окно), ошибок нет" % (tag, name), "ok")
                return True
            if rc == 0:
                note = "" if callable_ else " (вызов пропущен: нужны аргументы)"
                self._log("✓ %s %s — OK%s" % (tag, name, note), "ok")
                return True
            self._log("✗ %s %s — %s" % (tag, name, last_err_line(err)), "bad")
            return False

        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(one, targets))
        good = sum(results)
        self._log("Итого: %d из %d блоков без ошибок." % (good, len(results)), "ok" if good == len(results) else "warn")
