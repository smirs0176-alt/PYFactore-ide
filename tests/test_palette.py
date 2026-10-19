import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("tkinter")        # нужен tkinter (Linux: sudo apt install python3-tk)

from pyfactor.features.workspace.palette import filter_commands, fuzzy_score

CMDS = [("Запустить", "F5", 1), ("Сохранить", "Ctrl+S", 2), ("Сохранить все вкладки", "", 3), ("Поиск по проекту", "", 4),
        ("Закрыть вкладку", "", 5), ("ИИ: отменить запрос", "Esc", 6)]


def test_fuzzy_score_prefers_prefix_then_substring_then_letters():
    assert fuzzy_score("", "что угодно") == 0
    assert fuzzy_score("зап", "Запустить") < fuzzy_score("уст", "Запустить") < fuzzy_score("зпт", "Запустить")
    assert fuzzy_score("xyz", "Запустить") is None


def test_filter_orders_and_drops():
    assert [c[2] for c in filter_commands("сохр", CMDS)] == [2, 3]
    assert [c[2] for c in filter_commands("вкл", CMDS)] == [5, 3]      # раньше в названии — выше
    assert filter_commands("qqq", CMDS) == []
    assert len(filter_commands("", CMDS)) == len(CMDS)             # пустой запрос — все команды
    assert filter_commands("ии", CMDS)[0][2] == 6                  # регистр не важен


try:
    import tkinter  # noqa: F401
    HAVE_TK = True
except ImportError:
    HAVE_TK = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = textwrap.dedent('''
    import sys, time, traceback
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
    pump(0.6)
    called = []
    app.run_file = lambda: called.append("run")
    titles = [c[0] for c in app.palette_commands()]
    print("HAS_RUN=%%s" %% ("Запустить" in titles), "HAS_TAB=%%s" %% any(t.startswith("Перейти к:") for t in titles))
    app.event_generate("<Control-Shift-P>"); pump(0.4)
    print("OPEN=%%s" %% (app._palette is not None))
    pal = app._palette
    entry = [w for w in pal.winfo_children() if isinstance(w, tk.Entry)][0]
    entry.insert(0, "запуст"); entry.event_generate("<KeyRelease>", keysym="t"); pump(0.2)
    lb = [w for w in pal.winfo_children() if isinstance(w, tk.Listbox)][0]
    print("TOP=%%s" %% lb.get(0).split()[0])
    entry.event_generate("<Return>"); pump(0.5)
    print("CLOSED=%%s" %% (app._palette is None), "CALLED=%%s" %% called)
    app.event_generate("<Control-Shift-P>"); pump(0.3)
    app._palette.winfo_children()[0].event_generate("<Escape>"); pump(0.3)
    print("ESC_CLOSED=%%s" %% (app._palette is None), "ERRS=%%d" %% len(errs))
    app.destroy()
''')


@pytest.mark.skipif(not HAVE_TK or not (os.environ.get("DISPLAY") or sys.platform == "win32"), reason="нужны tkinter и дисплей")
def test_palette_opens_filters_runs_and_closes(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYFACTOR_NO_LOGIN="1")
    r = subprocess.run([sys.executable, "-c", SCRIPT % {"root": ROOT}], capture_output=True, text=True, timeout=90, env=env)
    out = r.stdout + r.stderr
    assert "HAS_RUN=True HAS_TAB=True" in out, out
    assert "OPEN=True" in out and "TOP=Запустить" in out, out
    assert "CLOSED=True CALLED=['run']" in out, out
    assert "ESC_CLOSED=True ERRS=0" in out, out
