"""Связь с твоим сервером (папка server/): аварийный выключатель.
Если сервер отключён, IDE показывает экран «Произошла ошибка» с твоим сообщением, пока ты его не включишь."""
import json
import os
import re
import threading
import time
import tkinter as tk
import urllib.request
from tkinter import simpledialog

from pyfactor.config import ACC, BG, DIM, SETTINGS_F, YEL
from pyfactor.core.utils import save_json
from pyfactor.ui.widgets import mkbtn

DEFAULT_MSG = "Произошла ошибка. Мы уже чиним — попробуй через несколько минут."


def norm_url(u):
    """Адрес может быть любым: домен, IP, localhost:8080 — схему (http/https) допишем сами."""
    u = (u or "").strip().rstrip("/")
    if u and "://" not in u:
        host = u.split("/")[0].split(":")[0]
        local = (host in ("localhost", "::1") or host.startswith(("127.", "10.", "192.168.")) or host.endswith(".local")
                 or re.match(r"172\.(1[6-9]|2\d|3[01])\.", host) is not None)
        u = ("http://" if local else "https://") + u
    if u and not u.lower().startswith(("http://", "https://")):     # file://, ftp:// и прочее не пускаем
        return ""
    return u


class ServerMixin:
    def init_server(self):
        self._srv_block, self._srv_warned = None, False
        self._srv_loop()

    def server_url(self):
        return norm_url(self.settings.get("server_url") or os.environ.get("PYFACTOR_SERVER", ""))

    def _srv_loop(self):
        self._srv_now()
        self.after(10000 if self._srv_block else 30000, self._srv_loop)

    def _srv_now(self):
        url = self.server_url()
        if url:
            threading.Thread(target=self._srv_fetch, args=(url,), daemon=True).start()

    def _srv_fetch(self, url):
        try:
            req = urllib.request.Request(url + "/api/status", headers={"User-Agent": "PyFactor-IDE"})  # noqa: S310
            with urllib.request.urlopen(req, timeout=6) as r:  # noqa: S310
                res = ("ok", json.loads(r.read().decode("utf-8")))
        except Exception as e:
            res = ("down", str(e))
        try:
            self.ui(lambda: self._srv_apply(res))
        except Exception:
            pass

    def _srv_apply(self, res):
        kind, d = res
        if kind == "ok":
            self._srv_warned = False
            if d.get("enabled", True):
                self._srv_unblock()
            else:
                self._srv_show(d.get("message") or DEFAULT_MSG)
        elif self.settings.get("server_strict"):
            self._srv_show("Нет связи с сервером. Проверь интернет — IDE продолжит работу, когда связь появится.")
        elif not self._srv_warned:
            self._srv_warned = True
            self.toast("Сервер недоступен — работаю офлайн")

    def _srv_show(self, msg):
        stamp = "Последняя проверка: " + time.strftime("%H:%M:%S")
        if self._srv_block is None:
            f = tk.Frame(self, bg=BG)
            f.place(x=0, y=0, relwidth=1, relheight=1)
            f.lift()
            box = tk.Frame(f, bg=BG)
            box.place(relx=.5, rely=.45, anchor="center")
            tk.Label(box, text="⚠", fg=YEL, bg=BG, font=("Segoe UI Emoji", 48)).pack()
            tk.Label(box, text="Произошла ошибка", fg="#ffffff", bg=BG, font=("Segoe UI", 22, "bold")).pack(pady=(6, 6))
            lbl = tk.Label(box, text=msg, fg="#d4d7de", bg=BG, wraplength=520, font=("Segoe UI", 12))
            lbl.pack()
            mkbtn(box, "Проверить снова", self._srv_retry, bg=ACC, fg="#ffffff", font=("Segoe UI", 11, "bold")).pack(pady=(18, 8), ipady=4)
            chk = tk.Label(box, text=stamp, fg=DIM, bg=BG, font=("Segoe UI", 9))
            chk.pack()
            self._srv_block = (f, lbl, chk)
            f.focus_set()
        else:
            self._srv_block[1].config(text=msg)
            self._srv_block[2].config(text=stamp)

    def _srv_unblock(self):
        if self._srv_block:
            self._srv_block[0].destroy()
            self._srv_block = None
            self.toast("Сервер снова работает")

    def _srv_retry(self):
        if self._srv_block:
            self._srv_block[2].config(text="Проверяю…")
        self._srv_now()

    def server_dialog(self):
        url = simpledialog.askstring("Сервер", "Адрес сервера (пусто — не использовать):\nнапример https://pf.example.com",
                                     initialvalue=self.server_url(), parent=self)
        if url is None:
            return
        self.settings["server_url"] = url.strip()
        save_json(SETTINGS_F, self.settings, private=True)
        self._srv_unblock()
        self._srv_now()
