"""Защита от тихого пропуска GUI-тестов: если CI требует графику (PYFACTOR_REQUIRE_GUI=1), её отсутствие — ошибка, а не skip."""
import os
import sys

import pytest


def test_gui_environment_when_required():
    if os.environ.get("PYFACTOR_REQUIRE_GUI") != "1":
        pytest.skip("PYFACTOR_REQUIRE_GUI не задан")
    import tkinter
    assert sys.platform == "win32" or os.environ.get("DISPLAY"), "нет DISPLAY: запускай через xvfb-run"
    root = tkinter.Tk()
    root.destroy()
