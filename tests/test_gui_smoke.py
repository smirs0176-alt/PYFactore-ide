"""Запуск настоящего окна IDE в отдельном процессе. Пропускается, если нет tkinter или дисплея (на CI — через xvfb)."""
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
    os.environ["PYFACTOR_GEMINI_KEY"] = "SECRET-G"
    from pyfactor.ui.app import App
    app = App()
    def pump(sec):
        t = time.time()
        while time.time() - t < sec:
            app.update(); time.sleep(0.02)
    pump(1)
    open(%(script)r, "w").write("import os\\nprint('KEY=%%s' %% bool(os.environ.get('PYFACTOR_GEMINI_KEY')))\\n")
    app.open_file(%(script)r); pump(0.3); app.console_clear(); app.run_file(); pump(3)
    out = app.console.get("1.0", "end")
    app.destroy()
    print("ERRS=%%d" %% len(errs)); print("OUT_HAS_KEY_FALSE=%%s" %% ("KEY=False" in out))
''')


def test_app_starts_and_run_does_not_leak_secrets(tmp_path):
    script = tmp_path / "t.py"
    code = SCRIPT % {"root": ROOT, "script": str(script)}
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYFACTOR_NO_LOGIN="1")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=90, env=env)
    assert "ERRS=0" in r.stdout, r.stdout + r.stderr
    assert "OUT_HAS_KEY_FALSE=True" in r.stdout, r.stdout + r.stderr


CANCEL_SCRIPT = textwrap.dedent('''
    import http.client, os, socket, sys, threading, time, traceback
    sys.path.insert(0, %(root)r)
    import tkinter as tk
    errs = []
    tk.Tk.report_callback_exception = lambda self, *a: errs.append("".join(traceback.format_exception(*a)))
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
    held = []
    threading.Thread(target=lambda: [held.append(srv.accept()[0]) for _ in range(5)], daemon=True).start()
    from pyfactor.core.ai import gemini
    gemini.http.client.HTTPSConnection = http.client.HTTPConnection
    gemini.URL = "http://127.0.0.1:%%d/models/%%%%s:g" %% srv.getsockname()[1]
    from pyfactor.ui.app import App
    app = App()
    app.gemini_key = lambda force=False: "k"
    def pump(sec):
        t = time.time()
        while time.time() - t < sec:
            app.update(); time.sleep(0.02)
    pump(0.5)
    app.ai_in.insert("1.0", "привет"); app.ai_send(); pump(0.6)
    busy1, label1 = app.ai_busy, app.ai_send_btn.cget("text")
    t0 = time.time(); app.ai_send_or_cancel(); pump(0.3)
    print("BUSY_BEFORE=%%s" %% busy1, "LABEL=%%s" %% ("Отменить" in label1))
    print("BUSY_AFTER=%%s" %% app.ai_busy, "FAST=%%s" %% (time.time() - t0 < 2))
    app.ai_in.insert("1.0", "ещё раз"); app.ai_send(); pump(0.4)
    print("SECOND_STARTED=%%s" %% app.ai_busy)
    app.ai_cancel(); pump(0.3)
    print("ERRS=%%d" %% len(errs)); app.destroy()
''')


def test_ai_cancel_button_frees_ui_and_allows_new_request(tmp_path):
    code = CANCEL_SCRIPT % {"root": ROOT}
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYFACTOR_NO_LOGIN="1")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=90, env=env)
    out = r.stdout + r.stderr
    assert "BUSY_BEFORE=True LABEL=True" in out, out
    assert "BUSY_AFTER=False FAST=True" in out, out
    assert "SECOND_STARTED=True" in out and "ERRS=0" in out, out
