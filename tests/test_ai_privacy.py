"""Текст запроса к ИИ не должен попадать в журнал journal.md (в нём бывает вставленный код и ключи)."""
import pytest

pytest.importorskip("tkinter")

from pyfactor.features.ai.ai import AiMixin  # noqa: E402


class _Stub:
    _ai_done = AiMixin._ai_done

    def __init__(self):
        self._ai_req, self.ai_hist, self.ai_last_code = 1, [], ""
        self.logged, self.toasts, self.written = [], [], []

    def _ai_finish_ui(self):
        pass

    def _ai_write(self, text, tag=None, reset=False):
        self.written.append(text)

    def log(self, text):
        self.logged.append(text)

    def toast(self, text):
        self.toasts.append(text)


def test_prompt_text_is_not_written_to_journal():
    app = _Stub()
    secret_prompt = "почему падает? ключ " + "sk-" + "A" * 24 + " и пароль hunter2"
    app._ai_done(secret_prompt, "Вот код:\n```python\nprint(1)\n```", rid=1)
    assert app.logged, "событие должно попасть в журнал"
    joined = "\n".join(app.logged)
    assert "hunter2" not in joined and "sk-" not in joined and "почему" not in joined
    assert app.ai_hist[0] == ("user", secret_prompt)               # история диалога живёт только в памяти окна
    assert app.ai_last_code == "print(1)"


def test_error_is_shown_and_nothing_logged():
    app = _Stub()
    app._ai_done("вопрос", "", err="Gemini 401 (ключ не подошёл)", rid=1)
    assert app.logged == [] and any("401" in w for w in app.written) and app.ai_hist == []
