"""В исходниках не должно быть зашитых ключей: секрет-подобное имя, которому присвоена длинная строка-литерал."""
import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = re.compile(r"(key|secret|token|passw|credential)", re.I)
SKIP = {"tests", "legacy_unused", "__pycache__", "node_modules", "dist", ".git"}


def _hits():
    out = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(base, f)
            try:
                tree = ast.parse(open(p, encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(tree):
                name = val = None
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                    name, val = ast.unparse(n.targets[0]), n.value.value
                elif isinstance(n, ast.Call) and ast.unparse(n.func) in ("os.environ.get", "os.getenv") and len(n.args) == 2 \
                        and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
                    name, val = ast.unparse(n.args[0]), n.args[1].value
                if val and NAME.search(name) and len(val) >= 20 and not re.search(r"[\s/%:]", val):
                    out.append("%s:%d %s" % (os.path.relpath(p, ROOT), n.lineno, name))
    return out


def test_no_hardcoded_credentials():
    assert _hits() == []
