"""Запуск файла, консоль и ввод."""
import os
import queue
import re
import subprocess
import threading
import time

from pyfactor.config import PG2_DIR
from pyfactor.core.languages.langs import FUN_LANGS, FUNRUN, lang_of
from pyfactor.core.languages.packs import PACKS
from pyfactor.core.process import MAX_OUTPUT, kill_tree, popen_extra, scrubbed_env
from pyfactor.core.pyexe import python_cmd


class RunnerMixin:
    def make_env(self, cwd):
        env = scrubbed_env()
        paths = (self.import_paths() if cwd == self.project else [cwd]) + [PG2_DIR]
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
            py = self.py_cmd()
            if py:
                self.spawn(self.cur_file, self.project, cmd=py + ["-u", FUNRUN, self.cur_file])
            return
        if not self.cur_file.endswith(".py"):
            self.toast("Запускать можно .py, .js, а .html и .css — смотреть")
            return
        self.spawn(self.cur_file, self.project)

    def py_cmd(self):
        """Python для запуска программ пользователя (в EXE — установленный на компьютере). None — не найден, в консоль выведено пояснение."""
        cmd = python_cmd(self.settings.get("python_path"))
        if cmd is None:
            self.cprint("Не найден Python 3. Установи его с python.org (с галочкой Add to PATH) "
                        "или впиши путь в settings.json: \"python_path\".\n", "err")
        return cmd

    def spawn(self, script, cwd, cmd=None):
        self.stop_file()
        self.console_clear()
        self.cprint("▶ %s\n" % os.path.basename(script), "info")
        if cmd is None:
            py = self.py_cmd()
            if not py:
                return
            cmd = py + ["-u", script]
        try:
            p = subprocess.Popen(cmd, cwd=cwd, env=self.make_env(cwd),  # noqa: S603
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace", bufsize=1, **popen_extra())
        except Exception as e:
            self.cprint(str(e) + "\n", "err")
            return
        self.proc, t0 = p, time.time()

        limit = self.settings.get("run_timeout", 0)          # секунд; 0 — без ограничения
        if isinstance(limit, (int, float)) and limit > 0:
            tm = threading.Timer(limit, lambda: self._stop_if(p, "превышено время (%d с)" % limit))
            tm.daemon = True
            tm.start()

        def reader():
            sent = 0
            for line in p.stdout:
                sent += len(line)
                if sent > MAX_OUTPUT:
                    self._stop_if(p, "слишком большой вывод")
                    break
                self.ui(lambda l=line: self.cprint(l))
            rc = p.wait()
            self.ui(lambda: self.cprint("\n■ завершено (код %s, %.1f с)\n" % (rc, time.time() - t0), "info"))
        threading.Thread(target=reader, daemon=True).start()

    def _stop_if(self, p, why):
        if p.poll() is None:
            kill_tree(p)
            self.ui(lambda: self.cprint("\n■ остановлено: %s\n" % why, "err"))

    def stop_file(self):
        kill_tree(self.proc)
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
