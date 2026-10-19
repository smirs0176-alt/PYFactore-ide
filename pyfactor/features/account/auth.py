"""Окно авторизации при запуске: Google и GitHub, ввод ключей входа."""
import json
import os
import platform
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, simpledialog

from pyfactor.config import ACC, BG, BG2, BG3, CONNECT_F, DEFAULT_GOOGLE_CLIENT_ID, DIM, FG, GREEN, SETTINGS_F, USERS_F
from pyfactor.core.account import cloud, local, mailer, oauth
from pyfactor.core.account.vault import cloud_clear, cloud_get, cloud_save
from pyfactor.core.secure_store import get_secret, set_secret, take_warning
from pyfactor.core.utils import save_json
from pyfactor.ui.widgets import mkbtn

ERR = "#ff5370"


class AuthMixin:
    def auth_creds(self):
        s, e = self.settings, os.environ
        return {"gid": s.get("google_client_id") or e.get("PYFACTOR_GOOGLE_CLIENT_ID", "") or DEFAULT_GOOGLE_CLIENT_ID,
                "gsec": get_secret("google_client_secret", s.get("google_client_secret") or e.get("PYFACTOR_GOOGLE_CLIENT_SECRET", "")),
                "ghid": s.get("github_client_id") or e.get("PYFACTOR_GITHUB_CLIENT_ID", "")}

    def resend_key(self):
        return get_secret("resend_key", self.settings.get("resend_key") or os.environ.get("PYFACTOR_RESEND_KEY", ""))

    def _warn_storage(self):
        """Если секрет не удалось сохранить безопасно — говорим об этом явно, а не молча."""
        warn = take_warning()
        if warn:
            messagebox.showwarning("PyFactor", warn, parent=self)

    def resend_from(self):
        return self.settings.get("resend_from") or mailer.DEFAULT_FROM

    def resend_dialog(self):
        k = simpledialog.askstring("Resend", "API-ключ Resend (начинается с re_).\nОставь пустым, чтобы отключить коды на почту:",
                                   show="•", parent=self)
        if k is None:
            return
        key = k.strip()
        self.settings.pop("resend_key", None)
        if key:
            set_secret("resend_key", key)
            self._warn_storage()
        else:
            from pyfactor.core.secure_store import delete_secret
            delete_secret("resend_key")
        f = simpledialog.askstring("Resend", "Адрес отправителя.\nonboarding@resend.dev шлёт письма только на почту владельца Resend;\n"
                                   "чтобы писать всем, подтверди свой домен: resend.com/domains", initialvalue=self.resend_from(), parent=self)
        if f:
            self.settings["resend_from"] = f.strip()
        save_json(SETTINGS_F, self.settings, private=True)
        self.toast("Коды на почту " + ("включены" if key else "выключены"))

    def auto_connect(self):
        """Рядом лежит connect.json (его кладёт сайт в скачанный архив): меняем код на токен и входим в аккаунт сами."""
        if not os.path.isfile(CONNECT_F):
            return False
        try:
            with open(CONNECT_F, encoding="utf-8") as f:
                c = json.load(f)
            url, code = str(c["server"]), str(c["code"])
        except (OSError, ValueError, KeyError):
            return False
        try:
            r = cloud.claim(url, code, "%s · %s" % (platform.node() or "ПК", platform.system()))
        except cloud.CloudError as ex:
            self._connect_msg = "Подключение к сайту не удалось: %s" % ex
            if ex.kind == "auth":                     # код больше не годится, файл только мешает
                self._remove_connect()
            return False
        cloud_save(self.settings, url, r["token"])
        save_json(SETTINGS_F, self.settings, private=True)
        self._remove_connect()                        # токен остаётся только в ~/.pyfactor, а не в папке приложения
        self.set_account({"provider": "PyFactor", "name": r["name"], "email": r["email"], "cloud": True})
        return True

    def _remove_connect(self):
        try:
            os.remove(CONNECT_F)
        except OSError:
            pass

    def cloud_check(self):
        """В фоне проверяем, что устройство не отключено на сайте. Нет связи — спокойно работаем дальше."""
        c = cloud_get(self.settings)
        if not (c and self.account.get("cloud")):
            return

        def work():
            try:
                r = cloud.me(c["url"], c["token"])
            except cloud.CloudError as ex:
                if ex.kind == "auth":
                    self.ui(self._cloud_revoked)
                return
            if (r.get("name"), r.get("email")) != (self.account.get("name"), self.account.get("email")):
                self.ui(lambda: self.set_account(dict(self.account, name=r.get("name"), email=r.get("email"))))
        threading.Thread(target=work, daemon=True).start()

    def _cloud_revoked(self):
        cloud_clear(self.settings)
        save_json(SETTINGS_F, self.settings, private=True)
        self.logout(revoke=False)
        self.toast("Это устройство отключено на сайте. Войди заново")
        self.auth_gate()

    def auth_gate(self):
        """Перед входом в IDE: сначала автоподключение по connect.json, иначе просим авторизоваться."""
        self._auth_quit = False
        self._connect_msg = ""
        if self.auto_connect():
            return
        if self._connect_msg:
            self.after(800, lambda: self.toast(self._connect_msg))
        if self.account.get("name") or os.environ.get("PYFACTOR_NO_LOGIN"):
            self.cloud_check()
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
        W, H = 400, 760
        d.geometry("%dx%d+%d+%d" % (W, H, (d.winfo_screenwidth() - W) // 2, (d.winfo_screenheight() - H) // 3))
        if getattr(self, "_icon", None):
            d.iconphoto(True, self._icon)
            d._img = self._icon.subsample(4)
            tk.Label(d, image=d._img, bg=BG2).pack(pady=(22, 4))
        tk.Label(d, text="Авторизация", bg=BG2, fg="#ffffff", font=("Segoe UI", 18, "bold")).pack()
        tk.Label(d, text="Войди или создай аккаунт — это займёт 10 секунд", bg=BG2, fg=DIM).pack(pady=(2, 10))
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

        # --- вход и регистрация по email и паролю (без Google и ключей)
        def field(parent, label, secret=False):
            tk.Label(parent, text=label, bg=BG2, fg=DIM, anchor="w").pack(fill="x")
            e = tk.Entry(parent, show="•" if secret else "", bg=BG, fg=FG, insertbackground="#ffffff", relief="flat",
                         font=("Segoe UI", 11), highlightthickness=1, highlightbackground=BG3, highlightcolor=ACC)
            e.pack(fill="x", ipady=5, pady=(0, 6))
            return e
        e_mail, e_pass = field(main, "Email"), field(main, "Пароль", True)
        extra = tk.Frame(main, bg=BG2)                      # поля только для регистрации
        e_pass2, e_name = field(extra, "Повтори пароль", True), field(extra, "Имя (необязательно)")
        show_pw = tk.BooleanVar(value=False)
        tk.Checkbutton(main, text="показать пароль", variable=show_pw, bg=BG2, fg=DIM, selectcolor=BG, activebackground=BG2,
                       activeforeground=FG, highlightthickness=0, bd=0,
                       command=lambda: [w.config(show="" if show_pw.get() else "•") for w in (e_pass, e_pass2)]).pack(anchor="w")
        mode, pend = {"reg": False}, {}
        slot = tk.Frame(main, bg=BG2)                       # сюда встаёт шаг «введи код из письма»
        code_box = tk.Frame(slot, bg=BG2)
        tk.Label(code_box, text="Мы отправили 6-значный код на твою почту.\nПосмотри «Входящие» и «Спам».",
                 bg=BG2, fg=FG, justify="left").pack(anchor="w", pady=(4, 6))
        e_code = field(code_box, "Код из письма")

        def finish_register(p):
            try:
                acc = local.register(USERS_F, p["email"], p["password"], p["name"])
            except local.AuthError as ex:
                say(str(ex), ERR)
                return
            self.set_account(acc)
            d.destroy()

        def layout(reg):
            for w in (extra, btns["go"], btns["switch"]):
                w.pack_forget()
            if reg:
                extra.pack(fill="x", before=slot)
            btns["go"].pack(fill="x", ipady=5, pady=(8, 4), before=slot)
            btns["switch"].pack(fill="x", pady=(0, 6), before=slot)

        def set_mode(reg):
            mode["reg"] = reg
            say("")
            layout(reg)
            btns["go"].config(text="Создать аккаунт" if reg else "Войти")
            btns["switch"].config(text="Уже есть аккаунт? Войти" if reg else "Нет аккаунта? Создать")
            e_mail.focus_set()

        def code_step(on):
            for w in (extra, btns["go"], btns["switch"]):
                w.pack_forget()
            if on:
                code_box.pack(fill="x")
                e_code.delete(0, "end")
                e_code.focus_set()
            else:
                code_box.pack_forget()
                set_mode(True)

        def sent(p, err):
            if not d.winfo_exists():
                return
            if err:
                say(err, ERR)
                return
            pend.clear()
            pend.update(p)
            code_step(True)
            say("Код отправлен на %s" % p["email"], GREEN)

        def send_code(p):
            key, sender = self.resend_key(), self.resend_from()
            say("Отправляю код на %s…" % p["email"])

            def work():
                err = None
                try:
                    local.make_code(p["email"])
                    mailer.send_code(key, p["email"], local._PENDING[p["email"]]["code"], sender)
                except (local.AuthError, mailer.MailError) as ex:
                    err = str(ex)
                    if isinstance(ex, mailer.MailError):
                        local.drop_code(p["email"])
                self.ui(lambda: sent(p, err))
            threading.Thread(target=work, daemon=True).start()

        def confirm():
            try:
                local.check_code(pend["email"], e_code.get())
            except local.AuthError as ex:
                say(str(ex), ERR)
                return
            finish_register(pend)

        def do_auth():
            try:
                if mode["reg"]:
                    if e_pass.get() != e_pass2.get():
                        raise local.AuthError("Пароли не совпадают")
                    email, name = local.validate(USERS_F, e_mail.get(), e_pass.get(), e_name.get())
                    p = {"email": email, "password": e_pass.get(), "name": name}
                    if self.resend_key():                   # ключ Resend есть: подтверждаем почту кодом
                        return send_code(p)
                    return finish_register(p)
                acc = local.login(USERS_F, e_mail.get(), e_pass.get())
            except local.AuthError as ex:
                say(str(ex), ERR)
                return
            self.set_account(acc)
            d.destroy()
        btns["go"] = mkbtn(main, "Войти", do_auth, bg=ACC, fg="#ffffff", font=("Segoe UI", 11, "bold"))
        btns["switch"] = mkbtn(main, "Нет аккаунта? Создать", lambda: set_mode(not mode["reg"]))
        btns["go"].pack(fill="x", ipady=5, pady=(8, 4))
        btns["switch"].pack(fill="x", pady=(0, 6))
        slot.pack(fill="x")
        btns["confirm"] = mkbtn(code_box, "Подтвердить и создать аккаунт", confirm, bg=ACC, fg="#ffffff", font=("Segoe UI", 11, "bold"))
        btns["confirm"].pack(fill="x", ipady=5, pady=(2, 4))
        r2 = tk.Frame(code_box, bg=BG2)
        r2.pack(fill="x", pady=(0, 6))
        mkbtn(r2, "Отправить ещё раз", lambda: send_code(pend)).pack(side="left", fill="x", expand=True, padx=(0, 3))
        mkbtn(r2, "← Назад", lambda: code_step(False)).pack(side="left", fill="x", expand=True, padx=(3, 0))
        e_code.bind("<Return>", lambda ev: confirm())
        e_mail.bind("<Return>", lambda ev: e_pass.focus_set())
        e_pass.bind("<Return>", lambda ev: e_pass2.focus_set() if mode["reg"] else do_auth())
        e_pass2.bind("<Return>", lambda ev: do_auth())
        e_mail.focus_set()
        tk.Label(main, text="— или через сервис (нужны ключи входа) —", bg=BG2, fg=DIM).pack(pady=(6, 0))

        for key, txt in (("google", "🟦  Войти через Google"), ("github", "🐙  Войти через GitHub")):
            btns[key] = mkbtn(main, txt, lambda k=key: start(k), bg=BG3, fg="#ffffff", font=("Segoe UI", 12, "bold"))
            btns[key].pack(fill="x", pady=3, ipady=5)
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
                value = v.get().strip()
                if key.endswith("client_secret"):
                    self.settings.pop(key, None)
                    if value:
                        set_secret(key, value)
                        self._warn_storage()
                    else:
                        from pyfactor.core.secure_store import delete_secret
                        delete_secret(key)
                elif key.endswith("client_id"):
                    self.settings[key] = value
                else:
                    self.settings[key] = value
            save_json(SETTINGS_F, self.settings, private=True)
            k.destroy()
        mkbtn(row, "Сохранить", save, bg=ACC, fg="#ffffff").pack(side="right")
