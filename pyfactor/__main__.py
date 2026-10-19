"""Запуск: python -m pyfactor"""
import os


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    from pyfactor.ui.app import App
    app = App()
    try:
        app.winfo_exists()
    except Exception:
        return
    app.mainloop()


if __name__ == "__main__":
    main()
