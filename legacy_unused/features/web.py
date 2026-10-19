"""HTML, CSS и JavaScript: вкладка «Просмотр», переливание для CSS, проверка и запуск."""
import os
import tempfile
import threading
import tkinter as tk
import webbrowser
from pyfactor.config import BG, DIM, FG, GREEN, RED, YEL
from pyfactor.core.check import check_code
from pyfactor.core.htmlview import render_html
from pyfactor.core.langs import LANG_NAMES, node_path
from pyfactor.core.webcheck import fix_js, node_syntax_check, run_js_once
from pyfactor import config
from pyfactor.ui.widgets import mkbtn

RAINBOW = ["#ff5370", "#ffcb6b", "#c3e88d", "#89ddff", "#82aaff", "#c792ea"]


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(palette, t):
    """Цвет на «круговом градиенте» из palette в точке t (0..1)."""
    n = len(palette)
    if n == 1:
        return palette[0]
    x = (t % 1.0) * n
    i = int(x) % n
    f = x - int(x)
    a, b = _rgb(palette[i]), _rgb(palette[(i + 1) % n])
    return "#%02x%02x%02x" % tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3))


class WebMixin:
    def init_web(self):
        self.shim_canvases, self.shim_palette = [], RAINBOW
        self.shim_on, self.shim_phase, self.shim_job = False, 0.0, None
        self._last_res = None
        self._bug_lang = "python"

    # ================================================== вкладка «Просмотр»
    def build_preview(self):
        f = self.tab_prev
        head = tk.Frame(f, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(head, text="Просмотр", bg=BG, fg="#ffffff", font=("Segoe UI", 14, "bold")).pack(side="left")
        self.prev_browser_btn = mkbtn(head, "🌐 Открыть в браузере", self.open_in_browser)
        self.prev_browser_btn.pack(side="right")
        self.prev_info = tk.Label(f, text="", bg=BG, fg=DIM, anchor="w", justify="left", wraplength=800,
                                  font=("Segoe UI", 10, "bold"))
        self.prev_info.pack(fill="x", padx=14)
        self.prev_shim = self.add_shimmer(f, 22)
        self.prev_shim.pack(fill="x", padx=14, pady=6)
        self.prev_chips = tk.Frame(f, bg=BG)
        self.prev_chips.pack(fill="x", padx=14)
        self.prev_text = tk.Text(f, wrap="word", relief="flat", bd=0, padx=18, pady=14, state="disabled",
                                 highlightthickness=0, font=("Segoe UI", 11))
        self.prev_text.pack(fill="both", expand=True, padx=14, pady=10)
        t = self.prev_text
        t.tag_configure("h1", font=("Segoe UI", 24, "bold"))
        t.tag_configure("h2", font=("Segoe UI", 19, "bold"))
        t.tag_configure("h3", font=("Segoe UI", 15, "bold"))
        t.tag_configure("h4", font=("Segoe UI", 12, "bold"))
        t.tag_configure("b", font=("Segoe UI", 11, "bold"))
        t.tag_configure("i", font=("Segoe UI", 11, "italic"))
        t.tag_configure("u", underline=True)
        t.tag_configure("a", underline=True)
        t.tag_configure("strike", overstrike=True)
        t.tag_configure("small", font=("Segoe UI", 9))
        t.tag_configure("mono", font=(config.MONO, 10))
        t.tag_configure("mark", background="#fff3a0")
        t.tag_configure("bad", foreground=RED)
        t.tag_configure("warn", foreground=YEL)
        t.tag_configure("ok", foreground=GREEN)
        t.tag_configure("dim", foreground=DIM)
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.preview_render())

    def _prev_visible(self):
        try:
            return self.nb.select() == str(self.tab_prev)
        except tk.TclError:
            return False

    def _prev_style(self, html):
        t = self.prev_text
        if html:        # HTML: белая страница, чёрный текст
            t.config(bg="#ffffff", fg="#000000", selectbackground="#b8d4ff", selectforeground="#000000")
        else:
            t.config(bg="#171b1e", fg=FG, selectbackground="#3b3f5c", selectforeground="#ffffff")

    def _prev_write(self, parts):
        t = self.prev_text
        t.config(state="normal")
        t.delete("1.0", "end")
        for text, tags in parts:
            t.insert("end", text, tags)
        t.config(state="disabled")

    def preview_render(self):
        if not self._prev_visible():
            return
        if self._last_res is None:
            code = self.editor.get_code()
            res = check_code(code, self.editor.lang)
        else:
            res, code = self._last_res
        lang = res.get("lang", "python")
        errs, warns = res["errors"], res["warnings"]
        for w in self.prev_chips.winfo_children():
            w.destroy()
        self.prev_browser_btn.config(state="normal" if lang == "html" else "disabled")
        if lang == "html":
            self._prev_style(True)
            segs, title = render_html(code)
            self.prev_shim.pack_forget()
            if errs:
                self.prev_info.config(text="✖ В коде HTML есть ошибки (%d) — смотри вкладку Bug. Показываю как получилось."
                                           % len(errs), fg=RED)
            else:
                self.prev_info.config(text="Так выглядит твоя страница: белый фон, чёрный текст"
                                           + ("  ·  заголовок: «%s»" % title if title else ""), fg=DIM)
            self._prev_write(segs or [("(страница пустая — напиши что-нибудь между <body> и </body>)", ("i",))])
        elif lang == "css":
            self._prev_style(False)
            self.prev_shim.pack(fill="x", padx=14, pady=6, before=self.prev_chips)
            parts = []
            if errs:
                self.prev_info.config(text="✖ CSS с ошибками — переливаться не будет. Исправь и цвета заиграют.", fg=RED)
                for ln, col, msg in errs:
                    parts.append(("Строка %d: %s\n" % (ln, msg), ("bad",)))
            else:
                self.prev_info.config(text="✔ CSS правильный — цвета переливаются!", fg=GREEN)
                for c in res.get("colors", [])[:40]:
                    tk.Label(self.prev_chips, text=" %s " % c, bg=c, fg="#000000" if sum(
                        int(c[i:i + 2], 16) for i in (1, 3, 5)) > 380 else "#ffffff",
                        font=(config.MONO, 9)).pack(side="left", padx=2, pady=2)
                if not res.get("colors"):
                    parts.append(("В файле пока нет цветов — переливается радуга. Добавь, например, color: #7c5cff;\n", ("dim",)))
            for ln, col, msg, kind, name in warns:
                parts.append(("Строка %d (совет): %s\n" % (ln, msg), ("warn",)))
            self._prev_write(parts or [("Все цвета из файла собраны в полосе выше.", ("dim",))])
        else:
            self._prev_style(False)
            self.prev_shim.pack_forget()
            if lang == "js":
                msg = "JavaScript: предпросмотра нет — нажми ▶ Запуск (F5), результат появится в консоли."
                if not node_path():
                    msg += "\nДля запуска нужен Node.js (nodejs.org). Проверка кода работает и без него."
            else:
                msg = "Просмотр работает для HTML и CSS. Открой файл .html или .css."
            self.prev_info.config(text=msg, fg=DIM)
            self._prev_write([])

    # ================================================ переливающиеся цвета
    def add_shimmer(self, parent, height):
        c = tk.Canvas(parent, height=height, bg=BG, highlightthickness=0)
        self.shim_canvases.append(c)
        return c

    def start_shimmer(self, colors=None):
        self.shim_palette = list(colors) if colors else RAINBOW
        if len(self.shim_palette) == 1:
            self.shim_palette = self.shim_palette * 2
        if not self.shim_on:
            self.shim_on = True
            self._shimmer_tick()

    def stop_shimmer(self):
        if not self.shim_on:
            return
        self.shim_on = False
        for c in self.shim_canvases:
            try:
                c.delete("all")
            except tk.TclError:
                pass

    def _shimmer_tick(self):
        if not self.shim_on:
            return
        self.shim_phase = (self.shim_phase + 0.012) % 1.0
        pal, ph = self.shim_palette, self.shim_phase
        try:
            for c in self.shim_canvases:
                if not c.winfo_ismapped():
                    continue
                w, h = max(c.winfo_width(), 60), max(c.winfo_height(), 4)
                c.delete("all")
                n = 64
                for i in range(n):
                    c.create_rectangle(i * w / n, 0, (i + 1) * w / n + 1, h, fill=blend(pal, i / n - ph), outline="")
            col = blend(pal, -ph)
            self.led.itemconfigure(self.led_id, fill=col)
            self.status_lbl.config(fg=col)
            self.shim_job = self.after(60, self._shimmer_tick)
        except tk.TclError:
            self.shim_on = False

    # ================================================ связь с редактором
    def update_web(self, res, code):
        """Вызывается после каждой проверки кода."""
        lang = res.get("lang", "python")
        self._last_res = (res, code)
        lbl = getattr(self, "lang_lbl", None)
        if lbl is not None:
            lbl.config(text=self.lang_text(lang))
        if lang == "css" and not res["errors"]:
            self.start_shimmer(res.get("colors"))
        else:
            self.stop_shimmer()
        if lang != self._bug_lang:
            self._bug_lang = lang
            self.on_bug_mode()
        if self._prev_visible():
            self.preview_render()

    def open_in_browser(self):
        if self.editor.lang != "html":
            self.toast("В браузере открывается только HTML")
            return
        if self.cur_file:
            if self.editor.is_dirty():
                self.save_file()
            path = self.cur_file
        else:
            path = os.path.join(tempfile.mkdtemp(prefix="pyfactor_"), "preview.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.get_code())
        webbrowser.open("file:///" + path.replace("\\", "/").lstrip("/"))

    # ================================================== запуск (F5)
    def web_run(self):
        """HTML и CSS «запускаются» как просмотр."""
        self.nb.select(self.tab_prev)
        self.preview_render()

    def run_js(self):
        node = node_path()
        self.console_clear()
        if not node:
            self.cprint("Node.js не найден. Скачай его с nodejs.org — тогда JavaScript можно будет запускать.\n"
                        "Проверка кода (вкладка Bug) работает и без Node.js.\n", "err")
            return
        self.spawn(self.cur_file, self.project, cmd=[node, self.cur_file])

    # ============================================ вкладка Bug для HTML/CSS/JS
    WEB_DESC = {
        "html": "HTML: ищу незакрытые теги, лишние закрывающие, забытые alt и title. Страница показывается на вкладке «Просмотр» "
                "(белый фон, чёрный текст).",
        "css": "CSS: проверяю скобки, двоеточия и точки с запятой, цвета и единицы. Если всё правильно — цвета переливаются, "
               "если есть ошибка — нет.",
        "js": "JavaScript: проверяю скобки и кавычки, ищу var и неточное ==. Если установлен Node.js — ещё точный разбор "
              "синтаксиса и пробный запуск на 4 секунды. Режим «Авто» чинит скобки и == сам.",
    }

    def run_bug_web(self, mode, code, lang):
        res = check_code(code, lang)
        self.fill_issues(res)
        if mode == "manual":
            self.blog_print("Ручной режим: ошибок — %d, предупреждений — %d." % (len(res["errors"]), len(res["warnings"])), "info")
            return
        if self.cur_file and self.editor.is_dirty():
            self.save_file()
        threading.Thread(target=self._web_worker, args=(mode, code, lang), daemon=True).start()

    def _web_worker(self, mode, code, lang):
        log = self._log
        res = check_code(code, lang)
        if lang == "js" and mode == "auto" and (res["errors"] or res["warnings"]):
            new, notes = fix_js(code, res)
            if new != code:
                self.ui(lambda: self.editor.replace_all(new))
                for n in notes:
                    log("🤖 Исправлено: " + n, "ok")
                code, res = new, check_code(new, lang)
        node = node_path() if lang == "js" else None
        extra = node_syntax_check(node, code) if node and not res["errors"] else None
        errs = list(res["errors"]) + ([(extra[0], 0, "Node.js: " + extra[1])] if extra else [])
        self.ui(lambda: self.fill_issues({"errors": errs, "warnings": res["warnings"]}))
        for ln, col, msg in errs:
            log("🔴 строка %d: %s" % (ln, msg), "bad")
        for ln, col, msg, kind, name in res["warnings"][:15]:
            log("🟡 строка %d: %s" % (ln, msg), "warn")
        if errs:
            if lang == "css":
                log("✖ CSS неправильный — переливаться не будет.", "bad")
            else:
                log("✖ %s: найдено ошибок — %d." % (LANG_NAMES[lang], len(errs)), "bad")
            return
        if lang == "css":
            log("✔ CSS правильный — цвета переливаются (смотри индикатор вверху и вкладку «Просмотр»).", "ok")
        elif lang == "html":
            log("✔ HTML в порядке. Открываю просмотр.", "ok")
            self.ui(lambda: (self.nb.select(self.tab_prev), self.preview_render()))
        elif lang == "js":
            log("✔ Синтаксис правильный.", "ok")
            if not node:
                log("Node.js не найден — пробный запуск пропущен (установи с nodejs.org).", "info")
                return
            log("▶ Пробный запуск (до 4 секунд)…", "info")
            rc, out = run_js_once(node, code, 4)
            if out.strip():
                log(out.rstrip(), "bad" if rc not in (0, None) else None)
            if rc is None:
                log("■ Работает дольше 4 секунд и остановлен — для таймеров и серверов это нормально.", "warn")
            elif rc == 0:
                log("✔ Выполнилось без ошибок.", "ok")
            else:
                log("✖ Скрипт завершился с ошибкой (код %s)." % rc, "bad")
