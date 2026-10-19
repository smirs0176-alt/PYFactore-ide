"""Аккаунт и выкладка проекта на GitHub."""
import base64
import os
import re
import threading
import tkinter as tk
import urllib.request, urllib.error
import webbrowser
from tkinter import messagebox
from tkinter import simpledialog
from pyfactor.config import ACC, ACCOUNT_F, BG2, BG3, DIM
from pyfactor.core.github import gh_request
from pyfactor.core.utils import save_json
from pyfactor.ui.widgets import mkbtn


class AccountMixin:
    # --- аккаунт
    def refresh_account(self):
        p = self.panels["acc"]
        for w in p.winfo_children():
            w.destroy()
        acc = self.account
        tk.Label(p, text="Аккаунт", bg=BG2, fg="#ffffff", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(8, 8))
        card = tk.Frame(p, bg=BG3)
        card.pack(fill="x", padx=10)
        name = acc.get("name")
        av = tk.Canvas(card, width=48, height=48, bg=BG3, highlightthickness=0)
        av.pack(side="left", padx=10, pady=10)
        av.create_oval(2, 2, 46, 46, fill=ACC if name else DIM, outline="")
        av.create_text(24, 24, text=(name or "?")[0].upper(), fill="#ffffff", font=("Segoe UI", 16, "bold"))
        info = tk.Frame(card, bg=BG3)
        info.pack(side="left")
        tk.Label(info, text=name or "Гость", bg=BG3, fg="#ffffff", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(info, text=("через " + acc["provider"]) if name else "Ты не вошёл", bg=BG3, fg=DIM).pack(anchor="w")
        if name:
            mkbtn(p, "Выйти", self.logout).pack(fill="x", padx=10, pady=8)
        else:
            for txt, prov in (("🟦  Войти через Google", "google"), ("   Войти через Apple", "apple"),
                              ("🐙  Войти через GitHub", "github"), ("✉  Email", "email")):
                mkbtn(p, txt, lambda pr=prov: self.login(pr), anchor="w").pack(fill="x", padx=10, pady=3)
        mkbtn(p, "🔑 GitHub-токен для выкладки", self.ask_token).pack(fill="x", padx=10, pady=(12, 3))
        mkbtn(p, "⬆ Выложить проект на GitHub", self.publish_github, bg=ACC, fg="#ffffff").pack(fill="x", padx=10, pady=3)
        tk.Label(p, text="Google и GitHub — настоящий вход (OAuth).\nApple / Email — локальный профиль.",
                 bg=BG2, fg=DIM, font=("Segoe UI", 8), justify="left").pack(anchor="w", padx=12, pady=10)

    def set_account(self, acc):
        old = self.account
        if "token" not in acc and old.get("token"):
            acc["token"] = old["token"]
        self.account = acc
        save_json(ACCOUNT_F, acc)
        self.refresh_account()
        self.toast("Привет, %s!" % acc.get("name", ""))

    def logout(self):
        self.account = {}
        save_json(ACCOUNT_F, {})
        self.refresh_account()

    def ask_token(self):
        tok = simpledialog.askstring("GitHub", "Personal Access Token (право repo).\nСоздать: github.com/settings/tokens",
                                     show="•", parent=self)
        if tok:
            self.account["token"] = tok.strip()
            save_json(ACCOUNT_F, self.account)
            self.toast("Токен сохранён")

    def login(self, prov):
        if prov in ("google", "github"):
            return self.auth_dialog()
        if prov == "github":
            tok = simpledialog.askstring("GitHub", "Вставь Personal Access Token (право repo):", show="•", parent=self)
            if not tok:
                return

            def work():
                st, d = gh_request("GET", "https://api.github.com/user", tok.strip())
                if st == 200:
                    acc = {"provider": "GitHub", "name": d.get("name") or d.get("login"), "login": d.get("login"),
                           "token": tok.strip()}
                    self.ui(lambda: self.set_account(acc))
                else:
                    self.ui(lambda: messagebox.showerror("GitHub", "Не удалось войти (код %s)" % st, parent=self))
            threading.Thread(target=work, daemon=True).start()
            return
        urls = {"google": "https://accounts.google.com", "apple": "https://appleid.apple.com"}
        if prov in urls:
            webbrowser.open(urls[prov])
        name = simpledialog.askstring("Вход", "Имя профиля:", parent=self)
        if not name:
            return
        email = simpledialog.askstring("Вход", "Email:", parent=self) or ""
        self.set_account({"provider": prov.title(), "name": name, "email": email})

    def publish_github(self):
        if not self.project:
            return
        if self.cur_file:
            self.save_file()
        tok = self.account.get("token")
        if not tok:
            self.ask_token()
            tok = self.account.get("token")
            if not tok:
                return
        repo = simpledialog.askstring("GitHub", "Название репозитория:", initialvalue=re.sub(r"[^\w.-]", "-", os.path.basename(self.project)), parent=self)
        if not repo:
            return
        private = messagebox.askyesno("GitHub", "Сделать репозиторий приватным?", parent=self)
        proj = self.project
        self.nb.select(self.tab_bug)
        self.on_bug_mode()
        self.blog.config(state="normal")
        self.blog.delete("1.0", "end")
        self.blog.config(state="disabled")
        threading.Thread(target=self._gh_worker, args=(tok, repo, private, proj), daemon=True).start()

    def _gh_worker(self, tok, repo, private, proj):
        st, u = gh_request("GET", "https://api.github.com/user", tok)
        if st != 200:
            self._log("✗ GitHub: токен не подошёл (код %s)" % st, "bad")
            return
        login = u["login"]
        st, d = gh_request("POST", "https://api.github.com/user/repos", tok,
                           {"name": repo, "private": private, "auto_init": True})
        if st == 201:
            self._log("✓ Репозиторий создан: %s/%s" % (login, repo), "ok")
        elif st == 422:
            self._log("ℹ Репозиторий уже есть — обновляю файлы", "info")
        else:
            self._log("✗ Не удалось создать репозиторий: %s" % d.get("message", st), "bad")
            return
        count = 0
        for root, dirs, files in os.walk(proj):
            dirs[:] = [x for x in dirs if not x.startswith(".") and x != "__pycache__"]
            for fn in files:
                if fn.startswith("."):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, proj).replace(os.sep, "/")
                if os.path.getsize(full) > 5 * 1024 * 1024:
                    self._log("• пропущен (больше 5 МБ): " + rel, "warn")
                    continue
                with open(full, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                url = "https://api.github.com/repos/%s/%s/contents/%s" % (login, repo, urllib.request.quote(rel))
                s1, ex = gh_request("GET", url, tok)
                data = {"message": "PyFactor: " + rel, "content": b64}
                if s1 == 200 and isinstance(ex, dict) and ex.get("sha"):
                    data["sha"] = ex["sha"]
                s2, r2 = gh_request("PUT", url, tok, data)
                if s2 in (200, 201):
                    count += 1
                    self._log("✓ " + rel, "ok")
                else:
                    self._log("✗ %s — %s" % (rel, r2.get("message", s2)), "bad")
        self._log("Готово! Файлов выложено: %d → https://github.com/%s/%s" % (count, login, repo), "ok")
        self.ui(lambda: webbrowser.open("https://github.com/%s/%s" % (login, repo)))
