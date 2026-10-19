"""Единая точка проверки кода: выбирает проверку по языку."""
from pyfactor.core.python.analysis import analyze
from pyfactor.core.web.webcheck import check_css, check_html, check_js


def check_code(code, lang):
    if lang == "python":
        res = analyze(code)
    elif lang == "js":
        res = check_js(code)
    elif lang == "css":
        res = check_css(code)
    elif lang == "html":
        res = check_html(code)
    else:
        res = {"errors": [], "warnings": []}
    res.setdefault("lang", lang)
    res.setdefault("colors", [])
    return res
