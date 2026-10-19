"""Запуск пользовательских программ: чистое окружение, остановка всего дерева процессов."""
import os
import signal
import subprocess
import sys

SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
MAX_OUTPUT = 5_000_000            # символов вывода за один запуск; дальше процесс останавливается


def scrubbed_env(base=None):
    """Копия окружения без ключей PyFactor: запускаемая программа не должна получать ключи Gemini, Resend и т. п."""
    env = dict(os.environ if base is None else base)
    for k in list(env):
        up = k.upper()
        if up.startswith("PYFACTOR_") and any(w in up for w in SECRET_WORDS):
            del env[k]
    return env


def popen_extra():
    """Параметры Popen, чтобы потом можно было остановить весь запущенный набор процессов."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {"start_new_session": True}


def kill_tree(proc):
    """Останавливает процесс вместе с дочерними. Не бросает исключений."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=5,  # noqa: S603, S607
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
