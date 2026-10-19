"""Простой просмотр HTML: белая страница и чёрный текст — только то, что ты написал.

render_html(code) -> (список (текст, теги), заголовок страницы)
"""
import re
from html.parser import HTMLParser

_SKIP = {"script", "style", "head", "title", "noscript", "template"}
_BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "nav", "aside", "ul", "ol", "li",
          "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "pre", "blockquote", "form", "dl", "dt", "dd",
          "fieldset", "figure", "details", "summary", "address", "body", "html"}
_FMT = {"h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h4", "h6": "h4",
        "b": "b", "strong": "b", "i": "i", "em": "i", "cite": "i", "u": "u", "ins": "u", "a": "a",
        "code": "mono", "pre": "mono", "kbd": "mono", "samp": "mono", "tt": "mono",
        "s": "strike", "del": "strike", "strike": "strike", "small": "small", "mark": "mark", "th": "b"}


class _Render(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.fmt, self.lists = [], [], []
        self.skip, self.pre, self.nl = 0, 0, 2       # nl — сколько переводов строки в конце
        self.title, self._in_title, self.row_cells = "", False, 0

    def _emit(self, text, tags=None):
        if not text:
            return
        self.out.append((text, tuple(dict.fromkeys(tags if tags is not None else self.fmt))))
        stripped = text.rstrip("\n")
        self.nl = len(text) - len(stripped) if not stripped else 0
        if stripped:
            self.nl = len(text) - len(stripped)

    def _break(self, n=1):
        if self.nl < n and self.out:
            self._emit("\n" * (n - self.nl), ())

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag in _SKIP:
            self.skip += 1
            return
        if tag in ("ul", "ol"):
            self._break(1)
            self.lists.append([tag, 0])
        elif tag == "li":
            self._break(1)
            if self.lists:
                self.lists[-1][1] += 1
                mark = "• " if self.lists[-1][0] == "ul" else "%d. " % self.lists[-1][1]
                self._emit("    " * (len(self.lists) - 1) + mark, ())
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._break(2)
        elif tag in _BLOCK:
            self._break(2 if tag in ("p", "blockquote", "table", "pre") else 1)
        elif tag == "br":
            self._emit("\n", ())
        elif tag == "hr":
            self._break(1)
            self._emit("─" * 48 + "\n", ())
        elif tag == "img":
            self._emit("[картинка%s]" % (": " + a["alt"] if a.get("alt") else ""), ("i",))
        elif tag == "input":
            kind = (a.get("type") or "text").lower()
            self._emit("[%s]" % (a.get("value") or "☐" if kind in ("checkbox", "radio") else
                                 a.get("value") or a.get("placeholder") or "поле ввода"), ("mono",))
        elif tag == "button":
            self._emit("[ ", ())
        elif tag in ("td", "th"):
            if self.row_cells:
                self._emit("  │  ", ())
            self.row_cells += 1
        elif tag == "tr":
            self.row_cells = 0
        if tag == "pre":
            self.pre += 1
        if tag in _FMT:
            self.fmt.append(_FMT[tag])
            if tag == "a" and a.get("href"):
                pass

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if tag in ("ul", "ol") and self.lists:
            self.lists.pop()
        if tag == "button":
            self._emit(" ]", ())
        if tag == "pre":
            self.pre = max(0, self.pre - 1)
        if tag in _FMT and _FMT[tag] in self.fmt:
            for k in range(len(self.fmt) - 1, -1, -1):
                if self.fmt[k] == _FMT[tag]:
                    del self.fmt[k]
                    break
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "blockquote"):
            self._break(2)
        elif tag in _BLOCK:
            self._break(1)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()
            return
        if self.skip:
            return
        if self.pre:
            self._emit(data)
            return
        data = re.sub(r"\s+", " ", data)
        if self.nl and data.startswith(" "):
            data = data.lstrip(" ")
        if data:
            self._emit(data)


def render_html(code):
    r = _Render()
    try:
        r.feed(code)
        r.close()
    except Exception:
        pass
    out = r.out
    while out and not out[-1][0].strip():
        out.pop()
    return out, r.title
