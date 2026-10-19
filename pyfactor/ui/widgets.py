"""Общие виджеты tkinter."""
import tkinter as tk
from tkinter import ttk

from pyfactor.config import ACC, BG2, BG3, FG


def lighten(color, k=0.14):
    """Чуть осветляет цвет #rrggbb (для подсветки кнопки под курсором)."""
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return color
    return "#%02x%02x%02x" % tuple(int(c + (255 - c) * k) for c in (r, g, b))


def mkbtn(parent, text, cmd, bg=None, fg=None, **kw):
    base = bg or BG3
    opts = dict(activebackground=ACC, activeforeground="#ffffff", relief="flat", bd=0, padx=10, pady=4,
                cursor="hand2", highlightthickness=0)
    opts.update(kw)                      # padx=, pady=, font= и т.д. переопределяют значения по умолчанию
    b = tk.Button(parent, text=text, command=cmd, bg=base, fg=fg or FG, **opts)
    hover = lighten(base)
    b.bind("<Enter>", lambda e: b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=base))
    return b


class ScrollFrame(tk.Frame):
    def __init__(self, master, bg=BG2):
        super().__init__(master, bg=bg)
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.cv.yview)
        self.inner = tk.Frame(self.cv, bg=bg)
        self.win = self.cv.create_window((0, 0), window=self.inner, anchor="nw")
        self.cv.configure(yscrollcommand=sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self.win, width=e.width))
        for w in (self.cv, self.inner):
            w.bind("<Enter>", self._bind)
            w.bind("<Leave>", self._unbind)

    def _bind(self, e=None):
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.cv.bind_all(ev, self._wheel)

    def _unbind(self, e=None):
        w = self.winfo_containing(*self.winfo_pointerxy())
        if w is not None and str(w).startswith(str(self)):
            return
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.cv.unbind_all(ev)

    def _wheel(self, e):
        if getattr(e, "num", 0) == 4:
            d = -1
        elif getattr(e, "num", 0) == 5:
            d = 1
        else:
            d = -1 if e.delta > 0 else 1
        self.cv.yview_scroll(d * 2, "units")

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
