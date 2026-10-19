"""Подсветка остальных форматов (JSON, YAML, Markdown, TOML, INI, XML, shell, bat, SQL) через Pygments (BSD-2-Clause).

Pygments необязателен: нет библиотеки — подсветки нет, и редактор работает как раньше.
spans_for_path(code, path) -> [(начало, конец, тег)] с теми же тегами, что у остальных языков (kw, bi, func, cls, deco, number, string, comment)."""
import os

MAX_CHARS = 150_000        # подсветка идёт в потоке интерфейса: большие файлы не разбираем

LEXER_BY_EXT = {".json": "json", ".yaml": "yaml", ".yml": "yaml", ".md": "markdown", ".toml": "toml", ".ini": "ini",
                ".cfg": "ini", ".xml": "xml", ".sh": "bash", ".bat": "bat", ".sql": "sql"}

_cache = {}


def available():
    try:
        import pygments  # noqa: F401
        return True
    except ImportError:
        return False


def _lexer(name):
    if name not in _cache:
        try:
            from pygments.lexers import get_lexer_by_name
            _cache[name] = get_lexer_by_name(name, stripnl=False, ensurenl=False)
        except Exception:
            _cache[name] = None
    return _cache[name]


def _tag(tok):
    from pygments.token import Comment, Generic, Keyword, Name, Number, String
    if tok in Comment:
        return "comment"
    if tok in String:
        return "string"
    if tok in Number:
        return "number"
    if tok in Name.Builtin:
        return "bi"
    if tok in Name.Function or tok in Name.Attribute:
        return "func"
    if tok in Name.Class or tok in Generic.Heading or tok in Generic.Subheading:
        return "cls"
    if tok in Name.Decorator or tok in Name.Label:
        return "deco"
    if tok in Keyword or tok in Name.Tag or tok in Generic.Strong:
        return "kw"
    return None


def spans_for_path(code, path):
    ext = os.path.splitext(path or "")[1].lower()
    name = LEXER_BY_EXT.get(ext)
    if not name or not code or len(code) > MAX_CHARS or not available():
        return []
    lx = _lexer(name)
    if lx is None:
        return []
    out = []
    try:
        for i, tok, val in lx.get_tokens_unprocessed(code):
            tag = _tag(tok)
            if tag and val:
                out.append((i, i + len(val), tag))
    except Exception:
        return []
    return out
