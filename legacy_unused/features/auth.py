"""Окно авторизации при запуске: Google и GitHub, ввод ключей входа."""
import os
import threading
import tkinter as tk
import webbrowser

from pyfactor.config import ACC, BG, BG2, BG3, DIM, FG, GREEN, SETTINGS_F
from pyfactor.core import oauth
from pyfactor.core.utils import save_json
from pyfactor.ui.widgets import mkbtn

ERR = "#ff5370"


class AuthMixin:
    def auth_creds(self):
        s, e = self.settings, os.environ
        return {"gid": s.get("google_client_id") or e.get("PYFACTOR_GOOGLE_CLIENT_ID", ""),
                "gsec": s.get("google_client_secret") or e.get("PYFACTOR_GOOGLE_CLIENT_SECRET", ""),
                "ghid": s.get("github_client_id") or e.get("PYFACTOR_GITHUB_CLIENT_ID", "")}

    def auth_gate(self):
        """Перед входом в IDE просим авторизоваться (если ещё не вошли)."""
        self._auth_quit = False
        if self.account.get("name") or os.environ.get("PYFACTOR_NO_LOGIN"):
            return
        self.withdraw()
        self.wait_window(self.auth_dialog(gate=True))
        if self._auth_quit:
            self.destroy()
        else:
            self.deiconify()

    def auth_dialog(self, gate=False):
        d = self._auth_win = tk.Toplevel(self)
        d.title("PyFactor — авторизация")
        d.configure(bg=BG2)
        d.resizable(False, False)
        W, H = 400, 520
        d.geometry("%dx%d+%d+%d" % (W, H, (d.winfo_screenwidth() - W) // 2, (d.winfo_screenheight() - H) // 3))
        if getattr(self, "_icon", None):
            d.iconphoto(True, self._icon)
            d._img = self._icon.subsample(4)
            tk.Label(d, image=d._img, bg=BG2).pack(pady=(22, 4))
        tk.Label(d, text="Авторизация", bg=BG2, fg="#ffffff", font=("Segoe UI", 18, "bold")).pack()
        tk.Label(d, text="Войди, чтобы продолжить работу в PyFactor", bg=BG2, fg=DIM).pack(pady=(2, 14))
        stop, st = [threading.Event()], {"busy": False}
        btns = d.btns = {}
        main = tk.Frame(d, bg=BG2)
        main.pack(fill="x", padx=36)
        wait = tk.Frame(d, bg=BG2)
        status = tk.Label(d, text="", bg=BG2, fg=DIM, wraplength=340, justify="center")

        def say(txt, color=DIM):
            status.config(text=txt, fg=color)

        def leave(quit_app=False):
            stop[0].set()
            self._auth_quit = quit_app
            d.destroy()

        def show_main():
            wait.pack_forget()
            main.pack(fill="x", padx=36, before=status)
            st["busy"] = False

        def show_wait(code=None, uri=None):
            main.pack_forget()
            for w in wait.winfo_children():
                w.destroy()
            if code:
                tk.Label(wait, text="Введи этот код на GitHub:", bg=BG2, fg=FG).pack(pady=(4, 6))
                tk.Label(wait, text=code, bg=BG3, fg=ACC, font=("Consolas", 26, "bold"), padx=16, pady=8).pack()
                mkbtn(wait, "🌐 Открыть страницу GitHub", lambda: webbrowser.open(uri), bg=ACC, fg="#ffffff").pack(fill="x", pady=10, ipady=4)
            else:
                tk.Label(wait, text="Открылся браузер — выбери аккаунт Google…", bg=BG2, fg=FG).pack(pady=16)
            mkbtn(wait, "Отмена", lambda: (stop[0].set(), show_main(), say("Отменено"))).pack(fill="x", ipady=3)
            wait.pack(fill="x", padx=36, before=status)

        def start(prov):
            c = self.auth_creds()
            if (prov == "google" and not (c["gid"] and c["gsec"])) or (prov == "github" and not c["ghid"]):
                say("Сначала впиши ключи входа (кнопка «🔑 Ключи входа» ниже).", ERR)
                return
            stop[0], box = threading.Event(), {}
            ev = stop[0]
            st["busy"] = True
            say("Подключаюсь…")

            def work():
                try:
                    if prov == "github":
                        dc = oauth.github_start(c["ghid"])
                        box["code"] = (dc["user_code"], dc["verification_uri"])
                        box["acc"] = oauth.github_wait(c["ghid"], dc, ev)
                    else:
                        box["acc"] = oauth.google_login(c["gid"], c["gsec"], ev)
                except Exception as e:
                    box["err"] = str(e)
                box["done"] = True
            threading.Thread(target=work, daemon=True).start()
            shown = []

            def poll():
                if ev.is_set() or not d.winfo_exists():
                    return
                if (box.get("code") or prov == "google") and not shown:
                    shown.append(1)
                    show_wait(*(box["code"] if prov == "github" else (None, None)))
                    if prov == "github":
                        d.clipboard_clear()
                        d.clipboard_append(box["code"][0])
                    say("Жду подтверждения…")
                if box.get("err"):
                    show_main()
                    say(box["err"], ERR)
                elif box.get("acc"):
                    self.set_account(box["acc"])
                    d.destroy()
                else:
                    d.after(300, poll)
            poll()

        for key, txt in (("google", "🟦  Войти через Google"), ("github", "🐙  Войти через GitHub")):
            btns[key] = mkbtn(main, txt, lambda k=key: start(k), bg=BG3, fg="#ffffff", font=("Segoe UI", 12, "bold"))
            btns[key].pack(fill="x", pady=5, ipady=8)
        status.pack(pady=10, padx=30)
        bottom = tk.Frame(d, bg=BG2)
        bottom.pack(side="bottom", fill="x", padx=36, pady=16)
        btns["keys"] = mkbtn(bottom, "🔑 Ключи входа", lambda: self.auth_keys(d))
        btns["keys"].pack(side="left")
        if gate:
            btns["guest"] = mkbtn(bottom, "Как гость →", lambda: leave(False))
            btns["guest"].pack(side="right")
            btns["quit"] = mkbtn(bottom, "Выйти", lambda: leave(True))
            btns["quit"].pack(side="right", padx=6)
            d.protocol("WM_DELETE_WINDOW", lambda: leave(True))
        else:
            mkbtn(bottom, "Закрыть", lambda: leave(False)).pack(side="right")
            d.protocol("WM_DELETE_WINDOW", lambda: leave(False))
        d.transient(self) if not gate else None
        d.grab_set()
        d.lift()
        return d

    def auth_keys(self, parent):
        k = tk.Toplevel(parent)
        k.title("Ключи входа")
        k.configure(bg=BG2)
        k.geometry("460x470")
        k.grab_set()
        c = self.auth_creds()
        tk.Label(k, text="Ключи входа", bg=BG2, fg="#ffffff", font=("Segoe UI", 14, "bold")).pack(pady=(14, 2))
        tk.Label(k, text="Их создаёшь ты сам, бесплатно, один раз. Без них вход не заработает.",
                 bg=BG2, fg=DIM, wraplength=420).pack()
        vars_ = {}
        for key, label, val in (("google_client_id", "Google Client ID", c["gid"]),
                                ("google_client_secret", "Google Client Secret", c["gsec"]),
                                ("github_client_id", "GitHub Client ID", c["ghid"])):
            tk.Label(k, text=label, bg=BG2, fg=FG).pack(anchor="w", padx=20, pady=(10, 0))
            vars_[key] = tk.StringVar(value=val)
            tk.Entry(k, textvariable=vars_[key], bg=BG3, fg=FG, insertbackground="#ffffff", relief="flat",
                     show="•" if "secret" in key else "").pack(fill="x", padx=20, ipady=4)
        tk.Label(k, justify="left", bg=BG2, fg=DIM, wraplength=420, text=(
            "Google: Cloud Console → «Учётные данные» → создать OAuth-клиент, тип «Приложение для ПК». "
            "Нужны Client ID и Client Secret.\n\n"
            "GitHub: Settings → Developer settings → OAuth Apps → New. Включи «Enable Device Flow». "
            "Нужен только Client ID.")).pack(padx=20, pady=12)
        row = tk.Frame(k, bg=BG2)
        row.pack(fill="x", padx=20)
        mkbtn(row, "Google", lambda: webbrowser.open("https://console.cloud.google.com/apis/credentials")).pack(side="left")
        mkbtn(row, "GitHub", lambda: webbrowser.open("https://github.com/settings/developers")).pack(side="left", padx=6)

        def save():
            for key, v in vars_.items():
                self.settings[key] = v.get().strip()
            save_json(SETTINGS_F, self.settings)
            k.destroy()
        mkbtn(row, "Сохранить", save, bg=ACC, fg="#ffffff").pack(side="right")
