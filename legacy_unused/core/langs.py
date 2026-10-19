"""Языки: определение по расширению, названия, шаблоны новых файлов, поиск Node.js."""
import os
import shutil

LANG_BY_EXT = {".py": "python", ".pyw": "python", ".html": "html", ".htm": "html",
               ".css": "css", ".js": "js", ".mjs": "js",
               ".bf": "bf", ".ook": "ook", ".lol": "lol", ".rus": "rus"}
FUN_LANGS = {"bf", "ook", "lol", "rus"}
FUNRUN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "funrun.py")
LANG_NAMES = {"python": "Python", "html": "HTML", "css": "CSS", "js": "JavaScript", "text": "Текст",
              "bf": "Brainfuck", "ook": "Ook!", "lol": "LOLCODE", "rus": "Русский Питон"}
LANG_ICONS = {"python": "🐍", "html": "🌐", "css": "🎨", "js": "📜", "bf": "🧠", "ook": "🦧", "lol": "😹", "rus": "🇷🇺"}


def lang_of(path):
    """Язык файла. Для файла без пути (черновик) считаем Python."""
    if not path:
        return "python"
    return LANG_BY_EXT.get(os.path.splitext(path)[1].lower(), "text")


def node_path():
    return shutil.which("node")


def _ook(bf):
    m = {">": "Ook. Ook?", "<": "Ook? Ook.", "+": "Ook. Ook.", "-": "Ook! Ook!", ".": "Ook! Ook.", ",": "Ook. Ook!",
         "[": "Ook! Ook?", "]": "Ook? Ook!"}
    return " ".join(m[c] for c in bf) + "\n"


TEMPLATES = {
    ".bf": "Выводит Hello World!\n++++++++[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]>>.>---.+++++++..+++.>>.<-.<.+++.------.--------.>>+.>++.\n",
    ".ook": _ook("++++++++[>+++++++++<-]>.+."),
    ".lol": """HAI 1.2
BTW Привет от LOLCODE!
I HAS A name ITZ "мир"
VISIBLE "ПРИВЕТ, " name "!"
I HAS A i ITZ 0
IM IN YR loop UPPIN YR i TIL BOTH SAEM i AN 3
    VISIBLE "Раз: " i
IM OUTTA YR loop
KTHXBYE
""",
    ".rus": """# Русский Питон — это Python с русскими словами
имя = ввод("Как тебя зовут? ")
вывод("Привет,", имя)
для i в диапазон(3):
    вывод("Раз", i)
""",
    ".html": """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Моя страница</title>
</head>
<body>
    <h1>Привет, мир!</h1>
    <p>Это моя первая страница в PyFactor.</p>
</body>
</html>
""",
    ".css": """body {
    background: #14191c;
    color: #d7dae0;
    font-family: sans-serif;
}

h1 {
    color: #7c5cff;
}
""",
    ".js": """// Мой первый скрипт в PyFactor
function hello(name) {
    return `Привет, ${name}!`;
}

console.log(hello("мир"));
""",
}
