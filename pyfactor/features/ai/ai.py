"""ИИ-чат Gemini в правой панели: зона для проблем и промптов, смешные фразы во время генерации."""
import random
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog

from pyfactor.config import ACC, BG, BG2, BG3, FG, GREEN, RED, SETTINGS_F, YEL
from pyfactor.core.ai import gemini
from pyfactor.core.secure_store import get_secret, set_secret, take_warning
from pyfactor.core.utils import save_json
from pyfactor.ui.widgets import mkbtn

SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class AiMixin:
    def init_ai(self):
        self.ai_hist, self.ai_busy, self.ai_last_code, self._ai_tick = [], False, "", 0
        self._ai_req, self._ai_cancel = 0, None

    # ---------- ключ и модель
    def gemini_key(self, force=False):
        import os
        k = get_secret("gemini_key", self.settings.get("gemini_key") or os.environ.get("PYFACTOR_GEMINI_KEY", ""))
        if force or not k:
            k = (simpledialog.askstring("Gemini", "Вставь API-ключ Gemini:", show="*", parent=self) or "").strip() or k
            if k:
                self.settings.pop("gemini_key", None)
                set_secret("gemini_key", k)
                warn = take_warning()
                if warn:
                    messagebox.showwarning("PyFactor", warn, parent=self)
                save_json(SETTINGS_F, self.settings, private=True)
        return k

    def gemini_model_dialog(self):
        cur = self.settings.get("gemini_model", gemini.DEFAULT_MODEL)
        m = (simpledialog.askstring("Модель Gemini", "Имя модели (например gemini-2.5-flash):", initialvalue=cur, parent=self) or "").strip()
        if m:
            self.settings["gemini_model"] = m
            save_json(SETTINGS_F, self.settings, private=True)
            self.toast("Модель: " + m)

    # ---------- интерфейс (вызывается из build_ai_panel)
    def build_ai_chat(self, p):
        tk.Label(p, text="Опиши проблему или задачу", bg=BG2, fg=YEL, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(6, 2))
        self.ai_in = tk.Text(p, height=5, bg=BG, fg=FG, insertbackground="#ffffff", relief="flat", wrap="word",
                             font=("Segoe UI", 10), padx=8, pady=6, highlightthickness=1, highlightbackground=BG3, highlightcolor=ACC)
        self.ai_in.pack(fill="x", padx=10)
        self.ai_in.bind("<Control-Return>", lambda e: self.ai_send() or "break")
        self.ai_in.bind("<Escape>", lambda e: self.ai_cancel() or "break")
        opts = tk.Frame(p, bg=BG2)
        opts.pack(fill="x", padx=10, pady=(4, 0))
        self.ai_ctx_code, self.ai_ctx_err = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        for var, txt in ((self.ai_ctx_code, "мой код"), (self.ai_ctx_err, "ошибки из терминала")):
            tk.Checkbutton(opts, text=txt, variable=var, bg=BG2, fg=FG, selectcolor=BG, activebackground=BG2,
                           activeforeground=FG, highlightthickness=0, bd=0, font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
        row = tk.Frame(p, bg=BG2)
        row.pack(fill="x", padx=10, pady=6)
        self.ai_send_btn = mkbtn(row, "✨ Спросить  Ctrl+Enter", self.ai_send_or_cancel, bg=ACC, fg="#ffffff")
        self.ai_send_btn.pack(side="left", fill="x", expand=True)
        mkbtn(row, "🗑", self.ai_clear, padx=8).pack(side="left", padx=(4, 0))
        self.ai_fun = tk.Label(p, text="", bg=BG2, fg=GREEN, font=("Segoe UI", 10, "italic"), anchor="w", wraplength=300, justify="left")
        self.ai_fun.pack(fill="x", padx=12)
        self.ai_out = tk.Text(p, height=10, bg=BG, fg=FG, relief="flat", wrap="word", state="disabled", font=("Segoe UI", 10),
                              padx=8, pady=6, highlightthickness=0)
        self.ai_out.tag_configure("me", foreground=YEL, font=("Segoe UI", 10, "bold"))
        self.ai_out.tag_configure("ai", foreground=FG)
        self.ai_out.tag_configure("err", foreground=RED)
        self.ai_out.tag_configure("code", foreground="#c3e88d", background="#14151b", font=("Consolas", 10))
        self.ai_out.pack(fill="both", expand=True, padx=10, pady=(2, 4))
        act = tk.Frame(p, bg=BG2)
        act.pack(fill="x", padx=10, pady=(0, 6))
        mkbtn(act, "⤵ Вставить в код", lambda: self.ai_apply("insert"), padx=6).pack(side="left", padx=1)
        mkbtn(act, "♻ Заменить файл", lambda: self.ai_apply("replace"), padx=6).pack(side="left", padx=1)
        mkbtn(act, "📋", self.ai_copy, padx=6).pack(side="left", padx=1)

    def ai_clear(self):
        self.ai_hist.clear()
        self._ai_write("", reset=True)
        self.ai_last_code = ""

    def _ai_write(self, text, tag="ai", reset=False):
        o = self.ai_out
        o.config(state="normal")
        if reset:
            o.delete("1.0", "end")
        parts = text.split("```")
        for i, part in enumerate(parts):          # нечётные куски — код
            if i % 2:
                part = part.split("\n", 1)[1] if "\n" in part else part
                o.insert("end", part.strip("\n") + "\n", "code")
            elif part:
                o.insert("end", part, tag)
        o.config(state="disabled")
        o.see("end")

    # ---------- отправка
    def _console_tail(self, n=25):
        try:
            return "\n".join(self.console.get("1.0", "end").strip().split("\n")[-n:])
        except Exception:
            return ""

    def ai_send_or_cancel(self):
        if self.ai_busy:
            self.ai_cancel()
        else:
            self.ai_send()

    def ai_cancel(self):
        """Прерывает текущий запрос к Gemini: соединение закрывается, интерфейс освобождается сразу."""
        if not self.ai_busy:
            return
        if self._ai_cancel:
            self._ai_cancel.cancel()
        self._ai_req += 1                       # ответ отменённого запроса больше ничего не изменит
        self._ai_finish_ui()
        self._ai_write("⏹ Запрос отменён\n\n", "err")

    def _ai_finish_ui(self):
        self.ai_busy = False
        self.ai_fun.config(text="")
        self.ai_send_btn.config(text="✨ Спросить  Ctrl+Enter", state="normal")

    def ai_send(self):
        if self.ai_busy:
            return
        q = self.ai_in.get("1.0", "end").strip()
        if not q:
            return self.toast("Напиши, что нужно: проблему или промпт")
        key = self.gemini_key()
        if not key:
            return
        prompt = q
        code = self.editor.get_code().strip()[:12000]
        if self.ai_ctx_code.get() and code:
            prompt += "\n\nМой текущий код (%s):\n```\n%s\n```" % (self.editor.lang, code)
        err = self._console_tail() if self.ai_ctx_err.get() else ""
        if err:
            prompt += "\n\nПоследний вывод терминала:\n```\n%s\n```" % err
        self._ai_write("Ты: " + q + "\n", "me")
        self.ai_in.delete("1.0", "end")
        self.ai_busy = True
        self.ai_send_btn.config(text="⏹ Отменить  Esc", state="normal")
        self._ai_req += 1
        rid, cancel = self._ai_req, gemini.Cancel()
        self._ai_cancel = cancel
        self._ai_animate()
        model, hist = self.settings.get("gemini_model", gemini.DEFAULT_MODEL), list(self.ai_hist)

        def work():
            try:
                ans = gemini.ask(key, prompt, model, hist, cancel=cancel)
                self.ui(lambda: self._ai_done(q, ans, rid=rid))
            except gemini.GeminiCancelled:
                pass                            # отмену уже показал ai_cancel
            except gemini.GeminiError as ex:
                msg = str(ex)
                self.ui(lambda: self._ai_done(q, None, msg, rid=rid))
        threading.Thread(target=work, daemon=True).start()

    def _ai_animate(self):
        if not self.ai_busy:
            return
        self._ai_tick += 1
        if self._ai_tick % 14 == 1:               # новая смешная фраза каждые ~1,5 с
            self._ai_word = random.choice(gemini.FUN_WORDS)
        self.ai_fun.config(text="%s %s" % (SPIN[self._ai_tick % len(SPIN)], self._ai_word))
        self.after(110, self._ai_animate)

    def _ai_done(self, q, ans, err=None, rid=None):
        if rid is not None and rid != self._ai_req:
            return                              # запрос был отменён или заменён новым
        self._ai_finish_ui()
        if err:
            self._ai_write("⚠ " + err + "\n\n", "err")
            return
        self.ai_hist += [("user", q), ("model", ans)]
        self.ai_hist[:] = self.ai_hist[-12:]
        blocks = gemini.code_blocks(ans)
        self.ai_last_code = blocks[-1] if blocks else ""
        self._ai_write("Gemini: " + ans + "\n\n", "ai")
        self.log("ИИ ответил")                      # текст запроса в журнал не пишем: в нём может быть вставленный код с ключами
        self.toast("Готово! Код можно вставить кнопкой ⤵" if blocks else "Ответ готов")

    # ---------- действия с кодом
    def ai_apply(self, mode):
        if not self.ai_last_code:
            return self.toast("В ответе нет кода")
        if mode == "replace":
            self.editor.replace_all(self.ai_last_code + "\n")
        else:
            self.editor.text.insert("insert", self.ai_last_code + "\n")
        self.nb.select(self.tab_code)

    def ai_copy(self):
        if self.ai_last_code:
            self.clipboard_clear()
            self.clipboard_append(self.ai_last_code)
            self.toast("Код скопирован")
