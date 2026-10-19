"""Подсветка синтаксиса JavaScript, CSS и HTML. spans(code, lang) -> [(начало, конец, тег)]"""
import re

# ----------------------------------------------------------- JavaScript
JS_KW = set("""break case catch class const continue debugger default delete do else export extends finally for
function if import in instanceof let new of return static super switch throw try typeof var void while with yield
async await from as get set true false null undefined""".split())
JS_BI = set("""console document window Math JSON Array Object String Number Boolean Promise Date Map Set RegExp Error
parseInt parseFloat setTimeout setInterval clearTimeout clearInterval fetch require module exports process
localStorage sessionStorage alert prompt confirm isNaN Symbol BigInt WeakMap WeakSet Intl navigator location
history Buffer globalThis""".split())

JS_TOKEN = re.compile(
    r"(?P<comment>//[^\n]*|/\*[\s\S]*?(?:\*/|\Z))"
    r"|(?P<string>\"(?:\\.|[^\"\\\n])*\"?|'(?:\\.|[^'\\\n])*'?|`(?:\\[\s\S]|[^`\\])*`?)"
    r"|(?P<number>\b(?:0[xX][0-9a-fA-F]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)\b)"
    r"|(?P<word>[A-Za-z_$][\w$]*)")


def spans_js(code):
    out, prev = [], ""
    for m in JS_TOKEN.finditer(code):
        k, tag = m.lastgroup, None
        if k == "word":
            w = m.group()
            if w in JS_KW:
                tag = "kw"
            elif w == "this":
                tag = "self"
            elif prev == "function" or code[m.end():m.end() + 1] == "(":
                tag = "func"
            elif prev == "class":
                tag = "cls"
            elif w in JS_BI:
                tag = "bi"
            prev = w
        else:
            prev, tag = "", k
        if tag:
            out.append((m.start(), m.end(), tag))
    return out


# ------------------------------------------------------------------ CSS
CSS_TOKEN = re.compile(
    r"(?P<comment>/\*[\s\S]*?(?:\*/|\Z))"
    r"|(?P<string>\"(?:\\.|[^\"\\\n])*\"?|'(?:\\.|[^'\\\n])*'?)"
    r"|(?P<open>\{)|(?P<close>\})|(?P<semi>;)"
    r"|(?P<other>[^{};/\"']+|/)")
_CSS_PROP = re.compile(r"\s*(-{0,2}[\w-]+)\s*:")
_CSS_VAL = re.compile(r"(?P<number>(?<![\w#-])[+-]?(?:\d+\.?\d*|\.\d+)[A-Za-z%]*|#[0-9A-Za-z]+\b)"
                      r"|(?P<kw>!\s*important)|(?P<func>[A-Za-z-]+(?=\())")
_CSS_SEL = re.compile(r"(?P<cls>[.#][-\w]+)|(?P<deco>::?[-\w]+)|(?P<kw>@[-\w]+)"
                      r"|(?P<func>(?<![-\w])[A-Za-z][-\w]*)|(?P<number>(?<![\w#-])\d+\.?\d*[A-Za-z%]*)")


def spans_css(code):
    out, stack, prelude = [], [], ""
    for m in CSS_TOKEN.finditer(code):
        k = m.lastgroup
        if k in ("comment", "string"):
            out.append((m.start(), m.end(), k))
        elif k == "open":
            pre = prelude.strip()
            if pre.startswith("@"):
                nm = re.match(r"@([\w-]+)", pre)
                stack.append((nm.group(1).lower() if nm else "") in ("font-face", "page", "property", "counter-style"))
            else:
                stack.append(True)
            prelude = ""
        elif k == "close":
            if stack:
                stack.pop()
            prelude = ""
        elif k == "semi":
            prelude = ""
        else:
            chunk, base = m.group(), m.start()
            prelude += chunk
            if stack and stack[-1]:                   # внутри блока свойств
                pm = _CSS_PROP.match(chunk)
                pos = 0
                if pm:
                    out.append((base + pm.start(1), base + pm.end(1), "bi"))
                    pos = pm.end()
                for v in _CSS_VAL.finditer(chunk, pos):
                    out.append((base + v.start(), base + v.end(), v.lastgroup))
            else:                                     # селектор или @-правило
                for v in _CSS_SEL.finditer(chunk):
                    out.append((base + v.start(), base + v.end(), v.lastgroup))
    return out


# ----------------------------------------------------------------- HTML
HTML_TOKEN = re.compile(
    r"(?P<comment><!--[\s\S]*?(?:-->|\Z))"
    r"|(?P<decl><![A-Za-z][^>]*>)"
    r"|(?P<tag></?[A-Za-z][-\w:]*(?:\"[^\"]*\"|'[^']*'|[^'\">])*>)"
    r"|(?P<entity>&#?\w+;)")
_ATTR = re.compile(r"([A-Za-z_:@][-\w:.]*)(?:(\s*=\s*)(\"[^\"]*\"?|'[^']*'?|[^\s\"'>]+))?")


def spans_html(code):
    out, pos, n = [], 0, len(code)
    while pos < n:
        m = HTML_TOKEN.search(code, pos)
        if not m:
            break
        k = m.lastgroup
        if k in ("comment", "entity"):
            out.append((m.start(), m.end(), "comment" if k == "comment" else "number"))
        elif k == "decl":
            out.append((m.start(), m.end(), "deco"))
        else:
            tag = m.group()
            nm = re.match(r"</?([A-Za-z][-\w:]*)", tag)
            out.append((m.start() + nm.start(1), m.start() + nm.end(1), "kw"))
            for a in _ATTR.finditer(tag, nm.end()):
                out.append((m.start() + a.start(1), m.start() + a.end(1), "func"))
                if a.group(3):
                    out.append((m.start() + a.start(3), m.start() + a.end(3), "string"))
            name = nm.group(1).lower()
            if name in ("script", "style") and not tag.startswith("</") and not tag.endswith("/>"):
                close = re.compile(r"</%s\s*>" % name, re.I).search(code, m.end())
                end = close.start() if close else n
                sub = spans_js(code[m.end():end]) if name == "script" else spans_css(code[m.end():end])
                out.extend((s + m.end(), e + m.end(), t) for s, e, t in sub)
                pos = end
                continue
        pos = m.end()
    return out


def spans(code, lang):
    if lang == "js":
        return spans_js(code)
    if lang == "css":
        return spans_css(code)
    if lang == "html":
        return spans_html(code)
    from pyfactor.core.funlang import spans_fun
    return spans_fun(code, lang)
