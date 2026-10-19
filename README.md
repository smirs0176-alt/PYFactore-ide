# PyFactor IDE

**PyFactor IDE 1.0.0** — IDE на Python (tkinter + стандартная библиотека). Для запуска из исходников нужен только Python с tkinter;
необязательные пакеты (`keyring`, `pygments`) включают защищённое хранение ключей и красивую подсветку.
Языки: **Python, HTML, CSS, JavaScript** (для запуска JS нужен Node.js, для остального — нет).

## Требования

- Python **3.9+** с tkinter. Минимум 3.9 определён статическим анализом (vermin) и совпадает с `pyproject.toml`; **реально запускалось и тестировалось только на Python 3.12**.
- Необязательно: `pip install -r requirements-optional.txt` — `keyring` (Windows Credential Manager) и `pygments`.
- Для запуска JavaScript — Node.js. Для Go-сервера (`server/`) — Go 1.22.

## Запуск

    python scripts/run.py
    # или
    python -m pyfactor

## Что умеет

- Вкладки файлов (Ctrl+W закрыть, Ctrl+Tab переключить)
- Поиск и замена: Ctrl+F / Ctrl+H, по всему проекту — Ctrl+Shift+F
- Правая кнопка по коду: меню и **цвет текста** (цвета запоминаются в проекте)
- Своя проверка для каждого языка (вкладка Bug):
  - Python — ошибки, предупреждения, автоисправление, тест функций
  - HTML — незакрытые теги, alt, title; просмотр: белый фон, чёрный текст
  - CSS — скобки, ; и :, цвета, единицы; если всё верно — цвета **переливаются**
  - JavaScript — скобки, кавычки, var, ==; с Node.js ещё точный разбор и пробный запуск
- Library: Python-библиотеки, Web-библиотеки (Bootstrap, jQuery, Chart.js…) и кнопка «＋ Своя»
- Автодополнение (Ctrl+Space и само при наборе), парные скобки и кавычки
- Сниппеты: `def`, `class`, `for`, `while`, `if`, `try`, `with`, `main` + Tab
- Структура файла: Ctrl+R · Темы: Ctrl+T · Форматирование: Ctrl+Shift+L
- Автосохранение (15 с) и восстановление вкладок · подсветка текущей строки
- Журнал всего, что делали в IDE: файл `~/.pyfactor/journal.md`, открыть — Ctrl+J
- Своя нейросеть (core/ai/brain.py, чистый Python): учится на твоём коде, подсказки ★ в Ctrl+Space; переучить — Ctrl+Shift+N
- Весёлые языки (запуск F5): Brainfuck `.bf`, Ook! `.ook`, LOLCODE `.lol`, Русский Питон `.rus` (core/languages/funrun.py)
- Озвучка ElevenLabs: Ctrl+Shift+V (выделенное или весь файл), ключ — Ctrl+Shift+K
- Иконка: pyfactor/assets/icon.png и icon.ico (перерисовать — scripts/make_icon.py)
- Вкладка «🌍 Языки»: C#, Lua, Ruby, Go, Java, PHP, Rust, C++ — скачать (анимация) → открывается Mystery.<ext> (core/languages/packs.py)
- Авторизация при запуске: Google (OAuth + PKCE) и GitHub (Device Flow), ключи — кнопка «Ключи входа» (core/account/oauth.py, features/account/auth.py); без окна входа: PYFACTOR_NO_LOGIN=1
- Интерфейс как в VS Code: полоса значков слева, панель инструментов, вкладки файлов, терминал, строка состояния
- Адрес сервера любой (домен, IP, localhost:порт — http/https допишется сам)
- Сервер-выключатель на Go + JS-панель (папка server/, см. server/README.md): выключил сервер — в IDE «Произошла ошибка»
- Движок PG2 (pyfactor/pg2/pg2.py): 2D-движок на tkinter, одним файлом; «Новый файл» → «PG2 — Платформер / Шутер / Пустая игра»
- Шрифт: Ctrl + колесо мыши, F1 — все горячие клавиши

## Структура

    pyfactor_project/
    ├── scripts/                 run.py, run.bat, run.sh, check.py, make_icon.py
    ├── server/                  сервер-выключатель на Go + JS-панель
    ├── site/                    сайт: аккаунты, скачивание, автоподключение приложения (server.py, store.py, packager.py, index.html — вся страница в одном файле)
    └── pyfactor/
        ├── config.py            пути, цвета, каталог библиотек
        ├── assets/              иконки и скриншот
        ├── pg2/                 игровой движок PG2
        ├── ui/                  app.py (главное окно), editor.py, widgets.py
        ├── core/                логика без интерфейса
        │   ├── check.py, utils.py
        │   ├── python/          analysis.py — анализ и автоисправление Python
        │   ├── web/             webcheck.py, syntax.py, htmlview.py — HTML / CSS / JS
        │   ├── languages/       langs.py, packs.py, funrun.py, funlang.py — языки и весёлые языки
        │   ├── ai/              gemini.py (Gemini), brain.py (своя мини-нейросеть)
        │   ├── account/         local.py, mailer.py (Resend), cloud.py (связь с сайтом), oauth.py, github.py
        │   └── games/           pg2_templates.py
        └── features/            возможности окна (миксины)
            ├── workspace/       tabs, search, colors, extras, status, runner
            ├── project/         project, library, langstore, games
            ├── tools/           bug, web, voice
            ├── ai/              ai.py (чат Gemini), panels.py (правая панель)
            └── account/         account, auth, server

## ИИ на Gemini (панель 🤖 справа)

- Зона «Опиши проблему или задачу» + Ctrl+Enter: можно писать промпт или проблему, к запросу сам прикладывается твой код и последние строки терминала (галочки).
- Пока Gemini думает, внизу всплывают случайные смешные фразы (список `FUN_WORDS` в `core/ai/gemini.py` — дописывай свои).
- Кнопки под ответом: «Вставить в код», «Заменить файл», копирование.
- Ключ: ⚙ → «Ключ Gemini…» (хранится в защищённом хранилище, см. «Безопасность и данные») или переменная `PYFACTOR_GEMINI_KEY`. Ключ создаётся бесплатно в Google AI Studio. Модель: ⚙ → «Модель Gemini…» (по умолчанию `gemini-2.5-flash`; допускаются буквы, цифры, `.`, `-`, `_`; существует ли модель, решает Google — при ошибке 404 смени имя).
- Запрос можно отменить кнопкой «Отменить»: соединение рвётся сразу. История диалога (последние 12 реплик) живёт только в памяти окна и на диск не пишется; текст запросов в журнал не попадает.
- Ошибки (неверный ключ 401/403, лимит 429, нет сети, слишком большой или непонятный ответ) показываются в чате с пометкой «⚠», а не выдаются за ответ ИИ.
- Файлы: `core/ai/gemini.py` (запросы), `features/ai/ai.py` (интерфейс). Старая мини-нейросеть `brain.py` осталась для автодополнения ★.

## Аккуратные папки

- Новый файл сам попадает в нужную папку: `.py` → `python/`, HTML/CSS/JS → `web/`, картинки и звуки → `assets/`, txt/json/csv → `data/`, остальное → `other/`. Папки создаются сами.
- Если в дереве выбрана конкретная папка, файл создаётся в ней.
- Пустой проект сразу получает папки `python`, `web`, `assets`, `data`, а `main.py` лежит в `python/`.
- Выключить: ⚙ → «Авто-папки для новых файлов». Старые файлы раскладывает кнопка «⇅ Сортировать» (↶ вернёт назад).

## Сайт и автоподключение

`python site/server.py` запускает сайт с регистрацией. Скачанный с него архив содержит `connect.json`, и приложение при запуске само входит в аккаунт. Подробности и настройки: `site/README.md`.

## Windows: запуск и сборка EXE

    py -3.12 -m venv .venv && .venv\Scripts\activate
    pip install -r requirements-dev.txt           # тесты, ruff, flask, keyring, pygments
    python scripts/run.py                         # запуск из исходников
    python scripts/test.py                        # все тесты (в Linux сам поднимает xvfb)

    pip install -r requirements-build.txt         # + PyInstaller
    python scripts/build_exe.py                   # результат: dist\PyFactor.exe

`PyFactor.exe` — **один файл (PyInstaller --onefile), а не установщик**; подписи кода нет, поэтому Windows SmartScreen и антивирусы могут ругаться.
Сборка и запуск EXE в Windows этим релизом **не проверялись** (проверка выполняется CI-заданием `windows` и вручную по `docs/RELEASING.md`).

Важно для EXE: программы пользователя запускаются установленным на компьютере Python 3
(python.org, с галочкой Add to PATH). Свой интерпретатор можно указать в settings.json: `"python_path": "C:\\Python312\\python.exe"`
или переменной `PYFACTOR_PYTHON`. Если ключи должны храниться в Credential Manager, `keyring` должен быть установлен до сборки.
`connect.json` кладут рядом с `PyFactor.exe`.

Linux: для GUI-тестов нужны `sudo apt install xvfb python3-tk`.

## Безопасность и данные

- **Ключи и токены** (Gemini, Resend, ElevenLabs, Google client secret, токен GitHub, токен связи с сайтом) хранятся в системном хранилище через `keyring`
  (в Windows — Credential Manager). Старые значения из `settings.json` переносятся при запуске.
- **Если `keyring` не установлен или недоступен**, ключ записывается в `~/.pyfactor/secrets.json` **открытым текстом**, а IDE один раз показывает предупреждение.
  В Windows права доступа к файлу (0600) не защищают его от других программ под тем же пользователем. Хочешь запретить такую запись — задай `PYFACTOR_REQUIRE_KEYRING=1`:
  сохранение ключа тогда завершится ошибкой с пояснением. Для EXE `keyring` должен быть установлен до сборки.
- Программы, запущенные из IDE, не получают переменные `PYFACTOR_*` с ключами.
- Локальные файлы в `~/.pyfactor/` (в Windows `%USERPROFILE%\.pyfactor\`): `settings.json`, `account.json`, `journal.md` (журнал действий: имена файлов и события без текста запросов к ИИ),
  `brain.json` (веса мини-нейросети для автодополнения; обучается на твоём коде и остаётся на диске), `secrets.json` (только если нет `keyring`).
- Сайт (`site/`) и Go-сервер (`server/`) — отдельные серверные части; их настройки и меры защиты описаны в `site/README.md` и `server/README.md`.

## Устранение неполадок

| Симптом | Что делать |
|---|---|
| «Не найден Python 3» при запуске программы из EXE | Установи Python с python.org (галочка Add to PATH) или укажи путь: `"python_path"` в `settings.json` либо переменная `PYFACTOR_PYTHON` |
| Предупреждение «Защищённое хранилище ключей недоступно» | `pip install keyring` (для EXE — до сборки) или принять хранение в файле; запретить файл: `PYFACTOR_REQUIRE_KEYRING=1` |
| Gemini: «ключ не подошёл» (401/403) | Проверь ключ в Google AI Studio и введи заново: ⚙ → «Ключ Gemini…» |
| Gemini: 404 «такой модели нет» | ⚙ → «Модель Gemini…» и выбери существующую модель |
| Gemini: 429 | Лимит запросов — подожди и повтори |
| «Нет связи с Gemini» | Проверь интернет, прокси и брандмауэр; запрос можно отменить и повторить |
| Окно входа мешает | `PYFACTOR_NO_LOGIN=1` |
| Вход через Google не работает | В «Ключи входа» нужны твои `client_id` и `client_secret` (OAuth-клиент типа «Приложение для ПК» в Google Cloud) |
| GUI-тесты пропущены (`s`) | Нет tkinter или дисплея: в Linux `sudo apt install xvfb python3-tk`, затем `python scripts/test.py` |
| SmartScreen блокирует EXE | EXE не подписан: «Подробнее → Выполнить в любом случае» (только для файла, собранного тобой или из доверенного источника) |
| Порт сайта занят | `set SITE_PORT=8082` (Windows) и повторить запуск `python site/server.py` |

## Известные ограничения

- **Windows не проверялся**: EXE, Credential Manager, поиск Python на чистой машине, установка/первый запуск — нужно проверить по `docs/RELEASING.md`.
- Нет установщика и подписи кода; EXE не работает без установленного Python, если нужно запускать программы пользователя (сама IDE запускается без него).
- Тестировалось только на Python 3.12 (минимум 3.9 — по статическому анализу) и Linux (Xvfb).
- Живые сервисы не проверялись: Google/GitHub OAuth, реальные запросы к Gemini, отправка писем Resend, озвучка ElevenLabs, скачивание языковых пакетов («🌍 Языки»). Проверены только модульные и интеграционные тесты с подменой сети.
- Не проверена история Git исходного проекта (в присланном архиве её нет): секреты, ранее зашитые в исходники, считаются скомпрометированными и требуют ротации.
- Готовые бинарники в `server/dist/` не входят в архив релиза (происхождение не проверено).
- Лицензия не выбрана: файл `LICENSE` не добавлен, пока владелец проекта не подтвердит лицензию.
- Gemini — единственный поддерживаемый ИИ-провайдер; мини-нейросеть `brain.py` — не LLM, а подсказки автодополнения.

## Разработка и проверки

    pip install -r requirements-dev.txt         # pytest, ruff, flask, keyring, pygments
    python scripts/check.py                     # синтаксис всех .py
    ruff check .                                # статический анализ
    python scripts/test.py                      # pytest (в Linux сам поднимает xvfb; CI требует GUI-тесты: PYFACTOR_REQUIRE_GUI=1)
    cd server && gofmt -l . && go vet ./... && go test -race ./...
    python scripts/make_release.py              # архив release/PyFactor-<версия>-source.zip (с проверкой на секреты)

Выпуск релиза и проверка в Windows: `docs/RELEASING.md`. Изменения: `CHANGELOG.md`.
#   P Y F a c t o r e - i d e  
 