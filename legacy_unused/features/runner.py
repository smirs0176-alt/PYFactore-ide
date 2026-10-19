"""Запуск файла, консоль и ввод."""
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pyfactor.config import NO_WIN
from pyfactor.core.langs import FUN_LANGS, FUNRUN, lang_of
from pyfactor.core.packs import PACKS


class RunnerMixin:
    def make_env(self, cwd):
        env = os.environ.copy()
        paths = self.import_paths() if cwd == self.project else [cwd]
        env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        env["PYTHONUNBUFFERED"] = "1"
        env["PYFACTOR_PROJECT"] = cwd or ""
        return env

    def run_file(self):
        if not self.cur_file:
            self.save_file()
            if not self.cur_file:
                return
        elif self.editor.is_dirty():
            self.save_file()
        lang = lang_of(self.cur_file)
        if lang in ("html", "css"):
            self.web_run()
            return
        if lang == "js":
            self.run_js()
            return
        if lang in PACKS:
            self.run_pack(lang)
            return
        if lang in FUN_LANGS:
            self.spawn(self.cur_file, self.project, cmd=[sys.executable, "-u", FUNRUN, self.cur_file])
            return
        if not self.cur_file.endswith(".py"):
            self.toast("Запускать можно .py, .js, а .html и .css — смотреть")
            return
        self.spawn(self.cur_file, self.project)

    def spawn(self, script, cwd, cmd=None):
        self.stop_file()
        self.console_clear()
        self.show_terminal()
        self.set_ready("Running…")
        self.cprint("[PyFactor Terminal] Run: %s\n" % os.path.basename(script), "info")
        try:
            p = subprocess.Popen(cmd or [sys.executable, "-u", script], cwd=cwd, env=self.make_env(cwd),
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=NO_WIN)
        except Exception as e:
            self.cprint(str(e) + "\n", "err")
            self.set_ready("Error")
            return
        self.proc, t0 = p, time.time()

        def reader():
            for line in p.stdout:
                self.ui(lambda l=line: self.cprint(l))
            rc = p.wait()
            dt = time.time() - t0
            self.ui(lambda: self.cprint("\n[PyFactor Terminal] Command finished: %s (code %s, %.1f s)\n"
                                        % (os.path.basename(script), rc, dt), "info"))
            self.ui(lambda: self.set_ready("Ready · last run: %.1f s" % dt))
        threading.Thread(target=reader, daemon=True).start()

    def stop_file(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def send_stdin(self, e=None):
        line = self.stdin_entry.get()
        self.stdin_entry.delete(0, "end")
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(line + "\n")
                self.proc.stdin.flush()
                self.cprint(line + "\n", "info")
            except Exception:
                pass

    def cprint(self, text, tag=None):
        c = self.console
        if tag is None and re.search(r"Traceback|Error|Exception", text):
            tag = "err"
        c.config(state="normal")
        c.insert("end", text, tag)
        if int(c.index("end-1c").split(".")[0]) > 5000:
            c.delete("1.0", "1000.0")
        c.see("end")
        c.config(state="disabled")

    def console_clear(self):
        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")

    # ---------- служебное
    def ui(self, fn):
        self.q.put(fn)

    def poll(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        except Exception as e:
            print("UI error:", e)
        self.after(80, self.poll)
