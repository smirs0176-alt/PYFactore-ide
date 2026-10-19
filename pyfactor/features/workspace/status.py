"""Статус-бар, подсказки и закрытие окна."""
from tkinter import messagebox

from pyfactor.config import DIM, GREEN, RED, YEL


class StatusMixin:
    def after_refresh(self, res, code):
        self.set_status(res)
        self.refresh_used(res)
        if self.bug_mode.get() == "manual":
            self.fill_issues(res)
        self.update_title()
        self.update_pos()
        self.find_refresh()
        self.update_web(res, code)

    def set_status(self, res):
        lang = res.get("lang", "python")
        if lang == "text":
            self.led.itemconfigure(self.led_id, fill=DIM)
            self.status_lbl.config(text="Текстовый файл", fg=DIM)
            return
        if res["errors"]:
            ln, _, msg = res["errors"][0]
            self.led.itemconfigure(self.led_id, fill=RED)
            self.status_lbl.config(text="Ошибка · строка %d: %s" % (ln, msg[:60]), fg=RED)
        elif res["warnings"]:
            self.led.itemconfigure(self.led_id, fill=YEL)
            self.status_lbl.config(text="Работает · предупреждений: %d" % len(res["warnings"]), fg=YEL)
        else:
            self.led.itemconfigure(self.led_id, fill=GREEN)
            ok = {"html": "HTML в порядке ✓", "css": "CSS правильный ✓ — переливается", "js": "JavaScript в порядке ✓"}
            self.status_lbl.config(text=ok.get(lang, "Код правильный ✓"), fg=GREEN)

    def update_pos(self):
        try:
            ln, col = self.editor.text.index("insert").split(".")
            self.pos_lbl.config(text="Стр %s, Кол %d" % (ln, int(col) + 1))
        except Exception:
            pass

    def toast(self, msg):
        self.toast_lbl.config(text=msg)
        self.after(3500, lambda: self.toast_lbl.config(text=""))

    def on_close(self):
        dirty = self.tabs_dirty()
        if dirty:
            names = ", ".join(self._tab_name(i) for i in dirty[:4]) + (" …" if len(dirty) > 4 else "")
            ans = messagebox.askyesnocancel("PyFactor", "Сохранить изменения?\n" + names, parent=self)
            if ans is None:
                return
            if ans:
                self.tabs_save_all()
        if getattr(self, "ai_busy", False) and getattr(self, "_ai_cancel", None):
            self._ai_cancel.cancel()
        self.stop_file()
        self.destroy()

    def show_help(self, e=None):
        messagebox.showinfo("Горячие клавиши", (
            "F5 — запустить / показать\n"
            "Ctrl+S — сохранить\n"
            "Ctrl+Shift+P — палитра команд (поиск любого действия)\n"
            "Ctrl+F / Ctrl+H — найти / заменить в файле\n"
            "Ctrl+Shift+F — поиск по всему проекту\n"
            "Ctrl+W — закрыть вкладку,  Ctrl+Tab — следующая вкладка\n"
            "Ctrl+/ — закомментировать строки\n"
            "Ctrl + колесо мыши или Ctrl + / Ctrl − — размер шрифта (Ctrl+0 — обычный)\n"
            "Правая кнопка мыши по коду — меню и цвет текста"), parent=self)

