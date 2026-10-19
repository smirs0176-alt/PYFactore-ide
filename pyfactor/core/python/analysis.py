"""Анализ кода: ошибки, предупреждения, автоисправление синтаксиса, ИИ-подсказки."""
import ast
import builtins
import re
import subprocess

from pyfactor.config import IMPORT_BY_NAME, NO_WIN
from pyfactor.core.pyexe import python_cmd


def analyze(code):
    res = {"errors": [], "warnings": [], "tree": None}
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        res["errors"].append((e.lineno or 1, e.offset or 1, e.msg or "синтаксическая ошибка"))
        return res
    except Exception as e:
        res["errors"].append((1, 1, str(e)))
        return res
    res["tree"] = tree
    res["warnings"] = lint(tree)
    return res


def lint(tree):
    defined = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__", "__builtins__", "__path__"}
    imported, loads, star = {}, [], False
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = n.args
            for x in a.posonlyargs + a.args + a.kwonlyargs:
                defined.add(x.arg)
            if a.vararg:
                defined.add(a.vararg.arg)
            if a.kwarg:
                defined.add(a.kwarg.arg)
        elif isinstance(n, ast.Import):
            for al in n.names:
                nm = al.asname or al.name.split(".")[0]
                defined.add(nm)
                imported.setdefault(nm, n.lineno)
        elif isinstance(n, ast.ImportFrom):
            for al in n.names:
                if al.name == "*":
                    star = True
                    continue
                nm = al.asname or al.name
                defined.add(nm)
                imported.setdefault(nm, n.lineno)
        elif isinstance(n, ast.Name):
            if isinstance(n.ctx, ast.Load):
                loads.append(n)
            else:
                defined.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            defined.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            defined.update(n.names)
        elif hasattr(ast, "MatchAs") and isinstance(n, (ast.MatchAs, ast.MatchStar)) and getattr(n, "name", None):
            defined.add(n.name)
    used = {n.id for n in loads}
    out = []
    if not star:
        for n in loads:
            if n.id not in defined:
                out.append((n.lineno, n.col_offset, "Имя '%s' не определено" % n.id, "undef", n.id))
        for nm, ln in imported.items():
            if nm not in used:
                out.append((ln, 0, "Импорт '%s' не используется" % nm, "unused", nm))
    return sorted(out)


def unclosed_brackets(code):
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack, i, line, n = [], 0, 1, len(code)
    while i < n:
        c = code[i]
        if c == "\n":
            line += 1
        elif c == "#":
            j = code.find("\n", i)
            i = n if j < 0 else j
            continue
        elif c in "\"'":
            q = c * 3 if code.startswith(c * 3, i) else c
            j = i + len(q)
            while j < n:
                if code[j] == "\\":
                    j += 2
                    continue
                if code.startswith(q, j):
                    break
                if len(q) == 1 and code[j] == "\n":
                    break
                j += 1
            line += code.count("\n", i, min(j, n))
            i = j + len(q)
            continue
        elif c in pairs:
            stack.append((c, line))
        elif c in ")]}" and stack:
            stack.pop()
        i += 1
    return stack


def _open_quote(line):
    q = None
    i = 0
    while i < len(line):
        c = line[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c == "#":
            break
        elif c in "\"'":
            q = c
        i += 1
    return q


def _indent(s):
    return len(s) - len(s.lstrip(" "))


def fix_syntax(code, lineno, msg):
    """Пытается автоматически починить типичную синтаксическую ошибку. None — не смог."""
    lines = code.split("\n")
    i = max(0, min(lineno - 1, len(lines) - 1))
    L, m = lines[i], msg.lower()
    if "\t" in code and ("tab" in m or "indent" in m):
        return code.replace("\t", "    ")
    if "never closed" in m or "unexpected eof" in m:
        st = unclosed_brackets(code)
        if st:
            ch, ln = st[-1]
            k = ln - 1
            closer = {"(": ")", "[": "]", "{": "}"}[ch]
            lines[k] = lines[k].rstrip() + closer
            return "\n".join(lines)
    if "unterminated string" in m or "eol while scanning" in m:
        q = _open_quote(L)
        if q:
            lines[i] = L + q
            return "\n".join(lines)
    if "unmatched" in m:
        for k, ch in enumerate(L):  # noqa: B007
            if ch in ")]}":
                pass
        mm = re.search(r"unmatched '(.)'", msg)
        if mm and mm.group(1) in L:
            idx = L.rfind(mm.group(1))
            lines[i] = L[:idx] + L[idx + 1:]
            return "\n".join(lines)
    if "expected an indented block" in m:
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        base = _indent(lines[j]) if j >= 0 else 0
        lines.insert(i, " " * (base + 4) + "pass")
        return "\n".join(lines)
    if "unindent does not match" in m:
        prev = sorted({_indent(x) for x in lines[:i] if x.strip()})
        cur = _indent(L)
        less = [p for p in prev if p < cur]
        lines[i] = " " * (max(less) if less else 0) + L.lstrip(" ")
        return "\n".join(lines)
    if "unexpected indent" in m:
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        lines[i] = " " * (_indent(lines[j]) if j >= 0 else 0) + L.lstrip(" ")
        return "\n".join(lines)
    if "missing parentheses in call to 'print'" in m:
        mm = re.match(r"(\s*)print\s+(.*)$", L)
        if mm:
            lines[i] = "%sprint(%s)" % (mm.group(1), mm.group(2))
            return "\n".join(lines)
    if "maybe you meant '=='" in m and re.match(r"\s*(if|elif|while)\b", L):
        lines[i] = L.replace(" = ", " == ", 1)
        return "\n".join(lines)
    if re.match(r"\s*(if|elif|else|for|while|def|class|try|except|finally|with)\b", L) and not L.rstrip().endswith(":") \
            and not L.rstrip().endswith(("(", ",", "\\")):
        lines[i] = L.rstrip() + ":"
        return "\n".join(lines)
    return None


def add_import(code, line):
    """Вставляет import после последнего импорта (или после докстринга/шебанга)."""
    lines = code.split("\n")
    at = 0
    try:
        tree = ast.parse(code)
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                at = node.end_lineno
            elif at == 0 and isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) \
                    and isinstance(node.value.value, str):
                at = node.end_lineno
    except Exception:
        while at < len(lines) and lines[at].startswith("#"):
            at += 1
    lines.insert(at, line)
    return "\n".join(lines)


def add_after_imports(code, snippet):
    return add_import(code, snippet)


def run_py(path, cwd, env, timeout=5):
    """Запуск скрипта в отдельном процессе. -> (код, stdout, stderr, превышен_таймаут)"""
    py = python_cmd()
    if not py:
        return 1, "", "Не найден Python 3 для пробного запуска", False
    try:
        p = subprocess.run(py + ["-X", "utf8", path], cwd=cwd, env=env, capture_output=True,  # noqa: S603
                           text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL, creationflags=NO_WIN)
        return p.returncode, p.stdout, p.stderr, False
    except subprocess.TimeoutExpired:
        return 0, "", "", True
    except Exception as e:
        return 1, "", str(e), False


def last_err_line(stderr):
    ls = [l for l in stderr.strip().split("\n") if l.strip()]
    return ls[-1] if ls else "неизвестная ошибка"


def required_args(fn):
    a = fn.args
    pos = len(a.posonlyargs) + len(a.args)
    req = pos - len(a.defaults)
    req += sum(1 for d in a.kw_defaults if d is None)
    return req


def ai_suggest(code):
    """Локальная «нейросеть»: набор умных правил, подсказывает что добавить."""
    r = analyze(code)
    if r["errors"]:
        ln, _, msg = r["errors"][0]
        return [("Сначала исправь ошибку", "Строка %d: %s\nМожно попробовать вкладку Bug → Авто." % (ln, msg), None)]
    out, tree = [], r["tree"]
    seen = set()
    for ln, _col, msg, kind, name in r["warnings"]:  # noqa: B007
        if kind == "undef" and name in IMPORT_BY_NAME and name not in seen:
            seen.add(name)
            imp = IMPORT_BY_NAME[name]
            out.append(("Добавить  " + imp, "'%s' используется, но не импортирован (строка %d)." % (name, ln),
                        lambda c, imp=imp: add_import(c, imp)))
    if "pygame" in code:
        if "pygame.init" not in code:
            out.append(("pygame.init()", "Без инициализации pygame может работать неправильно.",
                        lambda c: add_after_imports(c, "\npygame.init()")))
        if "Clock" not in code:
            out.append(("Ограничь FPS", "Добавь clock = pygame.time.Clock() и clock.tick(60) в игровой цикл.", None))
        if "pygame.quit" not in code:
            out.append(("pygame.quit() в конце", "Корректно закрывает окно и звук.",
                        lambda c: c.rstrip("\n") + "\n\npygame.quit()\n"))
        if "QUIT" not in code:
            out.append(("Обработка закрытия окна", "Нет проверки pygame.QUIT — окно не закроется крестиком.", None))
    if "tkinter" in code and "mainloop" not in code:
        out.append(("Нет mainloop()", "Окно tkinter закроется сразу. Добавь root.mainloop() в конец.", None))
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    has_guard = "__name__" in code
    if any(f.name == "main" for f in funcs) and not has_guard:
        out.append(("Защита запуска", 'Добавить if __name__ == "__main__": main()',
                    lambda c: c.rstrip("\n") + '\n\n\nif __name__ == "__main__":\n    main()\n'))
    elif funcs and not has_guard and len(code.split("\n")) > 30:
        out.append(("Добавь функцию main()", "Так код проще тестировать и импортировать.", None))
    if re.search(r"^\s*except\s*:", code, re.M):
        out.append(("except: без типа", "Ловит вообще всё, даже Ctrl+C. Лучше except Exception:",
                    lambda c: re.sub(r"^(\s*)except\s*:", r"\1except Exception:", c, flags=re.M)))
    if re.search(r"(?<!with )\bopen\(", code) and "with open" not in code:
        out.append(("open() без with", "Файл может остаться открытым. Используй with open(...) as f:", None))
    if re.search(r"while\s+True\s*:", code) and "break" not in code and "sys.exit" not in code and "return" not in code:
        out.append(("Бесконечный цикл", "В while True нет break/exit — убедись, что выход есть.", None))
    if re.search(r"\bint\(\s*input", code) and "try" not in code:
        out.append(("Защита ввода", "int(input()) упадёт, если ввести не число. Оберни в try/except ValueError.", None))
    nodoc = [f.name for f in funcs if not ast.get_docstring(f)]
    if len(nodoc) >= 3:
        out.append(("Добавь описания функций", "Без docstring: " + ", ".join(nodoc[:5]), None))
    for ln, _col, msg, kind, name in r["warnings"]:  # noqa: B007
        if kind == "unused":
            out.append(("Лишний импорт  " + name, "Строка %d: не используется." % ln, None))
    if not out:
        out.append(("Всё выглядит хорошо ✓", "Подсказок нет. Можно запускать тест во вкладке Bug.", None))
    return out
