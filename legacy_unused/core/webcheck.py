"""Проверка HTML, CSS и JavaScript.

Каждая функция возвращает словарь такого же вида, как analyze() для Python:
    {"errors": [(строка, колонка, текст)], "warnings": [(строка, колонка, текст, вид, имя)], ...}
"""
import colorsys
import difflib
import os
import re
import subprocess
import tempfile
from bisect import bisect_right
from html.parser import HTMLParser

from pyfactor.config import NO_WIN


def _starts(code):
    s = [0]
    for m in re.finditer("\n", code):
        s.append(m.end())
    return s


def _pos(starts, i):
    l = bisect_right(starts, i) - 1
    return l + 1, i - starts[l]


# =============================================================== JavaScript
_RX_PREV = set("(,=:[!&|?{};+-*%<>~^")
_RX_KW = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "yield", "await"}
_PAIR = {")": "(", "]": "[", "}": "{"}
_WORD = re.compile(r"[A-Za-z_$][\w$]*")
_NUM = re.compile(r"\d[\w.]*")


def check_js(code):
    errors, warnings = [], []
    st = _starts(code)
    n = len(code)
    stack = []                      # (символ, позиция)
    last = None                     # последний значимый токен
    i = 0

    def err(p, msg):
        errors.append(_pos(st, p) + (msg,))

    def warn(p, msg, kind, name=""):
        warnings.append(_pos(st, p) + (msg, kind, name))

    def scan_template(j):
        """Читает текст шаблонной строки с позиции j. -> (индекс, 'end'|'expr'|'eof')"""
        while j < n:
            ch = code[j]
            if ch == "\\":
                j += 2
            elif ch == "`":
                return j + 1, "end"
            elif ch == "$" and code[j:j + 2] == "${":
                return j + 2, "expr"
            else:
                j += 1
        return n, "eof"

    while i < n:
        c = code[i]
        if c in " \t\r\n":
            i += 1
        elif code.startswith("//", i):
            j = code.find("\n", i)
            i = n if j < 0 else j
        elif code.startswith("/*", i):
            j = code.find("*/", i + 2)
            if j < 0:
                err(i, "комментарий /* не закрыт (нет */)")
                break
            i = j + 2
        elif c in "\"'":
            j = i + 1
            while j < n and code[j] != c and code[j] != "\n":
                j += 2 if code[j] == "\\" else 1
            if j >= n or code[j] != c:
                err(i, "строка не закрыта — не хватает кавычки %s" % c)
                i = min(j, n)
            else:
                i = j + 1
            last = "str"
        elif c == "`":
            i, status = scan_template(i + 1)
            if status == "expr":
                stack.append(("${", i - 2))
                last = "{"
            elif status == "eof":
                err(i, "шаблонная строка ` не закрыта")
                break
            else:
                last = "str"
        elif c == "/":
            is_rx = last is None or last in _RX_PREV or last in _RX_KW
            j = i + 1
            if is_rx:
                in_cls = False
                while j < n:
                    ch = code[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "\n":
                        break
                    if ch == "[":
                        in_cls = True
                    elif ch == "]":
                        in_cls = False
                    elif ch == "/" and not in_cls:
                        break
                    j += 1
                if j < n and code[j] == "/":
                    j += 1
                    while j < n and code[j].isalpha():
                        j += 1
                    i, last = j, "rx"
                    continue
            i += 1
            last = "/"
        elif c in "([{":
            stack.append((c, i))
            last = c
            i += 1
        elif c in ")]}":
            if c == "}" and stack and stack[-1][0] == "${":
                stack.pop()
                i, status = scan_template(i + 1)
                if status == "expr":
                    stack.append(("${", i - 2))
                elif status == "eof":
                    err(i, "шаблонная строка ` не закрыта")
                    break
                last = "str"
                continue
            want = _PAIR[c]
            if not stack:
                err(i, "лишняя закрывающая скобка '%s'" % c)
            elif stack[-1][0] == want:
                stack.pop()
            elif any(s[0] == want for s in stack):
                while stack and stack[-1][0] != want:
                    ch, p = stack.pop()
                    err(p, "скобка '%s' не закрыта (строка %d)" % (ch if ch != "${" else "${", _pos(st, p)[0]))
                stack.pop()
            else:
                err(i, "лишняя закрывающая скобка '%s'" % c)
            last = c
            i += 1
        elif c.isalpha() or c in "_$":
            m = _WORD.match(code, i)
            w = m.group()
            if w == "var":
                warn(i, "var — старый способ, лучше let или const", "var", w)
            elif w == "debugger":
                warn(i, "debugger остановит программу в отладчике — убери перед публикацией", "debugger", w)
            last = w
            i = m.end()
        elif c.isdigit():
            i = _NUM.match(code, i).end()
            last = "0"
        elif c in "=!" and code.startswith(("===", "!=="), i):
            i += 3
            last = "="
        elif c in "=!" and code.startswith(("==", "!="), i) and (i == 0 or code[i - 1] not in "=!<>"):
            if not re.match(r"\s*(null|undefined)\b", code[i + 2:i + 20]):
                warn(i, "%s сравнивает неточно — надёжнее %s=" % (code[i:i + 2], code[i:i + 2]), "eq", code[i:i + 2])
            i += 2
            last = "="
        else:
            last = c
            i += 1

    for ch, p in stack:
        err(p, "скобка '%s' не закрыта" % ("{" if ch == "${" else ch))
    errors.sort()
    warnings.sort()
    return {"errors": errors, "warnings": warnings, "unclosed": stack, "lang": "js"}


def fix_js(code, res):
    """Осторожные автоисправления: недостающие закрывающие скобки и == → ===."""
    notes = []
    new = code
    st = _starts(code)
    edits = []
    for ln, col, msg, kind, name in res["warnings"]:
        if kind == "eq":
            edits.append(st[ln - 1] + col)
    for p in sorted(edits, reverse=True):
        new = new[:p] + new[p:p + 2] + "=" + new[p + 2:]
    if edits:
        notes.append("%s → строгое сравнение (===, !==): %d" % ("==, !=", len(edits)))
    only_unclosed = res["errors"] and all("не закрыта" in e[2] and "строка не" not in e[2]
                                          and "комментарий" not in e[2] and "шаблонная" not in e[2]
                                          for e in res["errors"])
    if only_unclosed and res.get("unclosed"):
        closers = "".join({"(": ")", "[": "]", "{": "}", "${": "}"}[ch] for ch, _ in reversed(res["unclosed"]))
        cand = new.rstrip("\n") + "\n" + closers + "\n"
        if not check_js(cand)["errors"]:            # применяем, только если после этого ошибок нет
            new = cand
            notes.append("добавлены недостающие скобки: " + closers)
    return new, notes


def node_syntax_check(node, code):
    """Точная проверка синтаксиса через Node.js. -> (строка, сообщение) или None."""
    ext = ".mjs" if re.search(r"^\s*(import\s.+from|export\s)", code, re.M) else ".js"
    d = tempfile.mkdtemp(prefix="pyfactor_js_")
    p = os.path.join(d, "check" + ext)
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(code)
        r = subprocess.run([node, "--check", p], capture_output=True, text=True, timeout=10,
                           encoding="utf-8", errors="replace", creationflags=NO_WIN)
    except Exception:
        return None
    finally:
        try:
            os.remove(p)
            os.rmdir(d)
        except OSError:
            pass
    if r.returncode == 0:
        return None
    text = r.stderr
    m = re.search(r"check\.m?js:(\d+)", text)
    msg = re.search(r"SyntaxError:\s*(.+)", text)
    return (int(m.group(1)) if m else 1, msg.group(1).strip() if msg else "синтаксическая ошибка")


def run_js_once(node, code, timeout=4):
    """Пробный запуск. -> (код возврата | None при таймауте, вывод)"""
    ext = ".mjs" if re.search(r"^\s*(import\s.+from|export\s)", code, re.M) else ".js"
    d = tempfile.mkdtemp(prefix="pyfactor_js_")
    p = os.path.join(d, "run" + ext)
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(code)
        r = subprocess.run([node, p], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           encoding="utf-8", errors="replace", creationflags=NO_WIN)
        return r.returncode, (r.stdout + r.stderr).replace(p, "script" + ext)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return None, out
    except Exception as e:
        return -1, str(e)
    finally:
        try:
            os.remove(p)
            os.rmdir(d)
        except OSError:
            pass


# ===================================================================== CSS
CSS_PROPS = set("""
accent-color align-content align-items align-self all animation animation-delay animation-direction
animation-duration animation-fill-mode animation-iteration-count animation-name animation-play-state
animation-timing-function appearance aspect-ratio backdrop-filter backface-visibility background
background-attachment background-blend-mode background-clip background-color background-image
background-origin background-position background-position-x background-position-y background-repeat
background-size block-size border border-block border-bottom border-bottom-color border-bottom-left-radius
border-bottom-right-radius border-bottom-style border-bottom-width border-collapse border-color
border-end-end-radius border-end-start-radius border-image border-inline border-left border-left-color
border-left-style border-left-width border-radius border-right border-right-color border-right-style
border-right-width border-spacing border-start-end-radius border-start-start-radius border-style border-top
border-top-color border-top-left-radius border-top-right-radius border-top-style border-top-width
border-width bottom box-decoration-break box-shadow box-sizing break-after break-before break-inside
caption-side caret-color clear clip clip-path color color-scheme column-count column-fill column-gap
column-rule column-rule-color column-rule-style column-rule-width column-span column-width columns contain
container container-name container-type content counter-increment counter-reset counter-set cursor
direction display empty-cells fill fill-opacity fill-rule filter flex flex-basis flex-direction flex-flow
flex-grow flex-shrink flex-wrap float font font-display font-family font-feature-settings font-kerning
font-size font-size-adjust font-stretch font-style font-variant font-variant-caps font-variant-numeric
font-variation-settings font-weight gap grid grid-area grid-auto-columns grid-auto-flow grid-auto-rows
grid-column grid-column-end grid-column-gap grid-column-start grid-gap grid-row grid-row-end grid-row-gap
grid-row-start grid-template grid-template-areas grid-template-columns grid-template-rows hanging-punctuation
height hyphens image-rendering inline-size inset inset-block inset-inline isolation justify-content
justify-items justify-self left letter-spacing line-break line-height list-style list-style-image
list-style-position list-style-type margin margin-block margin-bottom margin-inline margin-left margin-right
margin-top mask mask-image mask-position mask-repeat mask-size max-height max-width max-block-size
max-inline-size min-block-size min-height min-inline-size min-width mix-blend-mode object-fit object-position
offset opacity order orphans outline outline-color outline-offset outline-style outline-width overflow
overflow-anchor overflow-wrap overflow-x overflow-y overscroll-behavior padding padding-block
padding-bottom padding-inline padding-left padding-right padding-top page-break-after page-break-before
page-break-inside paint-order perspective perspective-origin place-content place-items place-self
pointer-events position quotes resize right rotate row-gap scale scroll-behavior scroll-margin scroll-padding
scroll-snap-align scroll-snap-type scrollbar-color scrollbar-width shape-outside tab-size table-layout
text-align text-align-last text-decoration text-decoration-color text-decoration-line text-decoration-style
text-decoration-thickness text-indent text-justify text-overflow text-shadow text-transform
text-underline-offset text-underline-position top touch-action transform transform-origin transform-style
transition transition-delay transition-duration transition-property transition-timing-function translate
unicode-bidi user-select vertical-align visibility white-space widows width will-change word-break
word-spacing word-wrap writing-mode z-index zoom src unicode-range size margin-trim
""".split())

_AT_DECL = {"font-face", "page", "property", "counter-style", "viewport"}
_AT_KNOWN = _AT_DECL | {"media", "supports", "keyframes", "import", "charset", "namespace", "layer",
                        "container", "document", "font-feature-values", "scope", "starting-style"}
_UNITS = set("px em rem % vh vw vmin vmax svh svw lvh lvw dvh dvw ch ex cm mm in pt pc q deg rad grad turn "
             "s ms fr dppx dpi dpcm x cqw cqh cqi cqb lh rlh e".split())
_COLOR_PROPS = ("color", "background", "border", "outline", "fill", "stroke", "box-shadow", "text-shadow",
                "text-decoration", "caret-color", "accent-color", "column-rule")
_CSS_WIDE = {"inherit", "initial", "unset", "revert", "currentcolor", "transparent", "none"}

NAMED = dict(x.split(":") for x in (
    "aliceblue:f0f8ff,antiquewhite:faebd7,aqua:00ffff,aquamarine:7fffd4,azure:f0ffff,beige:f5f5dc,"
    "bisque:ffe4c4,black:000000,blanchedalmond:ffebcd,blue:0000ff,blueviolet:8a2be2,brown:a52a2a,"
    "burlywood:deb887,cadetblue:5f9ea0,chartreuse:7fff00,chocolate:d2691e,coral:ff7f50,"
    "cornflowerblue:6495ed,cornsilk:fff8dc,crimson:dc143c,cyan:00ffff,darkblue:00008b,darkcyan:008b8b,"
    "darkgoldenrod:b8860b,darkgray:a9a9a9,darkgreen:006400,darkgrey:a9a9a9,darkkhaki:bdb76b,"
    "darkmagenta:8b008b,darkolivegreen:556b2f,darkorange:ff8c00,darkorchid:9932cc,darkred:8b0000,"
    "darksalmon:e9967a,darkseagreen:8fbc8f,darkslateblue:483d8b,darkslategray:2f4f4f,"
    "darkslategrey:2f4f4f,darkturquoise:00ced1,darkviolet:9400d3,deeppink:ff1493,deepskyblue:00bfff,"
    "dimgray:696969,dimgrey:696969,dodgerblue:1e90ff,firebrick:b22222,floralwhite:fffaf0,"
    "forestgreen:228b22,fuchsia:ff00ff,gainsboro:dcdcdc,ghostwhite:f8f8ff,gold:ffd700,"
    "goldenrod:daa520,gray:808080,green:008000,greenyellow:adff2f,grey:808080,honeydew:f0fff0,"
    "hotpink:ff69b4,indianred:cd5c5c,indigo:4b0082,ivory:fffff0,khaki:f0e68c,lavender:e6e6fa,"
    "lavenderblush:fff0f5,lawngreen:7cfc00,lemonchiffon:fffacd,lightblue:add8e6,lightcoral:f08080,"
    "lightcyan:e0ffff,lightgoldenrodyellow:fafad2,lightgray:d3d3d3,lightgreen:90ee90,lightgrey:d3d3d3,"
    "lightpink:ffb6c1,lightsalmon:ffa07a,lightseagreen:20b2aa,lightskyblue:87cefa,"
    "lightslategray:778899,lightslategrey:778899,lightsteelblue:b0c4de,lightyellow:ffffe0,lime:00ff00,"
    "limegreen:32cd32,linen:faf0e6,magenta:ff00ff,maroon:800000,mediumaquamarine:66cdaa,"
    "mediumblue:0000cd,mediumorchid:ba55d3,mediumpurple:9370db,mediumseagreen:3cb371,"
    "mediumslateblue:7b68ee,mediumspringgreen:00fa9a,mediumturquoise:48d1cc,mediumvioletred:c71585,"
    "midnightblue:191970,mintcream:f5fffa,mistyrose:ffe4e1,moccasin:ffe4b5,navajowhite:ffdead,"
    "navy:000080,oldlace:fdf5e6,olive:808000,olivedrab:6b8e23,orange:ffa500,orangered:ff4500,"
    "orchid:da70d6,palegoldenrod:eee8aa,palegreen:98fb98,paleturquoise:afeeee,palevioletred:db7093,"
    "papayawhip:ffefd5,peachpuff:ffdab9,peru:cd853f,pink:ffc0cb,plum:dda0dd,powderblue:b0e0e6,"
    "purple:800080,rebeccapurple:663399,red:ff0000,rosybrown:bc8f8f,royalblue:4169e1,"
    "saddlebrown:8b4513,salmon:fa8072,sandybrown:f4a460,seagreen:2e8b57,seashell:fff5ee,sienna:a0522d,"
    "silver:c0c0c0,skyblue:87ceeb,slateblue:6a5acd,slategray:708090,slategrey:708090,snow:fffafa,"
    "springgreen:00ff7f,steelblue:4682b4,tan:d2b48c,teal:008080,thistle:d8bfd8,tomato:ff6347,"
    "turquoise:40e0d0,violet:ee82ee,wheat:f5deb3,white:ffffff,whitesmoke:f5f5f5,yellow:ffff00,"
    "yellowgreen:9acd32").split(","))


def _hex_norm(h):
    h = h.lstrip("#").lower()
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h[:3])
    return "#" + h[:6]


def _fn_color(name, args):
    """rgb()/hsl() -> '#rrggbb' или None"""
    parts = [p for p in re.split(r"[,\s/]+", args.strip()) if p]
    if len(parts) not in (3, 4):
        return None

    def num(p, scale=1.0):
        pc = p.endswith("%")
        v = float(p[:-1] if pc else re.sub(r"(deg|rad|turn|grad)$", "", p))
        return v / 100.0 if pc else v / scale
    try:
        if name.startswith("rgb"):
            r, g, b = (min(1.0, max(0.0, num(p, 255.0))) for p in parts[:3])
        else:
            h = float(re.sub(r"(deg)$", "", parts[0])) / 360.0
            s, l = num(parts[1], 100.0), num(parts[2], 100.0)
            r, g, b = colorsys.hls_to_rgb(h % 1.0, min(1, max(0, l)), min(1, max(0, s)))
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
    except ValueError:
        return None


def check_css(code):
    errors, warnings, colors = [], [], []
    st = _starts(code)
    n = len(code)

    def err(p, msg):
        errors.append(_pos(st, p) + (msg,))

    def warn(p, msg, kind="css", name=""):
        warnings.append(_pos(st, p) + (msg, kind, name))

    # 1. прячем комментарии и содержимое строк (длина и переводы строк сохраняются)
    clean = list(code)
    i = 0
    while i < n:
        c = code[i]
        if code.startswith("/*", i):
            j = code.find("*/", i + 2)
            if j < 0:
                err(i, "комментарий /* не закрыт (нет */)")
                j = n - 2
            for k in range(i, j + 2):
                if code[k] != "\n":
                    clean[k] = " "
            i = j + 2
        elif c in "\"'":
            j = i + 1
            while j < n and code[j] != c and code[j] != "\n":
                j += 2 if code[j] == "\\" else 1
            j = min(j, n)
            if j >= n or code[j] != c:
                err(i, "строка не закрыта — не хватает кавычки %s" % c)
                end = j
            else:
                end = j + 1
            for k in range(i + 1, min(end, j if j < n and code[j] == c else end)):
                if code[k] != "\n":
                    clean[k] = "_"
            i = max(end, i + 1)
        else:
            i += 1
    text = "".join(clean)

    def add_color(h):
        if h not in colors:
            colors.append(h)

    def process_decl(chunk, off):
        s = chunk.strip()
        if not s:
            return
        at = off + (len(chunk) - len(chunk.lstrip()))
        depth, colon = 0, -1
        for k, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == ":" and depth == 0:
                colon = k
                break
        if colon < 0:
            err(at, "после «%s» нет двоеточия ':'" % s[:30])
            return
        prop, val = s[:colon].strip(), s[colon + 1:].strip()
        if not re.fullmatch(r"-{0,2}[A-Za-z_][\w-]*", prop):
            err(at, "странное имя свойства «%s»" % prop[:30])
            return
        if not val:
            err(at, "у свойства «%s» нет значения" % prop)
            return
        lp = prop.lower()
        if not lp.startswith("-") and lp not in CSS_PROPS:
            hint = difflib.get_close_matches(lp, CSS_PROPS, 1, 0.75)
            warn(at, "неизвестное свойство «%s»%s" % (prop, " — может, %s?" % hint[0] if hint else ""), "prop", prop)
        # скобки в значении
        if val.count("(") != val.count(")"):
            err(at, "в значении «%s» не закрыта скобка" % prop)
        flat = val
        while True:
            nxt = re.sub(r"\([^()]*\)", "()", flat)
            if nxt == flat:
                break
            flat = nxt
        m = re.search(r"(?:^|\s)([a-z-]{3,})\s*:\s*\S", flat)
        if m and m.group(1) in CSS_PROPS:
            err(at, "пропущена ';' перед «%s:»" % m.group(1))
            return
        nourl = re.sub(r"url\([^)]*\)", " ", val)
        # шестнадцатеричные цвета
        for m in re.finditer(r"#([0-9A-Za-z]+)\b", nourl):
            h = m.group(1)
            if re.fullmatch(r"[0-9a-fA-F]+", h) and len(h) in (3, 4, 6, 8):
                add_color(_hex_norm(h))
            elif lp != "content":
                err(at, "цвет #%s записан неверно (нужно 3, 4, 6 или 8 цифр 0-9, a-f)" % h)
        # rgb()/hsl()
        for m in re.finditer(r"\b(rgba?|hsla?)\(([^()]*)\)", nourl, re.I):
            hx = _fn_color(m.group(1).lower(), m.group(2))
            if hx:
                add_color(hx)
            elif "var(" not in m.group(2):
                err(at, "неверный цвет %s(%s)" % (m.group(1), m.group(2)[:25]))
        # названия цветов и опечатки в них
        if lp.startswith(_COLOR_PROPS):
            for w in re.findall(r"(?<![\w#.-])[A-Za-z]+(?![\w(-])", re.sub(r"\([^()]*\)", "()", nourl)):
                lw = w.lower()
                if lw in NAMED:
                    add_color("#" + NAMED[lw])
                elif lp in ("color", "background-color", "caret-color", "accent-color", "fill", "stroke") \
                        and lw not in _CSS_WIDE:
                    hint = difflib.get_close_matches(lw, list(NAMED), 1, 0.7)
                    warn(at, "«%s» — неизвестный цвет%s" % (w, " (может, %s?)" % hint[0] if hint else ""), "color", w)
        # единицы измерения
        body = re.sub(r"#[0-9A-Za-z]+", " ", nourl)
        for m in re.finditer(r"(?<![\w#.-])[+-]?(?:\d+\.?\d*|\.\d+)([A-Za-z%]+)", body):
            u = m.group(1).lower()
            if u not in _UNITS and lp not in ("content", "font-family", "src", "unicode-range"):
                warn(at, "неизвестная единица «%s» в %s" % (m.group(1), prop), "unit", m.group(1))

    stack = []
    start, paren, i = 0, 0, 0

    def in_decl():
        return bool(stack) and stack[-1]["kind"] == "decl"

    while i < n:
        c = text[i]
        if c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        elif paren and c in "{}":
            paren = 0
        if paren and c != "{" and c != "}":
            i += 1
            continue
        if c == "{":
            pre = text[start:i].strip()
            at = start + (len(text[start:i]) - len(text[start:i].lstrip()))
            if pre.startswith("@"):
                m = re.match(r"@([\w-]+)", pre)
                nm = m.group(1).lower() if m else ""
                if nm not in _AT_KNOWN and not nm.startswith("-"):
                    warn(at, "неизвестное правило @%s" % nm, "at", nm)
                kind = "decl" if nm in _AT_DECL else "rules"
            else:
                kind = "decl"
                if not pre:
                    err(i, "перед '{' нет селектора")
                elif pre.endswith(",") or pre.startswith(","):
                    err(at, "лишняя запятая в селекторе «%s»" % pre[:30])
                elif pre.count("(") != pre.count(")") or pre.count("[") != pre.count("]"):
                    err(at, "в селекторе «%s» не закрыта скобка" % pre[:30])
            stack.append({"kind": kind, "pos": i, "decls": 0})
            start = i + 1
        elif c == "}":
            if in_decl():
                process_decl(text[start:i], start)
            elif text[start:i].strip():
                err(start + len(text[start:i]) - len(text[start:i].lstrip()),
                    "«%s» стоит вне правила — ожидалось '{'" % text[start:i].strip()[:30])
            if not stack:
                err(i, "лишняя закрывающая скобка '}'")
            else:
                top = stack.pop()
                if top["kind"] == "decl" and not text[top["pos"] + 1:i].strip():
                    warn(top["pos"], "пустое правило — внутри {} ничего нет", "empty")
            start = i + 1
        elif c == ";":
            if in_decl():
                process_decl(text[start:i], start)
            else:
                stmt = text[start:i].strip()
                if stmt and not stmt.startswith("@"):
                    err(start + len(text[start:i]) - len(text[start:i].lstrip()),
                        "«%s» — здесь не хватает { }" % stmt[:30])
            start = i + 1
        i += 1
    for s in stack:
        err(s["pos"], "скобка '{' не закрыта")
    tail = text[start:].strip()
    if tail and not stack:
        err(start + len(text[start:]) - len(text[start:].lstrip()), "в конце остался лишний текст «%s»" % tail[:30])
    elif tail and stack and in_decl():
        process_decl(text[start:], start)
    errors.sort()
    warnings.sort()
    return {"errors": errors, "warnings": warnings, "colors": colors, "lang": "css"}


# =================================================================== HTML
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_OPT_END = {"p", "li", "dt", "dd", "tr", "td", "th", "thead", "tbody", "tfoot", "option", "optgroup",
            "colgroup", "body", "head", "html"}
_OLD_TAGS = {"font", "center", "marquee", "blink", "big", "strike", "tt", "frame", "frameset"}


class _Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.warnings = [], [], []
        self.seen, self.doctype = set(), False

    def _info(self, tag, attrs):
        ln, col = self.getpos()
        self.seen.add(tag)
        if tag in _OLD_TAGS:
            self.warnings.append((ln, col, "тег <%s> устарел" % tag, "old", tag))
        if tag == "img" and not any(k == "alt" for k, _ in attrs):
            self.warnings.append((ln, col, "у <img> нет alt — добавь описание картинки", "alt", "img"))
        if tag == "a" and not any(k == "href" for k, _ in attrs):
            self.warnings.append((ln, col, "у <a> нет href — ссылка никуда не ведёт", "href", "a"))

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype"):
            self.doctype = True

    def handle_starttag(self, tag, attrs):
        self._info(tag, attrs)
        if tag not in _VOID:
            ln, col = self.getpos()
            self.stack.append((tag, ln, col))

    def handle_startendtag(self, tag, attrs):
        self._info(tag, attrs)

    def handle_endtag(self, tag):
        ln, col = self.getpos()
        if tag in _VOID:
            return
        k = next((k for k in range(len(self.stack) - 1, -1, -1) if self.stack[k][0] == tag), None)
        if k is None:
            self.errors.append((ln, col, "лишний закрывающий тег </%s>" % tag))
            return
        for t, l, c in reversed(self.stack[k + 1:]):
            if t not in _OPT_END:
                self.errors.append((l, c, "тег <%s> не закрыт (ждём </%s>)" % (t, t)))
        del self.stack[k:]


def check_html(code):
    ck = _Checker()
    st = _starts(code)
    pre = []
    for m in re.finditer(r"<!--", code):
        if code.find("-->", m.end()) < 0:
            pre.append(_pos(st, m.start()) + ("комментарий <!-- не закрыт (нет -->)",))
            break
    try:
        ck.feed(code)
        ck.close()
    except Exception as e:                       # разбор не должен ронять редактор
        pre.append((1, 0, "не удалось разобрать HTML: %s" % e))
    for t, l, c in ck.stack:
        if t not in _OPT_END:
            ck.errors.append((l, c, "тег <%s> не закрыт" % t))
    errors, warnings = pre + ck.errors, list(ck.warnings)
    if "html" in ck.seen or "head" in ck.seen:
        if not ck.doctype:
            warnings.append((1, 0, "нет <!DOCTYPE html> в начале страницы", "doctype", ""))
        if "title" not in ck.seen:
            warnings.append((1, 0, "нет <title> — у вкладки браузера не будет названия", "title", ""))
    # скрипты и стили внутри страницы
    for m in re.finditer(r"<(script|style)\b([^>]*)>([\s\S]*?)</\1\s*>", code, re.I):
        kind, attrs, body = m.group(1).lower(), m.group(2), m.group(3)
        if not body.strip():
            continue
        if kind == "script" and re.search(r"type\s*=\s*[\"']?(?!text/javascript|module|application/javascript)", attrs, re.I):
            continue
        sub = check_js(body) if kind == "script" else check_css(body)
        base = _pos(st, m.start(3))[0] - 1
        tag = "JS" if kind == "script" else "CSS"
        for ln, col, msg in sub["errors"]:
            errors.append((ln + base, col, "%s: %s" % (tag, msg)))
        for ln, col, msg, k, nm in sub["warnings"]:
            warnings.append((ln + base, col, "%s: %s" % (tag, msg), k, nm))
    errors.sort()
    warnings.sort()
    return {"errors": errors, "warnings": warnings, "lang": "html"}
