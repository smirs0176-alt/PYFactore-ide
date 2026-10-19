"""Интерпретаторы весёлых языков: Brainfuck (.bf), Ook! (.ook), LOLCODE (.lol), Русский Питон (.rus).
Запуск: python funrun.py файл. Чистый Python, без зависимостей."""
import io
import re
import sys
import tokenize


def bf(code, limit=50_000_000):
    code = [c for c in code if c in "+-<>[],."]
    jump, st = {}, []
    for i, c in enumerate(code):
        if c == "[":
            st.append(i)
        elif c == "]":
            if not st:
                sys.exit("Лишняя ] (команда №%d)" % i)
            j = st.pop()
            jump[i], jump[j] = j, i
    if st:
        sys.exit("Не закрыта [")
    tape, p, pc, n = [0] * 30000, 0, 0, 0
    while pc < len(code):
        c = code[pc]
        if c == "+":
            tape[p] = (tape[p] + 1) % 256
        elif c == "-":
            tape[p] = (tape[p] - 1) % 256
        elif c == ">":
            p = (p + 1) % 30000
        elif c == "<":
            p = (p - 1) % 30000
        elif c == ".":
            sys.stdout.write(chr(tape[p]))
            if tape[p] == 10:
                sys.stdout.flush()
        elif c == ",":
            ch = sys.stdin.read(1)
            tape[p] = ord(ch) % 256 if ch else 0
        elif c == "[" and not tape[p]:
            pc = jump[pc]
        elif c == "]" and tape[p]:
            pc = jump[pc]
        pc += 1
        n += 1
        if n > limit:
            sys.exit("Слишком долго работает — похоже на бесконечный цикл")
    sys.stdout.flush()


OOK = {("Ook.", "Ook?"): ">", ("Ook?", "Ook."): "<", ("Ook.", "Ook."): "+", ("Ook!", "Ook!"): "-",
       ("Ook!", "Ook."): ".", ("Ook.", "Ook!"): ",", ("Ook!", "Ook?"): "[", ("Ook?", "Ook!"): "]"}


def ook(code):
    w = re.findall(r"Ook[.?!]", code)
    bf("".join(OOK[(w[i], w[i + 1])] for i in range(0, len(w) - 1, 2)))


def lol(code):
    code = re.sub(r"OBTW.*?TLDR", "", code, flags=re.S)
    lines = []
    for raw in code.split("\n"):
        toks = re.findall(r'"(?:[^"]|:")*"|[^\s"]+', re.sub(r'^((?:[^"]|"[^"]*")*?)\bBTW\b.*', r"\1", raw))
        if toks:
            lines.append(toks)
    V = {"IT": None}

    def unesc(s):
        return s[1:-1].replace(":)", "\n").replace(":>", "\t").replace(':"', '"').replace("::", ":")

    def fmt(x):
        if x is None:
            return "NOOB"
        if isinstance(x, bool):
            return "WIN" if x else "FAIL"
        return "%.2f" % x if isinstance(x, float) else str(x)

    def num(x):
        if isinstance(x, (bool, int, float)):
            return int(x) if isinstance(x, bool) else x
        try:
            return int(x)
        except (TypeError, ValueError):
            try:
                return float(x)
            except (TypeError, ValueError):
                sys.exit("Не могу сделать число из %r" % (x,))

    def truth(x):
        return x not in ("", 0, 0.0, False, None)

    def ev(t):
        if not t:
            sys.exit("Не хватает значения в выражении")
        w = t.pop(0)
        if w[0] == '"':
            return unesc(w)
        if w in ("WIN", "FAIL", "NOOB"):
            return {"WIN": True, "FAIL": False, "NOOB": None}[w]
        if re.fullmatch(r"-?\d+", w):
            return int(w)
        if re.fullmatch(r"-?\d*\.\d+", w):
            return float(w)
        if w == "NOT":
            return not truth(ev(t))
        if w == "SMOOSH":
            a = [fmt(ev(t))]
            while t and t[0] == "AN":
                t.pop(0)
                a.append(fmt(ev(t)))
            if t and t[0] == "MKAY":
                t.pop(0)
            return "".join(a)
        if w in ("SUM", "DIFF", "PRODUKT", "QUOSHUNT", "MOD", "BIGGR", "SMALLR", "BOTH", "EITHER", "DIFFRINT"):
            op = t.pop(0) if w != "DIFFRINT" else ""
            a = ev(t)
            if t and t[0] == "AN":
                t.pop(0)
            b = ev(t)
            if w == "BOTH":
                return a == b if op == "SAEM" else truth(a) and truth(b)
            if w == "EITHER":
                return truth(a) or truth(b)
            if w == "DIFFRINT":
                return a != b
            a, b = num(a), num(b)
            if w == "SUM":
                return a + b
            if w == "DIFF":
                return a - b
            if w == "PRODUKT":
                return a * b
            if w == "BIGGR":
                return max(a, b)
            if w == "SMALLR":
                return min(a, b)
            if b == 0:
                sys.exit("Деление на ноль")
            return a % b if w == "MOD" else (a // b if isinstance(a, int) and isinstance(b, int) else a / b)
        if w in V:
            return V[w]
        sys.exit("Нет переменной " + w)

    n, orly, loops, pair = len(lines), [], [], {}
    try:
        for i, l in enumerate(lines):
            h = " ".join(l[:3])
            if h.startswith("O RLY"):
                orly.append({"o": i})
            elif h.startswith("YA RLY"):
                orly[-1]["y"] = i
            elif h.startswith("NO WAI"):
                orly[-1]["n"] = i
            elif l[0] == "OIC":
                d = orly.pop()
                d["c"] = i
                pair[d["o"]] = d
                if "n" in d:
                    pair[d["n"]] = d
            elif h.startswith("IM IN YR"):
                loops.append(i)
            elif h.startswith("IM OUTTA YR"):
                s = loops.pop()
                pair[s], pair[i] = i, s
    except (IndexError, KeyError):
        sys.exit("Ошибка в структуре: проверь O RLY?/OIC и IM IN YR/IM OUTTA YR")
    pc, run, steps = 0, [], 0
    while pc < n:
        steps += 1
        if steps > 20_000_000:
            sys.exit("Слишком долго работает — похоже на бесконечный цикл")
        l = lines[pc]
        w, h = l[0], " ".join(l[:3])
        if w in ("HAI", "KTHXBYE", "OIC") or h.startswith("YA RLY"):
            pass
        elif w == "VISIBLE":
            t, nl, out = l[1:], True, ""
            if t and t[-1] == "!":
                t, nl = t[:-1], False
            while t:
                out += fmt(ev(t))
            sys.stdout.write(out + ("\n" if nl else ""))
            sys.stdout.flush()
        elif h.startswith("I HAS A"):
            t = l[4:]
            V[l[3]] = ev(t[1:]) if t and t[0] == "ITZ" else None
        elif w == "GIMMEH":
            s = input()
            V[l[1]] = int(s) if re.fullmatch(r"-?\d+", s) else s
        elif len(l) > 2 and l[1] == "R":
            V[w] = ev(l[2:])
        elif h.startswith("O RLY"):
            if not truth(V["IT"]):
                d = pair[pc]
                pc = d["n"] + 1 if "n" in d else d["c"]
                continue
        elif h.startswith("NO WAI"):
            pc = pair[pc]["c"]
            continue
        elif h.startswith("IM IN YR"):
            t = l[4:]
            if t and t[0] in ("UPPIN", "NERFIN"):
                t = t[3:]
            if t and t[0] in ("TIL", "WILE"):
                c = truth(ev(t[1:]))
                if (t[0] == "TIL" and c) or (t[0] == "WILE" and not c):
                    if run and run[-1] == pc:
                        run.pop()
                    pc = pair[pc] + 1
                    continue
            if not run or run[-1] != pc:
                run.append(pc)
        elif h.startswith("IM OUTTA YR"):
            s = pair[pc]
            st = lines[s][4:]
            if st and st[0] in ("UPPIN", "NERFIN"):
                V[st[2]] = num(V[st[2]]) + (1 if st[0] == "UPPIN" else -1)
            pc = s
            continue
        elif w == "GTFO":
            if not run:
                sys.exit("GTFO вне цикла")
            pc = pair[run.pop()] + 1
            continue
        else:
            V["IT"] = ev(list(l))
        pc += 1


RUS = {"если": "if", "иначе": "else", "иначе_если": "elif", "пока": "while", "для": "for", "в": "in",
       "функция": "def", "вернуть": "return", "класс": "class", "вывод": "print", "ввод": "input",
       "истина": "True", "ложь": "False", "ничего": "None", "и": "and", "или": "or", "не": "not",
       "импорт": "import", "из": "from", "как": "as", "пропустить": "pass", "прервать": "break",
       "продолжить": "continue", "пробовать": "try", "кроме": "except", "наконец": "finally",
       "диапазон": "range", "длина": "len", "целое": "int", "строка": "str", "дробное": "float",
       "список": "list", "словарь": "dict", "открыть": "open", "сумма": "sum", "макс": "max", "мин": "min"}


def rus(code, path):
    edits = [(t.start, t.end, RUS[t.string]) for t in tokenize.generate_tokens(io.StringIO(code).readline)
             if t.type == tokenize.NAME and t.string in RUS]
    lines = code.split("\n")
    for (r, c), (_, c2), new in sorted(edits, reverse=True):
        lines[r - 1] = lines[r - 1][:c] + new + lines[r - 1][c2:]
    exec(compile("\n".join(lines), path, "exec"), {"__name__": "__main__"})  # noqa: S102


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    path = sys.argv[1]
    ext = path.rsplit(".", 1)[-1].lower()
    code = open(path, encoding="utf-8").read()
    try:
        if ext == "bf":
            bf(code)
        elif ext == "ook":
            ook(code)
        elif ext == "lol":
            lol(code)
        else:
            rus(code, path)
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as e:
        print("Ошибка: %s: %s" % (type(e).__name__, e))
        sys.exit(1)


if __name__ == "__main__":
    main()
