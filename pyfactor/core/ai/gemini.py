"""Клиент Gemini (REST, только стандартная библиотека). Ключ берётся из настроек IDE, в код он не вшит."""
import http.client
import json
import re
import socket
import threading
import urllib.parse

DEFAULT_MODEL = "gemini-2.5-flash"
URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"

SYSTEM = ("Ты — ИИ-помощник внутри IDE PyFactor. Отвечай по-русски, коротко и по делу. "
          "Когда нужен код — давай один законченный блок в тройных кавычках ``` с названием языка. "
          "Если пользователь прислал ошибку или свой код — найди причину и дай исправленный код.")

# смешные слова, которые всплывают, пока ИИ «пишет код»
FUN_WORDS = [
    "Завариваю кофе для процессора…", "Уговариваю переменные вести себя хорошо…",
    "Ищу пропавшую точку с запятой…", "Кормлю нейроны печеньками…",
    "Отлаживаю отладчик…", "Спрашиваю у утки-отладчика…", "Компилирую вдохновение…",
    "Рефакторю реальность…", "Спорю с индентацией…", "Считаю нули и единицы…",
    "Копирую со StackOverflow (шучу)…", "Разгоняю мысли до 60 FPS…",
    "Выращиваю дерево синтаксиса…", "Гуглю как выйти из vim…", "Негоциирую с багами…",
    "Прогреваю тензоры…", "Расчёсываю циклы…", "Нахожу смысл в рекурсии (см. рекурсию)…",
    "Паркую скобки по парам…", "Подкручиваю гайки в функции…", "Шепчу заклинания на Python…",
    "Дрессирую списки…", "Протираю пыль с алгоритмов…", "Взламываю матрицу (легально)…",
    "Переименовываю x в нормальное имя…", "Добавляю щепотку магии…", "Тестирую на кошках (виртуальных)…",
    "Бужу спящий Gemini…", "Строю мостик между идеей и кодом…", "Ловлю исключения сачком…",
    "Заряжаю пиксели энергией…", "Разгадываю чужие комментарии…", "Пишу код, а не роман…",
    "Ставлю пробелы, а не табы (война!)…", "Нюхаю код — пахнет багами…", "Ещё секундочку, почти готово…",
]


class GeminiError(Exception):
    pass


class GeminiCancelled(GeminiError):
    pass


class Cancel:
    """Токен отмены: cancel() обрывает соединение, и ждущий поток сразу выходит из запроса."""

    def __init__(self):
        self.event = threading.Event()
        self._conn = None
        self._lock = threading.Lock()

    @property
    def cancelled(self):
        return self.event.is_set()

    def attach(self, conn):
        with self._lock:
            self._conn = conn
            if self.event.is_set():
                self._kill()

    def cancel(self):
        with self._lock:
            self.event.set()
            self._kill()

    def _kill(self):
        conn = self._conn
        if conn is None:
            return
        try:
            if conn.sock is not None:
                conn.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass


MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_RESPONSE = 4_000_000          # байт; больше обычного ответа ИИ в десятки раз


def check_model(model):
    """Имя модели идёт прямо в адрес запроса, поэтому пускаем только безопасные символы (без / ? # : и пробелов)."""
    model = (model or DEFAULT_MODEL).strip()
    if not MODEL_RE.match(model):
        raise GeminiError("Недопустимое имя модели. Допустимы буквы, цифры, точка, дефис и подчёркивание, например gemini-2.5-flash.")
    return model


def _post(url, headers, body, timeout, cancel=None, limit=None):
    """POST без сторонних библиотек. Возвращает (код, байты). При cancel.cancel() соединение рвётся сразу."""
    parts = urllib.parse.urlsplit(url)
    conn = http.client.HTTPSConnection(parts.netloc, timeout=timeout)
    try:
        if cancel and cancel.cancelled:
            raise GeminiCancelled("Запрос отменён.")
        conn.connect()                       # сокет нужен заранее, чтобы cancel() мог его оборвать
        if cancel:
            cancel.attach(conn)              # если отменили во время соединения — закроется сразу
        conn.request("POST", parts.path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read((limit or MAX_RESPONSE) + 1)
        return resp.status, raw
    except GeminiCancelled:
        raise
    except Exception:
        if cancel and cancel.cancelled:
            raise GeminiCancelled("Запрос отменён.")
        raise
    finally:
        try:
            conn.close()
        except OSError:
            pass


def ask(key, prompt, model=DEFAULT_MODEL, history=None, timeout=90, cancel=None):
    """Отправляет запрос; history — список (роль, текст) с ролями 'user' / 'model'. Возвращает текст ответа.
    cancel — объект Cancel: его cancel() из другого потока прерывает запрос (GeminiCancelled)."""
    if not key:
        raise GeminiError("Нет ключа Gemini. Вставь его: ⚙ → «Ключ Gemini».")
    contents = [{"role": r, "parts": [{"text": t}]} for r, t in (history or [])]
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    body = json.dumps({"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents}).encode("utf-8")
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    try:
        status, raw = _post(URL % check_model(model), headers, body, timeout, cancel)
    except GeminiError:
        raise
    except Exception as ex:
        raise GeminiError("Нет связи с Gemini: %s" % ex)
    if len(raw) > MAX_RESPONSE:
        raise GeminiError("Ответ Gemini слишком большой — отклонён.")
    if status >= 400:
        txt = raw.decode("utf-8", "ignore")
        try:
            txt = json.loads(txt)["error"]["message"]
        except Exception:
            pass
        hint = {400: "неверный запрос или имя модели", 401: "ключ не подошёл", 403: "ключ не подошёл или нет доступа",
                404: "такой модели нет — смени имя модели", 429: "слишком много запросов, подожди"}.get(status, "")
        raise GeminiError("Gemini %s%s: %s" % (status, " (%s)" % hint if hint else "", txt[:200]))
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise GeminiError("Gemini прислал непонятный ответ")
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError):
        reason = (data.get("promptFeedback") or {}).get("blockReason", "пустой ответ")
        raise GeminiError("Gemini не ответил: %s" % reason)


CODE = re.compile(r"```[\w+#-]*\n(.*?)```", re.S)


def code_blocks(text):
    return [m.strip("\n") for m in CODE.findall(text)]
