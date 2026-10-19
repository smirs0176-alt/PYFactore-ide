"""Рабочий сценарий в настоящем окне: проект в папке с пробелами и кириллицей, правка, запуск (с автосохранением), ошибка в программе."""
import os
import subprocess
import sys
import textwrap

import pytest

try:
    import tkinter  # noqa: F401
    HAVE_TK = True
except ImportError:
    HAVE_TK = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(not HAVE_TK or not (os.environ.get("DISPLAY") or sys.platform == "win32"),
                                reason="нужны tkinter и дисплей (xvfb-run pytest)")

SCRIPT = textwrap.dedent('''
    import os, sys, time, traceback
    sys.path.insert(0, %(root)r)
    import tkinter as tk
    errs = []
    tk.Tk.report_callback_exception = lambda self, *a: errs.append("".join(traceback.format_exception(*a)))
    from pyfactor.ui.app import App
    app = App()
    def pump(sec):
        t = time.time()
        while time.time() - t < sec:
            app.update(); time.sleep(0.02)
    pump(0.8)
    def type_code(code):                       # как ввод пользователя: set_code() — это загрузка файла и она считает текст сохранённым
        app.editor.text.delete("1.0", "end"); app.editor.text.insert("1.0", code); pump(0.3)
    proj = %(proj)r
    os.makedirs(proj, exist_ok=True)
    main = os.path.join(proj, "программа с пробелом.py")
    open(main, "w", encoding="utf-8").write("print('старый')\\n")
    app.open_project(proj); pump(0.5)
    app.open_file(main); pump(0.3)
    type_code("print('Привет, мир ✓')\\n")
    print("DIRTY_BEFORE_RUN=%%s" %% app.editor.is_dirty())
    app.console_clear(); app.run_file(); pump(3)
    out = app.console.get("1.0", "end")
    print("SAVED_ON_RUN=%%s" %% ("Привет, мир ✓" in open(main, encoding="utf-8").read()))
    print("UNICODE_OUT=%%s" %% ("Привет, мир ✓" in out))
    type_code("def f(:\\n    pass\\n")
    app.console_clear(); app.run_file(); pump(3)
    out2 = app.console.get("1.0", "end")
    print("SYNTAX_ERR_SHOWN=%%s" %% ("SyntaxError" in out2))
    type_code("print('снова работает')\\n")
    app.console_clear(); app.run_file(); pump(3)
    print("RECOVERED=%%s" %% ("снова работает" in app.console.get("1.0", "end")))
    print("ERRS=%%d" %% len(errs))
    for e in errs: print(e)
    app.destroy()
''')


def test_unicode_project_edit_run_error_recover(tmp_path):
    home = tmp_path / "дом пользователя"
    home.mkdir()
    proj = str(tmp_path / "Мой проект с пробелами")
    code = SCRIPT % {"root": ROOT, "proj": proj}
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYFACTOR_NO_LOGIN="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", timeout=120, env=env)  # noqa: S603
    out = r.stdout + r.stderr
    for flag in ("DIRTY_BEFORE_RUN=True", "SAVED_ON_RUN=True", "UNICODE_OUT=True", "SYNTAX_ERR_SHOWN=True", "RECOVERED=True", "ERRS=0"):
        assert flag in out, "%s не выполнено:\n%s" % (flag, out[-1500:])
